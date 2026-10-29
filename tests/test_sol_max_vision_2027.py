"""Active vision checks using ordinary observations and physical movement."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import types
import unittest
import os
from unittest.mock import patch

from rmuc_arena import sdk
from rmuc_arena.engine import Match
from rmuc_arena.models import mirrored_lineups

ROOT=Path(__file__).resolve().parents[1]


class SolMaxVisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('vision_builder',ROOT/'scripts/build_gpt61_max_2027.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        cls.lineup=builder.LINEUP
        cls.policy=types.ModuleType('vision_policy')
        with patch.dict(sys.modules,{'sdk':sdk}):exec(builder.source(),cls.policy.__dict__)
        with Match(1,1,'rmuc2027',lineups=mirrored_lineups(cls.lineup,'2027')) as match:
            cls.fixture=match.observation('red')

    def test_empty_search_preserves_no_fire_and_does_not_add_a_firing_solution(self):
        obs=json.loads(json.dumps(self.fixture));obs['time']=20.
        r=next(r for r in obs['robots'] if r['slot']==3)
        ctx=self.policy.Context(obs,{})
        with patch.object(self.policy,'_search_weapon',return_value={'fire':False}):
            fields=self.policy.weapon(r,ctx)
        self.assertIn('aim',fields)
        self.assertFalse(fields['fire'])
        self.assertNotIn('pitch',fields)
        self.assertLessEqual(abs(fields['aim']),math.pi)

    def test_unarmed_anchor_searches_and_preserves_an_explicit_target(self):
        obs=json.loads(json.dumps(self.fixture));ctx=self.policy.Context(obs,{})
        r=next(r for r in obs['robots'] if r['slot']==1)
        with patch.object(self.policy,'_search_decide',return_value={'fire':False}):
            self.assertIn('aim',self.policy.decide(r,ctx))
        with patch.object(self.policy,'_search_decide',return_value={'aim':.3,'fire':False}):
            self.assertEqual(self.policy.decide(r,ctx)['aim'],.3)

    def test_searches_are_staggered_and_mirrored_between_teams(self):
        red=types.SimpleNamespace(team='red',time=20.)
        blue=types.SimpleNamespace(team='blue',time=20.)
        robots=[r for r in self.fixture['robots'] if r['slot'] in (3,4,7)]
        bearings=[self.policy.search_bearing(r,red) for r in robots]
        for a,b in zip(bearings,bearings[1:]):
            self.assertGreater(abs(self.policy.wrap(a-b)),1.)
        for r in robots:
            delta=self.policy.wrap(self.policy.search_bearing(r,red)-self.policy.search_bearing(r,blue))
            self.assertAlmostEqual(abs(delta),math.pi)

    def test_enhanced_attack_can_start_with_the_attack_stance_before_the_first_shot(self):
        obs=json.loads(json.dumps(self.fixture));obs.update(time=20.,tick=400)
        robot=next(r for r in obs['robots'] if r['slot']==7)
        robot.update(hp=robot['max_hp']*.6,ammo=100,posture='move',posture_ready_at=0.,
                     posture_enhanced_time=[0.,0.,0.])
        enemy=dict(robot,id='blue-3',team='blue',role='infantry',x=robot['x']+4.,invulnerable=False,targetable=True)
        obs['enemies']=[enemy];ctx=self.policy.Context(obs,{})
        pending={'aim':0.,'pitch':0.,'fire':False,'posture':'attack','posture_enhanced':False}
        with patch.object(self.policy,'_sentry_decide',return_value=pending):
            fields=self.policy._search_decide(robot,ctx)
        self.assertEqual(fields['posture'],'attack')
        self.assertTrue(fields['posture_enhanced'])
        self.assertFalse(fields['fire'])

    def test_sentry_does_not_spend_attack_budget_on_a_search_direction(self):
        obs=json.loads(json.dumps(self.fixture));obs.update(time=20.,tick=400)
        robot=next(r for r in obs['robots'] if r['slot']==7)
        robot.update(ammo=300,posture_ready_at=0.,posture_enhanced_time=[0.,0.,0.])
        obs['enemies']=[dict(robot,id='blue-3',team='blue',x=robot['x']+4.,invulnerable=False)]
        ctx=self.policy.Context(obs,{})
        with patch.object(self.policy,'_sentry_decide',return_value={'aim':0.,'fire':False}):
            fields=self.policy._search_decide(robot,ctx)
        self.assertFalse(fields.get('posture_enhanced',False))

    def test_exhausted_attack_budget_is_not_reactivated(self):
        obs=json.loads(json.dumps(self.fixture));obs.update(time=20.,tick=400)
        robot=next(r for r in obs['robots'] if r['slot']==7)
        robot.update(ammo=300,posture_ready_at=0.,posture_enhanced_time=[15.,0.,0.])
        obs['enemies']=[dict(robot,id='blue-3',team='blue',x=robot['x']+4.,invulnerable=False)]
        ctx=self.policy.Context(obs,{})
        with patch.object(self.policy,'_sentry_decide',return_value={'aim':0.,'pitch':0.,'fire':True}):
            fields=self.policy._search_decide(robot,ctx)
        self.assertFalse(fields.get('posture_enhanced',False))

    def test_distant_contact_does_not_spend_the_close_attack_budget(self):
        obs=json.loads(json.dumps(self.fixture));obs.update(time=20.,tick=400)
        robot=next(r for r in obs['robots'] if r['slot']==7)
        robot.update(ammo=300,posture_ready_at=0.,posture_enhanced_time=[0.,0.,0.])
        obs['enemies']=[dict(robot,id='blue-3',team='blue',x=robot['x']+7.,invulnerable=False)]
        ctx=self.policy.Context(obs,{})
        with patch.object(self.policy,'_sentry_decide',return_value={'aim':0.,'pitch':0.,'fire':True}):
            fields=self.policy._search_decide(robot,ctx)
        self.assertFalse(fields.get('posture_enhanced',False))

    def test_rear_intruder_is_seen_by_the_anchors_real_camera(self):
        self._assert_rear_camera_probe(full_route=False)

    @unittest.skipUnless(os.environ.get("RMUC_STRATEGY_BENCHMARKS")=="1",
                         "Reference strategy outcome; run scripts/benchmark_strategy.py")
    def test_reference_intruder_crosses_the_field_and_is_seen(self):
        self._assert_rear_camera_probe(full_route=True)

    def _assert_rear_camera_probe(self, full_route):
        p=self.policy
        route=[(11.8,5.3),(16.2,3.),(16.2,1.),(19.7,1.),(19.7,3.4),
               (20.,4.85),(23.7,4.85),(26.8,4.4),(27.,6.4)]
        # The sensor regression starts behind the base and walks to the card. The
        # full-field route is kept unchanged as a separate strategy benchmark.
        scenario=None if full_route else {'robots':{
            'red-1':{'x':3.8,'y':8.15,'heading':0.,'aim':0.},
            'blue-7':{'x':1.,'y':10.5,'heading':-math.pi/2}}}
        if not full_route:route=[(27.,6.4)]
        results={}
        for search in (False,True):
            states={team:{} for team in ('red','blue')};arrived=None;seen=None
            with Match(1,40 if full_route else 12,'rmuc2027',lineups=mirrored_lineups(self.lineup,'2027'),training_scenario=scenario) as match:
                commands={}
                while match.status!='finished':
                    if match.tick%2==0:
                        commands={};red_obs=None;probe=None
                        for team in ('red','blue'):
                            obs=match.observation(team);ctx=p.Context(obs,states[team]);commands[team]={}
                            if team=='red':
                                red_obs=obs
                                anchor=next(r for r in obs['robots'] if r['slot']==1)
                                # Keep chassis motion identical in this camera A/B.
                                # The reactive cover controller may otherwise turn
                                # or relocate the anchor after another camera sees
                                # the probe, confounding the search comparison.
                                fields=p._previous_base_guard(anchor,ctx)
                                if search:fields.setdefault('aim',p.search_bearing(anchor,ctx))
                                if not full_route:
                                    fields={'move':(0,0),'brake':True,'heading':0.,
                                            'aim':p.search_bearing(anchor,ctx) if search else 0.}
                                commands[team]['1']=sdk.action(**fields)
                            else:
                                probe=next(r for r in obs['robots'] if r['slot']==7)
                                fields=p.highland_entry(probe,ctx) if full_route else None
                                if fields is None:fields=p.max_route(probe,ctx,'vision_probe',route)
                                commands[team]['7']=sdk.action(**fields)
                            for robot in obs['robots']:
                                if robot['slot'] not in (3,4):continue
                                fields=p.highland_entry(robot,ctx)
                                if fields is None:
                                    goal=p.max_local(ctx,(10.8,9.25) if robot['slot']==4 else (11.5,9.7))
                                    fields=p.max_hold(robot,goal,ctx)
                                commands[team][str(robot['slot'])]=sdk.action(**fields)
                        if p.distance(probe,(1.,8.6))<.35:
                            if arrived is None:arrived=red_obs['time']
                            if 'blue-7' in red_obs['vision']['1']['enemies'] and seen is None:
                                seen=red_obs['time']
                    match.step(commands)
            self.assertIsNotNone(arrived,{'message':'Probe did not physically reach the rear card',
                'probe':{k:probe.get(k) for k in ('x','y','z','heading','tipped','upright','grounded','wheel_loads_n')},
                'serial':states['blue'].get('stuck',{}).get('serial',{}).get('7'),
                'route':states['blue'].get('max_routes',{}).get('7')})
            results[search]=(arrived,seen)
        self.assertIsNone(results[False][1])
        self.assertIsNotNone(results[True][1])
        self.assertLessEqual(results[True][1]-results[True][0],3.5)


if __name__=='__main__':unittest.main()
