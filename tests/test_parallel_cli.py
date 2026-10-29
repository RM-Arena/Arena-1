import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from rmuc_arena.batch import execute_jobs
from rmuc_arena.cli import main
from rmuc_arena.cli_options import make_spec, swap_spec
from rmuc_arena.replays import verify_replay
from rmuc_arena.runner import Battle, LatestFrameLog
from rmuc_arena.submissions import ROOT, save_submission


class ParallelCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        source=self.root/'source.py'
        source.write_text('def act(obs,state):\n return {}, state\n')
        self.red=self.root/'red';self.blue=self.root/'blue'
        save_submission(self.red,'team',{'team':source},season='2027')
        save_submission(self.blue,'team',{'team':source},season='2027')

    def spec(self,seed):
        return make_spec({'red':str(self.red),'blue':str(self.blue),'seed':seed,'duration':2,'trusted_local':True},index={})

    def test_parallel_workers_are_isolated_and_match_sequential_replays(self):
        specs=[self.spec(73),swap_spec(self.spec(74))]
        output=self.root/'parallel';rows=[]
        summary=execute_jobs(specs,output,workers=2,replays='all',on_result=rows.append)
        self.assertEqual(summary['succeeded'],2)
        self.assertEqual(len({r['worker_pid'] for r in rows}),2)
        self.assertLess(max(r['started_at'] for r in rows),min(r['finished_at'] for r in rows))
        for row,spec in zip(sorted(rows,key=lambda r:r['index']),specs):
            with Battle(**spec['options'],record=False) as battle:
                result=battle.run()
                self.assertEqual(row['digest'],result['digest'])
            self.assertEqual(verify_replay(row['replay'])['digest'],row['digest'])
        before=(output/'results.jsonl').read_bytes()
        resumed=[]
        execute_jobs(specs,output,workers=1,replays='all',resume=True,on_result=resumed.append)
        self.assertEqual(resumed,[])
        self.assertEqual((output/'results.jsonl').read_bytes(),before)
        with self.assertRaisesRegex(ValueError,'Cannot resume'):
            execute_jobs([self.spec(999)],output,workers=1,replays='all',resume=True)

    def test_a_bad_match_does_not_stop_other_jobs_and_errors_are_resumable(self):
        invalid=self.spec(75)
        invalid['options']['team_lineup']={'1':2711,'3':2731,'4':2731,'6':2761,'7':2731}
        rows=[];output=self.root/'errors'
        summary=execute_jobs([invalid,self.spec(76)],output,workers=2,on_result=rows.append)
        self.assertEqual(summary['failed'],1)
        self.assertEqual(summary['succeeded'],1)
        self.assertEqual(sorted(r['status'] for r in rows),['error','ok'])
        self.assertFalse((output/'replays').exists())
        self.assertEqual(len((output/'results.jsonl').read_text().splitlines()),2)
        with (output/'results.jsonl').open('ab') as f:f.write(b'{"job_id":')
        retried=[]
        execute_jobs([invalid,self.spec(76)],output,workers=1,resume=True,on_result=retried.append)
        self.assertEqual([r['index'] for r in retried],[0])
        self.assertEqual(len((output/'results.jsonl').read_text().splitlines()),3)

    def test_unrecorded_battles_keep_no_spool_or_action_history(self):
        with Battle(**self.spec(77)['options'],record=False) as battle:
            battle.run()
            self.assertIsInstance(battle.frames,LatestFrameLog)
            self.assertEqual(len(battle.frames),1)
            self.assertEqual(battle.actions,[])
            with self.assertRaisesRegex(ValueError,'disabled'):battle.save(self.root/'no.json')

    def test_command_line_supports_jsonl_explicit_seeds_and_resume(self):
        output=self.root/'cli'
        command=[sys.executable,'-m','rmuc_arena','run','--red',str(self.red),'--blue',str(self.blue),
                 '--trusted-local','--seeds','21','22','--swap-sides','--workers','2','--duration','1','--output',str(output)]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stderr)
        rows=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(rows),5)
        self.assertEqual({(r['seed'],r['swapped']) for r in rows[:-1]}, {(21,False),(21,True),(22,False),(22,True)})
        self.assertEqual(rows[-1]['type'],'summary')
        result=subprocess.run(command+['--resume'],cwd=ROOT,capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(result.stdout.splitlines()),1)

    def test_sources_are_frozen_for_the_whole_run(self):
        rows=[]
        def change_source(row):
            rows.append(row)
            if len(rows)==1:(self.red/'strategy.py').write_text('def act(obs,state):\n raise RuntimeError("edited")\n')
        summary=execute_jobs([self.spec(80),self.spec(80)],self.root/'frozen',workers=1,on_result=change_source)
        self.assertEqual(summary['succeeded'],2)
        self.assertEqual(rows[0]['digest'],rows[1]['digest'])

    def test_job_files_require_boolean_trust_flags(self):
        with self.assertRaisesRegex(ValueError,'boolean'):
            make_spec({'red':str(self.red),'blue':str(self.blue),'trusted_local':'false'},index={})

    def test_legacy_single_replay_remains_one_json_result(self):
        replay=self.root/'single.json'
        command=[sys.executable,'-m','rmuc_arena','headless','--red',str(self.red),'--blue',str(self.blue),
                 '--trusted-local','--duration','1','--output',str(replay)]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stderr)
        row=json.loads(result.stdout)
        self.assertEqual(verify_replay(replay)['digest'],row['digest'])

    def test_match_timeout_is_a_failed_job_and_fail_fast_preserves_journal(self):
        rows=[]
        summary=execute_jobs([self.spec(81),self.spec(82)],self.root/'timeout',workers=1,
                             match_timeout=.00001,fail_fast=True,on_result=rows.append)
        self.assertEqual(rows[0]['status'],'timeout')
        self.assertEqual(summary['failed'],1)
        self.assertEqual(summary['unfinished'],1)

    def test_spec_defaults_follow_season_and_decks_swap_controllers(self):
        standard=make_spec({'season':'2026','duration':1,'seed':1},index={
            'claude_opus55_xhigh_team':{'path':ROOT/'examples/claude_opus55_xhigh_team'},
            'claude_opus55_xhigh_hold':{'path':ROOT/'examples/claude_opus55_xhigh_hold'}})
        self.assertEqual(standard['options']['map_name'],'rmuc2026')
        deck=make_spec({'mode':'deck','seed':1,'red_deck':[str(ROOT/'examples/claude_opus55_xhigh_2027_adaptive_2731')],
                        'blue_deck':[str(ROOT/'examples/claude_opus55_xhigh_2027_adaptive_2771')],
                        'red_control':'team','red_team_strategy':str(self.red)},index={})
        swapped=swap_spec(deck)
        self.assertEqual(swapped['options']['decks']['red'],deck['options']['decks']['blue'])
        self.assertEqual(swapped['options']['free_team_strategies'],{'blue':str(self.red.resolve())})


if __name__=='__main__':unittest.main()
