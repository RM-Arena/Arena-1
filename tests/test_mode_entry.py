"""Homepage training entry and formal/free competition contracts."""
import json
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from rmuc_arena.server import create_app
from rmuc_arena.models import normalize_team_lineup

class ModeEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.registry=self.root/'registry.json'
        self.app=create_app('trusted-local',self.root/'submissions',self.root/'data',test_mode=True,workspace_registry=self.registry)
        self.addCleanup(self.app.state.training.shutdown);self.addCleanup(self.app.state.arena.shutdown)
        self.client=TestClient(self.app)

    def test_four_training_modes_create_correct_editable_files_and_start_clock(self):
        for mode,robot,files in [('team',None,['strategy.py']),('robot',6,['strategy.py']),
                ('distributed',None,['robot_1.py','robot_2.py','robot_3.py','robot_4.py','robot_6.py','robot_7.py']),('adaptive',103,['strategy.py'])]:
            with self.subTest(mode=mode):
                body={'name':'train-'+mode,'mode':mode,'minutes':15}
                if robot is not None:body['robot']=robot
                if mode=='team':body['team_lineup']={'1':103,'2':201,'3':301,'4':302,'6':601,'7':303}
                response=self.client.post('/api/training-workspaces',json=body)
                self.assertEqual(response.status_code,200,response.text)
                result=response.json();workspace=Path(result['workspace'])
                agent=json.loads((workspace/'agent.json').read_text())
                self.assertEqual(agent['editable'],files);self.assertEqual(agent['mode'],mode)
                self.assertIsNotNone(agent['training']['started_at']);self.assertEqual(result['time_limit_minutes'],15)
                self.assertTrue(Path(result['task_file']).is_file())
                if mode=='team':self.assertEqual(agent['team_lineup'],body['team_lineup'])
                self.assertEqual(self.client.post('/api/training-workspaces',json=body).status_code,400)

    def test_training_rejects_invalid_model_and_role_composition_before_creation(self):
        for body in [{'name':'bad','mode':'robot','robot':103}, {'name':'bad','mode':'adaptive','robot':999},
                {'name':'bad','mode':'distributed','robot':1}, {'name':'bad','mode':'team','team_lineup':{'1':3,'2':2,'3':3,'4':4,'6':6,'7':7}}]:
            with self.subTest(body=body):
                self.assertEqual(self.client.post('/api/training-workspaces',json=body).status_code,400)
                self.assertFalse((self.root/'data/workspaces/bad').exists())

    def test_formal_requires_exact_six_roles_and_free_requires_saved_policies(self):
        roles={'1':1,'2':2,'3':3,'4':4,'6':6,'7':7}
        for invalid in [{**roles,'6':3},{**roles,'7':1},{k:v for k,v in roles.items() if k!='2'},{**roles,'8':3}]:
            with self.subTest(lineup=invalid),self.assertRaises(ValueError):normalize_team_lineup(invalid)
        for body in [{'mode':'deck','red_deck':['missing'],'blue_deck':['official_adaptive_7']},
                {'mode':'deck','red_deck':['official_team'],'blue_deck':['official_adaptive_7']},
                {'mode':'deck','red_deck':[],'blue_deck':['official_adaptive_7']},
                {'mode':'deck','red_deck':['official_adaptive_3'],'blue_deck':['official_adaptive_7'],'team_lineup':roles}]:
            with self.subTest(body=body):self.assertEqual(self.client.post('/api/start',json=body).status_code,409)
        self.assertFalse(self.app.state.arena.busy)
