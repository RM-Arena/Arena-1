"""FastAPI control plane with WebSocket broadcasts and durable match records."""
import asyncio
from contextlib import asynccontextmanager
import copy
import json
import os
import secrets
from pathlib import Path
import tempfile
import threading
import time
import uuid
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictFloat
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.background import BackgroundTask

from .paths import data_path
from .engine import DT, Match, arena_map, SLOT_IDS, RULES_PROFILE, STATIC_FRAME_KEYS, _config as rules_config
from .runner import Battle
from .store import Store
from .strategy_names import canonical_key
from .battle_settings import BattleSettings, normalize as normalize_settings
from .submissions import ROOT, guide_path, load_submission, save_submission
from .worker import SOURCE_LIMIT
from .training import TrainingService
from .decks import prepare_decks
from .models import robot_models,normalize_team_lineup,mirrored_lineups,DEFAULT_TEAM_LINEUP
from . import __version__
from .robot_presets import preset_metadata
from .showcase import PROFILE_FILE, SHOWCASE_FILE, load_profile, load_showcase, validate_profile
from .custom_models import CustomModels
from .strategy_library import StrategyLibrary
from .video_export import JOB_PATTERN, MAX_VIDEO_BYTES, VideoExporter, VideoExportError
from .submissions import write_json, manifest_season
from . import seasons as season_rules

# The bundled baseline pair each season starts with when a request names no strategies.
DEFAULT_PAIRS = {"2026": ("claude_opus55_xhigh_team", "claude_opus55_xhigh_hold"), "2027": ("claude_opus55_xhigh_2027_team", "claude_opus55_xhigh_2027_hold")}

# Pre-match broadcast (rule 6.4 self-check): opening, a title card per team, one camera shot per robot and a face-off.
# frontend/src/intro.ts lays out the same segments, scaled to the duration the server announces. Every segment
# must stay on screen for at least INTRO_MIN_CUT seconds, so the self-check clock grows instead of compressing.
INTRO = {"open": 5.0, "team": 2.4, "faceoff": 4.5, "shot": 2.4, "shots": 28.8, "min_shot": 2.0, "min_cut": 2.0}


def intro_seconds(robots):
    shot = min(INTRO["shot"], max(INTRO["min_shot"], INTRO["shots"] / max(1, robots)))
    return round(INTRO["open"] + 2 * INTRO["team"] + robots * shot + INTRO["faceoff"], 2)


def intro_minimum_seconds(robots):
    """Shortest walk-on that still shows both cards, every chassis and the face-off for `min_cut`."""
    return round((robots + 4) * INTRO["min_cut"], 2)


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Omitted strategies default to the season's bundled baseline pair.
    red: str | None = None
    blue: str | None = None
    seed: int = Field(default=42, ge=-(2**31), le=2**31-1)
    duration: int = Field(default=420, ge=1, le=420)
    # RMUC 2027 is the default field; RMUC 2026 stays playable with its own rules. Without a
    # map, the season of the selected strategies decides, and 2027 when nothing is selected.
    map: Literal["rmuc2027", "rmuc2026"] | None = None
    mode: Literal["standard", "deck"] = "standard"
    red_deck: list[str] = Field(default_factory=list)
    blue_deck: list[str] = Field(default_factory=list)
    team_lineup: dict[str,int] | None = None
    # A standard match keeps each side on its own lineup; these only fill in a side whose strategy
    # declares none (a team strategy always runs the lineup it was developed on).
    red_lineup: dict[str,int] | None = None
    blue_lineup: dict[str,int] | None = None
    red_control: Literal["team","independent"] = "independent"
    blue_control: Literal["team","independent"] = "independent"
    red_team_strategy: str | None = None
    blue_team_strategy: str | None = None
    save_mp4: bool = False
    battle_settings: dict[str, StrictFloat] | None = None
    # Uploaded appearances, by hardware model number.
    red_skins: dict[str,str] = Field(default_factory=dict)
    blue_skins: dict[str,str] = Field(default_factory=dict)


class BattleSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    season: Literal["2026", "2027"]
    values: dict[str, StrictFloat]


class FreeControllerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["team","independent"] = "independent"
    strategy: str = ""


class DeckPresetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1,max_length=64)
    map: Literal["rmuc2027", "rmuc2026"] | None = None
    decks: dict[Literal["red","blue"],list[str]]
    controllers: dict[Literal["red","blue"],FreeControllerRequest]
    replace: bool = False


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: Literal["pause", "stop", "speed", "skip_prematch", "extend_prematch"]
    speed: float = 1
    # `extend_prematch`: seconds of extra self-check time, so the lineup intro is never compressed.
    seconds: float = Field(default=0.0, ge=0, le=30)


class PlayerRequest(BaseModel):
    """A human pilot's command for one robot; `action=None` returns it to its strategy."""
    model_config = ConfigDict(extra="forbid")
    team: Literal["red", "blue"]
    slot: int = Field(ge=1, le=64)
    action: dict | None = None
    # Robot id the pilot is locking onto; the server aims the gimbal along the engine's ballistics.
    assist: str | None = Field(default=None, max_length=32)


class HighlightRequest(BaseModel):
    """The moments of one finished match whose frames the post-match reel replays."""
    model_config = ConfigDict(extra="forbid")
    match_id: str = Field(min_length=1, max_length=64)
    at: list[float] = Field(min_length=1, max_length=12)
    # Run-up before the moment, so the shot is seen arriving, and the length of each window.
    before: float = Field(default=1.5, ge=0, le=10)
    seconds: float = Field(default=5.0, gt=0, le=30)


class SubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}$")
    mode: Literal["team", "robot", "squad", "distributed", "adaptive"] = "team"
    robot: int | None = None
    entries: dict[str, str]
    team_lineup: dict[str,int] | None = None
    season: Literal["2026","2027"] | None = None
    # The agent-written presentation is required; the questionnaire classifies the upload.
    showcase: str = Field(min_length=2, max_length=65536)
    profile: dict | None = None


class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: dict
    tactic: str = "balanced"
    tags: list[str] = Field(default_factory=list)
    display_name: str | None = None
    author: str | None = None
    description: str | None = None
    github: str | None = None


class CustomModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=40)
    base_model: int
    forward: Literal["+x", "-x", "+z", "-z"] = "+x"
    author: str | None = Field(default=None, max_length=40)
    glb_base64: str = Field(min_length=8)


class TeamBriefingRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    team_lineup:dict[str,int]
    season:Literal["2026","2027"]|None=None


class TeamWorkspaceRequest(TeamBriefingRequest):
    model_config=ConfigDict(extra="forbid")
    name:str=Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}$")
    minutes:int=Field(default=90,ge=1,le=1440)
    team_lineup:dict[str,int]


class TrainingWorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}$")
    mode: Literal["team", "robot", "distributed", "adaptive"]
    robot: int | None = None
    minutes: int = Field(default=90, ge=1, le=1440)
    team_lineup: dict[str,int] | None = None
    season: Literal["2026","2027"] | None = None


class RefereeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["yellow", "yellow_both", "red", "forfeit"]
    robot: str | None = None
    team: Literal["red", "blue"] | None = None
    reason: str = Field(default="referee_decision", max_length=128)


class PracticeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opponent: str = Field(default="baseline", pattern=r"^(baseline|self|[a-f0-9]{16})$")
    duration: int = Field(default=30, ge=1, le=420)
    games: int = Field(default=1, ge=1, le=1000)
    seed: int = Field(default=42, ge=-(2**31), le=2**31-1)
    swap_sides: bool = False


class ArenaService:
    def __init__(self, sandbox="docker", submission_root=None, data_root=None, test_mode=False, workspace_registry=None):
        self.sandbox = sandbox
        self.submission_root = Path(submission_root or data_path("submissions"))
        self.workspace_registry = Path(workspace_registry or data_path(".arena_host/workspaces.json"))
        self.store = Store(data_root or data_path(".arena_data"))
        self.settings = BattleSettings(self.store.directory / "battle-settings.json")
        self.custom_models = CustomModels(self.store.directory / "custom-models")
        token_path = self.store.directory / "referee.token"
        if not token_path.exists():
            fd = os.open(token_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,"w") as handle:
                handle.write(secrets.token_urlsafe(32))
        self.referee_token = token_path.read_text(encoding="utf-8").strip()
        if len(self.referee_token)<32:
            raise ValueError("Invalid organizer referee token")
        self.lock = threading.RLock()
        self.battle, self.thread, self.error = None, None, None
        self.speed, self.paused, self.stopping, self.revision = 1, False, False, 0
        with Match(duration=420, map_name=season_rules.map_of(season_rules.DEFAULT_SEASON)) as match:
            self.frame = match.snapshot()
        # An untouched arena per map (robots on their start pads), for the field between matches.
        self.previews = {season_rules.map_of(season_rules.DEFAULT_SEASON): self.frame}
        # Snapshots travel to the browser up to 20 times a second, and the static half of a frame
        # (arena geometry, hardware tables, rule text) never changes during a match. It is published
        # once per match instead of being re-sent with every tick.
        self.public_frame = {key: value for key, value in self.frame.items() if key not in STATIC_FRAME_KEYS}
        self.static_frame = {key: self.frame[key] for key in STATIC_FRAME_KEYS if key in self.frame}
        self.metadata, self.match_id = None, None
        self.busy = False
        self.test_mode = test_mode
        self.strategy_library = StrategyLibrary(self.store.directory / "strategy-library", enabled=not test_mode)
        self.strategy_version = self.strategy_library.status()["version"]
        # Rule 6.4/6.5: 15 s referee self-check, then a 5 s countdown before the 7 minutes start.
        # None: the self-check lasts as long as the lineup intro (intro_seconds).
        self.prematch_stages = () if test_mode else (("self_check", None), ("countdown", 5.0))
        self.prematch, self.skip_prematch = None, False
        # Seconds the client asked to add to the running self-check: the walk-on must never be squeezed
        # below `min_cut` per segment, so its clock is stretched instead of its cards being cut short.
        self.prematch_extra = 0.0

    def _publish(self, frame):
        """Keep the full frame for HTTP clients and the slim one for the snapshot stream."""
        self.frame = frame
        self.public_frame = {key: value for key, value in frame.items() if key not in STATIC_FRAME_KEYS}
        self.static_frame = {key: frame[key] for key in STATIC_FRAME_KEYS if key in frame}
        return frame

    def catalog(self, modes=("team", "squad", "distributed"), season=None):
        """Saved strategies by key; `season` keeps only strategies written for that season."""
        profiles = {season_rules.rules_profile(season)} if season else set(season_rules.profiles())
        bundled = {p.parent.name: p for p in (ROOT / "examples").glob("*/manifest.json")}
        remote = {canonical_key(p.parent.name): p for p in self.strategy_library.paths()}
        paths = [(p, "remote" if key in remote else "bundled") for key, p in (bundled | remote).items()]
        if self.submission_root.exists():
            paths += [(p, "local") for p in self.submission_root.glob("*/manifest.json")]
        choices = {}
        records=json.loads(self.workspace_registry.read_text(encoding="utf-8")) if self.workspace_registry.exists() else {}
        current_entries={str(Path(t["last_submission"]["path"]).resolve())
            for r in records.values() if (t:=r.get("training")) and t.get("last_submission")}
        for manifest_path, source in paths:
            try:
                if manifest_path.parent.name.startswith("entry-") and str(manifest_path.parent.resolve()) not in current_entries:
                    continue
                manifest, _ = load_submission(manifest_path.parent)
                if manifest["mode"] in modes and manifest.get("api_version")==3 and manifest.get("rules_profile") in profiles:
                    key = canonical_key(manifest_path.parent.name)
                    if key in choices:
                        key = "submission-" + key
                    strategy_season = manifest_season(manifest)
                    choices[key] = {"name": canonical_key(manifest_path.parent.name), "mode": manifest["mode"],
                                    "version": manifest["version"], "path": manifest_path.parent, "season": strategy_season, "source": source}
                    if manifest["mode"] == "adaptive":
                        choices[key]["robot"] = manifest["robot"]
                        model = robot_models()[str(manifest["robot"])]
                        choices[key]["model_name"] = model["name"]
                        choices[key]["role"] = model["role"]
                        if source in ("bundled", "remote"):
                            preset = preset_metadata(key, manifest['robot'], model['role'], strategy_season)
                            if preset:
                                choices[key]['preset'] = preset
                    if manifest['mode']=='team':choices[key]['team_lineup']=normalize_team_lineup(manifest.get('team_lineup'),strategy_season)
                    profile = load_profile(manifest_path.parent, bundled=source != "local")
                    choices[key]['agent'] = profile['agent']
                    if profile.get('display_name'):
                        choices[key]['display_name'] = profile['display_name']
            except (ValueError, OSError, KeyError, json.JSONDecodeError):
                continue
        return choices

    def pilot(self):
        """The robot a human is driving right now, or None once their commands go stale."""
        battle = self.battle
        if battle is None or not self.busy:
            return None
        with battle.manual_lock:
            if not battle.manual:
                return None
            team, slot = next(reversed(battle.manual))
        return {"team": team, "slot": int(slot)}

    def state(self, since=-1, slim=False):
        with self.lock:
            strategy_version = self.strategy_library.status()["version"]
            if strategy_version != self.strategy_version:
                self.strategy_version = strategy_version
                self.revision += 1
            events = []
            if self.battle:
                events = self.battle.frames.events_since(since)
            # Published frames and their events are never mutated, so they are shared rather
            # than copied on every websocket poll. `slim` leaves the static half of the frame out:
            # the snapshot stream delivers it once per match.
            return {"frame": self.public_frame if slim else self.frame, "revision": self.revision, "paused": self.paused,
                    "speed": self.speed, "error": self.error, "metadata": self.metadata, "sandbox": self.sandbox,
                    "match_id": self.match_id, "events": events, "player": self.pilot(),
                    "busy": self.busy, "prematch": copy.copy(self.prematch), "strategy_version": strategy_version}

    def preview(self, map_name):
        """The empty arena of `map_name`: shown once a finished match has been left behind."""
        with self.lock:
            frame = self.previews.get(map_name)
        if frame is None:
            with Match(duration=420, map_name=map_name) as match:
                frame = match.snapshot()
            with self.lock:
                self.previews[map_name] = frame
        return frame

    def static_state(self):
        with self.lock:
            return {"match_id": self.match_id, "frame": self.static_frame}

    def resolve_season(self, args):
        """The request with its map and default strategies filled in: an explicit map wins,
        otherwise the season shared by every selected strategy, otherwise RMUC 2027."""
        for field in ("red", "blue", "red_team_strategy", "blue_team_strategy"):
            setattr(args, field, canonical_key(getattr(args, field)))
        args.red_deck = [canonical_key(key) for key in args.red_deck]
        args.blue_deck = [canonical_key(key) for key in args.blue_deck]
        if args.map:
            season = season_rules.season_of_map(args.map)
        else:
            catalog = self.catalog(("team", "squad", "distributed", "adaptive"))
            keys = [args.red, args.blue, args.red_team_strategy, args.blue_team_strategy, *args.red_deck, *args.blue_deck]
            seasons = {catalog[key]["season"] for key in keys if key and key in catalog}
            season = seasons.pop() if len(seasons) == 1 else season_rules.DEFAULT_SEASON
        defaults = DEFAULT_PAIRS[season]
        return args.model_copy(update={"map": season_rules.map_of(season), "red": args.red or defaults[0],
                                       "blue": args.blue or defaults[1]}), season

    def free_controllers(self,args):
        choices=self.catalog(("team",),season_rules.season_of_map(args.map));controllers={}
        for team in ("red","blue"):
            mode=getattr(args,team+"_control");key=getattr(args,team+"_team_strategy")
            if mode=="team":
                if key not in choices:raise ValueError(f"{'红' if team=='red' else '蓝'}方请选择已保存的 Team 策略")
                controllers[team]=choices[key]["path"]
            elif key:raise ValueError("Independent control does not use a team strategy")
        return controllers

    def start(self, data):
        args, season = self.resolve_season(StartRequest.model_validate(data))
        args.battle_settings = normalize_settings(args.battle_settings if args.battle_settings is not None else self.settings.get(season)["overrides"], season)
        if args.duration!=420 and not self.test_mode:
            raise ValueError("Ranked matches are 420 seconds; use CLI for unranked short test matches")
        with self.lock:
            if self.busy:
                raise ValueError("请先结束当前比赛")
            choices = self.catalog(season=season)
            decks, lineups, free_team_strategies = None, None, None
            if args.mode == "deck":
                if args.team_lineup is not None or args.red_lineup is not None or args.blue_lineup is not None:
                    raise ValueError("Free battle takes its lineups from the selected robot cards")
                cards = self.catalog(("adaptive",), season)
                if not args.red_deck or not args.blue_deck or any(key not in cards for key in args.red_deck + args.blue_deck):
                    raise ValueError(f"每方至少选择一台机器人，且每台必须绑定 {season} 赛季已保存的单机策略（型号须符合 {season} 制作规范）")
                decks = {"red":[cards[key]["path"] for key in args.red_deck],"blue":[cards[key]["path"] for key in args.blue_deck]}
                free_team_strategies = self.free_controllers(args)
                lineups, _, team_metadata = prepare_decks(decks, args.seed, free_team_strategies, season)
            elif args.red_control!="independent" or args.blue_control!="independent" or args.red_team_strategy or args.blue_team_strategy:
                raise ValueError("Free controllers require free battle mode")
            elif args.red_deck or args.blue_deck:
                raise ValueError("Robot decks require deck mode")
            elif args.red not in choices or args.blue not in choices:
                raise ValueError(f"双方策略都必须是 {season} 赛季的策略" if any(k in self.catalog() for k in (args.red,args.blue)) else "Unknown submission")
            if not decks:
                manifests=[load_submission(choices[key]['path'])[0] for key in (args.red,args.blue)]
                requested={"red":args.red_lineup,"blue":args.blue_lineup}
                chosen={}
                for team,manifest in zip(("red","blue"),manifests):
                    lineup=manifest.get('team_lineup')
                    if lineup is None:lineup=requested[team] if requested[team] is not None else args.team_lineup
                    try:
                        chosen[team]=normalize_team_lineup(lineup,season)
                    except ValueError as exc:
                        raise ValueError(f"{'红' if team=='red' else '蓝'}方阵容不完整或不符合 {season} 制作规范：{exc}") from exc
                if season!=season_rules.LEGACY_SEASON or any(value!=season_rules.default_lineup(season) for value in chosen.values()):
                    lineups={team:[{"slot":int(slot),"model":value[slot]} for slot in value] for team,value in chosen.items()}
            fielded = lineups or mirrored_lineups(season_rules.default_lineup(season),season)
            skins = {team: self.custom_models.resolve(team, getattr(args, team + "_skins"), {d["model"] for d in fielded[team]}) for team in ("red", "blue")}
            with Match(args.seed, args.duration, args.map, lineups=lineups, battle_settings=args.battle_settings) as match:
                self._publish(match.snapshot())
            self.error, self.paused, self.stopping, self.battle = None, False, False, None
            self.match_id = uuid.uuid4().hex[:16]
            self.metadata = {"engine":"rust","rules":season_rules.rules_profile(season),"season":season,"roster":list(season_rules.slots(season)),"test_match":args.duration!=420,"seed":args.seed,"duration":args.duration,"map":args.map,
                             "teams":team_metadata if decks else {t:{k:v for k,v in choices[key].items() if k!="path"} for t,key in (("red",args.red),("blue",args.blue))}}
            self.metadata.update({"battle_settings": args.battle_settings, "save_mp4": args.save_mp4})
            if args.battle_settings:
                self.metadata["test_match"] = True
            if decks:
                self.metadata.update({"lineups":lineups,"test_match":True,"match_mode":"deck"})
            if any(skins.values()):
                self.metadata["skins"] = skins
            self.store.create(self.match_id, self.metadata)
            self.revision += 1
            self.busy = True
            self.thread = threading.Thread(target=self._run, args=(self.match_id,None if decks else choices[args.red]["path"],None if decks else choices[args.blue]["path"],args,decks,free_team_strategies,skins,None if decks else chosen), daemon=True)
            self.thread.start()
            return self.match_id

    def _run(self, match_id, red, blue, args, decks=None, free_team_strategies=None, skins=None, team_lineups=None):
        try:
            with Battle(red,blue,args.seed,args.duration,args.map,self.sandbox,decks=decks,team_lineup=args.team_lineup,team_lineups=team_lineups,free_team_strategies=free_team_strategies,battle_settings=args.battle_settings) as battle:
                battle.metadata["match_id"] = match_id
                battle.metadata["save_mp4"] = args.save_mp4
                if skins and any(skins.values()):
                    battle.metadata["skins"] = skins
                with self.lock:
                    self.battle, self.metadata = battle, battle.metadata
                self.store.running(match_id,battle.metadata)
                self._prematch()
                while battle.match.status != "finished":
                    with self.lock:
                        # A newer match may have replaced this one; a stale thread must not keep
                        # stepping or read the new match's pause/stop flags as its own.
                        if self.stopping or self.match_id != match_id:
                            break
                        paused,speed = self.paused,self.speed
                    if paused:
                        time.sleep(.03)
                        continue
                    started = time.monotonic()
                    # Step outside the lock: a policy decision may take up to 200 ms and must not
                    # delay a pilot's control request. Publishing the frame stays atomic.
                    # `budget` keeps the match clock honest when an agent overruns: the team keeps its
                    # previous command for this tick instead of holding the whole field still.
                    frame = battle.step(budget=DT/max(.1,speed))
                    with self.lock:
                        if self.match_id == match_id:
                            self._publish(frame)
                        self.revision += 1
                    time.sleep(max(0,DT/speed-(time.monotonic()-started)))
                if self.stopping and battle.match.status != "finished":
                    battle.match.finish(None,"stopped")
                    with self.lock:
                        if self.match_id == match_id:
                            self._publish(battle.match.snapshot())
                            battle.frames[-1] = self.frame
                        self.revision += 1
                replay_path = self.store.directory / "replays" / f"{match_id}.json"
                battle.save(replay_path)
                self.store.finish(match_id,battle.result(),replay_path)
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
                self.revision += 1
            self.store.finish(match_id,{},error=str(exc))
        finally:
            with self.lock:
                # Only the thread that still owns the arena may publish into it; a stale match
                # finishing late must not clobber the busy flag of the match that replaced it.
                if self.match_id == match_id:
                    self.busy = False
                    self.prematch = None
                self.revision += 1

    def _prematch(self):
        """Hold the initial frame through self-check and countdown; honours pause, speed, stop and skip.

        Only the self-check walk-on can be skipped: the 5-4-3-2-1 countdown always runs in full, because
        the match clock and the starting BGM are both cued off it.
        """
        with self.lock:
            self.skip_prematch = False
            self.prematch_extra = 0.0
        for stage, seconds in self.prematch_stages:
            if seconds is None:
                with self.lock:
                    seconds = intro_seconds(len(self.frame["robots"]))
            with self.lock:
                # A skip asked for during the walk-on must not bleed into the countdown.
                if stage != "self_check":
                    self.skip_prematch = False
                    self.prematch_extra = 0.0
            announced, left, last = seconds, seconds, time.monotonic()
            while left > 0:
                with self.lock:
                    if self.stopping or (stage == "self_check" and self.skip_prematch):
                        break
                    now = time.monotonic()
                    if not self.paused:
                        left -= (now - last) * self.speed
                    last = now
                    # An extension grows the clock and the announced length by the same amount, so the
                    # client's "time already spent" stays put and only the window for the intro grows.
                    if stage == "self_check" and self.prematch_extra:
                        left += self.prematch_extra
                        announced += self.prematch_extra
                        self.prematch_extra = 0.0
                    self.prematch = {"stage": stage, "remaining": round(max(0.0, left), 3), "duration": round(announced, 3)}
                    self.revision += 1
                time.sleep(.1)
        with self.lock:
            self.prematch = None
            self.prematch_extra = 0.0
            self.revision += 1

    def highlight_clips(self, data):
        """Only the frames a post-match reel plays, taken from the live frame log.

        Handing a browser the whole replay to cut a handful of five-second clips out of it does not
        work: a full seven-minute match is hundreds of megabytes of JSON, and merging its static half
        into every frame froze the tab for seconds. The referee already keeps the frames spooled, so
        the requested windows are sliced here and returned as a replay the scene can play as-is.
        """
        args = HighlightRequest.model_validate(data)
        with self.lock:
            battle, match_id = self.battle, self.match_id
            if not battle or match_id != args.match_id:
                raise ValueError("这场比赛已不在内存中，无法回放高光片段")
            dt = battle.metadata.get("dt") or .05
            total = len(battle.frames)
            if total < 2:
                raise ValueError("这场比赛没有留下可用的逐帧数据")
            windows, frames = [], []
            for at in args.at:
                start = max(0, min(total - 1, int(round((at - args.before) / dt))))
                count = max(1, min(total - start, int(round(args.seconds / dt))))
                windows.append({"start": len(frames), "count": count, "time": at,
                                "from": round(start * dt, 3)})
                frames.extend(json.loads(raw) for raw in battle.frames.encoded_range(start, count))
            return {"format": "rmuc-replay-v4", "metadata": battle.metadata,
                    "static": battle.frames.static, "windows": windows, "frames": frames}

    def control(self, data):
        args = ControlRequest.model_validate(data)
        with self.lock:
            if args.command == "pause":
                self.paused = not self.paused
            elif args.command == "stop":
                self.stopping = True
            elif args.command == "speed":
                if args.speed not in (.5,1,2,4,8):
                    raise ValueError("Unsupported playback speed")
                self.speed = args.speed
            elif args.command == "skip_prematch":
                # Only the walk-on is skippable. The 5-4-3-2-1 countdown always runs in full, so a
                # request that lands after it starts is refused instead of quietly ignored.
                if self.prematch and self.prematch["stage"] != "self_check":
                    raise ValueError("倒计时不可跳过")
                self.skip_prematch = True
            elif args.command == "extend_prematch":
                # A player picking a chassis eats the walk-on's screen time. Rather than cutting a card
                # short, the self-check clock is stretched — the countdown simply starts later.
                if not self.prematch or self.prematch["stage"] != "self_check":
                    raise ValueError("赛前自检已结束")
                self.prematch_extra = min(120.0, self.prematch_extra + args.seconds)
            self.revision += 1

    def player_control(self, data):
        """Take over one robot of either team while its strategy keeps running for the rest."""
        args = PlayerRequest.model_validate(data)
        with self.lock:
            battle = self.battle
            if not battle or not self.busy:
                # The engine still builds the match on a background thread; say so instead of
                # pretending the match is over.
                raise ValueError("对局正在准备中，请稍候再接管")
            if battle.match.status == "finished":
                raise ValueError("比赛已结束，请重新开始对局")
            battle.set_manual(args.team, args.slot, args.action, args.assist)
            # A pilot needs the real-time tick rate, not a sped-up replay of their own inputs.
            if args.action is not None and self.speed != 1:
                self.speed = 1
            self.revision += 1
            return self.pilot()

    def strategies(self):
        """Every playable strategy with its classification, presentation summary and Elo, for the gallery."""
        standings = {(s["name"], s["version"]): s for s in self.store.leaderboard()}
        result = {}
        for key, entry in {**self.catalog(), **self.catalog(("adaptive",))}.items():
            # Each entry already names its rules season.
            path = entry["path"]
            profile, showcase = load_profile(path, bundled=entry["source"] != "local"), load_showcase(path)
            item = {k: v for k, v in entry.items() if k != "path"}
            item.update(key=key, bundled=entry["source"] != "local", profile=profile,
                        showcase={k: showcase[k] for k in ("title", "tagline", "style")} if showcase else None,
                        created_at=profile.get("created_at") or (path / "manifest.json").stat().st_mtime)
            standing = standings.get((entry["name"], entry["version"]))
            if standing:
                item["standing"] = {k: standing[k] for k in ("rating", "games", "wins", "losses", "draws")}
            result[key] = (item, path)
        return result

    def shutdown(self):
        self.stopping = True
        self.strategy_library.shutdown()
        if self.thread:
            self.thread.join(timeout=30)


def create_app(sandbox="docker",submission_root=None,data_root=None,test_mode=False,workspace_registry=None):
    service = ArenaService(sandbox,submission_root,data_root,test_mode,workspace_registry)
    training = TrainingService(service.store.directory/"practice",workspace_registry,service.submission_root,sandbox,service.strategy_library)
    @asynccontextmanager
    async def lifespan(app):
        service.strategy_library.start()
        yield
        await asyncio.to_thread(service.shutdown)
        await asyncio.to_thread(training.shutdown)
    app = FastAPI(title="RMUC Arena",version=__version__,lifespan=lifespan)
    @app.get("/api/desktop/health")
    def desktop_health():
        return {"application": "arena-1", "instance": os.environ.get("RMUC_DESKTOP_INSTANCE", ""), "engine": "rust"}
    app.state.arena = service
    app.state.training = training
    video_exporter = VideoExporter(service.store.directory / "video-exports")
    app.state.video_exporter = video_exporter
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=["127.0.0.1","localhost","testserver"])
    app.add_middleware(CORSMiddleware,allow_origins=["http://127.0.0.1:5173","http://localhost:5173"],allow_methods=["GET","POST","DELETE"],allow_headers=["Content-Type"])

    @app.middleware("http")
    async def boundary(request:Request,call_next):
        if request.method in ("POST","DELETE"):
            origin = request.headers.get("origin")
            allowed = {f"http://{request.headers.get('host')}","http://127.0.0.1:5173","http://localhost:5173"}
            if origin and origin not in allowed:
                return JSONResponse({"error":"Invalid origin"},status_code=403)
        if request.method == "POST":
            video = request.url.path == "/api/video-export" or (request.url.path.startswith("/api/matches/") and request.url.path.endswith("/video"))
            expected_type = "video/webm" if video else "application/json"
            if request.headers.get("content-type","").split(";")[0] != expected_type:
                return JSONResponse({"error": f"{expected_type} required"},status_code=415)
            try:
                size=int(request.headers.get("content-length",0))
                # Strategy sources and robot models are larger than ordinary control requests.
                limit=MAX_VIDEO_BYTES if video else 48*1024*1024 if request.url.path=="/api/custom-models" else 8*1024*1024 if request.url.path=="/api/submissions" else 600000
                if size>limit:
                    return JSONResponse({"error":"Request too large"},status_code=413)
            except ValueError:
                return JSONResponse({"error":"Invalid body size"},status_code=400)
        return await call_next(request)

    @app.get("/api/health")
    def health():
        default=season_rules.DEFAULT_SEASON
        # Ammunition prices per season, so the cockpit can price an order before sending it.
        economy={}
        # Heat each round adds, so the cockpit can stop firing before the barrel crosses its limit.
        heat={}
        for season in season_rules.seasons():
            profile="rulebook_2027" if season=="2027" else "rulebook"
            ammo=rules_config.get(profile,{}).get("economy",{}).get("ammo",{})
            economy[season]={kind:{"local":{"batch":rule.get("local_batch",0),"cost":rule.get("local_cost",0),"cap":rule.get("team_purchase_cap",0)},
                                    "remote":{"batch":rule.get("remote_batch",0),"cost":rule.get("remote_cost",0),"cap":rule.get("team_purchase_cap",0)}}
                             for kind,rule in ammo.items()}
            projectiles=rules_config.get(profile,{}).get("projectiles",{})
            heat[season]={kind:rule.get("heat_per_shot",0) for kind,rule in projectiles.items() if isinstance(rule,dict)}
        return {"version":__version__,"rules":season_rules.rules_profile(default),"season":default,"roster":list(season_rules.slots(default)),
                "team_size":len(season_rules.slots(default)),"seasons":season_rules.summary(),"duration":420,"engine":service.frame["engine"],
                "simulation_hz":20,"policy_hz":10,"transport":"websocket","sandbox":sandbox,
                # Level spans, so a first-person HUD can draw the experience bar from the rules.
                "experience":{"thresholds":rules_config["rulebook"]["experience"]["thresholds"]},
                "economy":economy,"heat":heat}

    @app.get("/api/video-export")
    def video_export_capabilities():
        return video_exporter.capabilities()

    @app.post("/api/video-export")
    async def video_export(request: Request, duration: float | None = Query(default=None, gt=0, le=3600, allow_inf_nan=False),
                           job: str | None = Query(default=None, pattern=JOB_PATTERN)):
        try:
            path, temporary = await video_exporter.export(request.stream(), duration=duration, job=job)
        except VideoExportError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        return FileResponse(path, media_type="video/mp4", filename="rmuc-arena.mp4",
                            background=BackgroundTask(temporary.cleanup))

    @app.get("/api/video-export/jobs/{job}")
    def video_export_job(job: str):
        state = video_exporter.job(job)
        if state is None:
            raise HTTPException(404, "Unknown export")
        return state

    @app.get("/api/battle-settings")
    def battle_settings(season: Literal["2026", "2027"] = "2027"):
        return service.settings.get(season)

    @app.post("/api/battle-settings")
    def save_battle_settings(data: BattleSettingsRequest):
        try:
            return service.settings.save(data.season, data.values)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/matches/{match_id}/video")
    def match_video(match_id: str):
        path = service.store.video_path(match_id)
        if not path or not path.is_file():
            raise HTTPException(404, "MP4 not found")
        return FileResponse(path, media_type="video/mp4", filename=f"rmuc-{match_id}.mp4", content_disposition_type="inline")

    @app.post("/api/matches/{match_id}/video")
    async def save_match_video(match_id: str, request: Request,
                               duration: float | None = Query(default=None, gt=0, le=3600, allow_inf_nan=False),
                               job: str | None = Query(default=None, pattern=JOB_PATTERN)):
        with service.store.lock:
            record = service.store.match(match_id)
            if not record:
                raise HTTPException(404, "Unknown match")
            if record["status"] in ("initializing", "running") or record.get("video_status") == "processing":
                raise HTTPException(409, "Wait for the match or video export to finish")
            service.store.video_status(match_id, "processing")
        temporary = None
        try:
            path, temporary = await video_exporter.export(request.stream(), duration=duration, job=job)
            with service.store.lock:
                if not service.store.match(match_id):
                    raise HTTPException(404, "Match was deleted")
                target = service.store.directory / "videos" / f"{match_id}.mp4"
                target.parent.mkdir(parents=True, exist_ok=True)
                path.replace(target)
                service.store.video_status(match_id, "ready", path=target)
            return {"match_id": match_id, "url": f"/api/matches/{match_id}/video"}
        except VideoExportError as exc:
            service.store.video_status(match_id, "failed", error=str(exc))
            raise HTTPException(exc.status_code, str(exc)) from exc
        except BaseException:
            service.store.video_status(match_id, "failed", error="录像保存中断，可重试保存原始 WebM")
            raise
        finally:
            if temporary is not None:
                temporary.cleanup()

    @app.get('/api/models')
    def models():
        from .models import model_catalog
        default=season_rules.DEFAULT_SEASON
        return {'models':model_catalog(),'default_team_lineup':season_rules.default_lineup(default),'slots':list(season_rules.slots(default)),
                'default_season':default,'seasons':season_rules.summary()}

    @app.post('/api/team-briefing')
    def team_briefing(data:TeamBriefingRequest):
        from scripts.build_agent_guides import render,team_task_context
        try:
            season=data.season or season_rules.infer_season(data.team_lineup.keys())
            lineup=normalize_team_lineup(data.team_lineup,season)
            rules=json.loads((ROOT/'config/rules.json').read_text(encoding="utf-8"))
            return {'team_lineup':lineup,'season':season,
                'task':{lang:team_task_context(lang,rules,lineup,season) for lang in ('zh','en')},
                'guides':{lang:render(lang,team_lineup=lineup,season=season) for lang in ('zh','en')}}
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.post('/api/team-workspaces')
    def team_workspace(data:TeamWorkspaceRequest,request:Request):
        from .submissions import scaffold,start_training
        try:
            season=data.season or season_rules.infer_season(data.team_lineup.keys())
            lineup=normalize_team_lineup(data.team_lineup,season)
            root=service.store.directory/'workspaces' if service.test_mode else data_path('workspaces')
            path=scaffold(root/data.name,mode='team',minutes=data.minutes,registry=service.workspace_registry,team_lineup=lineup,training_url=str(request.base_url).rstrip('/'),season=season)
            clock=start_training(path,service.workspace_registry)
            return {'workspace':str(path),'task_file':str(path/'AGENT_TASK.md'),'team_lineup':lineup,'season':season,**clock}
        except (ValueError,OSError) as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.post('/api/training-workspaces')
    def training_workspace(data:TrainingWorkspaceRequest,request:Request):
        from .submissions import scaffold,start_training
        try:
            root=service.store.directory/'workspaces' if service.test_mode else data_path('workspaces')
            season=season_rules.request_season(data.season,data.mode,data.robot,data.team_lineup)
            path=scaffold(root/data.name,mode=data.mode,robot=data.robot,minutes=data.minutes,
                registry=service.workspace_registry,team_lineup=data.team_lineup,
                training_url=str(request.base_url).rstrip('/'),season=season)
            clock=start_training(path,service.workspace_registry)
            return {'workspace':str(path),'task_file':str(path/'AGENT_TASK.md'),'mode':data.mode,'season':season,**clock}
        except (ValueError,OSError) as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.get("/api/showcase-guide")
    def showcase_guide():
        return FileResponse(ROOT/"docs/STRATEGY_SHOWCASE.md",media_type="text/markdown; charset=utf-8")

    @app.get("/api/agent-guide")
    def agent_guide(mode:Literal["team","robot","distributed","adaptive"]="team",robot:int|None=None,lang:Literal["zh","en"]="zh",season:Literal["2026","2027"]|None=None):
        try:
            path=guide_path(mode,robot,lang,season_rules.request_season(season,mode,robot))
        except ValueError as error:
            raise HTTPException(404,str(error)) from error
        return FileResponse(path,media_type="text/markdown; charset=utf-8")

    @app.get("/api/catalog")
    def catalog(season:Literal["2026","2027"]|None=None):
        return {key:{k:v for k,v in value.items() if k!="path"} for key,value in service.catalog(season=season).items()}

    @app.get("/api/robot-catalog")
    def robot_catalog(season:Literal["2026","2027"]|None=None):
        return {key:{k:v for k,v in value.items() if k!="path"} for key,value in service.catalog(("adaptive",),season).items()}

    @app.get("/api/deck-presets")
    def deck_presets():
        path=service.store.directory/'deck-presets.json'
        with service.lock:
            presets = list(json.loads(path.read_text(encoding="utf-8")).values()) if path.exists() else []
        for preset in presets:
            preset["decks"] = {team: [canonical_key(key) for key in cards] for team, cards in preset["decks"].items()}
            for controller in preset["controllers"].values():
                controller["strategy"] = canonical_key(controller.get("strategy", ""))
        return presets

    @app.post("/api/deck-presets")
    def save_deck_preset(data:DeckPresetRequest):
        data.decks = {team: [canonical_key(key) for key in cards] for team, cards in data.decks.items()}
        for controller in data.controllers.values():
            controller.strategy = canonical_key(controller.strategy)
        from .submissions import write_json
        try:
            name=data.name.strip()
            if not name or set(data.decks)!={"red","blue"} or set(data.controllers)!={"red","blue"}:
                raise ValueError("卡组需要名称和完整的红蓝阵容")
            controllers={team:value.model_dump() for team,value in data.controllers.items()}
            args=StartRequest(mode="deck",red_deck=data.decks['red'],blue_deck=data.decks['blue'],
                red_control=controllers['red']['mode'],blue_control=controllers['blue']['mode'],
                red_team_strategy=controllers['red']['strategy'] if controllers['red']['mode']=='team' else None,
                blue_team_strategy=controllers['blue']['strategy'] if controllers['blue']['mode']=='team' else None)
            if data.map:args.map=data.map
            args,season=service.resolve_season(args)
            cards=service.catalog(("adaptive",),season)
            if any(key not in cards for team in data.decks.values() for key in team):raise ValueError(f"卡组含有不可用于 {season} 赛季的单机策略")
            decks={team:[cards[key]['path'] for key in keys] for team,keys in data.decks.items()}
            prepare_decks(decks,args.seed,service.free_controllers(args),season)
            path=service.store.directory/'deck-presets.json'
            with service.lock:
                presets=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
                if name in presets and not data.replace:raise HTTPException(409,"同名卡组已存在，请选择更新卡组或换一个名称")
                preset={'name':name,'map':args.map,'season':season,'decks':data.decks,'controllers':controllers,'updated_at':time.time()}
                presets[name]=preset;write_json(path,presets)
                return preset
        except (ValueError,OSError) as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.get("/api/strategies")
    def strategies():
        return sorted((item for item, _ in service.strategies().values()), key=lambda item: -item["created_at"])

    @app.get("/api/strategy-library")
    def strategy_library_status():
        return service.strategy_library.status()

    @app.post("/api/strategy-library/sync")
    def strategy_library_sync():
        return service.strategy_library.request_sync()

    @app.get("/api/strategies/{key}")
    def strategy(key:str):
        found = service.strategies().get(key)
        if not found:
            raise HTTPException(404, "Unknown strategy")
        item, path = found
        manifest, entries = load_submission(path)
        files = [{"name": file.name, "bytes": file.stat().st_size, "lines": file.read_bytes().count(b"\n"),
                  "sha256": manifest["hashes"][file.name]} for file in sorted(set(entries.values()))]
        return {**item, "showcase": load_showcase(path), "files": files}

    @app.post("/api/strategies/{key}/profile")
    def classify(key:str, data:ProfileRequest):
        found = service.strategies().get(key)
        if not found:
            raise HTTPException(404, "Unknown strategy")
        item, path = found
        if item["bundled"]:
            raise HTTPException(403, "内置与在线策略的分类由发布仓库维护，不能在网页修改")
        try:
            profile = validate_profile({**data.model_dump(exclude_none=True), "created_at": item["profile"].get("created_at") or item["created_at"]})
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        with service.lock:
            write_json(path / PROFILE_FILE, profile)
        return service.strategies()[key][0]

    @app.get("/api/custom-models")
    def custom_models():
        return service.custom_models.list()

    @app.post("/api/custom-models")
    def upload_model(data:CustomModelRequest):
        import base64, binascii
        try:
            raw = base64.b64decode(data.glb_base64, validate=True)
            return service.custom_models.create(data.name, data.base_model, data.forward, raw, data.author)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/custom-models/{model_id}.glb")
    def custom_model_file(model_id:str):
        path = service.custom_models.path(model_id)
        if not path or not path.is_file():
            raise HTTPException(404, "Model not found")
        return FileResponse(path, media_type="model/gltf-binary", headers={"Cache-Control": "public, max-age=86400, immutable"})

    @app.delete("/api/custom-models/{model_id}")
    def delete_model(model_id:str):
        if not service.custom_models.delete(model_id):
            raise HTTPException(404, "Model not found")
        return {"deleted": model_id}

    @app.get("/api/arena-preview")
    def arena_preview(map: Literal["rmuc2027", "rmuc2026"] = "rmuc2027"):
        return {"frame": service.preview(map)}

    @app.get("/api/maps")
    def maps():
        return {name:arena_map(name) for name in (season_rules.map_of(s) for s in season_rules.seasons())}

    @app.get("/api/state")
    def state(since:int=-1):
        return service.state(since)

    @app.post("/api/start")
    def start(data:StartRequest):
        try:
            return {"ok":True,"match_id":service.start(data.model_dump())}
        except (ValueError,RuntimeError) as exc:
            raise HTTPException(409,str(exc)) from exc

    @app.post("/api/control")
    def control(data:ControlRequest):
        try:
            service.control(data.model_dump())
            return {"ok":True}
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.post("/api/player")
    def player(data:PlayerRequest):
        try:
            return {"ok":True,"player":service.player_control(data.model_dump())}
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from exc

    @app.post("/api/referee")
    def referee(data:RefereeRequest,authorization:str|None=Header(default=None)):
        supplied = (authorization or "").removeprefix("Bearer ")
        if not secrets.compare_digest(supplied.encode(), service.referee_token.encode()):
            raise HTTPException(403,"Organizer authorization required")
        try:
            with service.lock:
                if service.stopping or not service.battle or service.battle.match.status == "finished":
                    raise ValueError("No running match")
                service.battle.queue_referee(data.model_dump(exclude_none=True))
            return {"ok":True,"queued":True}
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from exc

    @app.websocket("/api/ws")
    async def broadcast(websocket:WebSocket):
        origin = websocket.headers.get("origin")
        allowed={f"http://{websocket.headers.get('host')}","http://127.0.0.1:5173","http://localhost:5173"}
        if origin and origin not in allowed:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        # `match_id` is None before the first match starts, so the initial sentinel must be
        # something else or the idle arena never receives its static frame.
        revision,since,match_id=-1,-1,object()
        last_send=time.monotonic()
        try:
            while True:
                current=await asyncio.to_thread(service.state,since,True)
                if current["match_id"]!=match_id:
                    match_id=current["match_id"]
                    since=-1
                    current=await asyncio.to_thread(service.state,since,True)
                    # The static half of the frame — arena geometry, hardware tables, rule text —
                    # never changes during a match, so a new connection receives it once and the
                    # snapshot stream stays about a third of its former size.
                    static=await asyncio.to_thread(service.static_state)
                    if static["frame"]:
                        await websocket.send_json({"type":"static","state":static})
                        current=await asyncio.to_thread(service.state,since,True)
                if current["revision"]!=revision:
                    await websocket.send_json({"type":"snapshot","state":current})
                    revision=current["revision"]
                    since=current["frame"]["tick"]
                    last_send=time.monotonic()
                elif time.monotonic()-last_send>10:
                    await websocket.send_json({"type":"heartbeat"})
                    last_send=time.monotonic()
                # A pilot's view is only as fresh as this poll: at the old 25 ms cadence the newest
                # gimbal angle could sit in the server for up to half an engine tick (12.5 ms on
                # average) before going out, which the cockpit feels as a soft follow. While someone
                # is driving, poll at 8 ms; spectators keep the cheaper 25 ms cadence, which is plenty
                # for a broadcast and keeps a large fan-out cheap.
                try:
                    await asyncio.wait_for(websocket.receive_text(),timeout=.008 if current.get("player") else .025)
                except asyncio.TimeoutError:
                    pass
        except (WebSocketDisconnect,RuntimeError,ConnectionError):
            pass

    @app.get("/api/matches")
    def matches():
        return service.store.matches()

    @app.get("/api/matches/{match_id}")
    def match_record(match_id:str):
        value=service.store.match(match_id)
        if not value:
            raise HTTPException(404,"Unknown match")
        return value

    @app.delete("/api/matches/{match_id}")
    def delete_match(match_id:str):
        with service.lock:
            if service.busy and service.match_id==match_id:
                raise HTTPException(409,"Stop the match before deleting it")
        try:
            deleted=service.store.delete(match_id)
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from exc
        if not deleted:
            raise HTTPException(404,"Unknown match")
        return {"deleted":match_id}

    @app.get("/api/leaderboard")
    def leaderboard():
        return service.store.leaderboard()

    @app.get("/api/replays")
    def replays():
        return [m for m in service.store.matches() if m["has_replay"]]

    @app.get("/api/replays/{match_id}")
    def replay_file(match_id:str):
        path=service.store.replay_path(match_id)
        if not path or not path.is_file():
            raise HTTPException(404,"Replay not found")
        return FileResponse(path,media_type="application/json",filename=f"rmuc-{match_id}.json")

    @app.post("/api/highlights")
    def highlight_clips(data:HighlightRequest):
        """The highlight windows of a finished match that the post-match reel replays."""
        try:
            return service.highlight_clips(data.model_dump())
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from exc

    @app.get("/api/replay")
    def current_replay():
        with service.lock:
            if not service.battle:
                raise HTTPException(404,"No match yet")
            # Serve the captured file without creating a match-sized JSON heap.
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as temp:
                path = Path(temp.name)
            try:
                service.battle.save(path)
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            return FileResponse(path, media_type="application/json",
                                background=BackgroundTask(path.unlink, missing_ok=True))

    @app.post("/api/submissions")
    def upload(data:SubmissionRequest):
        if data.name.startswith("entry-"):
            raise HTTPException(400,"This name prefix is reserved for timed competition entries")
        try:
            season=season_rules.request_season(data.season,data.mode,data.robot,data.team_lineup if data.mode=="team" else None,data.entries.keys())
        except ValueError as exc:
            raise HTTPException(400,"Entries do not match the selected control mode") from exc
        expected={"team"} if data.mode=="team" else {str(data.robot)} if data.mode in ("robot","adaptive") else {str(i) for i in season_rules.slots(season)}
        if set(data.entries)!=expected or (data.mode in ("robot","adaptive") and data.robot is None):
            raise HTTPException(400,"Entries do not match the selected control mode")
        if any(len(code.encode())>SOURCE_LIMIT for code in data.entries.values()):
            raise HTTPException(400,f"Each strategy must be <={SOURCE_LIMIT // 1024} KiB")
        try:
            with tempfile.TemporaryDirectory() as temp:
                files={}
                for key,code in data.entries.items():
                    path=Path(temp)/f"{key}.py"
                    path.write_text(code,encoding="utf-8")
                    files[key]=path
                profile={**(data.profile or {}),"created_at":time.time()}
                manifest=save_submission(service.submission_root/data.name,data.mode,files,data.robot,team_lineup=data.team_lineup,
                                         showcase=data.showcase,profile=profile,season=season)
            return {"ok":True,"name":data.name,"manifest":manifest}
        except (ValueError,SyntaxError) as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.get("/api/training/{session_id}")
    def training_status(session_id:str,authorization:str|None=Header(default=None)):
        try:
            return training.status(session_id,authorization)
        except ValueError as exc:
            raise HTTPException(403,str(exc)) from exc

    @app.post("/api/training/{session_id}/tests")
    def practice(session_id:str,data:PracticeRequest,authorization:str|None=Header(default=None)):
        try:
            return training.test(session_id,authorization,data.model_dump())
        except (ValueError,SyntaxError) as exc:
            raise HTTPException(403,str(exc)) from exc

    @app.get("/api/training/{session_id}/tests/{job_id}")
    def practice_results(session_id:str,job_id:str,authorization:str|None=Header(default=None)):
        try:
            return training.results(session_id,authorization,job_id)
        except ValueError as exc:
            raise HTTPException(403,str(exc)) from exc

    @app.get("/api/training/{session_id}/tests/{job_id}/replays/{game}")
    def practice_replay(session_id:str,job_id:str,game:int,authorization:str|None=Header(default=None)):
        try:
            path=training.replay_path(session_id,authorization,job_id,game)
            return FileResponse(path,media_type="application/json",filename=f"practice-{job_id}-{game}.json")
        except ValueError as exc:
            raise HTTPException(403,str(exc)) from exc

    @app.post("/api/training/{session_id}/submit")
    def practice_submit(session_id:str,authorization:str|None=Header(default=None)):
        try:
            return training.submit(session_id,authorization)
        except (ValueError,SyntaxError) as exc:
            raise HTTPException(403,str(exc)) from exc

    assets=ROOT/"frontend/dist"
    if assets.exists():
        app.mount("/",StaticFiles(directory=assets,html=True),name="frontend")
    return app


def serve(port=8765,sandbox="docker",submission_root=None):
    import uvicorn
    uvicorn.run(create_app(sandbox,submission_root),host="127.0.0.1",port=port,log_level="warning")
