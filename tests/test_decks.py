"""Variable lineup deployment, duplicate policies, authoring and Web contracts."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from rmuc_arena.cli import verify_replay
from rmuc_arena.decks import prepare_decks
from rmuc_arena.engine import Match
from rmuc_arena.runner import Battle
from rmuc_arena.server import create_app
from rmuc_arena.submissions import ROOT, guide_path, load_submission, save_submission, scaffold, start_training, submit
from tests.showcase_fixture import SHOWCASE_TEXT, write_showcase


class DeckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = self.root / "registry.json"

    def card(self, model=3):
        source = self.root / f"source-{model}.py"
        source.write_text(f'''from sdk import action, message
COUNT = 0
MODEL = {model}
def act(obs, state):
    global COUNT
    slot = obs['controlled_ids'][0]
    assert len(obs['controlled_ids']) == 1
    own = next(r for r in obs['robots'] if str(r['slot']) == slot)
    assert own['model_slot'] == MODEL
    assert (state or {{'slot':slot}})['slot'] == slot
    assert len(obs['robots']) == len(obs['roster'][obs['team']])
    COUNT += 1
    assert COUNT == obs['tick']//2+1 == (state or {{'count':0}})['count']+1
    outgoing = [message({{'sender':slot}})] if obs['tick']==0 else []
    if obs['tick']==2:
        assert len(obs['messages']) == len(obs['robots'])-1
        assert {{m['from'] for m in obs['messages']}} == {{r['id'] for r in obs['robots'] if str(r['slot'])!=slot}}
        assert all(m['to']==own['id'] and m['delivery_tick']==2 for m in obs['messages'])
    elif obs['tick']!=0:
        assert not obs['messages']
    return {{slot:action(aim=COUNT,messages=outgoing)}},{{'slot':slot,'count':COUNT}}
''')
        destination = self.root / f"card-{model}"
        save_submission(destination, "adaptive", {str(model):source}, model)
        return destination

    def test_development_scaffold_has_one_model_without_a_final_lineup(self):
        workspace = scaffold(self.root / "author", "adaptive", 3, self.registry)
        metadata = json.loads((workspace / "agent.json").read_text())
        self.assertEqual(metadata["editable"], ["strategy.py"])
        self.assertNotIn("lineups", metadata)
        self.assertEqual((workspace / "AGENT_GUIDE.md").read_bytes(), guide_path("adaptive", 3).read_bytes())
        task = (workspace / "AGENT_TASK.md").read_text()
        self.assertIn("开发时不预告最终阵容", task)
        self.assertIn("比赛时可读取完整己方阵容", task)
        self.assertNotIn("其余五台", task)
        start_training(workspace, self.registry)
        write_showcase(workspace)
        submit(workspace, self.root / "submitted", self.registry)
        manifest, files = load_submission(self.root / "submitted")
        self.assertEqual((manifest["mode"], manifest["robot"], set(files)), ("adaptive",3,{"3"}))

    def duplicate_match(self, sandbox):
        three, seven = self.card(3), self.card(7)
        with Battle(None,None,duration=1,sandbox=sandbox,
                    decks={"red":[three]*3,"blue":[seven]*2}) as battle:
            initial = battle.match.snapshot()
            self.assertEqual(len(initial["robots"]), 5)
            self.assertEqual(initial["roster"], {"red":[1,2,3],"blue":[1,2]})
            self.assertEqual(len({p.process.pid for _,_,p in battle.policies}), 5)
            positions = {(r["team"],r["x"],r["y"]) for r in initial["robots"]}
            self.assertEqual(len(positions),5)
            self.assertEqual([r["model_slot"] for r in initial["robots"]], [3,3,3,7,7])
            result = battle.run()
            self.assertEqual(result["policy_errors"],0,battle.diagnostics)
            for team, count in (("red",3),("blue",2)):
                for slot in range(1,count+1):
                    self.assertEqual(battle.actions[4][team][str(slot)]["aim"],3)
            replay = self.root / "deck-replay.json"
            battle.save(replay)
            self.assertEqual(verify_replay(replay)["digest"],result["digest"])
            self.assertTrue(battle.metadata["test_match"])

    def test_duplicate_models_have_private_states_and_dynamic_team_messages(self):
        self.duplicate_match("trusted-local")

    @unittest.skipUnless(os.environ.get("RMUC_DOCKER_TESTS")=="1","Set RMUC_DOCKER_TESTS=1 for real sandbox deployment")
    def test_duplicate_cards_execute_in_separate_docker_containers(self):
        self.duplicate_match("docker")

    def test_model_specific_chassis_controls_use_model_instead_of_instance_id(self):
        lineups={"red":[{"slot":1,"model":7},{"slot":8,"model":3}],"blue":[{"slot":1,"model":6}]}
        with Match(duration=1,lineups=lineups) as match:
            initial = match.snapshot()
            self.assertEqual(initial["robots"][0]["max_hp"],200)
            self.assertTrue(initial["robots"][1]["legs"])
            frame = match.step({"red":{"1":{"crouch":True}},"blue":{}})
            self.assertTrue(frame["robots"][0]["crouched"])
            self.assertTrue(frame["robots"][1]["legs"])

    def test_more_than_twelve_instances_have_distinct_bounded_spawns(self):
        card=self.card()
        lineups, _, _ = prepare_decks({"red":[card]*17,"blue":[card]},42)
        with Match(duration=1,lineups=lineups) as match:
            frame=match.snapshot()
            self.assertEqual(len(frame["robots"]),18)
            points={(r["team"],r["x"],r["y"]) for r in frame["robots"]}
            self.assertEqual(len(points),18)
            self.assertTrue(all(0<r["x"]<28 and 0<r["y"]<15 for r in frame["robots"]))

    def test_deck_and_engine_input_validation(self):
        card = self.card()
        for decks in ({"red":[],"blue":[card]}, {"red":[ROOT/"examples/claude_opus55_xhigh_team"],"blue":[card]}, {"red":[card]}):
            with self.subTest(decks=decks), self.assertRaises(ValueError):
                prepare_decks(decks,42)
        for red in ([{"slot":1,"model":5}], [{"slot":1,"model":3}]*2, []):
            with self.subTest(red=red), self.assertRaises(ValueError):
                Match(duration=1,lineups={"red":red,"blue":[{"slot":1,"model":3}]})

    def app(self):
        app = create_app("trusted-local",self.root/"submissions",self.root/"data",test_mode=True,workspace_registry=self.registry)
        self.addCleanup(app.state.arena.shutdown)
        self.addCleanup(app.state.training.shutdown)
        return app, TestClient(app)

    def wait(self, read):
        until=time.monotonic()+20
        while time.monotonic()<until:
            result=read()
            if result["status"] not in ("initializing","running","queued"):
                return result
            time.sleep(.02)
        self.fail("Deck game did not finish")

    def test_api_single_robot_cards_and_repeated_unequal_lineups(self):
        app,client=self.app()
        # Model 3 is legal in both seasons; this deck plays the 2026 field.
        response=client.post("/api/submissions",json={"name":"custom-d","mode":"adaptive","robot":3,"season":"2026",
            "entries":{"3":'def act(obs,state):\n return {obs["controlled_ids"][0]:{}},state\n'},"showcase":SHOWCASE_TEXT})
        self.assertEqual(response.status_code,200,response.text)
        cards=client.get("/api/robot-catalog").json()
        self.assertEqual(cards["custom-d"]["robot"],3)
        self.assertNotIn("custom-d",client.get("/api/catalog").json())
        guide=client.get("/api/agent-guide",params={"mode":"adaptive","robot":3})
        self.assertIn("开发阶段不预告最终阵容",guide.text)
        args={"mode":"deck","red_deck":["custom-d"]*3,"blue_deck":["claude_opus55_xhigh_adaptive_7"],"duration":1}
        response=client.post("/api/start",json=args)
        self.assertEqual(response.status_code,200,response.text)
        record=self.wait(lambda:client.get("/api/matches/"+response.json()["match_id"]).json())
        self.assertEqual(record["status"],"finished",record)
        self.assertEqual(record["result"]["policy_errors"],0)
        self.assertEqual(len(record["metadata"]["lineups"]["red"]),3)
        self.assertEqual(len(app.state.arena.frame["robots"]),4)
        self.assertEqual(client.get("/api/leaderboard").json(),[])
        args["red_deck"]=["not-a-card"]
        self.assertNotEqual(client.post("/api/start",json=args).status_code,200)

    def test_training_uses_variable_practice_lineups_and_submits_one_card(self):
        workspace=scaffold(self.root/"author","adaptive",4,self.registry)
        start_training(workspace,self.registry)
        write_showcase(workspace)
        app,client=self.app()
        config=json.loads((workspace/"agent.json").read_text())["training"]
        headers={"Authorization":"Bearer "+config["token"]}
        base="/api/training/"+config["session_id"]
        submitted=client.post(base+"/submit",json={},headers=headers)
        self.assertEqual(submitted.status_code,200,submitted.text)
        self.assertIn(submitted.json()["entry"],client.get("/api/robot-catalog").json())
        response=client.post(base+"/tests",json={"duration":1,"games":1,"opponent":"self"},headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        job=self.wait(lambda:client.get(base+"/tests/"+response.json()["job_id"],headers=headers).json())
        self.assertEqual(job["status"],"finished",job)
        self.assertEqual(job["results"][0]["policy_errors"],0,job)


if __name__=="__main__":
    unittest.main()
