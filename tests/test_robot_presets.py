"""Preset coverage, role-specific decisions and real variable-lineup execution."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from rmuc_arena import sdk
from rmuc_arena.engine import Match
from rmuc_arena import seasons as season_rules
from rmuc_arena.models import model_ids
from rmuc_arena.robot_presets import TACTICS, preset_key
from rmuc_arena.runner import Battle
from rmuc_arena.server import create_app
from rmuc_arena.submissions import ROOT, load_submission
from tests.showcase_fixture import SHOWCASE_TEXT, write_showcase


def policy(model, tactic, season='2026'):
    path=ROOT/'examples'/preset_key(model,tactic,season)/'strategy.py'
    spec=importlib.util.spec_from_file_location(f'preset_{model}_{tactic}',path)
    module=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{'sdk':sdk}):
        spec.loader.exec_module(module)
    return module


class RobotPresetTests(unittest.TestCase):
    def test_every_model_has_three_valid_distinct_saved_policies(self):
        # Every model legal in a season has three presets written for that season.
        for season in season_rules.seasons():
            for model in season_rules.legal_models(season):
                hashes=[]
                for tactic in TACTICS:
                    with self.subTest(season=season,model=model,tactic=tactic):
                        manifest,files=load_submission(ROOT/'examples'/preset_key(model,tactic,season))
                        self.assertEqual((manifest['mode'],manifest['robot'],manifest['rules_profile']),('adaptive',model,season_rules.rules_profile(season)))
                        hashes.append(manifest['hashes']['strategy.py'])
                self.assertEqual(len(set(hashes)),3)
        # Models illegal in a season have no presets there.
        self.assertFalse((ROOT/'examples'/preset_key(1,'balanced','2027')).exists())
        self.assertFalse((ROOT/'examples'/preset_key(2711,'balanced','2026')).exists())

    def test_catalog_has_descriptive_presets_and_keeps_custom_policy_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            app=create_app('trusted-local',Path(temporary)/'submissions',Path(temporary)/'data',test_mode=True,workspace_registry=Path(temporary)/'registry.json')
            with TestClient(app) as client:
                response=client.post('/api/submissions',json={'name':'custom-model-305','mode':'adaptive','robot':305,'entries':{'305':'def act(obs,state):\n return {obs["controlled_ids"][0]:{}},state\n'},'showcase':SHOWCASE_TEXT})
                self.assertEqual(response.status_code,200,response.text)
                cards=client.get('/api/robot-catalog').json()
                for season in season_rules.seasons():
                    for model in season_rules.legal_models(season):
                        self.assertEqual({cards[preset_key(model,t,season)]['preset']['id'] for t in TACTICS},set(TACTICS))
                        self.assertTrue(all(cards[preset_key(model,t,season)]['preset']['description'] for t in TACTICS))
                        self.assertTrue(all(cards[preset_key(model,t,season)]['season']==season for t in TACTICS))
                only_2027=client.get('/api/robot-catalog',params={'season':'2027'}).json()
                self.assertTrue(only_2027)
                self.assertTrue(all(card['season']=='2027' for card in only_2027.values()))
                self.assertNotIn('preset',cards['custom-model-305'])
                self.assertEqual(cards['custom-model-305']['role'],'infantry')

    def test_attack_and_defense_have_different_role_decisions_on_both_sides(self):
        for model in (1,2,3,6,305):
            lineups={team:[{'slot':9,'model':model},{'slot':12,'model':3}] for team in ('red','blue')}
            with Match(duration=1,lineups=lineups) as match:
                for team in ('red','blue'):
                    obs=match.observation(team,[9])
                    # Compare healthy, supplied robots at midfield rather than
                    # their shared initial supply/launch-pad behavior.
                    own=next(r for r in obs['robots'] if r['slot']==9)
                    own.update(x=14.,y=7.5,alive=True,weak=False,hp=own['max_hp'],ammo=50)
                    attack,_=policy(model,'assault').act(copy.deepcopy(obs),None)
                    defense,_=policy(model,'guard').act(copy.deepcopy(obs),None)
                    with self.subTest(model=model,team=team):
                        self.assertEqual(set(attack),{'9'})
                        self.assertEqual(set(defense),{'9'})
                        self.assertNotEqual({k:v for k,v in attack['9'].items() if k!='messages'}, {k:v for k,v in defense['9'].items() if k!='messages'})
                        self.assertNotIn('profile',attack['9'])

    def test_engineer_presets_dock_and_brake_for_physical_core_alignment(self):
        for model in (2,201,202,203):
            lineups={team:[{'slot':9,'model':model}] for team in ('red','blue')}
            with Match(duration=1,lineups=lineups) as match:
                for team in ('red','blue'):
                    obs=match.observation(team,[9])
                    obs['messages']=[]
                    own=obs['robots'][0]
                    goal=sdk.assembly_work_point(own,obs['arena'])
                    own.update(x=goal[0],y=goal[1],alive=True,weak=False,carried_units=1)
                    obs['assemblies'][team].update(stage='moving',difficulty=1)
                    for tactic in ('balanced','assault'):
                        with self.subTest(model=model,team=team,tactic=tactic):
                            with patch.dict(sys.modules,{'sdk':sdk}):
                                commands,_=policy(model,tactic).act(copy.deepcopy(obs),None)
                            self.assertEqual(tuple(commands['9']['move']),(0,0))
                            self.assertTrue(commands['9']['brake'])
                            self.assertTrue(commands['9']['assembly_confirm'])

    def test_every_preset_runs_with_duplicate_models_and_arbitrary_slots(self):
        # A separate short real battle for each tactic covers all 19 models in
        # workers, including two copies of model 305 with separate state. The decision window is
        # widened because a dozen workers share a small CI runner: this test covers preset
        # coverage, while the deadline contract itself is pinned by test_runner.
        for tactic in TACTICS:
            with self.subTest(tactic=tactic):
                red=[ROOT/'examples'/preset_key(model,tactic) for model in season_rules.legal_models('2026')]+[ROOT/'examples'/preset_key(305,tactic)]
                blue=[ROOT/'examples'/preset_key(3,'balanced'),ROOT/'examples'/preset_key(2,'guard')]
                with Battle(None,None,duration=1,sandbox='trusted-local',timeout=.6,decks={'red':red,'blue':blue}) as battle:
                    result=battle.run()
                    self.assertEqual(result['policy_errors'],0,battle.diagnostics)
                    self.assertEqual(len(battle.match.snapshot()['robots']),len(red)+len(blue))
                    self.assertEqual(len(battle.policies),len(red)+len(blue))
                    aerials=[r for r in battle.match.snapshot()['robots'] if r['team']=='red' and r['role']=='aerial']
                    self.assertTrue(aerials)
                    self.assertTrue(all(r['support_active'] for r in aerials),aerials)

    def test_every_2027_preset_runs_in_a_free_battle(self):
        # Each 2027 model's presets in one short deck battle; one aerial system per team. Same
        # widened window as the 2026 sweep: the workers outnumber a CI runner's cores.
        for tactic in TACTICS:
            with self.subTest(tactic=tactic):
                models=[m for m in season_rules.legal_models('2027') if m not in (2762,2763)]
                red=[ROOT/'examples'/preset_key(model,tactic,'2027') for model in models]
                blue=[ROOT/'examples'/preset_key(2771,'balanced','2027'),ROOT/'examples'/preset_key(2763,'guard','2027')]
                with Battle(None,None,duration=2,map_name='rmuc2027',sandbox='trusted-local',timeout=.6,decks={'red':red,'blue':blue}) as battle:
                    result=battle.run()
                    self.assertEqual(result['policy_errors'],0,battle.diagnostics)
                    self.assertEqual(battle.metadata['season'],'2027')
                    self.assertEqual(len(battle.match.snapshot()['robots']),len(red)+len(blue))


if __name__=='__main__':
    unittest.main()
