import json
from pathlib import Path
import tempfile
import time
import struct
import unittest

from rmuc_arena.models import DEFAULT_TEAM_LINEUP,normalize_team_lineup,robot_models
from rmuc_arena.submissions import ROOT,scaffold,start_training,save_submission,submit,validate_workspace
from rmuc_arena.runner import Battle
from rmuc_arena.server import create_app
from fastapi.testclient import TestClient
from tests.showcase_fixture import SHOWCASE_TEXT, write_showcase

CUSTOM={**DEFAULT_TEAM_LINEUP,'1':103,'2':201,'3':301,'4':302,'6':602,'7':303}

class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.registry=self.root/'registry.json'

    def test_catalog_and_role_limits(self):
        from scripts.robot_designs import make_designs,construction_limits,validate_designs
        models=make_designs();validate_designs(models,construction_limits());self.assertEqual(len(models),19)
        self.assertFalse(models['103']['deploy_allowed']);self.assertTrue(models['301']['transform_allowed']);self.assertEqual(models['201']['arm_count'],2)
        for value in [{**CUSTOM,'1':201},{**CUSTOM,'3':602},{**CUSTOM,'1':999}, {'1':1}]:
            with self.assertRaises(ValueError):normalize_team_lineup(value)

    def test_only_robots_that_cannot_right_themselves_need_the_engineer(self):
        from rmuc_arena import sdk
        robots=[{'slot':3,'tipped':True,'alive':True,'powered':True,'hip_angle':0.4},
                {'slot':4,'tipped':True,'alive':True,'powered':False,'hip_angle':0.0},
                {'slot':7,'tipped':True,'alive':True,'powered':True},
                {'slot':1,'tipped':False,'alive':True}]
        self.assertEqual([r['slot'] for r in sdk.tipped_teammates({'robots':robots})],[4,7])

    def test_exported_models_preserve_the_parts_that_need_animation(self):
        def gltf(model):
            raw=(ROOT/'frontend/public'/robot_models()[str(model)]['asset'].lstrip('/')).read_bytes()
            length=struct.unpack_from('<I',raw,12)[0]
            return json.loads(raw[20:20+length])
        for model,prefix,count in [(101,'SteerModule_',4),(201,'Aux_ArmSlew',1),(301,'FoldMast_',3),(305,'LegR_Thigh',1),(305,'LegL_Shank',1)]:
            data=gltf(model);nodes=[n for n in data['nodes'] if n.get('name','').startswith(prefix) and n.get('children')]
            self.assertEqual(len(nodes),count,(model,prefix))
            self.assertTrue(all(n.get('children') for n in nodes),(model,'animated parts were merged into chassis'))
        envelope=json.loads((ROOT/'frontend/public/assets/robot-301-envelope.json').read_text())
        self.assertLessEqual(envelope['folded_top_m'],.235)
        for model in robot_models():
            if robot_models()[model]['role']=='aerial':continue
            self.assertEqual(sum(n.get('name','').startswith('ArmorNumber') and bool(n.get('children')) for n in gltf(model)['nodes']),4)

    def test_lineup_is_selected_before_clock_and_protected_afterward(self):
        workspace=scaffold(self.root/'agent',registry=self.registry,team_lineup=CUSTOM)
        record=json.loads(self.registry.read_text())[str(workspace)]
        self.assertIsNone(record['training']['started_at']);self.assertEqual(record['team_lineup'],CUSTOM)
        self.assertEqual(json.loads((workspace/'lineup.json').read_text()),CUSTOM)
        self.assertIn('H-W',(workspace/'AGENT_GUIDE.md').read_text());self.assertIn('transform=True',(workspace/'AGENT_GUIDE.en.md').read_text())
        start_training(workspace,self.registry)
        write_showcase(workspace)
        manifest=submit(workspace,self.root/'submission',self.registry);self.assertEqual(manifest['team_lineup'],CUSTOM)
        (workspace/'lineup.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Protected file'):validate_workspace(workspace,self.registry)

    def test_different_lineups_change_version_and_are_rejected_before_matching(self):
        source=ROOT/'examples/official_team/strategy.py'
        a=save_submission(self.root/'a','team',{'team':source},team_lineup=CUSTOM)
        b=save_submission(self.root/'b','team',{'team':source})
        self.assertNotEqual(a['version'],b['version'])
        with self.assertRaisesRegex(ValueError,'identical registered'):
            Battle(self.root/'a',self.root/'b',duration=1,sandbox='trusted-local')

    def test_custom_team_match_has_the_same_models_on_both_sides(self):
        source=self.root/'noop.py';source.write_text('def act(obs,state):\n return {},state\n')
        for side in ('a','b'):save_submission(self.root/side,'team',{'team':source},team_lineup=CUSTOM)
        with Battle(self.root/'a',self.root/'b',duration=1,sandbox='trusted-local') as battle:
            battle.run();self.assertFalse(battle.diagnostics)
            for slot,model in CUSTOM.items():
                robots=[r for r in battle.match.robots if str(r['slot'])==slot]
                self.assertEqual([r['model_slot'] for r in robots],[model,model])

    def test_models_and_team_development_are_available_from_the_local_app(self):
        app=create_app('trusted-local',submission_root=self.root/'submissions',data_root=self.root/'data',workspace_registry=self.registry,test_mode=True)
        with TestClient(app) as client:
            info=client.get('/api/models').json();self.assertEqual(len(info['models']),19);self.assertEqual(info['default_team_lineup'],DEFAULT_TEAM_LINEUP)
            response=client.post('/api/team-workspaces',json={'name':'custom-team','minutes':10,'team_lineup':CUSTOM})
            self.assertEqual(response.status_code,200,response.text);data=response.json()
            self.assertEqual(data['team_lineup'],CUSTOM);self.assertTrue(Path(data['task_file']).is_file())
            record=json.loads(self.registry.read_text())[data['workspace']];self.assertIsNotNone(record['training']['started_at'])

    def test_team_briefing_is_generated_for_confirmed_models_without_starting_a_clock(self):
        app=create_app('trusted-local',submission_root=self.root/'submissions',data_root=self.root/'data',workspace_registry=self.registry,test_mode=True)
        with TestClient(app) as client:
            generic=client.get('/api/agent-guide').text
            self.assertNotIn('已锁定的双方共同阵容',generic)
            self.assertNotIn('H42',generic)
            response=client.post('/api/team-briefing',json={'team_lineup':CUSTOM})
            self.assertEqual(response.status_code,200,response.text);briefing=response.json()
            self.assertEqual(briefing['team_lineup'],CUSTOM)
            self.assertIn('H-W',briefing['task']['zh']);self.assertIn('I-T',briefing['task']['en'])
            self.assertIn('You know the complete deployed lineup',briefing['task']['en'])
            self.assertIn('| 1 | 英雄 | H-W',briefing['guides']['zh'])
            self.assertIn('无部署机构',briefing['guides']['zh'])
            self.assertFalse(self.registry.exists());self.assertFalse((self.root/'data/workspaces').exists())
            default=client.post('/api/team-briefing',json={'team_lineup':DEFAULT_TEAM_LINEUP}).json()
            self.assertNotIn('I-T',default['task']['zh'])
            self.assertIn('H42',default['task']['zh'])
            wrong=client.post('/api/team-briefing',json={'team_lineup':{**CUSTOM,'1':201}})
            self.assertEqual(wrong.status_code,400)
            created=client.post('/api/team-workspaces',json={'name':'confirmed-team','minutes':20,'team_lineup':CUSTOM}).json()
            task=Path(created['task_file']).read_text()
            for lang in ('zh','en'):self.assertIn(briefing['task'][lang],task)
            self.assertNotIn('final lineup is not disclosed',task)

    def test_catalog_numbers_are_the_preselected_engine_performance(self):
        from rmuc_arena.models import model_catalog
        from rmuc_arena.engine import Match
        catalog=model_catalog()
        for model in (1,103,201,301,302,303,601,602):
            role=catalog[str(model)]['role'];slot={'hero':1,'engineer':2,'infantry':3,'aerial':6}[role]
            lineup={**DEFAULT_TEAM_LINEUP,str(slot):model}
            from rmuc_arena.models import mirrored_lineups
            with Match(42,1,lineups=mirrored_lineups(lineup)) as match:
                robot=next(r for r in match.robots if r['team']=='red' and r['slot']==slot)
                stats=catalog[str(model)]['initial_stats']
                for key,field in [('hp','hp'),('power_w','power_limit'),('max_heat','max_heat'),('cooling','cooling_rate')]:
                    self.assertEqual(stats[key],robot[field],(model,key))

    def test_new_adaptive_model_receives_its_own_rules(self):
        workspace=scaffold(self.root/'card',mode='adaptive',robot=301,registry=self.registry)
        self.assertIn('变形隧道',(workspace/'AGENT_GUIDE.md').read_text())
        self.assertIn('transform=True',(workspace/'AGENT_GUIDE.en.md').read_text())

    def test_bad_lineup_does_not_leave_a_partial_workspace_or_submission(self):
        wrong={**CUSTOM,'1':201}
        with self.assertRaises(ValueError):scaffold(self.root/'bad-workspace',registry=self.registry,team_lineup=wrong)
        self.assertFalse((self.root/'bad-workspace').exists())
        with self.assertRaises(ValueError):save_submission(self.root/'bad-submission','team',{'team':ROOT/'examples/official_team/strategy.py'},team_lineup=wrong)
        self.assertFalse((self.root/'bad-submission').exists())

    def test_custom_team_practice_keeps_models_when_swapping_sides_against_baseline(self):
        workspace=scaffold(self.root/'practice-team',registry=self.registry,team_lineup=CUSTOM)
        start_training(workspace,self.registry)
        training=json.loads((workspace/'agent.json').read_text())['training']
        base='/api/training/'+training['session_id'];headers={'Authorization':'Bearer '+training['token']}
        app=create_app('trusted-local',submission_root=self.root/'submissions',data_root=self.root/'data',workspace_registry=self.registry,test_mode=True)
        with TestClient(app) as client:
            response=client.post(base+'/tests',json={'duration':1,'opponent':'baseline','swap_sides':True},headers=headers)
            self.assertEqual(response.status_code,200,response.text);job_id=response.json()['job_id']
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                job=client.get(base+'/tests/'+job_id,headers=headers).json()
                if job['status'] not in ('queued','running'):break
                time.sleep(.02)
            self.assertEqual(job['status'],'finished',job);self.assertEqual(len(job['results']),2)
            self.assertEqual(sum(r['policy_errors'] for r in job['results']),0)
            for game in (0,1):
                replay=client.get(base+f'/tests/{job_id}/replays/{game}',headers=headers).json()
                self.assertEqual(replay['metadata']['team_lineup'],CUSTOM)
                for side in ('red','blue'):
                    self.assertEqual({str(r['slot']):r['model'] for r in replay['metadata']['lineups'][side]},CUSTOM)

