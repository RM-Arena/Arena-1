"""Exercise the real two-frame heat budget while geometry is held constant."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from rmuc_arena import sdk
from rmuc_arena.engine import Match
from rmuc_arena.models import mirrored_lineups

ROOT=Path(__file__).resolve().parents[1]


class SolMaxThermalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('thermal_builder',ROOT/'scripts/build_gpt61_max_2027.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        cls.lineup=builder.LINEUP
        cls.policy=types.ModuleType('thermal_policy')
        with patch.dict(sys.modules,{'sdk':sdk}):exec(builder.source(),cls.policy.__dict__)

    def test_defense_stance_sustains_fire_without_an_overheat_lock(self):
        p=self.policy
        with Match(211,10,'rmuc2027',lineups=mirrored_lineups(self.lineup,'2027')) as match:
            commands={};state={};overheats=[];peak=0.
            while match.status!='finished':
                if match.tick%2==0:
                    obs=match.observation('red')
                    robot=next(r for r in obs['robots'] if r['slot']==7)
                    obs['enemies']=[{'id':'blue-3','role':'infantry','alive':True,'hp':200.,
                        'x':robot['x']+2.,'y':robot['y'],'z':robot['z'],'vx':0.,'vy':0.}]
                    ctx=p.Context(obs,state)
                    yaw,pitch=p.barrel_angles(robot)
                    # Isolate thermal control from target acquisition. The actual
                    # robot, cooldown, heat and posture use the ordinary engine.
                    with patch.object(p,'max_shot_clear',return_value=True), \
                            patch.object(p,'firing_solution',return_value=(yaw,pitch)):
                        fields=p.weapon(robot,ctx)
                    fields.update(posture='defense',posture_enhanced=True)
                    commands={'red':{'7':sdk.action(**fields)}}
                frame=match.step(commands)
                robot=next(r for r in frame['robots'] if r['id']=='red-7')
                peak=max(peak,robot['heat'])
                overheats.extend(e for e in frame['events'] if e['type']=='overheat')
                self.assertFalse(robot['overheated'])
            self.assertFalse(overheats)
            self.assertLessEqual(peak,robot['max_heat'])
            self.assertGreaterEqual(300-robot['ammo'],30)


if __name__=='__main__':unittest.main()
