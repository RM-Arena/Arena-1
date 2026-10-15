import json
from pathlib import Path
import tempfile
import time
import unittest

from fastapi.testclient import TestClient
from rmuc_arena.engine import Match
from rmuc_arena.runner import Battle, Policy
from rmuc_arena.referee import validate_referee
from rmuc_arena.cli import verify_replay
from rmuc_arena.server import create_app
from rmuc_arena.submissions import ROOT
from rmuc_arena import sdk


class RefereeTests(unittest.TestCase):
    def test_validation_rejects_nonexistent_targets_and_malformed_commands(self):
        for value in [None, [], {}, {"kind":"yellow","robot":[]}, {"kind":"yellow","robot":"red-5"},
                      {"kind":"red","robot":"other-3"}, {"kind":"yellow_both","robot":"red-4"},
                      {"kind":"forfeit","team":"green"}, {"kind":"yellow","robot":"red-4","reason":"x"*129}]:
            with self.subTest(value=value),self.assertRaises(ValueError):
                validate_referee(value)

    def test_contestant_cannot_issue_a_referee_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"strategy.py"
            path.write_text('def act(obs,state):\n return {"referee": [{"kind":"red","robot":"blue-3"}]},None\n')
            with Match() as match:
                policy=Policy(path,42,"trusted-local")
                try:
                    actions,error=policy.decide(match.observation("red"))
                    self.assertEqual(actions,{})
                    self.assertIn("unowned robot",error)
                finally:policy.close()

    def test_queued_cards_execute_once_and_replay_verifies(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"replay.json"
            with Battle(ROOT/"examples/official_team",ROOT/"examples/official_hold",duration=2,sandbox="trusted-local") as battle:
                battle.step()
                battle.queue_referee({"kind":"yellow","robot":"red-4"})
                battle.run()
                self.assertEqual(battle.frames[-1]["robots"][3]["yellow_cards"],1)
                self.assertEqual(sum("referee" in command for command in battle.actions),1)
                self.assertEqual(battle.result()["policy_errors"],0)
                battle.save(path)
            self.assertEqual(verify_replay(path)["verified_ticks"],40)

    def test_forfeit_early_finish_is_recorded_and_verifiable(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"replay.json"
            with Battle(ROOT/"examples/official_team",ROOT/"examples/official_hold",duration=420,sandbox="trusted-local") as battle:
                battle.step()
                battle.queue_referee({"kind":"forfeit","team":"blue"})
                battle.step()
                self.assertEqual(battle.match.reason,"forfeit")
                self.assertEqual(battle.match.winner,"red")
                battle.save(path)
            self.assertEqual(verify_replay(path)["verified_ticks"],2)

    def test_sdk_respects_all_independent_launcher_locks(self):
        with Match() as match:
            robot=dict(match.robots[3],ammo=100,heat=0,max_heat=170)
        self.assertTrue(sdk.can_fire(robot))
        for key in ["heat_permanent_lock","overspeed_locked","overspeed_permanent_lock","red_card","launcher_fault"]:
            with self.subTest(key=key):self.assertFalse(sdk.can_fire(dict(robot,**{key:True})))

    def test_organizer_endpoint_is_authenticated_and_queues_a_single_card(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            app=create_app("trusted-local",root/"submissions",root/"data",True,root/"registry.json")
            client=TestClient(app)
            try:
                token=app.state.arena.referee_token
                decision={"kind":"yellow","robot":"red-4"}
                self.assertEqual(client.post('/api/referee',json=decision).status_code,403)
                self.assertEqual(client.post('/api/referee',json=decision,headers={"Authorization":"Bearer invalid"}).status_code,403)
                self.assertNotIn(token,json.dumps(client.get('/api/state').json()))
                headers={"Authorization":"Bearer "+token}
                self.assertEqual(client.post('/api/referee',json=decision,headers=headers).status_code,409)
                client.post('/api/start',json={"duration":5})
                deadline=time.monotonic()+10
                while app.state.arena.battle is None and time.monotonic()<deadline:time.sleep(.01)
                client.post('/api/control',json={"command":"pause"})
                self.assertEqual(client.post('/api/referee',json=decision,headers=headers).status_code,200)
                self.assertEqual(client.post('/api/referee',json={"kind":"yellow","robot":"red-5"},headers=headers).status_code,409)
                client.post('/api/control',json={"command":"pause"})
                deadline=time.monotonic()+2
                # The default (RMUC 2027) roster has no slot 2, so find red-4 by id.
                red4=lambda:next(r for r in app.state.arena.frame['robots'] if r['id']=='red-4')
                while time.monotonic()<deadline and not red4()['yellow_cards']:time.sleep(.01)
                self.assertEqual(red4()['yellow_cards'],1)
            finally:
                app.state.arena.shutdown();app.state.training.shutdown()


if __name__=='__main__':unittest.main()
