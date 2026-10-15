"""Robot-addressed communication works in whole-team and free-battle control."""
import json
from pathlib import Path
import tempfile
import unittest
from rmuc_arena.runner import Battle,Policy
from rmuc_arena.submissions import ROOT,save_submission
from rmuc_arena.cli import verify_replay
from rmuc_arena.communication import TeamCommunication

class TeamCommunicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def team(self,name,recipient=2):
        source=self.root/(name+'.py')
        source.write_text(f'''from sdk import action,message
def act(obs,state):
    own=obs['controlled_ids']
    assert len(own)>1
    assert set(obs['message_inboxes'])==set(own)
    assert obs['messages']==[m for s in own for m in obs['message_inboxes'][s]]
    if obs['tick']==0:
        assert not obs['messages']
        return {{'1':action(messages=[message({{'intent':'look-behind','sender':1}},to={recipient}),message({{'intent':'advance'}})])}},{{'round':1}}
    elif obs['tick']==2:
        inbox=obs['message_inboxes'][str({recipient})]
        assert [m['data']['intent'] for m in inbox]==['look-behind','advance']
        assert all(m['from']==obs['team']+'-1' and m['to']==obs['team']+'-{recipient}' and m['delivery_tick']==2 for m in inbox)
        assert not obs['message_inboxes']['1']
        return {{str({recipient}):action(messages=[message({{'intent':'ack'}},to=1)])}},{{'round':2}}
    elif obs['tick']==4:
        assert [m['data']['intent'] for m in obs['message_inboxes']['1']]==['ack']
    else:
        assert not obs['messages']
    return {{}},state
''')
        path=self.root/name;save_submission(path,'team',{'team':source});return path

    def test_standard_whole_team_messages_are_delayed_scoped_and_recorded(self):
        red=self.team('red');blue=self.team('blue')
        with Battle(red,blue,duration=1,sandbox='trusted-local') as battle:
            self.assertEqual(len(battle.policies),2);self.assertEqual(battle.run()['policy_errors'],0,battle.diagnostics)
            self.assertEqual(len(battle.actions[0]['communication']),4);self.assertNotIn('communication',battle.actions[1])
            self.assertEqual(len(battle.actions[2]['communication']),2)
            self.assertNotIn('messages',battle.actions[0]['red']['1'])
            replay=self.root/'team.json';battle.save(replay);self.assertEqual(verify_replay(replay)['digest'],battle.result()['digest'])

    def test_free_whole_team_supports_recipient_instances_above_seven(self):
        policy=self.team('large',13)
        decks={'red':[ROOT/'examples/official_adaptive_3']*13,'blue':[ROOT/'examples/official_adaptive_7']}
        with Battle(None,None,duration=1,sandbox='trusted-local',decks=decks,free_team_strategies={'red':policy}) as battle:
            self.assertEqual(len(battle.policies),2);self.assertEqual(battle.run()['policy_errors'],0,battle.diagnostics)
            self.assertEqual(battle.actions[0]['communication'][0]['to'],['red-13'])

    def test_whole_team_validation_rejects_cross_team_spoofing_and_oversized_messages(self):
        with Battle(ROOT/'examples/official_team',ROOT/'examples/official_hold',duration=1,sandbox='trusted-local') as battle:obs=battle.observation('red',None)
        for index,action in enumerate([{'1':{'messages':[{'to':'blue-2','data':{}}]}}, {'1':{'messages':[{'to':'1','data':{}}]}}, {'1':{'messages':[{'to':'2','data':{},'from':'red-7'}]}}, {'1':{'messages':[{'to':'2','data':'x'*513}]}}, {'1':{'messages':[{'to':'2','data':{}}]*5}}, {'9':{'messages':[]}}]):
            with self.subTest(index=index):
                source=self.root/f'invalid-{index}.py';source.write_text(f'def act(obs,state):\n return {action!r},state\n')
                policy=Policy(source,1,'trusted-local');self.addCleanup(policy.close);self.assertIsNotNone(policy.decide(obs)[1])

    def test_reports_do_not_create_visual_contacts_or_modify_public_telemetry(self):
        with Battle(ROOT/'examples/official_team',ROOT/'examples/official_hold',duration=1,sandbox='trusted-local') as battle:
            before=battle.observation('red',[1])
            report={'enemy':'blue-4','position':[20.0,7.5],'seen_tick':0}
            battle.communication.route([('red','3',[{'to':'1','data':report}])],0,2)
            after=battle.observation('red',[1])
            self.assertEqual(after['messages'][0]['data'],report)
            self.assertEqual(after['enemies'],before['enemies']);self.assertEqual(after['referee'],before['referee']);self.assertEqual(after['robots'],before['robots'])
            self.assertEqual(battle.observation('blue',[1])['messages'],[])

    def test_delivery_order_uses_sender_instances_not_dictionary_order(self):
        routing=TeamCommunication({'red':[1,2,3,13],'blue':[1]})
        outgoing=[('red','13',[{'to':'2','data':13}]),('red','3',[{'to':'2','data':3}]),('red','1',[{'to':'2','data':1}])]
        routing.route(outgoing,0,2);self.assertEqual([m['data'] for m in routing.inboxes['red']['2']],[1,3,13]);self.assertEqual(routing.inboxes['blue']['1'],[])
