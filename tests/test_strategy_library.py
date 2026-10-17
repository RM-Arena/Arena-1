import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

import httpx
from fastapi.testclient import TestClient

from rmuc_arena.server import create_app
from rmuc_arena.strategy_library import CATALOG_URL, StrategyLibrary, unpack_snapshot
from rmuc_arena.submissions import load_submission, save_submission, write_json
from scripts.strategies.publish import publish
from tests.showcase_fixture import SHOWCASE

CODE = "def act(obs, state):\n return {}, state\n"


class StrategyLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.feed = self.root / "feed"
        self.cache = self.root / "cache"
        self.requests = []
        self.offline = False
        self.client = httpx.Client(transport=httpx.MockTransport(self.respond))
        self.addCleanup(self.client.close)
        self.library = StrategyLibrary(self.cache, client=self.client)
        self.addCleanup(self.library.shutdown)
        self.write_strategy("online-team")
        self.catalog = publish(self.source, self.feed)

    def write_strategy(self, name, code=CODE):
        file = self.root / "entry.py"
        file.write_text(code, encoding="utf-8")
        return save_submission(self.source / name, "team", {"team": file}, season="2027",
                               showcase=SHOWCASE, profile={"agent": {"provider": "human"}})

    def respond(self, request):
        self.requests.append(str(request.url))
        if self.offline:
            raise httpx.ConnectError("offline", request=request)
        if str(request.url) == CATALOG_URL:
            return httpx.Response(200, content=(self.feed / "catalog.json").read_bytes())
        expected = CATALOG_URL.rsplit("/", 1)[0] + "/" + self.catalog["archive"]
        if str(request.url) != expected:
            return httpx.Response(404)
        return httpx.Response(200, content=(self.feed / self.catalog["archive"]).read_bytes())

    def repack(self, modify):
        """Build intentionally invalid archives independently of the publishing checks."""
        with zipfile.ZipFile(self.feed / self.catalog["archive"]) as archive:
            files = [(file, archive.read(file)) for file in archive.infolist()]
        files = modify(files)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, data in files:
                archive.writestr(name, data)
        data = stream.getvalue()
        digest = hashlib.sha256(data).hexdigest()
        self.catalog.update(sha256=digest, archive=f"bundles/{digest}.zip", bytes=len(data))
        (self.feed / self.catalog["archive"]).write_bytes(data)
        write_json(self.feed / "catalog.json", self.catalog)

    def test_sync_validates_without_executing_and_restores_offline_cache(self):
        self.write_strategy("never-import", "raise RuntimeError('must not execute while downloading')\n" + CODE)
        self.catalog = publish(self.source, self.feed)
        status = self.library.sync()
        self.assertIsNone(status["error"])
        self.assertEqual(status["count"], 2)
        self.assertEqual(status["version"], self.catalog["sha256"])
        self.assertEqual(len(self.library.paths()), 2)
        self.offline = True
        reopened = StrategyLibrary(self.cache, client=self.client)
        self.assertEqual(reopened.status()["version"], status["version"])
        self.assertEqual(reopened.sync()["error"], "offline")
        self.assertEqual(len(reopened.paths()), 2)

    def test_unchanged_catalog_does_not_redownload_and_snapshots_remain_immutable(self):
        first = self.library.sync()
        old = self.library.paths()[0].parent
        self.requests.clear()
        self.library.sync()
        self.assertEqual(self.requests, [CATALOG_URL])
        self.write_strategy("second-team")
        self.catalog = publish(self.source, self.feed)
        second = self.library.sync()
        self.assertNotEqual(first["version"], second["version"])
        self.assertEqual(second["count"], 2)
        self.assertEqual((old / "strategy.py").read_text(), CODE)
        self.assertEqual(load_submission(old)[0]["mode"], "team")

    def test_checksum_failure_and_incompatible_version_leave_active_pointer_untouched(self):
        self.library.sync()
        pointer = (self.cache / "active.json").read_bytes()
        self.catalog["sha256"] = "0" * 64
        self.catalog["archive"] = "bundles/" + "0" * 64 + ".zip"
        original = next((self.feed / "bundles").glob("*.zip")).read_bytes()
        (self.feed / self.catalog["archive"]).write_bytes(original)
        write_json(self.feed / "catalog.json", self.catalog)
        self.assertIn("checksum", self.library.sync()["error"])
        self.assertEqual((self.cache / "active.json").read_bytes(), pointer)
        self.catalog["min_client_version"] = "999.0.0"
        write_json(self.feed / "catalog.json", self.catalog)
        self.requests.clear()
        self.assertIn("新版", self.library.sync()["error"])
        self.assertEqual(self.requests, [CATALOG_URL])
        self.assertEqual((self.cache / "active.json").read_bytes(), pointer)

    def test_tampered_sources_are_rejected_even_with_a_valid_archive_checksum(self):
        self.library.sync()
        version = self.library.status()["version"]
        self.repack(lambda files: [(name, data + b"\n# changed" if name.filename.endswith(".py") else data) for name, data in files])
        self.assertIn("changed", self.library.sync()["error"])
        self.assertEqual(self.library.status()["version"], version)

    def test_unknown_rules_and_malformed_sidecars_are_not_installed(self):
        def unknown_rules(files):
            result = []
            for name, data in files:
                if name.filename.endswith("manifest.json"):
                    manifest = json.loads(data)
                    manifest["rules_profile"] = "rmuc-2099"
                    manifest["version"] = hashlib.sha256(json.dumps({k: v for k, v in manifest.items() if k != "version"}, sort_keys=True).encode()).hexdigest()[:16]
                    data = json.dumps(manifest).encode()
                result.append((name, data))
            return result
        self.repack(unknown_rules)
        self.assertIn("newer", self.library.sync()["error"])
        self.assertFalse((self.cache / "active.json").exists())
        self.catalog = publish(self.source, self.feed)
        self.repack(lambda files: [(name, b"{}" if name.filename.endswith("showcase.json") else data) for name, data in files])
        self.assertIn("showcase", self.library.sync()["error"])
        self.assertEqual(self.library.paths(), [])

    def test_archive_rejects_traversal_symlinks_duplicate_and_unexpected_files(self):
        malicious = ["../escape.py", "strategies/../../escape.py", "/strategies/a/strategy.py",
                     "strategies/a/../strategy.py", "strategies/a\\b/strategy.py", "strategies/a/evil.exe"]
        symlink = zipfile.ZipInfo("strategies/a/strategy.py")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        for name in [*malicious, symlink]:
            with self.subTest(name=name):
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, "w") as archive:
                    archive.writestr(name, b"outside")
                with self.assertRaises(ValueError):
                    unpack_snapshot(stream.getvalue(), self.root / "unpacked")
        self.repack(lambda files: files + [("strategies/online-team/extra.py", b"x=1")])
        self.assertIn("Unexpected", self.library.sync()["error"])
        self.catalog = publish(self.source, self.feed)
        with self.assertWarns(UserWarning):
            self.repack(lambda files: files + [files[0]])
        self.assertIn("Unsafe", self.library.sync()["error"])
        self.assertFalse((self.root / "escape.py").exists())

    def test_catalog_cannot_redirect_downloads_and_enforces_size_and_count(self):
        original = dict(self.catalog)
        for change in ({"archive": "https://other.example/strategy.zip"}, {"bytes": 100 * 1024 * 1024},
                       {"count": 999}, {"format": "other"}):
            with self.subTest(change=change):
                self.catalog = original | change
                write_json(self.feed / "catalog.json", self.catalog)
                self.assertIsNotNone(self.library.sync()["error"])
                self.assertIsNone(self.library.status()["version"])

    def test_publisher_is_deterministic_and_rejects_stale_manifest(self):
        self.assertEqual(publish(self.source, self.feed), self.catalog)
        (self.source / "online-team/strategy.py").write_text(CODE + "# altered")
        with self.assertRaisesRegex(ValueError, "checksum"):
            publish(self.source, self.feed)

    def test_corrupted_cache_falls_back_and_can_be_repaired(self):
        self.library.sync()
        path = self.library.paths()[0].parent
        (path / "strategy.py").write_text("# corrupted")
        reopened = StrategyLibrary(self.cache, client=self.client)
        self.assertEqual(reopened.paths(), [])
        self.assertIsNone(reopened.sync()["error"])
        self.assertEqual((reopened.paths()[0].parent / "strategy.py").read_text(), CODE)

    def test_tracked_export_excludes_untracked_strategies(self):
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        subprocess.run(["git", "-C", str(self.source), "add", "online-team"], check=True)
        self.write_strategy("unpublished")
        catalog = publish(self.source, self.feed, tracked=True)
        self.assertEqual(catalog["count"], 1)

    def test_disabled_updates_do_not_make_requests(self):
        with patch.dict("os.environ", {"RMUC_STRATEGY_UPDATES": "0"}):
            disabled = StrategyLibrary(self.cache, client=self.client)
        disabled.request_sync()
        disabled.sync()
        self.assertFalse(disabled.status()["enabled"])
        self.assertEqual(self.requests, [])

    def test_lifespan_downloads_on_startup_and_manual_check_wakes_worker(self):
        app = create_app("trusted-local", self.root / "submissions", self.root / "data", test_mode=True)
        app.state.arena.strategy_library = self.library
        app.state.training.strategy_library = self.library
        def wait_for_count(count):
            deadline = time.monotonic() + 5
            while self.library.status()["count"] != count and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(self.library.status()["count"], count, self.library.status())
        with TestClient(app) as client:
            wait_for_count(1)
            self.assertIn("online-team", client.get("/api/catalog").json())
            self.write_strategy("auto-updated")
            self.catalog = publish(self.source, self.feed)
            self.assertEqual(client.post("/api/strategy-library/sync", json={}).status_code, 200)
            wait_for_count(2)
            self.assertIn("auto-updated", client.get("/api/catalog").json())
        self.assertFalse(self.library.thread.is_alive())

    def test_catalog_overlay_api_refresh_and_local_uploads(self):
        self.write_strategy("official_2027_team", CODE + "# newer online version\n")
        self.catalog = publish(self.source, self.feed)
        app = create_app("trusted-local", self.root / "submissions", self.root / "data", test_mode=True)
        service = app.state.arena
        self.addCleanup(service.shutdown)
        service.strategy_library = self.library
        app.state.training.strategy_library = self.library
        file = self.root / "local.py"
        file.write_text(CODE)
        save_submission(service.submission_root / "official_2027_team", "team", {"team": file}, season="2027")
        client = TestClient(app)
        before = service.state()["revision"]
        self.library.sync()
        catalog = client.get("/api/catalog").json()
        self.assertEqual(catalog["official_2027_team"]["source"], "remote")
        self.assertEqual(app.state.training.example("2027", "team"), service.catalog()["official_2027_team"]["path"])
        self.assertEqual(app.state.training.example("2027", "hold").name, "official_2027_hold")
        self.assertEqual(catalog["submission-official_2027_team"]["source"], "local")
        self.assertIn("online-team", catalog)
        self.assertEqual(service.state()["revision"], before + 1)
        self.assertEqual(service.state()["strategy_version"], self.catalog["sha256"])
        item = client.get("/api/strategies/official_2027_team").json()
        self.assertTrue(item["official"])
        response = client.post("/api/strategies/official_2027_team/profile", json={"agent": {"provider": "human"}})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(client.get("/api/strategy-library").json()["count"], 2)
        with patch.object(self.library, "request_sync", return_value=self.library.status()) as request:
            self.assertEqual(client.post("/api/strategy-library/sync", json={}).status_code, 200)
            request.assert_called_once()
        self.assertEqual(client.post("/api/strategy-library/sync", json={}, headers={"Origin": "https://other.example"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
