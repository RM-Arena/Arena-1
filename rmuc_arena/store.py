"""SQLite match journal, replay catalog, and version-aware Elo standings."""
from .strategy_names import normalize_metadata, display_name, canonical_key
import datetime
import json
from pathlib import Path
import sqlite3
import threading
from contextlib import contextmanager


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path, self.lock = self.directory / "arena.sqlite3", threading.RLock()
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS matches (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL,
                metadata TEXT NOT NULL, result TEXT, replay_path TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS standings (
                identity TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
                mode TEXT NOT NULL, rating REAL NOT NULL DEFAULT 1000,
                games INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0, draws INTEGER NOT NULL DEFAULT 0);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(matches)")}
            for column in ("video_path", "video_status", "video_error"):
                if column not in columns:
                    db.execute(f"ALTER TABLE matches ADD COLUMN {column} TEXT")
            db.execute("UPDATE matches SET video_status='failed',video_error='录像保存中断，可重新录制回放' WHERE video_status IN ('pending','processing')")
            db.execute("UPDATE matches SET status='interrupted', error='Backend restarted during the match' WHERE status IN ('initializing','running')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, match_id, metadata):
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO matches(id,created_at,status,metadata) VALUES(?,?,?,?)",
                       (match_id, datetime.datetime.now(datetime.timezone.utc).isoformat(), "initializing", json.dumps(metadata)))
            if metadata.get("save_mp4"):
                db.execute("UPDATE matches SET video_status='pending' WHERE id=?", (match_id,))

    def running(self, match_id, metadata):
        with self.lock, self.connect() as db:
            db.execute("UPDATE matches SET status='running',metadata=? WHERE id=?", (json.dumps(metadata), match_id))

    def finish(self, match_id, result, replay_path=None, error=None):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
            if row is None or row["status"] not in ("initializing", "running"):
                return
            status = "error" if error else "stopped" if result.get("reason") == "stopped" else "finished"
            db.execute("UPDATE matches SET status=?,result=?,replay_path=?,error=? WHERE id=?",
                       (status, json.dumps(result) if not error else None, str(replay_path) if replay_path else None, error, match_id))
            if status != "finished" or result.get("policy_errors", 0) > 0:
                return
            teams = json.loads(row["metadata"])["teams"]
            if json.loads(row["metadata"]).get("test_match"):
                return
            identities = {team: f"{data['name']}:{data['version']}" for team, data in teams.items()}
            if identities["red"] == identities["blue"]:
                return
            for team, identity in identities.items():
                entry = teams[team]
                db.execute("INSERT OR IGNORE INTO standings(identity,name,version,mode) VALUES(?,?,?,?)",
                           (identity, entry["name"], entry["version"], entry["mode"]))
            ratings = {t: db.execute("SELECT rating FROM standings WHERE identity=?", (i,)).fetchone()[0] for t, i in identities.items()}
            expected = 1 / (1 + 10 ** ((ratings["blue"] - ratings["red"]) / 400))
            actual = 0.5 if result["winner"] is None else 1 if result["winner"] == "red" else 0
            delta = 24 * (actual - expected)
            for team, identity in identities.items():
                won = result["winner"] == team
                draw = result["winner"] is None
                db.execute("UPDATE standings SET rating=rating+?,games=games+1,wins=wins+?,losses=losses+?,draws=draws+? WHERE identity=?",
                           (delta if team == "red" else -delta, int(won), int(not won and not draw), int(draw), identity))

    @staticmethod
    def decode(row):
        value = dict(row)
        value["metadata"] = normalize_metadata(json.loads(value["metadata"]))
        value["result"] = json.loads(value["result"]) if value["result"] else None
        # Host paths are never exposed through the public API.
        replay = value.pop("replay_path")
        value["has_replay"] = bool(replay)
        value["replay_bytes"] = Path(replay).stat().st_size if replay and Path(replay).is_file() else 0
        video = value.pop("video_path", None)
        value["has_video"] = bool(video and Path(video).is_file())
        value["video_bytes"] = Path(video).stat().st_size if value["has_video"] else 0
        return value

    def video_path(self, match_id):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT video_path FROM matches WHERE id=?", (match_id,)).fetchone()
            return Path(row[0]) if row and row[0] else None

    def video_status(self, match_id, status, path=None, error=None):
        with self.lock, self.connect() as db:
            return db.execute("UPDATE matches SET video_status=?,video_path=COALESCE(?,video_path),video_error=? WHERE id=?",
                              (status, str(path) if path else None, error, match_id)).rowcount > 0

    def matches(self, limit=50):
        with self.lock, self.connect() as db:
            return [self.decode(row) for row in db.execute("SELECT * FROM matches ORDER BY created_at DESC LIMIT ?", (limit,))]

    def match(self, match_id):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
            return self.decode(row) if row else None

    def replay_path(self, match_id):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT replay_path FROM matches WHERE id=?", (match_id,)).fetchone()
            return Path(row[0]) if row and row[0] else None

    def delete(self, match_id):
        """Remove a match record and its replay file; Elo standings keep the games already rated."""
        with self.lock:
            with self.connect() as db:
                row = db.execute("SELECT status,replay_path,video_path,video_status FROM matches WHERE id=?", (match_id,)).fetchone()
                if row is None:
                    return False
                if row["status"] in ("initializing", "running"):
                    raise ValueError("A running match cannot be deleted")
                if row["video_status"] == "processing":
                    raise ValueError("Wait for the MP4 export to finish before deleting it")
                db.execute("DELETE FROM matches WHERE id=?", (match_id,))
            replay = Path(row["replay_path"]) if row["replay_path"] else None
            # Only files inside this journal's own replay folder are ever removed.
            if replay and replay.resolve().parent == (self.directory / "replays").resolve():
                replay.unlink(missing_ok=True)
            video = Path(row["video_path"]) if row["video_path"] else None
            if video and video.resolve().parent == (self.directory / "videos").resolve():
                video.unlink(missing_ok=True)
            return True

    def leaderboard(self):
        with self.lock, self.connect() as db:
            return [{**dict(row), "name": display_name(canonical_key(row["name"]))} for row in db.execute("SELECT * FROM standings ORDER BY rating DESC, wins DESC, identity")]
