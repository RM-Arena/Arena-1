import json
from pathlib import Path
import tempfile
import time
import unittest

from fastapi.testclient import TestClient
from rmuc_arena.cli import verify_replay
from rmuc_arena.server import create_app
from rmuc_arena.submissions import scaffold,start_training,locked_registry,submit
from rmuc_arena.runner import Policy
from tests.showcase_fixture import SHOWCASE_TEXT, write_showcase


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.registry=self.root/'host/registry.json'
        self.workspace=scaffold(self.root/'author',registry=self.registry)
        write_showcase(self.workspace)
        config=json.loads((self.workspace/'agent.json').read_text())['training']
        self.sid=config['session_id']
        self.headers={'Authorization':'Bearer '+config['token']}
        self.base='/api/training/'+self.sid
        self.app=create_app('trusted-local',self.root/'submissions',self.root/'data',test_mode=True,workspace_registry=self.registry)
        self.client=TestClient(self.app)
        self.addCleanup(self.app.state.arena.shutdown)
        self.addCleanup(self.app.state.training.shutdown)

    def wait_job(self, job_id, base=None, headers=None):
        base = base or self.base
        headers = headers or self.headers
        # Includes policy initialization, simulation, replay writing and cleanup.
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            job=self.client.get(base+'/tests/'+job_id,headers=headers).json()
            if job['status'] not in ('queued','running'):return job
            time.sleep(.02)
        self.fail(f'Practice did not finish within 60 seconds: {job}')

    def test_host_starts_once_and_expiry_blocks_test_and_submission(self):
        status=self.client.get(self.base,headers=self.headers).json()
        self.assertEqual(status['phase'],'waiting')
        self.assertEqual(status['remaining_seconds'],5400)
        self.assertEqual(self.client.post(self.base+'/submit',json={},headers=self.headers).status_code,403)
        start_training(self.workspace,self.registry)
        with self.assertRaisesRegex(ValueError,'already started'):start_training(self.workspace,self.registry)
        self.assertEqual(self.client.get(self.base,headers=self.headers).json()['phase'],'active')
        first=self.client.post(self.base+'/submit',json={},headers=self.headers).json()
        (self.workspace/'strategy.py').write_text('def act(obs,state):\n return {}, {"revision":2}\n')
        latest=self.client.post(self.base+'/submit',json={},headers=self.headers).json()
        catalog=self.client.get('/api/catalog').json()
        self.assertNotIn(first['entry'],catalog)
        self.assertIn(latest['entry'],catalog)
        with locked_registry(self.registry) as records:
            records[str(self.workspace)]['training']['deadline_at']=time.time()-1
        self.assertEqual(self.client.get(self.base,headers=self.headers).json()['last_submission'],latest['version'])
        self.assertEqual(self.client.post(self.base+'/tests',json={},headers=self.headers).status_code,403)
        self.assertEqual(self.client.post(self.base+'/submit',json={},headers=self.headers).status_code,403)
        with self.assertRaisesRegex(ValueError,'deadline'):submit(self.workspace,self.root/'late',self.registry)

    def test_self_play_swap_sides_replay_and_private_access(self):
        start_training(self.workspace,self.registry)
        response=self.client.post(self.base+'/tests',json={'duration':1,'games':2,'opponent':'self','swap_sides':True},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        job_id=response.json()['job_id']
        job=self.wait_job(job_id)
        self.assertEqual(job['status'],'finished',job)
        self.assertEqual(len(job['results']),4)
        self.assertEqual([(r['seed'],r['swapped']) for r in job['results']],[(42,False),(42,True),(43,False),(43,True)])
        self.assertEqual(sum(r['policy_errors'] for r in job['results']),0)
        response=self.client.get(self.base+'/tests/'+job_id+'/replays/0',headers=self.headers)
        replay=self.root/'replay.json';replay.write_bytes(response.content)
        self.assertEqual(verify_replay(replay)['verified_ticks'],20)
        self.assertEqual(self.client.get(self.base+'/tests/'+job_id).status_code,403)
        other=scaffold(self.root/'other',registry=self.registry)
        other_config=json.loads((other/'agent.json').read_text())['training']
        other_headers={'Authorization':'Bearer '+other_config['token']}
        self.assertEqual(self.client.get('/api/training/'+other_config['session_id']+'/tests/'+job_id,headers=other_headers).status_code,403)
        self.assertEqual(self.client.get('/api/matches').json(),[])
        self.assertEqual(self.client.get('/api/leaderboard').json(),[])
        # Finished practice remains readable after the development window closes.
        with locked_registry(self.registry) as records:
            records[str(self.workspace)]['training']['deadline_at']=time.time()-1
        self.assertEqual(self.client.get(self.base+'/tests/'+job_id,headers=self.headers).status_code,200)

    def test_robot_practice_and_own_version_opponent(self):
        robot=scaffold(self.root/'robot','robot',7,self.registry)
        write_showcase(robot)
        start_training(robot,self.registry)
        config=json.loads((robot/'agent.json').read_text())['training']
        base='/api/training/'+config['session_id'];headers={'Authorization':'Bearer '+config['token']}
        first=self.client.post(base+'/submit',json={},headers=headers)
        self.assertEqual(first.status_code,200,first.text)
        (robot/'strategy.py').write_text('def act(obs,state):\n return {}, state\n')
        second=self.client.post(base+'/submit',json={},headers=headers).json()
        self.assertNotEqual(first.json()['version'],second['version'])
        self.assertEqual(self.client.get(base,headers=headers).json()['last_submission'],second['version'])
        response=self.client.post(base+'/tests',json={'duration':1,'opponent':first.json()['version']},headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        job=self.wait_job(response.json()['job_id'],base=base,headers=headers)
        self.assertEqual(job['status'],'finished',job)
        self.assertEqual(job['results'][0]['policy_errors'],0)

    def test_initializing_strategy_is_cancelled_at_the_total_deadline(self):
        path=self.root/'hang.py';path.write_text('while True: pass\n')
        started=time.monotonic()
        with self.assertRaisesRegex(RuntimeError,'initialize'):
            Policy(path,42,'trusted-local',deadline=time.monotonic()+.2)
        self.assertLess(time.monotonic()-started,2)

    def test_running_practice_stops_at_expiry_with_a_verifiable_partial_replay(self):
        start_training(self.workspace,self.registry)
        (self.workspace/'strategy.py').write_text('import time\ndef act(obs,state):\n time.sleep(.015)\n return {},state\n')
        with locked_registry(self.registry) as records:
            records[str(self.workspace)]['training']['deadline_at']=time.time()+1
        response=self.client.post(self.base+'/tests',json={'duration':420,'opponent':'self'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        job_id=response.json()['job_id'];job=self.wait_job(job_id)
        self.assertEqual(job['status'],'expired',job)
        self.assertEqual(len(job['results']),1,job)
        self.assertLess(job['results'][0]['time'],420)
        replay=self.root/'partial.json'
        replay.write_bytes(self.client.get(self.base+'/tests/'+job_id+'/replays/0',headers=self.headers).content)
        self.assertGreater(verify_replay(replay)['verified_ticks'],0)


if __name__=='__main__':unittest.main()
