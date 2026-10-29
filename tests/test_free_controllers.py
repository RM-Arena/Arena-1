"""Whole-team/independent free battle and durable saved lineups."""
from tests.strategy_fixtures import STRATEGIES
import json
from pathlib import Path
import tempfile
import time
import unittest
from fastapi.testclient import TestClient
from rmuc_arena.runner import Battle
from rmuc_arena.server import create_app
from rmuc_arena.submissions import ROOT,save_submission
from rmuc_arena.cli import verify_replay

class FreeControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        source=self.root/'team.py';source.write_text('''def act(obs,state):
    own={str(r['slot']) for r in obs['robots']}
    assert own==set(obs['controlled_ids'])=={str(s) for s in obs['roster'][obs['team']]}
    assert all(r['team']==obs['team'] for r in obs['robots'])
    assert not obs.get('messages')
    return {s:{'aim':.25} for s in own},(state or 0)+1
''')
        self.team=self.root/'submissions/free-team';save_submission(self.team,'team',{'team':source})
        self.decks={'red':[STRATEGIES / 'claude_opus55_xhigh_adaptive_3']*3,'blue':[STRATEGIES / 'claude_opus55_xhigh_adaptive_7']*2}
        self.registry=self.root/'registry.json'

    def app(self):
        app=create_app('trusted-local',self.root/'submissions',self.root/'data',test_mode=True,workspace_registry=self.registry)
        self.addCleanup(app.state.training.shutdown);self.addCleanup(app.state.arena.shutdown)
        return app,TestClient(app)

    def test_each_team_can_use_whole_team_or_independent_control_with_dynamic_roster(self):
        for sides in [('red',),('blue',),('red','blue')]:
            with self.subTest(sides=sides),Battle(None,None,duration=1,sandbox='trusted-local',decks=self.decks,free_team_strategies={t:self.team for t in sides}) as battle:
                self.assertEqual(len(battle.policies),sum(1 if t in sides else len(self.decks[t]) for t in self.decks))
                for t,slots,policy in battle.policies:
                    self.assertEqual(slots is None,t in sides)
                self.assertEqual(battle.metadata['match_mode'],'deck');result=battle.run();self.assertEqual(result['policy_errors'],0,battle.diagnostics)
                for t in sides:self.assertEqual(battle.metadata['teams'][t]['mode'],'team')
                replay=self.root/'mixed.json';battle.save(replay);self.assertEqual(verify_replay(replay)['digest'],result['digest'])

    def test_api_accepts_mixed_control_and_rejects_unavailable_or_wrong_strategy(self):
        app,client=self.app();body={'mode':'deck','duration':1,'red_deck':['claude_opus55_xhigh_adaptive_3']*3,'blue_deck':['claude_opus55_xhigh_adaptive_7']*2,'red_control':'team','red_team_strategy':'free-team'}
        for key in ['missing','claude_opus55_xhigh_adaptive_3','claude_opus55_xhigh_squad']:
            self.assertEqual(client.post('/api/start',json={**body,'red_team_strategy':key}).status_code,409)
        response=client.post('/api/start',json=body);self.assertEqual(response.status_code,200,response.text)
        # A one-second match still has to be built and ticked to completion; a slow runner needs
        # well over ten seconds for that, so wait for the arena instead of timing it.
        until=time.monotonic()+120
        while app.state.arena.busy and time.monotonic()<until:time.sleep(.02)
        self.assertFalse(app.state.arena.busy);self.assertIsNone(app.state.arena.error)
        record=client.get('/api/matches/'+response.json()['match_id']).json();self.assertEqual(record['result']['policy_errors'],0)
        self.assertEqual(record['metadata']['match_mode'],'deck');self.assertEqual(record['metadata']['teams']['red']['mode'],'team');self.assertEqual(record['metadata']['teams']['blue']['mode'],'adaptive')
        self.assertEqual(client.get('/api/leaderboard').json(),[])

    def test_named_presets_persist_and_restore_all_controls_without_starting_a_match(self):
        app,client=self.app();body={'name':'轮足突击','decks':{'red':['claude_opus55_xhigh_adaptive_3']*3,'blue':['claude_opus55_xhigh_adaptive_7']*2},'controllers':{'red':{'mode':'team','strategy':'free-team'},'blue':{'mode':'independent','strategy':'claude_opus55_xhigh_hold'}}}
        response=client.post('/api/deck-presets',json=body);self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(app.state.arena.busy);self.assertEqual(client.post('/api/deck-presets',json=body).status_code,409)
        presets=client.get('/api/deck-presets').json();self.assertEqual(presets[0]['decks'],body['decks']);self.assertEqual(presets[0]['controllers'],body['controllers'])
        changed={**body,'replace':True,'decks':{'red':['claude_opus55_xhigh_adaptive_103'],'blue':['claude_opus55_xhigh_adaptive_6']}}
        self.assertEqual(client.post('/api/deck-presets',json=changed).status_code,200)
        restarted,other=self.app();self.assertEqual(other.get('/api/deck-presets').json()[0]['decks'],changed['decks'])
        self.assertEqual(other.get('/api/deck-presets').json()[0]['controllers'],body['controllers'])
        for invalid in [{**body,'name':' '},{**body,'name':'bad','decks':{'red':['missing'],'blue':['claude_opus55_xhigh_adaptive_7']}},{**body,'name':'bad','controllers':{'red':{'mode':'team','strategy':'missing'},'blue':{'mode':'independent'}}}]:
            self.assertEqual(other.post('/api/deck-presets',json=invalid).status_code,400)
