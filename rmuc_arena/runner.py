"""Policy isolation, deadlines, action ownership, and replay recording."""
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from collections.abc import Sequence
import hashlib
import json
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
        fields = {"move", "aim", "pitch", "fire", "power", "profile", "buy_ammo", "remote_heal", "revive", "deploy", "support", "altitude", "pick_unit", "assembly", "assembly_insert", "assembly_translate", "assembly_rotate", "assembly_confirm", "rune_start", "heading", "crouch", "rescue", "yaw_rate", "brake", "leg_height", "jump", "lean", "arm", "arm2", "pickup_arm", "transform",
                  # 2027: heavy launcher and assembly steps, sentry posture, aerial system.
                  "install_launcher", "assembly_core", "assembly_lift", "assembly_flip", "assembly_rotate2", "posture", "posture_enhanced", "drones"}
        if has_messages:
            fields.add("messages")
        for slot, action in actions.items():
            if not isinstance(action, dict) or not set(action) <= fields:
                raise ValueError("Action contains unsupported fields")
            if len(json.dumps(action, allow_nan=False).encode()) > 1024:
                raise ValueError("Each robot action must be <=1 KiB")
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
    def __init__(self, red, blue, seed=42, duration=420, map_name=None, sandbox="docker", timeout=0.2, deadline=None, stop_event=None, decks=None, team_lineup=None, practice_lineup=False, free_team_strategies=None):
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
        self.match, self.sandbox, self.policies, self.closed = Match(seed, duration, map_name, lineups=lineups), sandbox, [], False
        self.deck_mode = decks is not None
        self.deadline, self.stop_event = deadline, stop_event
        self.pool = ThreadPoolExecutor(max_workers=24 if self.deck_mode else 12)
        self.metadata = {"api_version": 3, "engine": "rust", "rules": rules_profile, "season": season, "decision_timeout_s":timeout, "policy_timeout_limit":POLICY_TIMEOUT_LIMIT, "roster":list(slot_ids), "test_match":duration!=420, "dt": DT, "policy_interval": POLICY_INTERVAL, "seed": seed, "duration": duration,
                         "map": map_name, "sandbox": sandbox, "match_mode":"deck" if self.deck_mode else "standard", "teams": {}}
        self.frames, self.actions, self.diagnostics = FrameLog(self.match.snapshot()), [], []
        self.metadata["rules_hash"] = self.frames[0]["rules_hash"]
        self.metadata["engine_hash"] = self.frames[0]["engine_hash"]
        self.held_commands = {"red": {}, "blue": {}}
        self.communication = TeamCommunication({team:[d["slot"] for d in items] for team, items in lineups.items()} if lineups else None, slot_ids)
        if lineups:
            self.metadata.update({"lineups":lineups,"test_match":True,"roster":{team:[d["slot"] for d in items] for team,items in lineups.items()}})
        if not self.deck_mode:
            self.metadata['team_lineup']=chosen
            self.metadata['test_match']=duration!=420 or practice_lineup
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
        self.pool.shutdown(wait=True, cancel_futures=True)
        if self.policies:
            with ThreadPoolExecutor(max_workers=12) as pool:
                list(pool.map(lambda item: item[2].close(), self.policies))
        self.match.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
