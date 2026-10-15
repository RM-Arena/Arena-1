import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import weakref
from unittest.mock import patch

from fastapi.testclient import TestClient
from rmuc_arena import __version__
from rmuc_arena.paths import ROOT, data_path
from rmuc_arena.server import create_app
from rmuc_arena.engine import Match
from rmuc_arena.desktop import reconnect_workspaces
from rmuc_arena.submissions import scaffold, start_training, validate_workspace


class PlatformSupportTests(unittest.TestCase):
    def test_generated_submissions_keep_lf_when_text_writes_default_to_crlf(self):
        from rmuc_arena.submissions import write_json
        from scripts import build_examples_2027, build_robot_presets

        original_open = Path.open
        def windows_text_open(path, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
            if "b" not in mode and any(flag in mode for flag in "wax") and newline is None:
                newline = "\r\n"
            return original_open(path, mode, buffering, encoding, errors, newline)

        with tempfile.TemporaryDirectory() as temporary, patch.object(Path, "open", windows_text_open):
            root = Path(temporary)
            probe = root / "probe.txt"
            probe.write_text("line\n", encoding="utf-8")
            self.assertEqual(probe.read_bytes(), b"line\r\n")
            output = root / "record.json"
            write_json(output, {"名称": "策略"})
            self.assertNotIn(b"\r\n", output.read_bytes())
            self.assertEqual(json.loads(output.read_bytes()), {"名称": "策略"})
            for path, data in build_examples_2027.outputs().items():
                with self.subTest(path=str(path.relative_to(ROOT))):
                    self.assertEqual(data, path.read_bytes())
            build_robot_presets.materialize(root / "preset", build_examples_2027.POLICY.read_text(encoding="utf-8"), 2711, False, "2027")
            for name in ("strategy.py", "manifest.json"):
                self.assertEqual((root / "preset" / name).read_bytes(), (ROOT / "examples/official_2027_adaptive_2711" / name).read_bytes())

    def test_restarting_desktop_updates_practice_url_without_resetting_clock_or_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            registry = directory / ".arena_host/workspaces.json"
            workspace = scaffold(directory / "workspaces/returning-author", "team", registry=registry,
                                 training_url="http://127.0.0.1:12345")
            start_training(workspace, registry)
            before = json.loads((workspace / "agent.json").read_text(encoding="utf-8"))
            code = (workspace / "strategy.py").read_bytes()
            reconnect_workspaces(directory, "http://127.0.0.1:23456")
            after = json.loads((workspace / "agent.json").read_text(encoding="utf-8"))
            self.assertEqual(after["training"], {**before["training"], "url": "http://127.0.0.1:23456"})
            self.assertEqual((workspace / "strategy.py").read_bytes(), code)
            validate_workspace(workspace, registry)

    def test_temporary_match_does_not_leak_its_reader_or_engine(self):
        match = Match(duration=1)
        process, reader, reference = match.process, match._reader, weakref.ref(match)
        del match
        self.assertIsNone(reference())
        self.assertIsNotNone(process.poll())
        self.assertFalse(reader.is_alive())

    def test_registry_lock_serializes_independent_processes_and_unicode(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve() / "学习策略.json"
            code = '''import sys
from pathlib import Path
from rmuc_arena.submissions import locked_registry
for _ in range(15):
 with locked_registry(Path(sys.argv[1])) as records:
  records['次数'] = records.get('次数', 0) + 1
'''
            processes = [subprocess.Popen([sys.executable, "-B", "-X", "utf8", "-c", code, str(target)],
                                          cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(4)]
            for process in processes:
                _, error = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, error.decode("utf-8"))
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"次数": 60})

    def test_desktop_data_root_and_training_workspace_are_writable_outside_resources(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"RMUC_USER_DATA": temporary}):
            self.assertEqual(data_path("workspaces"), Path(temporary).resolve() / "workspaces")
            with TestClient(create_app(sandbox="trusted-local")) as client:
                service = client.app.state.arena
                self.assertEqual(service.store.directory, Path(temporary).resolve() / ".arena_data")
                self.assertEqual(service.submission_root, Path(temporary).resolve() / "submissions")
                response = client.post("/api/training-workspaces", json={"name":"unicode-learning", "mode":"team", "minutes":1})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(Path(response.json()["task_file"]).is_relative_to(Path(temporary).resolve()))
                self.assertTrue(service.workspace_registry.exists())
                self.assertEqual(client.get("/api/desktop/health").json()["engine"], "rust")
                self.assertEqual(client.get("/api/health").json()["version"], __version__)
                self.assertEqual(client.get("/openapi.json").json()["info"]["version"], __version__)
                self.assertEqual(json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"], __version__)


if __name__ == "__main__":
    unittest.main()
