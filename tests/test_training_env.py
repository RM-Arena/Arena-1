import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from rmuc_arena.env import ArenaEnv
from rmuc_arena.vector_env import VectorArena, VectorEnvError
from rmuc_arena.replays import verify_replay
from rmuc_arena.submissions import ROOT,save_submission


class TrainingEnvTests(unittest.TestCase):
    def test_new_commands_and_live_bandwidth_apply_to_external_and_saved_actors(self):
        messages = [{'to':'4','data':'x'*100}, {'to':'4','data':'x'*200}]
        actions = {'1':{'assembly_extract':True,'assembly_cancel':True},
                   '3':{'climb':True,'yaw_boost':True,'messages':messages}}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'policy.py'
            source.write_text(f'def act(obs,state):\n return {actions!r},state\n')
            opponent=root/'opponent';save_submission(opponent,'team',{'team':source},season='2027')
            with ArenaEnv(duration=1,opponent=opponent,sandbox='trusted-local') as env:
                env.reset(41)
                # Model a damaged base's live allowance without changing the protocol ceiling.
                with patch('rmuc_arena.env.message_byte_limit',return_value=128):
                    state=env.step({'red':actions})
                for team in ('red','blue'):
                    inbox=state['observations'][team]['message_inboxes']['4']
                    self.assertEqual([m['data'] for m in inbox],['x'*100])
                self.assertEqual(state['info']['policy_errors'],0)
                self.assertTrue(any('over 128 bytes' in line for line in env.policies[0][1].logs))
                with self.assertRaisesRegex(ValueError,'<=512 bytes'):
                    env.step({'red':{'3':{'messages':[{'to':'4','data':'x'*512}]}}})

    def test_vector_matches_serial_and_partial_reset_reuses_simulators(self):
        with VectorArena(2,duration=1,compact=True) as vector:
            initial=vector.reset([17,18])
            self.assertNotEqual(initial[0]['info']['worker_pid'],initial[1]['info']['worker_pid'])
            self.assertIn('arena',initial[0]['observations']['red'])
            for _ in range(10):states=vector.step([{},{}])
            for i,seed in enumerate((17,18)):
                with ArenaEnv(duration=1) as serial:
                    serial.reset(seed)
                    for _ in range(10):expected=serial.step({})
                self.assertEqual(states[i]['info']['digest'],expected['info']['digest'])
                self.assertTrue(states[i]['terminated'])
                self.assertFalse(states[i]['truncated'])
                self.assertEqual(sum(states[i]['rewards'].values()),0)
                self.assertNotIn('arena',states[i]['observations']['red'])
            reset=vector.reset([19],env_ids=[1])[0]
            self.assertEqual(reset['info']['simulator_pid'],initial[1]['info']['simulator_pid'])
            self.assertEqual(reset['info']['episode'],2)
            self.assertEqual(reset['info']['tick'],0)
            response=vector.request('step',[{},{}])
            self.assertFalse(response[0]['ok'])
            self.assertTrue(response[1]['ok'])
            processes=list(vector.processes)
        self.assertTrue(all(not p.is_alive() for p in processes))

    def test_actions_and_messages_keep_team_boundaries_and_truncations_verify(self):
        with tempfile.TemporaryDirectory() as temporary:
            with ArenaEnv(duration=2,max_steps=2,record=True,full_state=True) as environment:
                environment.reset(31)
                with self.assertRaisesRegex(ValueError,'unowned'):environment.step({'red':{'999':{}}})
                with self.assertRaisesRegex(ValueError,'only by red and blue'):environment.step({'referee':[]})
                self.assertEqual(environment.match.tick,0)
                state=environment.step({'red':{'3':{'messages':[{'to':'4','data':{'go':1}}]}}})
                self.assertEqual(state['observations']['red']['message_inboxes']['4'][0]['data'],{'go':1})
                self.assertEqual(state['observations']['blue']['messages'],[])
                # A trainer can mutate privileged output without changing simulator state.
                state['info']['state']['teams']['red']['score']=100000
                end=environment.step({})
                self.assertTrue(end['truncated']);self.assertFalse(end['terminated'])
                self.assertEqual(end['rewards'],{'red':0,'blue':0})
                path=Path(temporary)/'episode.json'
                environment.save_replay(path)
            self.assertEqual(verify_replay(path)['digest'],end['info']['digest'])

    def test_opponent_private_state_resets_and_remains_a_saved_controller(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'policy.py'
            source.write_text('def act(obs,state):\n n=(state or 0)+1\n return {"3":{"aim":n/10}},n\n')
            path=root/'opponent';save_submission(path,'team',{'team':source},season='2027')
            with ArenaEnv(duration=1,opponent=path,sandbox='trusted-local') as env:
                env.reset(41);pid=env.policies[0][1].process.pid
                with self.assertRaisesRegex(ValueError,'override'):env.step({'blue':{'3':{}}})
                env.step({});self.assertEqual(env.policies[0][1].calls,1)
                env.step({});self.assertEqual(env.policies[0][1].calls,2)
                env.reset(41)
                self.assertNotEqual(env.policies[0][1].process.pid,pid)
                env.step({});self.assertEqual(env.policies[0][1].calls,1)

    def test_reset_recovers_a_crashed_simulator(self):
        with ArenaEnv(duration=1) as env:
            first=env.reset(61)
            env.match.process.kill();env.match.process.wait(timeout=5)
            next_episode=env.reset(61)
            self.assertNotEqual(first['info']['simulator_pid'],next_episode['info']['simulator_pid'])
            self.assertEqual(next_episode['info']['tick'],0)
            self.assertEqual(env.step({})['info']['tick'],2)

    @unittest.skipIf(os.name=='nt','POSIX SIGTERM lifecycle; Windows normal close is covered separately')
    def test_sigterm_cleans_up_vector_and_simulator_children(self):
        process=subprocess.Popen([sys.executable,'-m','rmuc_arena','env','--num-envs','2'],
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=ROOT)
        try:
            self.assertEqual(json.loads(process.stdout.readline())['type'],'ready')
            process.stdin.write('{"op":"reset","seeds":[71,72]}\n');process.stdin.flush()
            response=json.loads(process.stdout.readline())
            pids=[r['result']['info'][key] for r in response['results'] for key in ('worker_pid','simulator_pid')]
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=20)
            self.assertEqual(process.returncode,130,process.stderr.read())
            for pid in pids:
                with self.assertRaises(ProcessLookupError):os.kill(pid,0)
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=10)
            process.stdin.close();process.stdout.close();process.stderr.close()

    def test_jsonl_protocol_reports_errors_without_losing_framing(self):
        request='\n'.join(json.dumps(v) for v in [
            {'id':'r','op':'reset','seeds':[51,52]},
            {'id':'bad','op':'step','actions':[{},{}],'env_ids':[0,0]},
            {'id':'s','op':'step','actions':[{},{}]},
            {'id':'end','op':'close'}])+'\n'
        result=subprocess.run([sys.executable,'-m','rmuc_arena','env','--num-envs','2','--max-steps','1'],
                              input=request,capture_output=True,text=True,cwd=ROOT,timeout=60)
        self.assertEqual(result.returncode,0,result.stderr)
        rows=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(rows[0]['type'],'ready')
        self.assertEqual([r['id'] for r in rows[1:]],['r','bad','s','end'])
        self.assertFalse(rows[2]['ok'])
        self.assertTrue(all(r['result']['truncated'] for r in rows[3]['results']))


if __name__=='__main__':unittest.main()
