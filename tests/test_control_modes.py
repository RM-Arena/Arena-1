"""Authoring, isolated execution and next-round team communication for B/C."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from rmuc_arena.cli import verify_replay
from rmuc_arena.engine import Match
from rmuc_arena.runner import Battle, Policy
from rmuc_arena.server import create_app
from rmuc_arena.submissions import (ROOT, SLOT_IDS, guide_path, load_submission,
    refresh_workspace, save_submission, scaffold, start_training, submit, validate_workspace)
from tests.showcase_fixture import SHOWCASE_TEXT, write_showcase


class ControlModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = self.root / "registry.json"

    def test_one_author_six_editable_sources_and_immutable_submission(self):
        workspace = scaffold(self.root / "author", "distributed", registry=self.registry)
        expected = {f"robot_{slot}.py" for slot in SLOT_IDS}
        self.assertEqual(set(json.loads((workspace / "agent.json").read_text())["editable"]), expected)
        self.assertFalse((workspace / "strategy.py").exists())
        self.assertEqual((workspace / "AGENT_GUIDE.md").read_bytes(), guide_path("distributed").read_bytes())
        sources = {}
        for slot in SLOT_IDS:
            sources[str(slot)] = f'def act(obs,state):\n return {{"{slot}":{{}}}}, {slot}\n'
            (workspace / f"robot_{slot}.py").write_text(sources[str(slot)])
        refresh_workspace(workspace, self.registry)
        start_training(workspace, self.registry)
        validate_workspace(workspace, self.registry)
        write_showcase(workspace)
        validate_workspace(workspace, self.registry)
        submit(workspace, self.root / "entry", self.registry)
        manifest, entries = load_submission(self.root / "entry")
        self.assertEqual(manifest["mode"], "distributed")
        self.assertEqual({slot: path.read_text() for slot, path in entries.items()}, sources)
        (workspace / "robot_1.py").write_text("changed after submission")
        self.assertEqual(entries["1"].read_text(), sources["1"])
        entries["2"].write_text("tampered")
        with self.assertRaisesRegex(ValueError, "strategy changed"):
            load_submission(self.root / "entry")

    def test_six_source_validation_protects_references_and_requires_each_slot(self):
        workspace = scaffold(self.root / "author", "distributed", registry=self.registry)
        start_training(workspace, self.registry)
        (workspace / "robot_7.py").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_workspace(workspace, self.registry)
        (workspace / "robot_7.py").symlink_to(workspace / "robot_1.py")
        with self.assertRaisesRegex(ValueError, "regular file"):
            validate_workspace(workspace, self.registry)
        (workspace / "robot_7.py").unlink()
        (workspace / "robot_7.py").write_text("def act(o,s): return {},s\n")
        (workspace / "sdk.py").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "Protected file"):
            validate_workspace(workspace, self.registry)
        with self.assertRaisesRegex(ValueError, "Entries"):
            save_submission(self.root / "incomplete", "distributed", {"1": workspace / "robot_1.py"})

    def communicating_submission(self, name, mode):
        entries = {}
        for slot in SLOT_IDS:
            source = self.root / f"{name}-{slot}.py"
            source.write_text(f'''from pathlib import Path
from sdk import action, message
import time
OWN = "{slot}"
COUNT = 0
def act(obs, state):
    global COUNT
    assert obs['controlled_ids'] == [OWN]
    assert not list(Path.cwd().glob('robot_*.py'))
    if Path('/runtime/worker.py').is_file():
        assert [p.name for p in Path('/submission').iterdir()] == ['strategy.py']
    assert (state or {{'own': OWN}})['own'] == OWN
    COUNT += 1
    assert COUNT == obs['tick'] // 2 + 1
    assert COUNT == (state or {{'count': 0}})['count'] + 1
    inbox = obs['messages']
    for envelope in inbox:
        assert envelope['from'].startswith(obs['team'] + '-')
        assert envelope['to'] == obs['team'] + '-' + OWN
        assert envelope['delivery_tick'] == obs['tick']
        assert envelope['tick'] == obs['tick'] - 2
    outgoing = []
    if obs['tick'] == 0:
        assert not inbox
        if OWN == '1':
            time.sleep(.02)  # The earlier sender finishes after slot 7.
            outgoing = [message({{'intent':'cover'}}, to=2), message({{'intent':'advance'}})]
        elif OWN == '7':
            outgoing = [message({{'intent':'flank'}}, to=2)]
    elif obs['tick'] == 2:
        if OWN == '1':
            assert not inbox
        else:
            expected = ['cover', 'advance', 'flank'] if OWN == '2' else ['advance']
            assert [m['data']['intent'] for m in inbox] == expected
        if OWN == '2':
            outgoing = [message({{'intent':'ack'}}, to=1)]
    elif obs['tick'] == 4 and OWN == '1':
        assert [m['data']['intent'] for m in inbox] == ['ack']
    else:
        assert not inbox
    return {{OWN: action(aim=COUNT, messages=outgoing)}}, {{'own': OWN, 'count': COUNT}}
''')
            entries[str(slot)] = source
        save_submission(self.root / name, mode, entries)
        return self.root / name

    def test_b_and_c_private_states_bidirectional_messages_and_replay(self):
        b = self.communicating_submission("b", "squad")
        c = self.communicating_submission("c", "distributed")
        for red, blue in ((b, c), (c, b)):
            with self.subTest(red=red.name), Battle(red, blue, duration=1, sandbox="trusted-local") as battle:
                self.assertEqual(len({p.process.pid for _, _, p in battle.policies}), 12)
                result = battle.run()
                self.assertEqual(result["policy_errors"], 0, battle.diagnostics)
                self.assertEqual(len(battle.actions[0]["communication"]), 6)
                self.assertNotIn("communication", battle.actions[1])
                self.assertEqual(len(battle.actions[2]["communication"]), 2)
                for team in ("red", "blue"):
                    for slot in SLOT_IDS:
                        self.assertEqual(battle.actions[4][team][str(slot)]["aim"], 3)
                        self.assertNotIn("messages", battle.actions[0][team][str(slot)])
                replay = self.root / f"{red.name}-replay.json"
                battle.save(replay)
                self.assertEqual(verify_replay(replay)["digest"], result["digest"])
                self.assertEqual(json.loads(replay.read_text())["actions"], battle.replay()["actions"])

    def test_message_protocol_rejects_invalid_recipients_spoofing_and_limits(self):
        with Match() as match:
            obs = match.observation("red", [1])
        obs["messages"] = []
        invalid = [
            [{"to": "blue-2", "data": {}}], [{"to": "5", "data": {}}],
            [{"to": "1", "data": {}}], [{"to": "2", "data": {}, "from": "red-7"}],
            [{"to": "2", "data": {}}] * 5,
            [{"to": "2", "data": "x" * 513}],
            {"to": "all", "data": {}},
        ]
        for index, messages in enumerate(invalid):
            with self.subTest(messages=messages):
                path = self.root / f"invalid-{index}.py"
                path.write_text(f'def act(obs,state):\n return {{"1":{{"messages":{messages!r}}}}},state\n')
                policy = Policy(path, 1, "trusted-local")
                self.addCleanup(policy.close)
                self.assertIsNotNone(policy.decide(obs)[1])
                self.assertTrue(policy.disabled)

    def test_one_c_policy_failure_does_not_disable_teammates(self):
        entries = {}
        for slot in SLOT_IDS:
            source = self.root / f"fault-{slot}.py"
            source.write_text('def act(obs,state):\n raise RuntimeError("slot one failed")\n' if slot == 1 else
                              f'def act(obs,state):\n n=(state or 0)+1\n return {{"{slot}":{{"aim":n}}}},n\n')
            entries[str(slot)] = source
        save_submission(self.root / "faulty", "distributed", entries)
        with Battle(self.root / "faulty", ROOT / "examples/claude_opus55_xhigh_team", duration=1, sandbox="trusted-local") as battle:
            self.assertEqual(battle.run()["policy_errors"], 1)
            self.assertTrue(battle.policies[0][2].disabled)
            for slot in SLOT_IDS[1:]:
                self.assertEqual(battle.actions[4]["red"][str(slot)]["aim"], 3)

    @unittest.skipUnless(os.environ.get("RMUC_DOCKER_TESTS") == "1", "Set RMUC_DOCKER_TESTS=1 to verify real containers")
    def test_b_c_communication_in_six_source_isolated_containers_each(self):
        b = self.communicating_submission("docker-b", "squad")
        c = self.communicating_submission("docker-c", "distributed")
        with Battle(c, b, duration=1) as battle:
            self.assertEqual(len(battle.policies), 12)
            self.assertEqual(battle.run()["policy_errors"], 0, battle.diagnostics)

    def test_team_observation_keeps_shared_control_and_enables_messages(self):
        with Battle(ROOT / "examples/claude_opus55_xhigh_team", ROOT / "examples/claude_opus55_xhigh_hold",
                    duration=1, sandbox="trusted-local") as battle:
            self.assertEqual(len(battle.policies), 2)
            self.assertEqual(battle.observation("red", None)["messages"],[])
            self.assertEqual(set(battle.observation("red",None)["message_inboxes"]),{str(s) for s in SLOT_IDS})
            self.assertEqual(battle.run()["policy_errors"], 0)
        source = self.root / "a.py"
        source.write_text('def act(obs,state):\n return {"1":{"messages":[]}},state\n')
        with Match() as match:
            observation = match.observation("red")
        observation["messages"]=[]
        policy = Policy(source, 1, "trusted-local")
        self.addCleanup(policy.close)
        self.assertIsNone(policy.decide(observation)[1])

    def test_c_api_upload_catalog_guide_training_and_submission(self):
        app = create_app("trusted-local", self.root / "submissions", self.root / "data",
                         test_mode=True, workspace_registry=self.registry)
        self.addCleanup(app.state.arena.shutdown)
        self.addCleanup(app.state.training.shutdown)
        client = TestClient(app)
        entries = {str(slot): f'def act(obs,state):\n assert obs["controlled_ids"]==["{slot}"]\n return {{}},state\n' for slot in SLOT_IDS}
        response = client.post("/api/submissions", json={"name": "c-upload", "mode": "distributed", "entries": entries, "showcase": SHOWCASE_TEXT})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.get("/api/catalog").json()["c-upload"]["mode"], "distributed")
        guide = client.get("/api/agent-guide", params={"mode": "distributed", "lang": "en", "season": "2026"})
        self.assertEqual(guide.text, guide_path("distributed", lang="en").read_text())
        workspace = scaffold(self.root / "c-author", "distributed", registry=self.registry)
        start_training(workspace, self.registry)
        write_showcase(workspace)
        config = json.loads((workspace / "agent.json").read_text())["training"]
        headers = {"Authorization": "Bearer " + config["token"]}
        base = "/api/training/" + config["session_id"]
        submitted = client.post(base + "/submit", json={}, headers=headers)
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(client.get("/api/catalog").json()[submitted.json()["entry"]]["mode"], "distributed")
        response = client.post(base + "/tests", json={"duration": 1, "opponent": submitted.json()["version"]}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        # A practice job starts up to twelve policy processes before simulating.
        # The per-policy startup budget is 15 s; the entire job needs its own wait.
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            job = client.get(base + "/tests/" + response.json()["job_id"], headers=headers).json()
            if job["status"] not in ("queued", "running"):
                break
            time.sleep(.02)
        self.assertEqual(job["status"], "finished", job)
        self.assertEqual(job["results"][0]["policy_errors"], 0, job)


if __name__ == "__main__":
    unittest.main()
