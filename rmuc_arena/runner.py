"""Policy isolation, deadlines, action ownership, and replay recording."""
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from collections.abc import Sequence
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import shutil
from .platform_support import kill_process_tree
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from .engine import Match, POLICY_INTERVAL, DT, SLOT_IDS, RULES_PROFILE, STATIC_FRAME_KEYS
from .referee import validate_referee
from .submissions import load_submission
from .communication import TeamCommunication, validate_messages
from .decks import prepare_decks
from .showcase import load_profile
from .worker import MEMORY_LIMIT
from . import seasons as season_rules

IMAGE = "rmuc-arena-policy:0.5"
CPU_LIMIT = 1.0
# Seconds for module import and global initialization before the first decision.
STARTUP_LIMIT = {"docker": 60, "trusted-local": 15}
# A stalled process is stopped after three consecutive missed decision windows.
POLICY_TIMEOUT_LIMIT = 3
# A pilot owns the robot until their commands stop: brief gaps coast, long silence hands back.
PLAYER_COAST = 0.35
PLAYER_TIMEOUT = 2.5
# First-person focus: the eye sits FPV_EYE_LIFT muzzle heights above the barrel (the camera in
# `ArenaScene.tsx` uses the same lift), and the aim assist only considers plates inside the lens.
# 1.27 is 15 % below the previous 1.495, matching the lowered cockpit camera.
FPV_EYE_LIFT = 1.27
# A lobbed shell only lands on the reticle once the launcher has climbed to the solved elevation:
# the gun slews in the engine (turret_pitch_rate_rad_s), so the trigger is held until it is there.
LOB_READY_RAD = 0.012
ASSIST_YAW = 0.80
ASSIST_PITCH = 0.56
# Beyond this range the assist still solves the elevation, but only applies 80 % of it: the
# normal assisted aim point is 20 % higher than the far shot wants, and a full long-range arc
# reads as a floating crosshair instead of a stable aim point.
ASSIST_PITCH_RANGE_M = 10.0
ASSIST_FAR_PITCH_SCALE = 0.8
# Every field a strategy or a pilot may send for one robot.
ACTION_FIELDS = frozenset({
    "move", "aim", "pitch", "fire", "power", "profile", "buy_ammo", "remote_heal", "revive", "deploy", "support",
    "altitude", "pick_unit", "assembly", "assembly_insert", "assembly_translate", "assembly_rotate", "assembly_confirm",
    "rune_start", "heading", "crouch", "rescue", "yaw_rate", "yaw_boost", "brake", "leg_height", "jump", "climb", "lean", "arm", "arm2",
    "pickup_arm", "transform",
    # 2027: heavy launcher and assembly steps, sentry posture, aerial system.
    "install_launcher", "assembly_core", "assembly_lift", "assembly_flip", "assembly_rotate2", "posture",
    "posture_enhanced", "drones",
    # A pilot's lobbed shot: the world point under the crosshair, solved into a high arc server-side.
    "aim_point",
})


def validate_action(action, has_messages=False):
    """Reject unknown fields and payloads larger than the 1 KiB action budget."""
    if not isinstance(action, dict):
        raise ValueError("Invalid action object")
    allowed = ACTION_FIELDS | {"messages"} if has_messages else ACTION_FIELDS
    if not set(action) <= allowed:
        raise ValueError("Action contains unsupported fields")
    if len(json.dumps(action, allow_nan=False).encode()) > 1024:
        raise ValueError("Each robot action must be <=1 KiB")
    return action


def sight_blocked(arena, start, end):
    """True when a wall, a deck or a ramp stands on the line between two 3-D points.

    Walls are the referee's own obstacle boxes and the ground is the same height field the
    simulation runs on, so an assist can never reach through cover — or through the central
    highland — that the pilot cannot see past.
    """
    if not arena:
        return False
    from . import sdk
    (ax, ay, az), (bx, by, bz) = start, end
    dx, dy, dz = bx - ax, by - ay, bz - az
    # Exact segment/box test for every barrier: walking the ray in fixed steps could step over a
    # 0.15 m wall and report a plate behind it as visible.
    for w in arena.get("obstacles", ()):
        angle = w.get("rotation", 0.0)
        c, s = math.cos(angle), math.sin(angle)
        cx, cy = w["x"] + w["w"] / 2, w["y"] + w["h"] / 2
        x0, y0 = (ax - cx) * c + (ay - cy) * s, -(ax - cx) * s + (ay - cy) * c
        x1, y1 = (bx - cx) * c + (by - cy) * s, -(bx - cx) * s + (by - cy) * c
        bottom = w.get("bottom", 0.0)
        t0, t1 = 0.0, 1.0
        for p0, p1, lo, hi in (
            (x0, x1, -w["w"] / 2, w["w"] / 2),
            (y0, y1, -w["h"] / 2, w["h"] / 2),
            (az, bz, bottom, bottom + w.get("height", 1.0)),
        ):
            delta = p1 - p0
            if abs(delta) < 1e-9:
                if not lo <= p0 <= hi:
                    break
            else:
                near, far = (lo - p0) / delta, (hi - p0) / delta
                if near > far:
                    near, far = far, near
                t0, t1 = max(t0, near), min(t1, far)
                if t0 > t1:
                    break
        else:
            return True
    # Terrain has no simple box form, so sample it; the step is small enough for the 0.15 m rims.
    steps = max(1, int(math.ceil(math.sqrt(dx * dx + dy * dy + dz * dz) / 0.1)))
    for i in range(1, steps):
        t = i / steps
        x, y, z = ax + dx * t, ay + dy * t, az + dz * t
        if sdk.terrain_height(arena, x, y) > z + 0.12:
            return True
    return False


def next_shot_overheats(robot):
    """True when firing one more round would push the barrel past its published heat limit.

    The engine adds the round's heat after the shot and locks the gun once the total crosses the
    limit, so a held trigger can overheat on a frame the cockpit has not received yet. A sentry in
    enhanced attack posture and a heavy's launcher-install shot add no heat, exactly as in the
    engine.
    """
    if robot.get("posture") == "attack" and robot.get("posture_enhanced"):
        return False
    if robot.get("role") == "heavy" and robot.get("launcher") == "fitted":
        return False
    from . import sdk
    heat = 100.0 if sdk.is_42(robot) else 10.0
    return robot.get("heat", 0.0) + heat > robot.get("max_heat", 0.0) + 1e-8


def lob_climb_seconds(robot, elevation):
    """How long the launcher needs to slew onto a solved lob elevation, plus a settling margin.

    The gun climbs at the design's `turret_pitch_rate_rad_s`, and the published elevation it starts
    from is accurate enough for timing: a couple of degrees of chassis attitude is a few hundredths
    of a second.
    """
    from . import sdk
    rate = float(sdk._design(robot).get("turret_pitch_rate_rad_s") or 2.5)
    return abs(elevation - float(robot.get("pitch") or 0.0)) / max(rate, 0.2) + 0.12


def aim_assist(robot, target_id, robots, arena=None, view=None, structures=None, pitch=None):
    """World yaw and ballistic pitch that put `robot`'s muzzle on `target_id`'s armour plate.

    Uses the same solver the public SDK gives policies, so a pilot's assisted shot obeys
    the engine's ballistics and aims at the plate facing the shooter rather than the hull
    centre. Robots, outposts and bases all carry armour plates. The plate must be inside the
    pilot's lens and clear of cover — a target behind a wall, a deck or the camera is not
    assisted at all.

    An outpost belongs to whichever team last rebuilt it (`owner`), not to the half of the
    field it stands on, so a red outpost rebuilt by blue is never locked by a red pilot.

    Inside ten metres the assist solves yaw and elevation; past that it still solves the elevation
    but returns 80 % of it, 20 % below the normal assisted aim point, so a distant shot does not
    float above the target.
    """
    if not robot:
        return None
    target = None
    parts = target_id.rsplit("_", 1)
    if structures and target_id in structures:
        target = structures[target_id]
        owner = (target.get("owner") if target.get("kind") == "outpost" else None) or parts[0]
        if owner == robot["team"] or target.get("hp", 0.0) <= 0.0:
            target = None
    else:
        tokens = target_id.split("-")
        target = robots.get((tokens[0], tokens[1])) if len(tokens) > 1 else None
        if target and (target["team"] == robot["team"] or not target.get("alive", True)):
            target = None
    if not target:
        return None
    from . import sdk
    try:
        plate = sdk._aim_target(robot, target)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
    muzzle_height = robot.get("muzzle_height_m", 0.45)
    # The pilot looks from the raised first-person eye; the barrel sits lower. The plate has to
    # be visible from the eye and reachable from the muzzle.
    eye = (robot["x"], robot["y"], robot.get("z", 0.0) + muzzle_height * FPV_EYE_LIFT)
    muzzle = (robot["x"], robot["y"], robot.get("z", 0.0) + muzzle_height + 0.08)
    dx, dy = plate[0] - robot["x"], plate[1] - robot["y"]
    distance = math.hypot(dx, dy)
    bearing = math.atan2(dy, dx)
    if view is not None:
        offset = (bearing - view + math.pi) % math.tau - math.pi
        if abs(offset) > ASSIST_YAW:
            return None
        if pitch is not None and distance > 1e-6:
            elevation = math.atan2(plate[2] - eye[2], distance)
            if abs(elevation - pitch) > ASSIST_PITCH:
                return None
    if sight_blocked(arena, eye, plate) or sight_blocked(arena, muzzle, plate):
        return None
    try:
        yaw = sdk.aim_at(robot, target)
        elevation = sdk.aim_pitch(robot, target)
        # Past ten metres the assist trims the solved elevation instead of handing the aim back to
        # the pilot: keeping the pitch fully solved made the crosshair float above a far target.
        if distance > ASSIST_PITCH_RANGE_M:
            elevation *= ASSIST_FAR_PITCH_SCALE
        return yaw, elevation
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


class FrameLog(Sequence):
    """Spool immutable frames to disk instead of retaining a full match's heap.

    Keeping thousands of nested frame dictionaries triggers long GC pauses that
    count against agents' wall-clock deadlines. Only offsets and events stay in
    memory; the public sequence interface remains available to replay callers.
    """
    def __init__(self, initial):
        self.file = tempfile.TemporaryFile(mode="w+b")
        self.offsets, self.events = [], []
        self.lock = threading.RLock()
        self.static = {key:initial[key] for key in STATIC_FRAME_KEYS if key in initial}
        self.append(initial)

    def __len__(self):
        return len(self.offsets)

    def __del__(self):
        if hasattr(self, "file"):
            self.file.close()

    def _write(self, frame, raw=None):
        if raw is None:
            raw = json.dumps({key:value for key,value in frame.items() if key not in self.static}, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        self.file.seek(0, 2)
        offset = self.file.tell()
        self.file.write(raw)
        return offset, len(raw)

    def append(self, frame, raw=None):
        """`raw` is the frame already encoded without its static fields, if available."""
        with self.lock:
            self.offsets.append(self._write(frame, raw))
            self.events.append(list(frame["events"]))

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self))) ]
        with self.lock:
            offset, size = self.offsets[index]
            self.file.seek(offset)
            return {**self.static,**json.loads(self.file.read(size))}

    def __setitem__(self, index, frame):
        with self.lock:
            # Preserve indexing semantics while appending a replacement record.
            self.offsets[index] = self._write(frame)
            self.events[index] = list(frame["events"])

    def events_since(self, tick):
        with self.lock:
            start = max(1, tick + 1, len(self) - 1000)
            return [event for events in self.events[start:] for event in events]

    def encoded(self):
        for index in range(len(self)):
            with self.lock:
                offset, size = self.offsets[index]
                self.file.seek(offset)
                raw = self.file.read(size)
            yield raw

    def encoded_range(self, start, count=None):
        """Static-free frames in `[start, start+count)`, for callers that merge the static half once.

        A highlight reel only needs the handful of five-second windows it plays, so it must not be
        handed a whole match: a full seven-minute replay is hundreds of megabytes.
        """
        stop = len(self.offsets) if count is None else min(len(self.offsets), start + max(0, count))
        with self.lock:
            for index in range(max(0, start), stop):
                offset, size = self.offsets[index]
                self.file.seek(offset)
                yield self.file.read(size)


class EncodedObservation:
    """An engine observation line forwarded to a policy without decoding it."""
    def __init__(self, payload, controlled_ids, has_messages):
        self.payload, self.controlled_ids, self.has_messages = payload, controlled_ids, has_messages


class Policy:
    def __init__(self, path, seed, sandbox="docker", timeout=0.2, expected_digest=None, deadline=None, stop_event=None, dynamic_messages=False):
        self.timeout, self.sandbox, self.disabled = timeout, sandbox, False
        self.deadline, self.stop_event = deadline, stop_event
        self.dynamic_messages = dynamic_messages
        self.logs, self.lines, self.calls, self.errors = deque(maxlen=32), queue.Queue(maxsize=2), 0, 0
        self.pending_response, self.consecutive_timeouts = None, 0
        self.name, self.temp = "rmuc-" + uuid.uuid4().hex[:16], tempfile.TemporaryDirectory(prefix="rmuc-policy-")
        stage = Path(self.temp.name)
        stage.chmod(0o755)
        source = path.read_bytes()
        self.digest = hashlib.sha256(source).hexdigest()
        if expected_digest is not None and self.digest != expected_digest:
            self.temp.cleanup()
            raise ValueError("Submitted strategy changed before staging")
        (stage / "strategy.py").write_bytes(source)
        (stage / "strategy.py").chmod(0o444)
        worker = Path(__file__).with_name("worker.py")
        if sandbox == "docker":
            command = ["docker", "run", "--rm", "--name", self.name, "--network=none", "--read-only",
                       "--cap-drop=ALL", "--security-opt=no-new-privileges", f"--memory={MEMORY_LIMIT}", f"--memory-swap={MEMORY_LIMIT}",
                       f"--cpus={CPU_LIMIT}", "--pids-limit=1", "--user=65534:65534", "--ipc=none",
                       "--ulimit", "nofile=64:64", "--mount", f"type=bind,source={stage},target=/submission,readonly",
                       "-i", IMAGE, "/submission/strategy.py", str(seed)]
        elif sandbox == "trusted-local":
            # Copy only the public runtime. Local mode is for trusted developer code.
            shutil.copyfile(worker, stage / "worker.py")
            shutil.copyfile(worker.with_name("sdk.py"), stage / "sdk.py")
            shutil.copyfile(worker.parent.parent / "config/rules.json", stage / "rules.json")
            command = [sys.executable, "-I", str(stage / "worker.py"), str(stage / "strategy.py"), str(seed)]
        else:
            self.temp.cleanup()
            raise ValueError("Unsupported sandbox")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""), "PYTHONHASHSEED": "0",
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "LANG": "C.UTF-8"}
        # Docker client needs its configured socket; never propagate arbitrary secrets.
        for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA"):
            if key in os.environ:
                env[key] = os.environ[key]
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            cwd=stage, env=env, start_new_session=True)
        except BaseException:
            self.temp.cleanup()
            raise
        threading.Thread(target=self._read_output, daemon=True).start()
        threading.Thread(target=self._read_errors, daemon=True).start()
        try:
            ready_until = min(time.monotonic() + STARTUP_LIMIT[sandbox], deadline or float("inf"))
            while True:
                remaining = ready_until - time.monotonic()
                if remaining <= 0 or (stop_event and stop_event.is_set()):
                    raise TimeoutError("Policy initialization deadline reached")
                try:
                    ready = self.lines.get(timeout=min(.1, remaining))
                    break
                except queue.Empty:
                    continue
            if json.loads(ready) != {"ready": True}:
                raise ValueError("Invalid ready response")
        except BaseException as exc:
            details = " ".join(self.logs)[-1500:]
            self.close()
            raise RuntimeError(f"Policy did not initialize: {details or str(exc)}") from exc

    def _read_output(self):
        try:
            while True:
                line = self.process.stdout.readline(16386)
                if not line:
                    break
                if len(line) > 16385 or not line.endswith(b"\n"):
                    line = b'{"error":"oversized protocol output"}\n'
                try:
                    self.lines.put_nowait(line)
                except queue.Full:
                    break
        finally:
            try:
                self.lines.put_nowait(b'{"error":"policy process exited"}\n')
            except queue.Full:
                pass

    def _read_errors(self):
        while True:
            chunk = self.process.stderr.read(512)
            if not chunk:
                return
            self.logs.append(chunk.decode("utf-8", errors="replace"))

    def decide(self, observation):
        if self.disabled:
            return {}, None
        self.calls += 1
        try:
            if isinstance(observation, EncodedObservation):
                payload, controlled, has_messages = observation.payload, set(observation.controlled_ids), observation.has_messages
            else:
                payload = json.dumps(observation, allow_nan=False, separators=(",", ":")).encode() + b"\n"
                controlled, has_messages = set(observation["controlled_ids"]), "messages" in observation
            started = time.monotonic()
            if (self.deadline is not None and started >= self.deadline) or (self.stop_event and self.stop_event.is_set()):
                return {}, None
            until = min(started + self.timeout, self.deadline if self.deadline is not None else float("inf"))
            if self.pending_response is not None:
                # Only one request may be in flight. Discard its late response before
                # sending fresh observations, preserving private state without ever
                # applying old actions to a new tick or building a stdin backlog.
                self._receive(until)
            if time.monotonic() >= until:
                raise queue.Empty
            self.pending_response = controlled, has_messages
            self.process.stdin.write(payload)
            self.process.stdin.flush()
            actions = self._receive(until)
            self.consecutive_timeouts = 0
            return actions, None
        except queue.Empty:
            self.errors += 1
            self.consecutive_timeouts += 1
            message = "decision exceeded deadline"
            self.logs.append(message)
            if self.consecutive_timeouts >= POLICY_TIMEOUT_LIMIT:
                self.close()
            return {}, message
        except Exception as exc:
            self.errors += 1
            message = str(exc)
            self.logs.append(message)
            self.close()
            return {}, message

    def _receive(self, until):
        remaining = until - time.monotonic()
        if remaining <= 0:
            raise queue.Empty
        raw = self.lines.get(timeout=remaining)
        controlled, has_messages = self.pending_response
        self.pending_response = None
        response = json.loads(raw, parse_constant=lambda s: (_ for _ in ()).throw(ValueError("non-finite JSON")))
        if response.get("error"):
            raise ValueError(response["error"])
        actions = response.get("actions")
        if not isinstance(actions, dict):
            raise ValueError("Invalid action object")
        if not set(actions) <= controlled:
            raise ValueError("Attempt to control an unowned robot")
        for slot, action in actions.items():
            validate_action(action, has_messages)
            if "messages" in action:
                validate_messages(action["messages"], slot, self.dynamic_messages)
        return actions

    def close(self):
        self.disabled = True
        if hasattr(self, "process"):
            if self.sandbox == "docker":
                # Killing docker's client alone does not always kill its container.
                try:
                    subprocess.run(["docker", "rm", "-f", self.name], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
            if self.process.poll() is None:
                try:
                    if self.sandbox == "docker":
                        self.process.kill()
                    else:
                        kill_process_tree(self.process)
                except (ProcessLookupError, PermissionError):
                    # Container deletion above is authoritative. Never turn a
                    # completed match into a failure by killing an exited group.
                    try:
                        self.process.terminate()
                    except (ProcessLookupError, PermissionError):
                        pass
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
        self.temp.cleanup()


class Battle:
    def __init__(self, red, blue, seed=42, duration=420, map_name=None, sandbox="docker", timeout=0.2, deadline=None, stop_event=None, decks=None, team_lineup=None, practice_lineup=False, free_team_strategies=None, battle_settings=None):
        # The field follows the strategies' rules season unless the caller names it.
        if map_name is None:
            from .submissions import manifest_season
            sources = [s for s in (red, blue) if s is not None] or [cards[0] for cards in (decks or {}).values() if cards]
            found = {manifest_season(load_submission(s)[0]) for s in sources}
            map_name = season_rules.map_of(found.pop() if len(found) == 1 else season_rules.LEGACY_SEASON)
        season = season_rules.season_of_map(map_name)
        self.season, rules_profile, slot_ids = season, season_rules.rules_profile(season), season_rules.slots(season)
        lineups, deck_policies, deck_metadata = prepare_decks(decks, seed, free_team_strategies, season) if decks is not None else (None, None, None)
        if decks is None:
            if free_team_strategies:raise ValueError("Free controllers require free battle")
            from .models import normalize_team_lineup,mirrored_lineups
            manifests=[load_submission(source)[0] for source in (red,blue)]
            if any(m.get("rules_profile") != rules_profile for m in manifests):
                raise ValueError(f"Both strategies must be written for the {season} season to play on {map_name}")
            selected=[normalize_team_lineup(m.get('team_lineup'),season) for m in manifests]
            chosen=normalize_team_lineup(team_lineup,season) if team_lineup is not None else selected[0]
            if not practice_lineup and (selected[0]!=selected[1] or any(s!=chosen for s in selected)):
                raise ValueError('Team matches require identical registered robot lineups; develop both strategies on the same lineup')
            if chosen!=season_rules.default_lineup(season) or season!=season_rules.LEGACY_SEASON:lineups=mirrored_lineups(chosen,season)
        elif team_lineup is not None:raise ValueError('Decks and shared team lineups cannot be combined')
        from .battle_settings import normalize
        battle_settings = normalize(battle_settings or {}, season)
        self.match, self.sandbox, self.policies, self.closed = Match(seed, duration, map_name, lineups=lineups, battle_settings=battle_settings), sandbox, [], False
        self.deck_mode = decks is not None
        self.deadline, self.stop_event = deadline, stop_event
        self.pool = ThreadPoolExecutor(max_workers=24 if self.deck_mode else 12)
        self.metadata = {"api_version": 3, "engine": "rust", "rules": rules_profile, "season": season, "decision_timeout_s":timeout, "policy_timeout_limit":POLICY_TIMEOUT_LIMIT, "roster":list(slot_ids), "test_match":duration!=420, "dt": DT, "policy_interval": POLICY_INTERVAL, "seed": seed, "duration": duration,
                         "map": map_name, "sandbox": sandbox, "match_mode":"deck" if self.deck_mode else "standard", "teams": {}}
        if battle_settings:
            self.metadata.update({"battle_settings": battle_settings, "test_match": True})
        self.frames, self.actions, self.diagnostics = FrameLog(self.match.snapshot()), [], []
        self.metadata["rules_hash"] = self.frames[0]["rules_hash"]
        self.metadata["engine_hash"] = self.frames[0]["engine_hash"]
        self.held_commands = {"red": {}, "blue": {}}
        # A human pilot's live commands, keyed (team, slot) and re-applied until they go stale.
        self.manual, self.manual_lock = {}, threading.Lock()
        # Ammunition orders wait here until a tick the rulebook actually reads (every second tick).
        self.pending_orders = {}
        # Last published gun elevation per piloted robot: a lobbed round is only released once the
        # launcher has stopped climbing, otherwise the frame's one-tick lag is a few degrees of arc.
        self.lob_ready = {}
        # The solved lob aim a `lob_ready` deadline belongs to, so a moving reticle re-arms the climb.
        self.lob_ready_aim = {}
        self.communication = TeamCommunication({team:[d["slot"] for d in items] for team, items in lineups.items()} if lineups else None, slot_ids)
        if lineups:
            self.metadata.update({"lineups":lineups,"test_match":True,"roster":{team:[d["slot"] for d in items] for team,items in lineups.items()}})
        if not self.deck_mode:
            self.metadata['team_lineup']=chosen
            self.metadata['test_match']=duration!=420 or practice_lineup or bool(battle_settings)
        self.pending_referee = []
        self.metadata["agents"] = {}
        try:
            for team, source in (("red", red), ("blue", blue)):
                if self.deck_mode:
                    self.metadata["teams"][team] = deck_metadata[team]
                    controller = (free_team_strategies or {}).get(team)
                    cards = deck_metadata[team]["cards"]
                    self.metadata["agents"][team] = {str(d["slot"]): ({**deck_metadata[team]["agent"], "strategy": deck_metadata[team].get("display_name") or Path(controller).name}
                        if controller else {**card["agent"], "strategy": card.get("display_name") or card["name"]}) for d, card in zip(lineups[team], cards)}
                    for slot, path, digest in deck_policies[team]:
                        if self.cancelled():
                            raise TimeoutError("Practice development window ended")
                        policy = Policy(path, seed*100+(0 if team == "red" else 10000)+(slot or 0), sandbox, timeout, expected_digest=digest,
                                        deadline=deadline,stop_event=stop_event,dynamic_messages=True)
                        self.policies.append((team,None if slot is None else [slot],policy))
                    continue
                manifest, entries = load_submission(source)
                if manifest.get("api_version") != 3 or manifest.get("rules_profile") != rules_profile:
                    raise ValueError(f"This submission does not use the {season} rules; create and submit a {season} strategy workspace")
                if manifest["mode"] not in ("team", "squad", "distributed"):
                    raise ValueError("Assemble robot submissions into a squad before matching")
                profile = load_profile(source)
                self.metadata["teams"][team] = {"name": Path(source).name, "version": manifest["version"], "mode": manifest["mode"], "agent": profile["agent"],
                                                **({"display_name": profile["display_name"]} if profile.get("display_name") else {})}
                self.metadata["agents"][team] = {str(slot): {**profile["agent"], "strategy": profile.get("display_name") or Path(source).name} for slot in slot_ids}
                # Each process sees exactly one strategy. Robot policy seed is stable per slot.
                for key, path in sorted(entries.items()):
                    if self.cancelled():
                        raise TimeoutError("Practice development window ended")
                    slots = None if manifest["mode"] == "team" else [int(key)]
                    policy = Policy(path, seed * 100 + (0 if team == "red" else 10) + (int(key) if slots else 0), sandbox, timeout,
                                    expected_digest=manifest["hashes"][manifest["entries"][key]],deadline=deadline,stop_event=stop_event)
                    self.policies.append((team, slots, policy))
        except BaseException:
            self.close()
            raise

    def cancelled(self):
        return (self.deadline is not None and time.monotonic() >= self.deadline) or bool(self.stop_event and self.stop_event.is_set())

    def set_manual(self, team, slot, action, assist=None):
        """Hold `action` for one robot of `team`; `action=None` hands it back to its strategy.

        `assist` names an enemy robot the pilot is locking onto: the gimbal then follows the
        engine's own ballistic solution, exactly like `sdk.aim_at`/`sdk.aim_pitch` in a policy.
        """
        if action is None:
            with self.manual_lock:
                self.manual.pop((team, str(slot)), None)
            return
        robot = next((item for item in self.match.robots
                      if item["team"] == team and str(item["slot"]) == str(slot)), None)
        if robot is None:
            raise ValueError("Robot is not on the field")
        if robot.get("role") == "aerial":
            raise ValueError("空中机器人由自动飞行系统控制，不能手动驾驶")
        validated = validate_action(action)
        # The rulebook reads orders every second tick, so an order that only rides on one 50 ms
        # command would be dropped half the time. Queue it and let `_manual_commands` deliver it on
        # a tick the engine reads, exactly once.
        key = (team, str(slot))
        order = validated.pop("buy_ammo", None)
        if order is not None:
            with self.manual_lock:
                self.pending_orders[key] = (order, time.monotonic())
        with self.manual_lock:
            self.manual[key] = (validated, time.monotonic(), assist)

    def _manual_commands(self):
        """Live pilot actions by team. A piloted robot never falls back to its strategy while the
        pilot is still connected: a brief gap only brakes it, and silence for `PLAYER_TIMEOUT`
        hands it back."""
        now = time.monotonic()
        with self.manual_lock:
            for key, (_, sent, _assist) in list(self.manual.items()):
                if now - sent > PLAYER_TIMEOUT:
                    del self.manual[key]
            held = dict(self.manual)
        if not held:
            return {}
        robots = {(item["team"], str(item["slot"])): item for item in self.match.robots}
        # Outposts and bases are targets too: their published armour plates are ordinary plates.
        structures = {f"{team}_base": {**base, "kind": "base"} for team, base in self.match.bases.items()}
        for team, outpost in (self.match.outposts or {}).items():
            structures[f"{team}_outpost"] = {**outpost, "kind": "outpost"}
        commands = {}
        for (team, slot), (action, sent, assist) in held.items():
            if now - sent > PLAYER_COAST:
                # Keep the gun where the pilot left it, but stop driving and shooting.
                action = {key: action[key] for key in ("aim", "pitch") if key in action}
                action.update({"move": [0.0, 0.0], "fire": False, "brake": True})
            else:
                action = dict(action)
            live = robots.get((team, slot))
            if live is not None and action.get("fire") and next_shot_overheats(live):
                # The engine adds heat after a shot and locks the barrel when the total crosses its
                # limit, so a held trigger could overheat on a frame the cockpit has not seen yet.
                # Drop the shot before that round: the last line of defence behind the cockpit's
                # own heat guard.
                action["fire"] = False
            if assist:
                aimed = aim_assist(robots.get((team, slot)), assist, robots, self.match.arena,
                                   action.get("aim"), structures, action.get("pitch"))
                if aimed:
                    action["aim"], action["pitch"] = aimed
            # Lobbed fire: the cockpit sends the world point under its crosshair and the shell has to
            # land there, so the elevation is solved on the steep branch. The engine never reads the
            # point itself, so it is dropped before the action reaches it.
            point = action.pop("aim_point", None)
            if point:
                from . import sdk
                solved = sdk.lob_aim(live, point) if live is not None else None
                if solved:
                    action["aim"], action["pitch"] = solved
                    # The launcher still has to arrive on the solved elevation: a round fired on the
                    # same tick would leave at the angle the gun still had, and the drop solve would
                    # be wrong — that is the shell that falls into the ground a few metres short. A
                    # reticle that moves solves a new arc, so the climb clock starts over.
                    key = (team, slot)
                    issued = self.lob_ready_aim.get(key)
                    if issued is None or abs(issued[0] - solved[0]) > LOB_READY_RAD or abs(issued[1] - solved[1]) > LOB_READY_RAD:
                        self.lob_ready_aim[key] = solved
                        self.lob_ready[key] = now + lob_climb_seconds(live, solved[1])
                    ready = self.lob_ready.get(key)
                    if action.get("fire") and ready is not None and now < ready:
                        action["fire"] = False
                else:
                    # No elevation puts the shell on that point any more: the flat arc is out of
                    # reach there, so the trigger waits instead of lobbing a round into the ground.
                    action["fire"] = False
            # An ammunition order waits for a tick the rulebook reads (`tick % 2 == 0`), so a single
            # 50 ms command can never be skipped, and it is delivered only once.
            order = self.pending_orders.get((team, slot))
            if order is not None:
                if now - order[1] > 2.0:
                    del self.pending_orders[(team, slot)]
                elif self.match.tick % 2 == 0:
                    action["buy_ammo"] = order[0]
                    del self.pending_orders[(team, slot)]
            commands.setdefault(team, {})[slot] = action
        return commands

    def queue_referee(self, command):
        value = validate_referee(command, [robot["id"] for robot in self.match.robots])
        if self.match.status == "finished":
            raise ValueError("The match has ended")
        if len(self.pending_referee) >= 16:
            raise ValueError("Too many pending referee decisions")
        self.pending_referee.append(value)

    def observation(self, team, slots):
        observation = self.match.observation(team, slots)
        inboxes={slot:self.communication.inboxes[team][slot] for slot in observation["controlled_ids"]}
        observation["message_inboxes"] = inboxes
        observation["messages"] = [message for inbox in inboxes.values() for message in inbox]
        return observation

    def encoded_observations(self, policies):
        """The same observations as `observation`, fetched together and left encoded."""
        controlled, lines = self.match.observations([(team, slots) for team, slots, _ in policies])
        encoded = []
        for (team, _, _), ids, line in zip(policies, controlled, lines):
            inboxes = {slot: self.communication.inboxes[team][slot] for slot in ids}
            messages = [message for inbox in inboxes.values() for message in inbox]
            # Append both keys last, in the order `observation` adds them.
            tail = ',"message_inboxes":' + json.dumps(inboxes, allow_nan=False, separators=(",", ":")) + ',"messages":' + json.dumps(messages, allow_nan=False, separators=(",", ":"))
            encoded.append(EncodedObservation(line.rstrip(b"\n")[:-1] + tail.encode() + b"}\n", ids, True))
        return encoded

    def step(self):
        if self.match.status == "finished":
            return self.frames[-1]
        if self.cancelled():
            self.match.finish(None, "stopped")
            self.frames[-1] = self.match.snapshot()
            return self.frames[-1]
        policy_tick = bool(self.policies) and self.match.tick % POLICY_INTERVAL == 0
        # Disabled policies return no actions, so they need no observation.
        deciding = [item for item in self.policies if not item[2].disabled] if policy_tick else []
        futures = []
        if deciding:
            for (team, slots, p), observation in zip(deciding, self.encoded_observations(deciding)):
                futures.append((team, slots, p, self.pool.submit(p.decide, observation)))
        commands, failures = ({"red": {}, "blue": {}} if policy_tick else self.held_commands), []
        outgoing = []
        for team, slots, p, future in futures:
            actions, error = future.result()
            for slot, action in actions.items():
                action = dict(action)
                messages = action.pop("messages", [])
                if messages:
                    outgoing.append((team, slot, messages))
                commands[team][slot] = action
            if error:
                scope = "team" if slots is None else "-".join(map(str, slots))
                detail = {"type": "policy_error", "id": f"policy:{team}:{scope}:{self.match.tick}",
                          "tick": self.match.tick, "time": self.match.time, "team": team, "slots": slots,
                          "disabled": p.disabled, "consecutive_timeouts": p.consecutive_timeouts,
                          "message": error, "logs": list(p.logs)[-8:]}
                self.diagnostics.append(detail)
                failures.append(detail)
        self.held_commands = commands
        # A pilot overrides the strategy for their own robot only, every tick, so the
        # policy's held actions keep driving the rest of the team.
        manual = self._manual_commands()
        if manual:
            commands = {team: {**slots, **manual.get(team, {})} for team, slots in commands.items()}
        communications = self.communication.route(outgoing, self.match.tick, self.match.tick + POLICY_INTERVAL) if policy_tick else []
        if self.pending_referee:
            commands = {**commands, "referee": self.pending_referee}
            self.pending_referee = []
        # Communication is recorded alongside actions, but never sent to physics
        # or repeated during the held-action tick. Replay verification uses the
        # recorded robot commands; strategies are not re-executed.
        self.actions.append({**commands, "communication": communications} if communications else commands)
        frame = self.match.step(commands)
        frame["events"].extend(failures)
        # Reuse the engine's encoding unless policy errors were added to the events.
        self.frames.append(frame, None if failures else self.match.raw_frame)
        return frame

    def run(self):
        while self.match.status != "finished":
            self.step()
        return self.result()

    def result(self):
        return {"winner": self.match.winner, "reason": self.match.reason, "time": self.match.time,
                "teams": self.match.snapshot()["teams"], "digest": getattr(self, "_digest_cache", None) or self.match.digest(), "policy_errors": len(self.diagnostics)}

    def replay(self):
        return {"format": "rmuc-replay-v4", "metadata": self.metadata, "static":self.frames.static,"frames": [json.loads(raw) for raw in self.frames.encoded()],
                "actions": self.actions, "diagnostics": self.diagnostics, "result": self.result()}

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        with path.open("wb") as stream:
            stream.write(b'{"format":"rmuc-replay-v4","metadata":')
            stream.write(encode(self.metadata))
            stream.write(b',"static":');stream.write(encode(self.frames.static))
            stream.write(b',"frames":[')
            for index, raw in enumerate(self.frames.encoded()):
                if index:
                    stream.write(b",")
                stream.write(raw)
            stream.write(b'],"actions":')
            stream.write(encode(self.actions))
            stream.write(b',"diagnostics":')
            stream.write(encode(self.diagnostics))
            stream.write(b',"result":')
            stream.write(encode(self.result()))
            stream.write(b"}")

    def close(self):
        if self.closed:
            return
        self._digest_cache = self.match.digest()
        self.closed = True
        with self.manual_lock:
            self.manual.clear()
            self.pending_orders.clear()
        self.pool.shutdown(wait=True, cancel_futures=True)
        if self.policies:
            with ThreadPoolExecutor(max_workers=12) as pool:
                list(pool.map(lambda item: item[2].close(), self.policies))
        self.match.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
