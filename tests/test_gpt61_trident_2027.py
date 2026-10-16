"""Behavioral checks for the triple serial-leg assault submission."""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from rmuc_arena import sdk
from rmuc_arena.engine import Match
from rmuc_arena.models import mirrored_lineups, robot_models
from rmuc_arena.submissions import load_submission
from rmuc_arena.showcase import load_profile, load_showcase

ROOT = Path(__file__).resolve().parents[1]


class Trident2027Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('trident_builder', ROOT / 'scripts/build_gpt61_trident_2027.py')
        cls.builder=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)
        cls.policy=types.ModuleType('trident_policy')
        with patch.dict(sys.modules, {'sdk':sdk}):
            exec(compile(cls.builder.source(), 'trident_policy.py', 'exec'), cls.policy.__dict__)
        with Match(seed=43, duration=1, map_name='rmuc2027',
                   lineups=mirrored_lineups(cls.builder.LINEUP, '2027')) as match:
            cls.observations={side:match.observation(side) for side in ('red','blue')}

    def obs(self, side='red'):
        return json.loads(json.dumps(self.observations[side]))

    def test_three_actual_serial_leg_models_and_standard_submission(self):
        models=robot_models()
        self.assertEqual([self.builder.LINEUP[s] for s in ('3','4','7')], [305,305,2772])
        for slot in ('3','4','7'):
            self.assertEqual(models[str(self.builder.LINEUP[slot])]['leg_type'], 'serial')
        folder=ROOT / 'examples' / self.builder.NAME
        manifest,_=load_submission(folder)
        self.assertEqual(manifest['team_lineup'], self.builder.LINEUP)
        self.assertEqual(load_profile(folder)['agent']['model'], 'gpt-6.1-sol-xhigh')
        self.assertEqual(load_showcase(folder)['generated_by'], load_profile(folder)['agent'])
        for filename,data in self.builder.output().items():
            self.assertEqual((folder / filename).read_bytes(), data)

    def test_owned_finite_actions_on_both_sides(self):
        for side in ('red','blue'):
            obs=self.obs(side)
            commands,state=self.policy.act(obs,None)
            self.assertEqual(set(commands), set(obs['controlled_ids']))
            self.assertLess(len(json.dumps(state,allow_nan=False)),256*1024)
            json.dumps(commands,allow_nan=False)
            for r in obs['robots']:
                if r['role'] in ('infantry','sentry'):
                    self.assertTrue(self.policy.serial_leg(r,obs))

    def test_healthy_units_keep_forward_assignments_even_with_large_lead(self):
        for side in ('red','blue'):
            obs=self.obs(side)
            enemy=self.policy.other(side)
            obs.update(time=140.,tick=2800,remaining=280.)
            obs['teams'][side]['control']=100.
            obs['teams'][enemy]['control']=0.
            ctx=self.policy.Context(obs,{})
            self.assertFalse(ctx.hold_lead)
            # Existing home point starts controlled. Force it explicitly in this fixture.
            ctx.positions[f'{side}_outpost']['controller']=side
            for r in obs['robots']:
                if r['role'] not in ('infantry','sentry'):continue
                goal=self.policy.assault_goal(r,ctx)
                self.assertGreater(self.policy.local_point(side,goal)[0],14.)

    def test_recovery_latches_until_eighty_percent(self):
        obs=self.obs();ctx=self.policy.Context(obs,{})
        r=next(r for r in obs['robots'] if r['slot']==3)
        r['hp']=r['max_hp']*.31
        self.assertIsNotNone(self.policy.recovery_goal(r,ctx))
        r['hp']=r['max_hp']*.60
        self.assertIsNotNone(self.policy.recovery_goal(r,ctx))
        r['hp']=r['max_hp']*.80
        self.assertIsNone(self.policy.recovery_goal(r,ctx))

    def test_opening_jump_requires_ground_and_cooldown(self):
        obs=self.obs();obs['time']=6.
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=8.9,y=7.,heading=0.,grounded=True)
        ctx=self.policy.Context(obs,{})
        m=self.policy.leg_memory(r,obs,ctx.memory)
        m['entry']={'phase':3,'since':5.,'began':1.2}
        self.assertEqual(self.policy.highland_entry(r,ctx)['jump'],1.)
        self.assertNotIn('jump',self.policy.highland_entry(r,ctx))
        ctx.time=8.;r['grounded']=False
        self.assertNotIn('jump',self.policy.highland_entry(r,ctx))

    def test_failed_entry_exits_instead_of_jumping_forever(self):
        obs=self.obs();obs['time']=30.
        r=next(r for r in obs['robots'] if r['slot']==3)
        ctx=self.policy.Context(obs,{})
        self.policy.leg_memory(r,obs,ctx.memory)['entry']={'phase':3,'since':2.,'began':1.2}
        self.assertIsNone(self.policy.highland_entry(r,ctx))

    def test_tip_pause_allows_automatic_self_righting(self):
        obs=self.obs();obs.update(time=6.,tick=120)
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(tipped=True,x=8.9,y=7.)
        commands,_=self.policy.act(obs,{})
        self.assertEqual(commands['3']['move'],[0,0])
        self.assertFalse(commands['3']['fire'])
        self.assertNotIn('jump',commands['3'])
        self.assertNotIn('power',commands['3'])

    def test_sdk_backoff_keeps_its_embedded_heading(self):
        obs=self.obs();r=next(r for r in obs['robots'] if r['slot']==3)
        move=sdk._HeldMove((-.4,0.),r['heading'])
        with patch.object(self.policy,'_core_drive',return_value={'move':move}):
            fields=self.policy.drive(r,(8.,6.),obs,{})
        self.assertEqual(fields['heading'],r['heading'])
        self.assertEqual(fields['move'],move)

    def test_road_escape_reverses_away_from_field_boundary(self):
        for side in ('red','blue'):
            obs=self.obs(side)
            r=next(r for r in obs['robots'] if r['slot']==3)
            x,y=self.policy.local_point(side,(6.3,14.5))
            r.update(x=x,y=y,heading=1.5707963267948966 if side=='red' else -1.5707963267948966)
            fields=self.policy.road_exit(r,obs)
            self.assertIsNotNone(fields)
            self.assertEqual(fields['heading'],r['heading'])
            self.assertAlmostEqual(sum(v*v for v in fields['move']),1.)
            self.assertNotIn('power',fields)
            self.assertLess(fields['move'][1] if side=='red' else -fields['move'][1],0.)

    def test_enemy_road_escape_also_uses_full_command(self):
        obs=self.obs('red');r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=21.7,y=.5,heading=-1.5707963267948966)
        fields=self.policy.road_exit(r,obs)
        self.assertIsNotNone(fields)
        self.assertGreater(fields['move'][1],0.)
        self.assertAlmostEqual(sum(v*v for v in fields['move']),1.)

    def test_revive_resets_opening_attempt(self):
        obs=self.obs();ctx=self.policy.Context(obs,{})
        r=next(r for r in obs['robots'] if r['slot']==3)
        m=self.policy.leg_memory(r,obs,ctx.memory)
        m.update(entry_done=True,entry={'phase':3,'since':1.,'began':1.})
        r['alive']=False
        self.policy.decide(r,ctx)
        self.assertNotIn('entry_done',m)
        self.assertNotIn('entry',m)

if __name__=='__main__':unittest.main()
