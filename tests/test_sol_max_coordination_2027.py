"""Check public-observation cover allocation and real departures from both recovery areas."""
import copy
import importlib.util
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


class SolMaxCoordinationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('coordination_builder',ROOT/'scripts/build_gpt61_max_2027.py')
        b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
        cls.lineup=b.LINEUP;cls.policy=types.ModuleType('coordination_policy')
        with patch.dict(sys.modules,{'sdk':sdk}):exec(b.source(),cls.policy.__dict__)
        with Match(211,1,'rmuc2027',lineups=mirrored_lineups(cls.lineup,'2027')) as m:
            cls.fixture=m.observation('red')

    def test_defensive_contact_uses_only_public_enemy_fields_and_waits_for_landing(self):
        p=self.policy;o=copy.deepcopy(self.fixture);o.update(time=50.,tick=1000)
        r=next(r for r in o['robots'] if r['slot']==7)
        r.update(grounded=True,posture_ready_at=0.,posture_enhanced_time=[0.,0.,0.])
        o['enemies']=[{'id':'blue-3','role':'infantry','alive':True,'hp':200.,'max_hp':200.,
            'x':r['x']+4.,'y':r['y'],'vx':0.,'vy':0.,'invulnerable':False}]
        ctx=p.Context(o,{});memory=p.leg_memory(r,o,ctx.memory);memory['entry_done']=True
        shot={'aim':0.,'pitch':0.,'fire':False}
        with patch.object(p,'_guarded_decide',return_value=dict(shot)):
            fields=p.decide(r,ctx)
        self.assertEqual(fields['posture'],'defense')
        self.assertTrue(fields['posture_enhanced'])
        memory['nav_jump']={'kind':'road'}
        with patch.object(p,'_guarded_decide',return_value=dict(shot)):
            self.assertNotIn('posture_enhanced',p.decide(r,ctx))

    def test_a_partly_hidden_two_robot_raid_does_not_swap_the_cover_unit(self):
        p=self.policy;o=copy.deepcopy(self.fixture);o.update(time=100.,tick=2000)
        for r in o['robots']:
            if r['slot'] in (3,4,7):r.update(ammo=100,hp=r['max_hp'])
        o['enemies']=[{'id':'blue-3','role':'infantry','alive':True,'hp':200.,'max_hp':200.,'x':8.,'y':10.,'vx':-1.,'vy':0.},
            {'id':'blue-7','role':'sentry','alive':True,'hp':400.,'max_hp':400.,'x':9.,'y':9.,'vx':-1.,'vy':0.}]
        state={};p.Context(o,state)
        self.assertEqual(state['base_alarm']['slot'],4)
        o['time']=100.1;o['enemies']=o['enemies'][1:];p.Context(o,state)
        self.assertEqual(state['base_alarm']['slot'],4)

    def test_base_cover_has_priority_over_another_highland_entry(self):
        p=self.policy;o=copy.deepcopy(self.fixture);o.update(time=100.,tick=2000)
        anchor=next(r for r in o['robots'] if r['slot']==1);anchor['alive']=False
        guard=next(r for r in o['robots'] if r['slot']==4);ctx=p.Context(o,{})
        self.assertIsNone(p.highland_entry(guard,ctx))
        self.assertNotIn('sortie_queue',ctx.state)

    @unittest.skipUnless(os.environ.get("RMUC_STRATEGY_BENCHMARKS")=="1",
                         "Reference strategy outcome; run scripts/benchmark_strategy.py")
    def test_six_robots_depart_again_from_supply_and_base_without_state_injection(self):
        p=self.policy
        for origin in ('supply','base'):
            with self.subTest(origin=origin):
                states={t:{} for t in ('red','blue')};returned={};crossed={};commands={};reset=False
                with Match(211,110,'rmuc2027',lineups=mirrored_lineups(self.lineup,'2027')) as match:
                    while match.status!='finished':
                        if match.tick%2==0:
                            if match.time>=60. and not reset:
                                # This is policy memory, as cleared after recovery;
                                # all robot positions were reached through physics.
                                for state in states.values():
                                    for memory in state.get('stuck',{}).get('serial',{}).values():
                                        memory.clear();memory['last_jump']=-10.
                                reset=True
                            commands={}
                            for team,state in states.items():
                                obs=match.observation(team);ctx=p.Context(obs,state);commands[team]={}
                                for r in obs['robots']:
                                    if r['slot']==1 and origin=='base':
                                        commands[team]['1']=sdk.action(**p.max_guard(r,ctx));continue
                                    if r['slot'] not in (3,4,7):continue
                                    if obs['time']<15.:
                                        fields=p.highland_entry(r,ctx) or {'move':(0,0),'brake':True}
                                    elif obs['time']<60.:
                                        goal=p.max_supply_point(r,ctx) if origin=='supply' else p.max_local(ctx,{3:(3.8,6.95),4:(3.8,8.15),7:(2.4,9.)}[r['slot']])
                                        fields=p.max_hold(r,goal,ctx)
                                        if p.distance(r,goal)<.8:returned.setdefault(r['id'],obs['time'])
                                    else:
                                        fields=p.highland_entry(r,ctx) or {'move':(0,0),'brake':True}
                                        if p.local_point(team,(r['x'],r['y']))[0]>10.75:crossed.setdefault(r['id'],obs['time'])
                                    fields['fire']=False;commands[team][str(r['slot'])]=sdk.action(**fields)
                        match.step(commands)
                self.assertEqual(len(returned),6,returned)
                frame=match.snapshot()
                self.assertEqual(len(crossed),6,{'crossed':crossed,'remaining':[
                    {**{k:r.get(k) for k in ('id','x','y','z','heading','tipped','upright','grounded','wheel_loads_n')},
                     'serial':states[r['team']].get('stuck',{}).get('serial',{}).get(str(r['slot'])),
                     'queue':states[r['team']].get('sortie_queue')}
                    for r in frame['robots'] if r['slot'] in (3,4,7) and r['id'] not in crossed]})
                self.assertLessEqual(max(crossed.values()),105.)


if __name__=='__main__':unittest.main()
