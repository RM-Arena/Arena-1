"""The team and single-robot competitions ship separate guides; each workspace gets only its own."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient
from rmuc_arena.server import create_app
from rmuc_arena.submissions import ROOT, SLOT_IDS, guide_path, scaffold


class AgentGuideTests(unittest.TestCase):
    def test_generated_guides_match_their_sources(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/build_agent_guides.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_each_competition_sees_only_its_own_rules(self):
        for lang, team_marker, robot_marker in (("zh", "全队赛", "单机器人赛"), ("en", "Team Competition", "Single-Robot Competition")):
            team = guide_path("team", lang=lang).read_text(encoding="utf-8")
            self.assertIn(team_marker, team)
            self.assertNotIn(robot_marker, team)
            for slot in SLOT_IDS:
                guide = guide_path("robot", slot, lang).read_text(encoding="utf-8")
                self.assertIn(robot_marker, guide)
                self.assertNotIn(team_marker, guide)
                self.assertIn(f'controlled_ids == ["{slot}"]', guide)
        with self.assertRaisesRegex(ValueError, "slots"):
            guide_path("robot", 5)

    def test_workspace_receives_its_guide_in_both_languages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            team = scaffold(root / "team", registry=root / "registry.json")
            robot = scaffold(root / "robot", "robot", 4, root / "registry.json")
            from scripts.build_agent_guides import render
            from rmuc_arena.models import DEFAULT_TEAM_LINEUP
            self.assertEqual((team / "AGENT_GUIDE.md").read_text(), render("zh",team_lineup=DEFAULT_TEAM_LINEUP))
            self.assertNotIn("H42",guide_path("team").read_text())
            self.assertEqual((robot / "AGENT_GUIDE.md").read_bytes(), guide_path("robot", 4).read_bytes())
            self.assertEqual((robot / "AGENT_GUIDE.en.md").read_bytes(), guide_path("robot", 4, "en").read_bytes())
            self.assertIn("只控制己方 4 号", (robot / "AGENT_TASK.md").read_text(encoding="utf-8"))

    def test_api_serves_the_requested_guide(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = create_app("trusted-local", root / "submissions", root / "data", test_mode=True,
                             workspace_registry=root / "registry.json")
            try:
                client = TestClient(app)
                self.assertEqual(client.get("/api/agent-guide").text, guide_path("team").read_text(encoding="utf-8"))
                response = client.get("/api/agent-guide", params={"mode": "robot", "robot": 6, "lang": "en"})
                self.assertEqual(response.text, guide_path("robot", 6, "en").read_text(encoding="utf-8"))
                self.assertEqual(client.get("/api/agent-guide", params={"mode": "robot", "robot": 5}).status_code, 404)
            finally:
                app.state.arena.shutdown()
                app.state.training.shutdown()


if __name__ == "__main__":
    unittest.main()
