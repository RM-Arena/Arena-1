"""Training initial conditions share ordinary physics, observations and replay verification."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from rmuc_arena.env import ArenaEnv
from rmuc_arena.engine import Match
from rmuc_arena.vector_env import VectorArena
from rmuc_arena.replays import verify_replay

LINEUPS={t:[{'slot':3,'model':3}] for t in ('red','blue')}
SCENARIO={'robots':{'red-3':{'x':4.7,'y':5.1,'heading':.4,'ammo':200}}}


class TrainingScenarios(unittest.TestCase):
    def test_reset_refreshes_the_cached_static_observation(self):
        with Match(duration=1,map_name='rmuc2027') as match:
            self.assertEqual(json.loads(match.observation_static())['arena']['name'],'rmuc2027')
            match.reset(duration=1,map_name='rmuc2026')
            cached=json.loads(match.observation_static())['arena']
            self.assertEqual(cached['name'],'rmuc2026')
            self.assertEqual(cached,match.observation('red')['arena'])

    def test_reset_reuses_actor_and_records_deterministic_replay(self):
        with ArenaEnv(season='2027',lineups=LINEUPS,record=True) as env:
            first=env.reset(73,scenario=SCENARIO)
            r=first['observations']['red']['robots'][0]
            self.assertEqual((r['x'],r['y'],r['ammo']),(4.7,5.1,200))
            self.assertAlmostEqual(r['heading'],.4)
            state=env.step({'red':{'3':{'move':[.4,0],'heading':0}}})
            self.assertGreater(state['observations']['red']['robots'][0]['x'],4.7)
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'episode.json';env.save_replay(path)
                self.assertEqual(verify_replay(path)['digest'],env.match.digest())
            again=env.reset(73,scenario=SCENARIO)
            self.assertEqual(first,again | {'info':{**again['info'],'episode':first['info']['episode']}})
            self.assertEqual(first['info']['simulator_pid'],again['info']['simulator_pid'])
            normal=env.reset(73)
            self.assertNotEqual(normal['observations']['red']['robots'][0]['x'],4.7)

    def test_invalid_initial_conditions_are_rejected_and_reset_recovers(self):
        with ArenaEnv(season='2027',lineups=LINEUPS) as env:
            for invalid in ({'unknown':1},{'robots':{'enemy':{}}},
                            {'robots':{'red-3':{'x':-1}}},{'robots':{'red-3':{'ammo':-1}}},
                            {'robots':{'red-3':{'hp':1}}}):
                with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                    env.reset(73,scenario=invalid)
            self.assertEqual(env.reset(73,scenario=SCENARIO)['info']['tick'],0)

    def test_vector_scenarios_are_per_actor_and_subset_reset_is_independent(self):
        other=copy.deepcopy(SCENARIO);other['robots']['red-3']['x']=5.5
        with VectorArena(2,season='2027',lineups=LINEUPS) as env:
            states=env.reset([73,74],scenarios=[SCENARIO,other])
            self.assertEqual([s['observations']['red']['robots'][0]['x'] for s in states],[4.7,5.5])
            with self.assertRaises(ValueError):env.reset([73],scenarios=[SCENARIO])
            env.reset([75],env_ids=[0],scenarios=[other])
            next_state=env.step([{}],env_ids=[1])[0]
            self.assertEqual(next_state['info']['seed'],74)


if __name__=='__main__':unittest.main()
