"""The application owns one offline example; other strategies belong to Arena-Strategies."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rmuc_arena.catalog import strategy_index
from rmuc_arena.paths import ROOT
from rmuc_arena.submissions import scaffold, save_submission, load_submission
from rmuc_arena.training import TrainingService


class ExamplesPolicyTests(unittest.TestCase):
    def test_only_sol_max_is_shipped_as_a_strategy(self):
        self.assertEqual({p.name for p in (ROOT/'examples').iterdir() if p.is_dir() and p.name!='__pycache__'}, {'gpt61_sol_max_2027'})
        self.assertEqual({p.parent.name for p in (ROOT/'examples').rglob('manifest.json')}, {'gpt61_sol_max_2027'})
        with patch.dict(os.environ):
            os.environ.pop('RMUC_TEST_STRATEGIES',None)
            bundled={v['key'] for v in strategy_index().values() if v['source']=='bundled'}
        self.assertEqual(bundled,{'gpt61_sol_max_2027'})

    def test_new_workspaces_do_not_require_a_downloaded_strategy(self):
        with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ):
            os.environ.pop('RMUC_TEST_STRATEGIES',None)
            root=Path(temporary)
            for season in ('2026','2027'):
                for mode,robot in [('team',None),('distributed',None),('robot',3),('adaptive',3)]:
                    path=root/(season+'-'+mode)
                    scaffold(path,mode,robot,registry=root/'registry.json',season=season)
                    source=next(path.glob('strategy.py'),None) or next(path.glob('robot_*.py'))
                    compile(source.read_bytes(),str(source),'exec')

    def test_single_robot_self_practice_has_offline_teammates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'robot.py'
            source.write_text('def act(obs,state):\n return {"3":{"aim":.3}},state\n')
            service=TrainingService(root/'practice',sandbox='trusted-local')
            self.addCleanup(service.shutdown)
            for season,count in [('2026',6),('2027',5)]:
                candidate=root/(season+'-candidate')
                save_submission(candidate,'robot',{'3':source},3,season=season)
                with patch.object(service,'example',side_effect=ValueError('no downloaded strategies')):
                    result=service._squad(candidate,root/(season+'-squad'))
                _,entries=load_submission(result)
                self.assertEqual(len(entries),count)
                self.assertEqual(entries['3'].read_bytes(),source.read_bytes())
                self.assertNotEqual(entries['4'].read_bytes(),source.read_bytes())
