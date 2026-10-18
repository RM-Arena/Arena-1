import base64
import json
import struct
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from rmuc_arena.custom_models import inspect_glb
from rmuc_arena.server import create_app, intro_seconds
from rmuc_arena.showcase import detect_provider, load_profile, parse_showcase, validate_profile, validate_showcase
from rmuc_arena.submissions import ROOT, load_submission, scaffold, start_training, submit
from tests.showcase_fixture import SHOWCASE, SHOWCASE_TEXT, write_showcase

CODE = 'def act(obs,state):\n return {obs["controlled_ids"][0]:{}},state\n'


def glb(gltf, binary=b""):
    body = json.dumps(gltf).encode()
    body += b" " * (-len(body) % 4)
    chunks = struct.pack("<II", len(body), 0x4E4F534A) + body
    if binary:
        binary += b"\0" * (-len(binary) % 4)
        chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
    return b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks


class ShowcaseFormatTests(unittest.TestCase):
    def test_legacy_bundle_attribution_is_not_an_author_category(self):
        self.assertEqual(validate_profile({"agent": {"provider": "bundled"}})["agent"], {"provider": "unknown"})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(json.dumps({"rules_profile": "rmuc-2027-v1.0.0-arena-v1"}))
            (root / "profile.json").write_text(json.dumps({"agent": {"provider": "bundled"}}))
            self.assertEqual(load_profile(root, bundled=True)["agent"], {"provider": "anthropic", "model": "Claude Opus 5.5 xhigh"})
            self.assertEqual(load_profile(root, bundled=False)["agent"], {"provider": "unknown"})

    def test_spec_example_and_limits(self):
        example = (ROOT / "docs/STRATEGY_SHOWCASE.md").read_text().split("```json\n")[1].split("```")[0]
        showcase = parse_showcase(example)
        self.assertEqual(showcase["generated_by"], {"provider": "anthropic", "model": "Claude Opus 5.5"})
        self.assertEqual(len(showcase["phases"]), 3)
        for change, message in ((({"style": {**SHOWCASE["style"], "speed": 3}}), "style"),
                                ({"phases": [{"from": 30, "to": 10, "title": "x", "goal": "y"}]}, "phases"),
                                ({"phases": [{"from": 0, "to": 10, "title": "x", "goal": "y", "focus": "dance"}]}, "focus"),
                                ({"units": [{"name": "1", "role": "r", "task": "t", "route": [[40, 3]]}]}, "route"),
                                ({"title": "x" * 41}, "title"), ({"format": "v0"}, "format")):
            with self.assertRaisesRegex(ValueError, message):
                validate_showcase({**SHOWCASE, **change})
        with self.assertRaisesRegex(ValueError, "JSON"):
            parse_showcase("{not json")

    def test_provider_detection_and_profile(self):
        for model, provider in (("Claude Opus 5.5", "anthropic"), ("gpt-5.1-codex", "openai"), ("Gemini 3 Pro", "google"),
                                ("Llama 4", "meta"), ("Grok 4", "spacexai"), ("Kimi K2", "moonshot"), ("GLM-4.6", "zai"),
                                ("MiMo-V2", "xiaomi"), ("DeepSeek-V3.2", "deepseek"), ("Qwen3-Max", "qwen"),
                                ("Hunyuan-T1", "tencent-hy"), ("Doubao-Seed-1.6", "bytedance-seed"), ("my own bot", None)):
            self.assertEqual(detect_provider(model), provider, model)
        profile = validate_profile({"agent": {"model": "kimi-k2"}, "tactic": "siege", "tags": ["rune", "aerial"], "display_name": " 突袭 "})
        self.assertEqual(profile["agent"], {"provider": "moonshot", "model": "kimi-k2"})
        self.assertEqual(profile["display_name"], "突袭")
        with self.assertRaisesRegex(ValueError, "tactic"):
            validate_profile({"tactic": "chaos"})
        with self.assertRaisesRegex(ValueError, "tags"):
            validate_profile({"tags": ["teleport"]})

    def test_intro_length_follows_the_lineup(self):
        self.assertEqual(intro_seconds(12), 43.1)
        self.assertEqual(intro_seconds(2), 19.1)
        self.assertLess(intro_seconds(60), 75)


class WorkspaceShowcaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.registry = self.root / "registry.json"

    def test_final_submission_requires_showcase_but_it_does_not_change_the_version(self):
        workspace = scaffold(self.root / "author", registry=self.registry)
        self.assertIn("showcase.json", (workspace / "AGENT_TASK.md").read_text())
        self.assertEqual((workspace / "SHOWCASE.md").read_text(), (ROOT / "docs/STRATEGY_SHOWCASE.md").read_text())
        start_training(workspace, self.registry)
        with self.assertRaisesRegex(ValueError, "showcase.json"):
            submit(workspace, self.root / "v0", self.registry)
        write_showcase(workspace, generated_by={"provider": "deepseek", "model": "DeepSeek-V3.2"})
        first = submit(workspace, self.root / "v1", self.registry)
        self.assertEqual(json.loads((self.root / "v1/profile.json").read_text())["agent"]["provider"], "deepseek")
        self.assertEqual(json.loads((self.root / "v1/showcase.json").read_text())["title"], SHOWCASE["title"])
        write_showcase(workspace, title="另一种描述")
        self.assertEqual(submit(workspace, self.root / "v2", self.registry)["version"], first["version"])
        (workspace / "showcase.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "format"):
            submit(workspace, self.root / "v3", self.registry)
        load_submission(self.root / "v1")


class GalleryApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = create_app("trusted-local", self.root / "submissions", self.root / "data", test_mode=True, workspace_registry=self.root / "registry.json")
        self.addCleanup(self.app.state.arena.shutdown)
        self.addCleanup(self.app.state.training.shutdown)
        self.client = TestClient(self.app)

    def upload(self, name, robot=3, model="Claude Opus 5.5", **extra):
        return self.client.post("/api/submissions", json={"name": name, "mode": "adaptive", "robot": robot, "entries": {str(robot): CODE},
                                                          "showcase": SHOWCASE_TEXT, "profile": {"agent": {"model": model}, "tactic": "assault", **extra}})

    def wait(self):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if not self.client.get("/api/state").json()["busy"]:
                return
            time.sleep(.05)
        self.fail("match did not finish")

    def test_upload_classify_and_browse_without_code(self):
        missing = self.client.post("/api/submissions", json={"name": "bare", "mode": "adaptive", "robot": 3, "entries": {"3": CODE}})
        self.assertEqual(missing.status_code, 422)
        self.assertEqual(self.upload("claude-legs", display_name="腿式突击").status_code, 200)
        strategies = {s["key"]: s for s in self.client.get("/api/strategies").json()}
        mine = strategies["claude-legs"]
        self.assertEqual((mine["agent"]["provider"], mine["display_name"], mine["profile"]["tactic"], mine["bundled"]), ("anthropic", "腿式突击", "assault", False))
        self.assertEqual(mine["showcase"]["title"], SHOWCASE["title"])
        self.assertTrue(strategies["siege_team"]["bundled"])
        self.assertEqual(strategies["siege_team"]["agent"]["provider"], "anthropic")
        detail = self.client.get("/api/strategies/claude-legs").json()
        self.assertEqual(detail["showcase"]["phases"][0]["title"], "全场")
        self.assertEqual([f["name"] for f in detail["files"]], ["strategy.py"])
        self.assertNotIn("act(", json.dumps(detail))
        changed = self.client.post("/api/strategies/claude-legs/profile", json={"agent": {"provider": "qwen", "model": "Qwen3-Max"}, "tactic": "guard", "tags": ["rescue"]}).json()
        self.assertEqual((changed["agent"]["provider"], changed["profile"]["tactic"]), ("qwen", "guard"))
        self.assertEqual(self.client.get("/api/robot-catalog").json()["claude-legs"]["agent"]["model"], "Qwen3-Max")
        self.assertEqual(self.client.post("/api/strategies/siege_team/profile", json={"agent": {"provider": "openai"}}).status_code, 403)
        self.assertEqual(self.client.get("/api/strategies/nope").status_code, 404)

    def test_robot_appearances_and_agents_reach_the_match_metadata(self):
        self.assertEqual(self.upload("kimi-hero", robot=1, model="Kimi K2").status_code, 200)
        model = (ROOT / "frontend/public/assets/robot-301-spec2026v4.glb").read_bytes()
        bad = self.client.post("/api/custom-models", json={"name": "x", "base_model": 301, "glb_base64": base64.b64encode(b"not a model").decode()})
        self.assertEqual(bad.status_code, 400)
        external = glb({"asset": {"version": "2.0"}, "buffers": [{"uri": "mesh.bin", "byteLength": 4}], "meshes": [{"primitives": []}]})
        with self.assertRaisesRegex(ValueError, "Embed"):
            inspect_glb(external)
        created = self.client.post("/api/custom-models", json={"name": "赤焰", "base_model": 301, "forward": "-z", "glb_base64": base64.b64encode(model).decode()})
        self.assertEqual(created.status_code, 200, created.text)
        skin = created.json()
        self.assertEqual(skin["asset"], f"/api/custom-models/{skin['id']}.glb?fit=0.56,0.55,0.56&fwd=-z")
        self.assertEqual(self.client.get(f"/api/custom-models/{skin['id']}.glb").content, model)
        args = {"mode": "deck", "red_deck": ["kimi-hero", "claude_opus55_xhigh_adaptive_301"], "blue_deck": ["claude_opus55_xhigh_adaptive_301"], "duration": 1}
        wrong = self.client.post("/api/start", json={**args, "red_skins": {"1": skin["id"]}})
        self.assertEqual(wrong.status_code, 409)
        absent = self.client.post("/api/start", json={**args, "blue_skins": {"302": skin["id"]}})
        self.assertEqual(absent.status_code, 409)
        started = self.client.post("/api/start", json={**args, "red_skins": {"301": skin["id"]}})
        self.assertEqual(started.status_code, 200, started.text)
        self.wait()
        record = self.client.get("/api/matches/" + started.json()["match_id"]).json()
        metadata = record["metadata"]
        self.assertEqual(metadata["skins"]["red"]["301"]["asset"], skin["asset"])
        self.assertEqual(metadata["skins"]["blue"], {})
        self.assertEqual(metadata["agents"]["red"]["1"], {"provider": "moonshot", "model": "Kimi K2", "strategy": "kimi-hero"})
        self.assertEqual(metadata["agents"]["red"]["2"]["model"], "Claude Opus 5.5 xhigh")
        self.assertEqual(metadata["teams"]["red"]["cards"][0]["agent"]["provider"], "moonshot")
        self.assertEqual(self.client.delete(f"/api/custom-models/{skin['id']}").status_code, 200)
        self.assertEqual(self.client.get("/api/custom-models").json(), [])

    def test_self_check_lasts_as_long_as_the_lineup_intro(self):
        arena = self.app.state.arena
        arena.prematch_stages = (("self_check", None), ("countdown", 30.0))
        response = self.client.post("/api/start", json={"red": "claude_opus55_xhigh_team", "blue": "claude_opus55_xhigh_hold", "duration": 1})
        self.assertEqual(response.status_code, 200, response.text)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = self.client.get("/api/state").json()
            if state["prematch"]:
                break
            time.sleep(.05)
        self.assertEqual(state["prematch"]["duration"], intro_seconds(12))
        self.assertEqual(state["metadata"]["agents"]["red"]["1"]["model"], "Claude Opus 5.5 xhigh")
        self.client.post("/api/control", json={"command": "stop"})
        self.wait()


if __name__ == "__main__":
    unittest.main()
