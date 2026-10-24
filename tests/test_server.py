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
        health=self.client.get('/api/health').json()
        self.assertEqual(health['engine'],'rust')
        # The cockpit's trigger guard reads the per-round heat from the same rulebook profile.
        self.assertEqual(health['heat']['2027']['17mm'],10)
        self.assertEqual(health['heat']['2027']['42mm'],100)
        self.assertEqual(self.client.get('/api/catalog').json()['claude_opus55_xhigh_squad']['mode'],'squad')
        self.assertEqual(self.client.post('/api/start',json={'red':'../../outside'}).status_code,409)
        self.assertEqual(self.client.post('/api/start',json={'duration':0}).status_code,422)
        self.assertEqual(self.client.post('/api/control',json={'command':'speed','speed':99}).status_code,400)
        self.assertEqual(self.client.post('/api/control',json={'command':'pause'},headers={'Origin':'https://other.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/health',headers={'Host':'evil.example'}).status_code,400)

    def test_websocket_pushes_real_rust_snapshots(self):
        with self.client.websocket_connect('/api/ws') as socket:
            # The static half of the idle frame arrives first, even while `match_id` is None.
            static=socket.receive_json()
            self.assertEqual(static['type'],'static')
            self.assertIn('arena',static['state']['frame'])
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

    def test_highlight_windows_return_only_the_frames_the_reel_plays(self):
        self.client.post('/api/control',json={'command':'speed','speed':8})
        response=self.client.post('/api/start',json={'duration':1})
        self.assertEqual(response.status_code,200,response.text)
        match_id=response.json()['match_id']
        deadline=time.monotonic()+15
        while self.app.state.arena.state()['busy'] and time.monotonic()<deadline:
            time.sleep(.02)
        response=self.client.post('/api/highlights',json={'match_id':match_id,'at':[.2,.6],'before':.1,'seconds':.3})
        self.assertEqual(response.status_code,200,response.text)
        payload=response.json()
        # Two windows of 0.3 s at a 0.05 s tick, and nothing else: the client must never receive a
        # whole match just to cut four clips out of it.
        self.assertEqual(len(payload['windows']),2)
        self.assertEqual([window['count'] for window in payload['windows']],[6,6])
        self.assertEqual(payload['windows'][1]['start'],6)
        self.assertEqual(len(payload['frames']),12)
        self.assertIn('arena',payload['static'])
        # The frames arrive without their static half; the client merges it once into each window.
        self.assertNotIn('arena',payload['frames'][0])
        self.assertIn('robots',payload['frames'][0])
        self.assertFalse(self.client.post('/api/highlights',json={'match_id':'other','at':[.2]}).status_code==200)

    def test_prematch_self_check_and_countdown_hold_the_first_frame(self):
        arena=self.app.state.arena
        arena.prematch_stages=(("self_check",2.0),("countdown",.4))
        response=self.client.post('/api/start',json={'duration':1})
        self.assertEqual(response.status_code,200,response.text)
        seen,deadline=[],time.monotonic()+15
        while time.monotonic()<deadline:
            state=arena.state()
            if state['prematch']:
                self.assertEqual(state['frame']['tick'],0)
                if not seen or seen[-1]!=state['prematch']['stage']:
                    seen.append(state['prematch']['stage'])
                if state['prematch']['stage']=='self_check':
                    # The walk-on is skippable, and skipping it must not skip the countdown.
                    self.assertEqual(self.client.post('/api/control',json={'command':'skip_prematch'}).status_code,200)
                if state['prematch']['stage']=='countdown':
                    break
            time.sleep(.02)
        self.assertEqual(seen,['self_check','countdown'])
        # 5-4-3-2-1 always runs in full: a skip that lands after it starts is refused.
        refused=self.client.post('/api/control',json={'command':'skip_prematch'})
        self.assertEqual(refused.status_code,400,refused.text)
        self.assertIn('倒计时不可跳过',refused.text)
        self.assertEqual(arena.state()['prematch']['stage'],'countdown')
        while arena.state()['busy'] and time.monotonic()<deadline:
            time.sleep(.02)
        state=arena.state()
        self.assertIsNone(state['prematch'])
        self.assertEqual(state['frame']['status'],'finished')

    def test_the_self_check_clock_can_be_extended_so_no_intro_card_is_cut_short(self):
        arena=self.app.state.arena
        arena.prematch_stages=(("self_check",3.0),("countdown",.4))
        self.assertEqual(self.client.post('/api/start',json={'duration':1}).status_code,200)
        deadline,extended=time.monotonic()+15,None
        while time.monotonic()<deadline:
            state=arena.state()
            prematch=state['prematch']
            if prematch and prematch['stage']=='self_check' and extended is None:
                # Asking for more self-check time grows the clock *and* the announced length, so the
                # client's "time already spent" — and with it the intro it has already shown — holds.
                spent=prematch['duration']-prematch['remaining']
                self.assertEqual(self.client.post('/api/control',json={'command':'extend_prematch','seconds':4}).status_code,200)
                deadline2=time.monotonic()+2
                while time.monotonic()<deadline2:
                    grown=arena.state()['prematch']
                    if grown and grown['duration']>prematch['duration']:
                        extended=grown
                        break
                    time.sleep(.02)
                self.assertIsNotNone(extended,'the extension never reached the announced clock')
                self.assertAlmostEqual(extended['duration'],prematch['duration']+4,delta=.2)
                self.assertAlmostEqual(extended['duration']-extended['remaining'],spent,delta=.3)
                self.assertGreater(extended['remaining'],prematch['remaining'])
            if prematch and prematch['stage']=='countdown':
                break
            time.sleep(.02)
        self.assertIsNotNone(extended)
        # The countdown cannot be stretched, and a request after the walk-on is refused.
        refused=self.client.post('/api/control',json={'command':'extend_prematch','seconds':4})
        self.assertEqual(refused.status_code,400,refused.text)
        self.assertIn('赛前自检已结束',refused.text)
        while arena.state()['busy'] and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertIsNone(arena.state()['prematch'])

    def test_the_intro_floor_keeps_every_segment_on_screen_for_two_seconds(self):
        from rmuc_arena.server import INTRO,intro_minimum_seconds,intro_seconds
        self.assertEqual(INTRO['min_shot'],2.0)
        self.assertEqual(intro_minimum_seconds(10),28)
        for robots in (2,10,12,40):
            self.assertGreaterEqual(intro_seconds(robots),intro_minimum_seconds(robots))


if __name__ == '__main__':
    unittest.main()
