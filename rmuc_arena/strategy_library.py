"""Download verified, immutable strategy snapshots without modifying the app bundle."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import threading
import time
import zipfile

import httpx

from . import __version__, seasons
from .showcase import parse_showcase, validate_profile
from .submissions import load_submission, write_json
from .worker import SOURCE_LIMIT

REPOSITORY = "https://github.com/RM-Arena/Arena-Strategies"
CATALOG_URL = "https://raw.githubusercontent.com/RM-Arena/Arena-Strategies/main/catalog.json"
FORMAT = "arena-strategy-library-v1"
CHECK_INTERVAL = 15 * 60
MAX_DOWNLOAD = 32 * 1024 * 1024
MAX_UNPACKED = 128 * 1024 * 1024
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("Invalid minimum client version")
    return tuple(map(int, value.split(".")))


def validate_snapshot(directory):
    """Validate data and compile syntax only; never import downloaded strategies."""
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("Invalid strategy snapshot")
    paths = sorted(directory.iterdir())
    if not paths or len(paths) > 2000:
        raise ValueError("Invalid strategy count")
    for path in paths:
        if not KEY.fullmatch(path.name) or path.is_symlink() or not path.is_dir():
            raise ValueError("Invalid strategy directory")
        manifest_path = path / "manifest.json"
        if manifest_path.is_symlink() or manifest_path.stat().st_size > SOURCE_LIMIT:
            raise ValueError("Invalid strategy manifest")
        manifest = json.loads(manifest_path.read_bytes())
        if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), dict) or not isinstance(manifest.get("hashes"), dict):
            raise ValueError("Invalid strategy manifest")
        if manifest.get("api_version") != 3 or manifest.get("rules_profile") not in seasons.profiles():
            raise ValueError("Strategy requires a newer Arena-1 client")
        manifest, entries = load_submission(path)
        allowed = {"manifest.json", "profile.json", "showcase.json", *manifest["entries"].values()}
        for file in path.iterdir():
            if file.name not in allowed or file.is_symlink() or not file.is_file() or file.stat().st_size > SOURCE_LIMIT:
                raise ValueError("Unexpected strategy file")
        for file in set(entries.values()):
            compile(file.read_bytes(), file.name, "exec")
        if (path / "showcase.json").exists():
            parse_showcase((path / "showcase.json").read_bytes())
        if (path / "profile.json").exists():
            validate_profile(json.loads((path / "profile.json").read_bytes()))
    return len(paths)


def unpack_snapshot(data, destination):
    """Reject traversal, symlinks, duplicate paths and oversized archives before writing."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = archive.infolist()
        if not files or len(files) > 16000 or sum(f.file_size for f in files) > MAX_UNPACKED:
            raise ValueError("Strategy archive is too large")
        seen = set()
        for file in files:
            parts = PurePosixPath(file.filename).parts
            mode = file.external_attr >> 16
            if (len(parts) != 3 or parts[0] != "strategies" or not KEY.fullmatch(parts[1])
                    or not re.fullmatch(r"[A-Za-z0-9_-]+\.(json|py)", parts[2])
                    or file.filename != "/".join(parts) or file.filename.casefold() in seen
                    or file.file_size > SOURCE_LIMIT or file.is_dir()
                    or stat.S_ISLNK(mode) or file.flag_bits & 1):
                raise ValueError("Unsafe strategy archive path")
            seen.add(file.filename.casefold())
        for file in files:
            target = destination / file.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(file))
    return validate_snapshot(destination / "strategies")


class StrategyLibrary:
    def __init__(self, directory, enabled=True, *, client=None):
        self.directory = Path(directory)
        self.enabled = enabled and os.environ.get("RMUC_STRATEGY_UPDATES", "1") != "0"
        self.client = client
        self.lock = threading.RLock()
        self.sync_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.active = None
        self.checked_at = None
        self.error = None
        self.checking = False
        try:
            active = json.loads((self.directory / "active.json").read_bytes())
            if not DIGEST.fullmatch(active["version"]):
                raise ValueError("Invalid cached version")
            path = self.directory / "versions" / active["version"] / "strategies"
            # Recheck persisted files before using them after a restart.
            active["count"] = validate_snapshot(path)
            self.active = active
        except (OSError, ValueError, TypeError, KeyError, SyntaxError):
            pass

    def status(self):
        with self.lock:
            return {"enabled": self.enabled, "checking": self.checking, "repository": REPOSITORY,
                    "version": self.active["version"] if self.active else None,
                    "count": self.active["count"] if self.active else 0,
                    "updated_at": self.active.get("updated_at") if self.active else None,
                    "checked_at": self.checked_at, "error": self.error}

    def paths(self):
        with self.lock:
            active = self.active
        if not active:
            return []
        return sorted((self.directory / "versions" / active["version"] / "strategies").glob("*/manifest.json"))

    def _download(self, client, url, limit):
        result = bytearray()
        deadline = time.monotonic() + 60
        with client.stream("GET", url) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(chunk_size=65536):
                if self.stop_event.is_set():
                    raise ValueError("Strategy update stopped")
                result.extend(chunk)
                if len(result) > limit or time.monotonic() > deadline:
                    raise ValueError("Strategy download exceeds size or time limit")
        return bytes(result)

    def sync(self):
        if not self.enabled or not self.sync_lock.acquire(blocking=False):
            return self.status()
        with self.lock:
            self.checking = True
        try:
            if self.client is not None:
                self._sync(self.client)
            else:
                with httpx.Client(timeout=15, follow_redirects=False, headers={"User-Agent": f"Arena-1/{__version__}", "Cache-Control": "no-cache"}) as client:
                    self._sync(client)
            with self.lock:
                self.error = None
        except Exception as exc:
            # Updates are optional. Never take the local arena down on network or validation errors.
            with self.lock:
                self.error = str(exc)
        finally:
            with self.lock:
                self.checked_at, self.checking = time.time(), False
            self.sync_lock.release()
        return self.status()

    def _sync(self, client):
        catalog = json.loads(self._download(client, CATALOG_URL, 65536))
        if not isinstance(catalog, dict) or catalog.get("format") != FORMAT:
            raise ValueError("Unsupported strategy catalog")
        version = catalog.get("sha256")
        if not isinstance(version, str) or not DIGEST.fullmatch(version):
            raise ValueError("Invalid archive checksum")
        if version_tuple(catalog.get("min_client_version")) > version_tuple(__version__):
            raise ValueError("策略更新需要新版 Arena-1；继续使用本地策略。")
        if type(catalog.get("bytes")) is not int or not 0 < catalog["bytes"] <= MAX_DOWNLOAD:
            raise ValueError("Invalid archive size")
        if type(catalog.get("count")) is not int or not 0 < catalog["count"] <= 2000:
            raise ValueError("Invalid strategy count")
        if catalog.get("archive") != f"bundles/{version}.zip":
            raise ValueError("Invalid archive location")
        with self.lock:
            if self.active and self.active["version"] == version:
                return
        data = self._download(client, CATALOG_URL.rsplit("/", 1)[0] + "/" + catalog["archive"], catalog["bytes"])
        if len(data) != catalog["bytes"] or hashlib.sha256(data).hexdigest() != version:
            raise ValueError("Strategy archive checksum mismatch")
        self.directory.mkdir(parents=True, exist_ok=True)
        versions = self.directory / "versions"
        versions.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="download-", dir=self.directory) as temporary:
            stage = Path(temporary)
            count = unpack_snapshot(data, stage)
            if count != catalog.get("count"):
                raise ValueError("Strategy count mismatch")
            target = versions / version
            if target.exists():
                try:
                    validate_snapshot(target / "strategies")
                except (OSError, ValueError, TypeError, KeyError, SyntaxError):
                    # A corrupt on-disk cache must not prevent a clean redownload.
                    os.replace(target, self.directory / ("corrupt-" + version + "-" + str(time.time_ns())))
            if not target.exists():
                os.replace(stage, target)
            active = {"version": version, "count": count, "updated_at": time.time()}
            # Keep older snapshots: running matches retain paths into their original version.
            write_json(self.directory / "active.json", active)
            with self.lock:
                self.active = active

    def start(self):
        with self.lock:
            if not self.enabled or self.thread is not None:
                return
            def run():
                while not self.stop_event.is_set():
                    self.wake.clear()
                    self.sync()
                    self.wake.wait(CHECK_INTERVAL)
            self.thread = threading.Thread(target=run, name="strategy-library", daemon=True)
            self.thread.start()

    def request_sync(self):
        self.start()
        self.wake.set()
        return self.status()

    def shutdown(self):
        self.stop_event.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=2)
