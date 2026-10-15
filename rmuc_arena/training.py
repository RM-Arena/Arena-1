"""Host-controlled development windows and private, unranked practice matches."""
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
from pathlib import Path
import re
import secrets
import threading
import time

from .runner import Battle
from .paths import data_path
from .submissions import (ROOT, SLOT_IDS, check_training_window, load_submission,
    locked_registry, save_submission, validate_workspace, workspace_entries, workspace_showcase, write_json)
from .showcase import PROFILE_FILE, SHOWCASE_FILE, validate_profile


class TrainingService:
    def __init__(self, directory, registry=None, submission_root=None, sandbox="docker"):
        self.directory = Path(directory)
        self.registry = Path(registry or data_path(".arena_host/workspaces.json"))
        self.submission_root = Path(submission_root or data_path("submissions"))
        self.sandbox = sandbox
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.active = set()
        self.stopping = threading.Event()

    def authenticate(self, session_id, authorization):
        records = json.loads(self.registry.read_text(encoding="utf-8")) if self.registry.exists() else {}
        token = authorization.removeprefix("Bearer ") if authorization else ""
        if not re.fullmatch(r"[a-f0-9]{64}",token):
            raise ValueError("Invalid development session")
        for workspace, record in records.items():
            training = record.get("training", {})
            if training.get("session_id") == session_id and secrets.compare_digest(training.get("token", ""), token):
                return Path(workspace), record
        raise ValueError("Invalid development session")

    def _session_directory(self, record):
        return self.directory / record["training"]["session_id"]

    def status(self, session_id, authorization):
        _, record = self.authenticate(session_id, authorization)
        t = record["training"]
        remaining = max(0, t["deadline_at"] - time.time()) if t["deadline_at"] else t["time_limit_seconds"]
        phase = "waiting" if t["started_at"] is None else "active" if remaining > 0 else "expired"
        jobs = []
        with self.lock:
            for file in sorted(self._session_directory(record).glob("jobs/*/job.json")):
                job = json.loads(file.read_text(encoding="utf-8"))
                if job["status"] in ("queued", "running") and session_id not in self.active:
                    job["status"] = "interrupted"
                jobs.append({"id": job["id"], "status": job["status"], "completed_games": len(job["results"])})
        versions = self._versions(record)
        return {"session_id": session_id, "phase": phase, "time_limit_seconds": t["time_limit_seconds"],
            "remaining_seconds": round(remaining, 1), "deadline_utc": self._iso(t["deadline_at"]),
            "last_submission": (t.get("last_submission") or {}).get("version"),
            "versions": sorted(versions), "jobs": jobs}

    @staticmethod
    def _iso(value):
        return datetime.datetime.fromtimestamp(value, datetime.timezone.utc).isoformat() if value else None

    def _versions(self, record):
        versions = {}
        for path in self._session_directory(record).glob("submissions/*"):
            if path.is_dir():
                manifest, _ = load_submission(path)
                versions[manifest["version"]] = path
        return versions

    def _capture(self, workspace, record, output):
        validate_workspace(workspace, self.registry)
        return save_submission(output, record["mode"], workspace_entries(workspace, record), record["robot"],team_lineup=record.get('team_lineup'))

    def _squad(self, candidate, directory):
        manifest, entries = load_submission(candidate)
        if manifest["mode"] in ("team", "distributed", "adaptive"):
            return candidate
        # A single author never receives other entrants' code. Practice teammates are public examples.
        _, baseline = load_submission(ROOT / "examples/official_squad")
        files = {str(slot): baseline[str(slot)] for slot in SLOT_IDS}
        files[str(manifest["robot"])] = entries[str(manifest["robot"])]
        save_submission(directory, "squad", files)
        return directory

    def test(self, session_id, authorization, options):
        workspace, record = self.authenticate(session_id, authorization)
        validate_workspace(workspace, self.registry)
        if options["opponent"] not in ("self", "baseline") and options["opponent"] not in self._versions(record):
            raise ValueError("Opponent must be baseline, self, or your own submitted version")
        with self.lock:
            if self.stopping.is_set():
                raise ValueError("Practice service is shutting down")
            if session_id in self.active:
                raise ValueError("One practice batch may run at a time; read its results first")
            job_id = secrets.token_hex(8)
            directory = self._session_directory(record) / "jobs" / job_id
            self._capture(workspace, record, directory / "candidate")
            candidate = self._squad(directory / "candidate", directory / "candidate-squad")
            candidate_mode = load_submission(candidate)[0]["mode"]
            opponent = ROOT / "examples/official_adaptive_3" if options["opponent"] == "baseline" and candidate_mode == "adaptive" else ROOT / "examples/official_hold" if options["opponent"] == "baseline" else candidate
            if options["opponent"] not in ("self", "baseline"):
                opponent = self._squad(self._versions(record)[options["opponent"]], directory / "opponent-squad")
            check_training_window(self.authenticate(session_id, authorization)[1])
            job = {"id": job_id, "status": "queued", "options": options, "results": [], "error": None,
                "requested_games": options["games"] * (2 if options["swap_sides"] else 1)}
            write_json(directory / "job.json", job)
            self.active.add(session_id)
            self.pool.submit(self._run, session_id, record["training"]["deadline_at"], directory, candidate, opponent, job)
            return {"job_id": job_id, "requested_games": job["requested_games"]}

    def _run(self, session_id, deadline_at, directory, candidate, opponent, job):
        def expired():
            return time.time() >= deadline_at or self.stopping.is_set()
        def publish():
            with self.lock:
                write_json(directory / "job.json", job)
        try:
            candidate_manifest=load_submission(candidate)[0]
            candidate_mode=candidate_manifest['mode']
            job["status"] = "running"
            publish()
            options = job["options"]
            for seed in range(options["seed"], options["seed"] + options["games"]):
                for swapped in ((False, True) if options["swap_sides"] else (False,)):
                    if expired():
                        job["status"] = "expired" if time.time() >= deadline_at else "interrupted"
                        return
                    red, blue = (opponent, candidate) if swapped else (candidate, opponent)
                    decks = None
                    if load_submission(candidate)[0]["mode"] == "adaptive":
                        # Practice varies the lineup; no final competition roster is
                        # fixed by the participant workspace or task description.
                        import random
                        rng = random.Random(seed)
                        extras = lambda: [ROOT / f"examples/official_adaptive_{rng.choice(SLOT_IDS)}" for _ in range(rng.randrange(4))]
                        candidate_deck, opponent_deck = [candidate] + extras(), [opponent] + extras()
                        decks = {"red":opponent_deck if swapped else candidate_deck,"blue":candidate_deck if swapped else opponent_deck}
                    remaining = deadline_at - time.time()
                    with Battle(red, blue, seed, options["duration"], sandbox=self.sandbox,
                                deadline=time.monotonic() + remaining, stop_event=self.stopping, decks=decks,
                                team_lineup=candidate_manifest.get('team_lineup') if candidate_mode=='team' else None,
                                practice_lineup=candidate_mode=='team') as battle:
                        battle.run()
                        game = len(job["results"])
                        battle.save(directory / f"game-{game}.json")
                        result = battle.result()
                        result.update({"game": game, "seed": seed, "swapped": swapped,
                            "candidate_team": "blue" if swapped else "red", "diagnostics": battle.diagnostics})
                        job["results"].append(result)
                        publish()
                    if expired():
                        job["status"] = "expired" if time.time() >= deadline_at else "interrupted"
                        return
            job["status"] = "finished"
        except Exception as error:
            job["status"] = "expired" if time.time() >= deadline_at else "error"
            job["error"] = "Development deadline reached" if job["status"] == "expired" else str(error)
        finally:
            publish()
            with self.lock:
                self.active.discard(session_id)

    def results(self, session_id, authorization, job_id):
        _, record = self.authenticate(session_id, authorization)
        if not re.fullmatch(r"[a-f0-9]{16}", job_id):
            raise ValueError("Invalid practice job")
        with self.lock:
            path = self._session_directory(record) / "jobs" / job_id / "job.json"
            if not path.is_file():
                raise ValueError("Unknown own practice job")
            job = json.loads(path.read_text(encoding="utf-8"))
            if job["status"] in ("queued", "running") and session_id not in self.active:
                job["status"] = "interrupted"
            return job

    def replay_path(self, session_id, authorization, job_id, game):
        job = self.results(session_id, authorization, job_id)
        if game < 0 or game >= len(job["results"]):
            raise ValueError("Practice game is not available")
        _, record = self.authenticate(session_id, authorization)
        return self._session_directory(record) / "jobs" / job_id / f"game-{game}.json"

    def submit(self, session_id, authorization):
        workspace, _ = self.authenticate(session_id, authorization)
        with locked_registry(self.registry) as records:
            record = records[str(workspace)]
            validate_workspace(workspace, self.registry)
            showcase = workspace_showcase(workspace)
            output = self._session_directory(record) / "submissions" / secrets.token_hex(8)
            manifest = self._capture(workspace, record, output)
            check_training_window(record)
            # Only explicitly submitted versions are made available to the organizer's match catalog.
            destination = self.submission_root / ("entry-" + session_id + "-" + manifest["version"])
            profile = validate_profile({"agent": showcase.get("generated_by") or {"provider": "unknown"}, "created_at": time.time()})
            if not destination.exists():
                _, entries = load_submission(output)
                save_submission(destination, record["mode"], entries, record["robot"],team_lineup=record.get('team_lineup'),
                                showcase=showcase, profile=profile)
            else:
                # Same code, newer presentation: the latest showcase describes the entry.
                write_json(destination / SHOWCASE_FILE, showcase)
                if not (destination / PROFILE_FILE).exists():
                    write_json(destination / PROFILE_FILE, profile)
            check_training_window(record)
            record["training"]["last_submission"] = {"version": manifest["version"],
                "path": str(destination), "submitted_at": time.time()}
            return {"version": manifest["version"], "entry": destination.name,
                "submitted_at_utc": self._iso(record["training"]["last_submission"]["submitted_at"])}

    def shutdown(self):
        self.stopping.set()
        self.pool.shutdown(wait=True, cancel_futures=False)
