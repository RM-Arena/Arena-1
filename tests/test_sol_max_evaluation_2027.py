"""Check that native-hardware validation really uses both registered lineups."""
from tests.strategy_fixtures import STRATEGIES
import json
import csv
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from scripts.evaluate_sol_max_2027 import play

ROOT=Path(__file__).resolve().parents[1]


class SolMaxEvaluationTests(unittest.TestCase):
    def test_cancelled_evaluation_closes_its_isolated_policy_sessions(self):
        with tempfile.TemporaryDirectory(prefix='sol-max-cancel-') as folder:
            ready=Path(folder)/'ready.json'
            stop=Path(folder)/'stop'
            script='''
import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from rmuc_arena import runner
Original=runner.Battle
class TrackedBattle(Original):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        Path(sys.argv[2]).write_text(json.dumps([p.process.pid for _,_,p in self.policies]))
runner.Battle=TrackedBattle
from scripts.evaluate_sol_max_2027 import play
root=Path(sys.argv[1])
from tests.strategy_fixtures import STRATEGIES
from rmuc_arena.paths import ROOT
play((str(ROOT / 'examples/gpt61_sol_max_2027'),str(STRATEGIES/'dsv41_1017_pair'),1,'red',420,None,False))
'''
            env=dict(os.environ,RMUC_EVAL_STOP_FILE=str(stop))
            process=subprocess.Popen([sys.executable,'-c',script,str(ROOT),str(ready)],cwd=ROOT,env=env,
                stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,start_new_session=True)
            try:
                deadline=time.monotonic()+30.
                while not ready.exists() and process.poll() is None and time.monotonic()<deadline:
                    time.sleep(.05)
                self.assertTrue(ready.exists(),'Evaluation did not initialize')
                workers=json.loads(ready.read_text())
                stop.write_text('stop\n')
                process.communicate(timeout=10.)
                self.assertNotEqual(process.returncode,0)
                for pid in workers:
                    if os.name == 'nt':
                        # Windows os.kill(pid, 0) is not a process-existence probe.
                        listing=subprocess.check_output(['tasklist','/FI',f'PID eq {pid}','/FO','CSV','/NH'],text=True)
                        self.assertFalse(any(len(row)>1 and row[1]==str(pid) for row in csv.reader(listing.splitlines())),listing)
                    else:
                        with self.assertRaises(ProcessLookupError):os.kill(pid,0)
            finally:
                if process.poll() is None:
                    stop.write_text('stop\n');process.kill();process.communicate()

    def test_native_hardware_is_not_rebound_to_the_candidate(self):
        candidate=ROOT / 'examples/gpt61_sol_max_2027'
        opponent=STRATEGIES / 'dsv41_1017_pair'
        own=json.loads((candidate/'manifest.json').read_text())
        other=json.loads((opponent/'manifest.json').read_text())
        self.assertNotEqual(own['team_lineup'],other['team_lineup'])
        record=play((str(candidate),str(opponent),1,'red',1,None,True))
        self.assertTrue(record['native_hardware'])
        self.assertTrue(record['valid'],record['diagnostics'])
        actual=record['actual_lineups']
        self.assertEqual({str(x['slot']):x['model'] for x in actual['red']},own['team_lineup'])
        self.assertEqual({str(x['slot']):x['model'] for x in actual['blue']},other['team_lineup'])


if __name__=='__main__':unittest.main()
