import json
from pathlib import Path
import tempfile
import time
import unittest

from fastapi.testclient import TestClient
from rmuc_arena.server import create_app
from rmuc_arena.cli import verify_replay
from rmuc_arena.store import Store
from tests.showcase_fixture import SHOWCASE_TEXT, write_showcase


class FastApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.app=create_app("trusted-local",self.root/"submissions",self.root/"data",test_mode=True)
        self.client=TestClient(self.app)
        self.addCleanup(self.app.state.arena.shutdown)

    def test_health_catalog_and_request_boundaries(self):
        self.assertEqual(self.client.get('/api/health').json()['engine'],'rust')
        self.assertEqual(self.client.get('/api/catalog').json()['official_squad']['mode'],'squad')
        self.assertEqual(self.client.post('/api/start',json={'red':'../../outside'}).status_code,409)
        self.assertEqual(self.client.post('/api/start',json={'duration':0}).status_code,422)
        self.assertEqual(self.client.post('/api/control',json={'command':'speed','speed':99}).status_code,400)
        self.assertEqual(self.client.post('/api/control',json={'command':'pause'},headers={'Origin':'https://other.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/health',headers={'Host':'evil.example'}).status_code,400)

    def test_websocket_pushes_real_rust_snapshots(self):
        with self.client.websocket_connect('/api/ws') as socket:
            message=socket.receive_json()
            self.assertEqual(message['type'],'snapshot')
            self.assertEqual(message['state']['frame']['engine'],'rust')
            # The idle arena shows the default RMUC 2027 field: five robots per team.
            self.assertEqual(len(message['state']['frame']['robots']),10)
            self.client.post('/api/control',json={'command':'speed','speed':4})
            self.assertEqual(socket.receive_json()['state']['speed'],4)

    def test_submission_compile_hash_and_version_validation(self):
        request={'name':'alpha-v2','mode':'team','entries':{'team':'def act(obs,state):\n return {},state\n'},'showcase':SHOWCASE_TEXT}
        response=self.client.post('/api/submissions',json=request)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.get('/api/catalog').json()['alpha-v2']['mode'],'team')
        self.assertEqual(self.client.post('/api/submissions',json=request).status_code,400)
        request['name']='broken';request['entries']['team']='def not valid'
        self.assertEqual(self.client.post('/api/submissions',json=request).status_code,400)
        request['name']='../outside'
        self.assertEqual(self.client.post('/api/submissions',json=request).status_code,422)

    def test_completed_match_is_persisted_replay_verifies_and_ranks_once(self):
        self.client.post('/api/control',json={'command':'speed','speed':8})
        response=self.client.post('/api/start',json={'duration':1})
        self.assertEqual(response.status_code,200,response.text)
        match_id=response.json()['match_id']
        deadline=time.monotonic()+10
        while self.app.state.arena.state()['busy'] and time.monotonic()<deadline:
            time.sleep(.02)
        record=self.client.get('/api/matches/'+match_id).json()
        self.assertEqual(record['status'],'finished')
        self.assertTrue(record['has_replay'])
        current = self.client.get('/api/replay')
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()['result']['digest'], record['result']['digest'])
        response=self.client.get('/api/replays/'+match_id)
        path=self.root/'download.json';path.write_bytes(response.content)
        self.assertEqual(verify_replay(path)['verified_ticks'],20)
        standings=self.client.get('/api/leaderboard').json()
        self.assertEqual(len(standings),0)
        self.assertTrue(record['metadata']['test_match'])
        self.app.state.arena.store.finish(match_id,record['result'])
        self.assertEqual(self.client.get('/api/leaderboard').json(),standings)
        reopened=Store(self.root/'data')
        self.assertEqual(len(reopened.matches()),1)
        self.assertEqual(reopened.leaderboard(),standings)

    def test_prematch_self_check_and_countdown_hold_the_first_frame(self):
        arena=self.app.state.arena
        arena.prematch_stages=(("self_check",.4),("countdown",30.0))
        response=self.client.post('/api/start',json={'duration':1})
        self.assertEqual(response.status_code,200,response.text)
        seen,deadline=[],time.monotonic()+15
        while time.monotonic()<deadline:
            state=arena.state()
            if state['prematch']:
                self.assertEqual(state['frame']['tick'],0)
                if not seen or seen[-1]!=state['prematch']['stage']:
                    seen.append(state['prematch']['stage'])
                if state['prematch']['stage']=='countdown':
                    break
            time.sleep(.02)
        self.assertEqual(seen,['self_check','countdown'])
        self.assertEqual(self.client.post('/api/control',json={'command':'skip_prematch'}).status_code,200)
        while arena.state()['busy'] and time.monotonic()<deadline:
            time.sleep(.02)
        state=arena.state()
        self.assertIsNone(state['prematch'])
        self.assertEqual(state['frame']['status'],'finished')


if __name__ == '__main__':
    unittest.main()
