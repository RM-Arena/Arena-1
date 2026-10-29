"""Regression checks for physical routing, cover and firing lanes."""
import importlib.util
import math
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from rmuc_arena import sdk
from rmuc_arena.engine import Match
from rmuc_arena.models import mirrored_lineups

ROOT=Path(__file__).resolve().parents[1]


class SolMaxNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('nav_builder',ROOT/'scripts/build_gpt61_max_2027.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        cls.lineup=builder.LINEUP
        cls.policy=types.ModuleType('navigation_policy')
        with patch.dict(sys.modules,{'sdk':sdk}):exec(builder.source(),cls.policy.__dict__)
        with Match(seed=1,duration=1,map_name='rmuc2027',lineups=mirrored_lineups(builder.LINEUP,'2027')) as match:
            cls.fixture=match.observation('red')

    def obs(self):
        import copy
        return copy.deepcopy(self.fixture)

    def test_narrow_highland_rim_is_not_a_walkable_segment(self):
        graph=self.policy._SERIAL_ROADMAPS['red']
        self.assertFalse(graph.clear((11.5,7.5),(8.,7.5)))
        self.assertTrue(graph.clear((11.5,9.7),(16.,9.7)))

    def test_route_from_highland_to_supply_has_a_bounded_exit(self):
        graph=self.policy._SERIAL_ROADMAPS['red']
        point=(11.5,7.5);goal=(1.4,13.)
        for _ in range(30):
            waypoint=graph.waypoint(point,goal)
            self.assertIsNotNone(waypoint)
            point=waypoint[2] if waypoint[0]=='jump' else waypoint
            if math.dist(point,goal)<.2:break
        self.assertLess(math.dist(point,goal),.2)

    def test_hump_escape_holds_heading_until_the_whole_body_is_clear(self):
        obs=self.obs();obs['time']=20.
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=6.,y=14.,heading=0.)
        memory={};first=self.policy.serial_escape(r,obs,memory)
        self.assertLess(first['move'][0],0.)
        r['x']=4.9;obs['time']=20.5
        held=self.policy.serial_escape(r,obs,memory)
        self.assertEqual(held['heading'],0.)
        self.assertLess(held['move'][0],0.)
        r['x']=4.5;obs['time']=21.
        self.assertIsNone(self.policy.serial_escape(r,obs,memory))

    def test_inflated_clearance_escape_cannot_cut_through_a_wall(self):
        graph=self.policy._SERIAL_ROADMAPS['red']
        self.assertFalse(graph.clear((1.12,7.5),(4.,7.5),True))

    def test_base_cover_points_are_inside_the_actual_card(self):
        obs=self.obs();zone=next(z for z in obs['arena']['zones'] if z['id']=='red_base')
        for p in ((1.05,7.5),(1.5,8.9),(2.5,9.),(3.85,8.05),(3.85,7.5),(3.85,6.95),(2.5,6.),(1.7,6.)):
            self.assertTrue(sdk.point_in_polygon(*p,zone['polygon']),p)
        body=next(z for z in obs['arena']['forbidden'] if z['kind']=='base' and z['x']<14)
        self.assertTrue(self.policy.base_body_blocks((1.,7.5),(3.85,7.5),body))
        self.assertFalse(self.policy.base_body_blocks((1.,5.),(4.,5.),body))

    def test_spacing_escapes_the_muzzle_dead_zone_without_blocking_the_sentry(self):
        obs=self.obs();obs.update(time=150.,tick=3000)
        r=next(r for r in obs['robots'] if r['slot']==3)
        ally=next(r for r in obs['robots'] if r['slot']==7)
        r.update(x=17.1,y=5.8,z=.35,last_raw_zones=['blue_central'])
        ally.update(x=17.4,y=8.1,z=.35)
        enemy=dict(r,id='blue-4',x=17.15,y=6.7,team='blue',invulnerable=False,targetable=True)
        obs['enemies']=[enemy]
        ctx=self.policy.Context(obs,{})
        self.policy.max_hold(r,(17.1,5.8),ctx)
        chosen=ctx.state['spacing']['3']['goal']
        self.assertGreater(self.policy.distance(enemy,chosen),1.5)
        self.assertGreater(self.policy.distance(ally,chosen),.8)

    def test_cover_transit_does_not_leave_the_base_card_for_capture_duration(self):
        with Match(seed=1,duration=12,map_name='rmuc2027',lineups=mirrored_lineups(self.lineup,'2027')) as match:
            state={};longest=0.;gap=0.
            while match.status!='finished':
                obs=match.observation('red');obs['time']+=30.
                robot=next(r for r in obs['robots'] if r['slot']==1)
                robot.update(hp=200.,last_damage_time=obs['time']-.1)
                enemy=dict(robot,id='blue-3',team='blue',role='infantry',x=4.3,y=7.5,invulnerable=False,targetable=True)
                obs['enemies']=[enemy]
                ctx=self.policy.Context(obs,state);ctx.budget=0.
                fields=self.policy.max_guard(robot,ctx)
                frame=match.step({'red':{'1':sdk.action(**fields)}})
                inside='red-1' in frame['zones']['red_base']['occupants']
                gap=0. if inside else gap+.05;longest=max(longest,gap)
            self.assertLess(longest,4.5)

    def test_public_motion_tracker_bounds_acceleration(self):
        obs=self.obs();obs.update(time=10.,tick=200)
        r=dict(next(r for r in obs['robots'] if r['slot']==3),id='blue-3',team='blue',vx=0.,vy=0.)
        obs['enemies']=[r];state={};self.policy.Context(obs,state)
        obs['time']=10.1;r['vx']=1.
        ctx=self.policy.Context(obs,state)
        self.assertGreater(ctx.obs['enemies'][0]['_accel'][0],0.)
        self.assertLessEqual(math.hypot(*ctx.obs['enemies'][0]['_accel']),6.)
        self.assertNotIn('_accel',obs['enemies'][0])

    def test_wounded_infantry_uses_a_nearby_fully_controlled_outpost(self):
        obs=self.obs();obs.update(time=150.,tick=3000)
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=11.2,y=9.7,hp=30.,weak=True)
        obs['positions']['red_outpost'].update(controller='red',control='full')
        ctx=self.policy.Context(obs,{})
        with patch.object(self.policy,'max_homeward',return_value={'move':(0,0)}) as move:
            self.policy.max_fighter(r,ctx)
        destination=move.call_args.args[1]
        card=next(z for z in obs['arena']['zones'] if z['id']=='red_outpost')
        self.assertTrue(sdk.point_in_polygon(*destination,card['polygon']))
        self.assertLess(self.policy.distance(r,destination),3.)

    def test_outpost_recovery_finishes_without_a_supply_detour(self):
        obs=self.obs();obs.update(time=150.,tick=3000)
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=11.4,y=10.65,hp=r['max_hp'],weak=False,last_raw_zones=['red_outpost'])
        obs['positions']['red_outpost'].update(controller='red',control='full')
        ctx=self.policy.Context(obs,{'max_recovery':{'3':True}})
        self.policy.max_fighter(r,ctx)
        self.assertFalse(ctx.state['max_recovery']['3'])

    def test_safe_base_anchor_does_not_recall_the_mobile_infantry(self):
        obs=self.obs();obs.update(time=100.,tick=2000)
        heavy=next(r for r in obs['robots'] if r['slot']==1)
        heavy.update(hp=heavy['max_hp'],last_damage_time=-99.)
        r=next(r for r in obs['robots'] if r['slot']==3)
        obs['enemies']=[dict(r,id='blue-3',team='blue',x=3.8,y=8.,invulnerable=False)]
        obs['positions']['red_base'].update(controller='red',active=['red','blue'])
        ctx=self.policy.Context(obs,{})
        with patch.object(self.policy,'_support_parent',return_value={'fire':False}) as parent:
            self.policy.support_fighter(r,ctx)
        parent.assert_called_once()
        self.assertNotIn('base_threat_until',ctx.state)

    def test_home_sentry_with_relief_collects_its_free_rations(self):
        obs=self.obs();obs.update(time=150.,tick=3000)
        sentry=next(r for r in obs['robots'] if r['slot']==7)
        guard=next(r for r in obs['robots'] if r['slot']==4)
        sentry.update(x=10.8,y=6.,ammo=0,last_raw_zones=['red_central'])
        guard.update(x=10.8,y=9.2,hp=guard['max_hp'],last_raw_zones=['red_central'])
        obs['zones']['red_central'].update(owner='red',occupants=[sentry['id'],guard['id']])
        obs['positions']['red_outpost'].update(controller='blue',control='full')
        ctx=self.policy.Context(obs,{'home_sentry':True})
        with patch.object(self.policy,'max_homeward',return_value={'move':(0,0)}) as move:
            self.policy.front_response(sentry,ctx)
        self.assertTrue(ctx.state['max_recovery']['7'])
        card=next(z for z in obs['arena']['zones'] if z['id']=='red_supply')
        self.assertTrue(sdk.point_in_polygon(*move.call_args.args[1],card['polygon']))

    def test_kerb_escape_ignores_road_ramps_and_has_a_bounded_duration(self):
        obs=self.obs();obs['time']=40.
        r=next(r for r in obs['robots'] if r['slot']==4)
        memory={'nav_stall':{'4':{'until':41.}}}
        with patch.object(self.policy,'_unwedge_parent',return_value={'move':(0,0)}):
            r.update(x=8.3,y=12.7,weak=False)
            self.policy.drive(r,(10.8,9.25),obs,memory)
            self.assertNotIn('rim_hop',self.policy.leg_memory(r,obs,memory))

            r.update(x=10.03,y=5.7,grounded=True)
            fields=self.policy.drive(r,(10.8,9.25),obs,memory)
            self.assertEqual(fields['leg_height'],.12)
            self.assertNotIn('jump',fields)
            obs['time']=40.8
            self.assertEqual(self.policy.drive(r,(10.8,9.25),obs,memory)['jump'],1.)
            obs['time']=43.
            self.policy.drive(r,(2.5,12.4),obs,memory)
            self.assertNotIn('rim_hop',self.policy.leg_memory(r,obs,memory))

    def test_unloaded_wheels_on_a_ramp_get_a_bounded_crouch_and_hop(self):
        obs=self.obs();obs['time']=40.
        r=next(r for r in obs['robots'] if r['slot']==7)
        r.update(x=11.88,y=12.62,grounded=True,upright=.714,wheel_loads_n=[0.,0.,0.,0.])
        memory={'nav_stall':{'7':{'until':41.}}}
        with patch.object(self.policy,'_unwedge_parent',return_value={'move':(0,0)}):
            fields=self.policy.drive(r,(11.8,14.),obs,memory)
            self.assertEqual(fields['leg_height'],.12)
            self.assertNotIn('jump',fields)
            obs['time']=40.8
            self.assertEqual(self.policy.drive(r,(11.8,14.),obs,memory)['jump'],1.)
            obs['time']=43.
            self.policy.drive(r,(11.8,14.),obs,memory)
            self.assertNotIn('rim_hop',self.policy.leg_memory(r,obs,memory))

    def test_road_portal_can_reverse_without_a_half_turn_at_the_boundary(self):
        obs=self.obs();obs['time']=40.
        r=next(r for r in obs['robots'] if r['slot']==7)
        r.update(x=8.3,y=13.55,heading=math.pi/2,grounded=True)
        memory={};m=self.policy.leg_memory(r,obs,memory)
        m['nav_jump']={'start':(8.3,13.55),'end':(8.3,11.5),'prep':(8.3,13.55),
                       'kind':'road','phase':0,'began':39.,'settled':39.,'lock':'test'}
        fields=self.policy.drive(r,(2.5,12.4),obs,memory)
        self.assertAlmostEqual(fields['heading'],math.pi/2)
        obs['time']=40.1
        fields=self.policy.drive(r,(2.5,12.4),obs,memory)
        self.assertAlmostEqual(fields['heading'],math.pi/2)
        self.assertLess(fields['move'][1],0.)

    def test_fire_readiness_respects_the_first_gimbal_microstep(self):
        obs=self.obs();ctx=self.policy.Context(obs,{})
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(ammo=100,heat=0.,angular_velocity=[0.,0.,0.])
        yaw,pitch=self.policy.barrel_angles(r)
        with patch.object(self.policy,'_motion_weapon',return_value={'aim':yaw+.02,'pitch':pitch+.01,'fire':False}):
            self.assertTrue(self.policy.weapon(r,ctx)['fire'])
        with patch.object(self.policy,'_motion_weapon',return_value={'aim':yaw+.15,'pitch':pitch+.01,'fire':False}):
            self.assertFalse(self.policy.weapon(r,ctx)['fire'])

    def test_turn_settling_has_a_finite_window(self):
        obs=self.obs();obs['time']=30.;state={}
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(heading=0.,x=4.,y=5.)
        self.policy.Context(obs,state)
        self.assertEqual(self.policy.pointed_move(r,(4.,8.),2.)['move'],(0,0))
        obs['time']=30.8;self.policy.Context(obs,state)
        self.assertGreater(math.hypot(*self.policy.pointed_move(r,(4.,8.),2.)['move']),0.)

    def test_stationary_turn_can_back_away_from_a_road_boundary(self):
        obs=self.obs();r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=8.3,y=14.5,heading=math.pi/2,vx=0.,vy=0.)
        memory={}
        with patch.object(self.policy,'_route_drive',return_value={'move':(0,0),'heading':0.}):
            for t in (10.,11.,12.,12.4):
                obs['time']=t
                fields=self.policy.drive(r,(2.5,12.4),obs,memory)
        self.assertLess(fields['move'][1],0.)
        self.assertAlmostEqual(fields['heading'],math.pi/2)

    def test_road_portal_launches_once_then_brakes_its_landing(self):
        obs=self.obs();obs['time']=40.
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=8.3,y=12.3,heading=math.pi/2,grounded=True,vx=0.,vy=0.)
        memory={};m=self.policy.leg_memory(r,obs,memory)
        m['nav_jump']={'start':(8.3,11.5),'end':(8.3,13.55),'prep':(8.3,11.5),
                       'kind':'road','phase':1,'began':39.,'lock':'test','heading':math.pi/2}
        self.assertEqual(self.policy.drive(r,(8.3,13.55),obs,memory)['jump'],1.)
        obs['time']=41.5;r['y']=12.6
        self.assertNotIn('jump',self.policy.drive(r,(8.3,13.55),obs,memory))
        obs['time']=42.;r['y']=13.3
        self.assertEqual(self.policy.drive(r,(8.3,13.55),obs,memory)['move'],(0,0))
        obs['time']=42.8;self.policy.drive(r,(8.3,13.55),obs,memory)
        self.assertNotIn('nav_jump',m)

    def test_descending_road_jump_starts_before_the_drop(self):
        obs=self.obs();obs['time']=40.
        r=next(r for r in obs['robots'] if r['slot']==7)
        r.update(x=8.3,y=13.2,heading=math.pi/2,grounded=True,vx=0.,vy=0.)
        memory={};m=self.policy.leg_memory(r,obs,memory)
        m['nav_jump']={'start':(8.3,13.55),'end':(8.3,11.5),'prep':(8.3,13.55),
                       'kind':'road','phase':1,'began':39.,'lock':'test','heading':math.pi/2}
        fields=self.policy.drive(r,(2.5,12.4),obs,memory)
        self.assertEqual(fields['jump'],1.)
        self.assertLess(fields['move'][1],0.)

    def test_paid_healing_is_skipped_on_a_free_supply_card(self):
        obs=self.obs();obs.update(time=150.,tick=3000)
        obs['teams']['red']['resources']=400
        r=next(r for r in obs['robots'] if r['slot']==1)
        r.update(hp=r['max_hp']*.4,last_shot_time=-99.,last_damage_time=-99.,
                 last_raw_zones=['red_supply'])
        ctx=self.policy.Context(obs,{})
        self.assertNotIn('remote_heal',self.policy.max_logistics(r,ctx))
        self.assertEqual(ctx.budget,400)
        r['last_raw_zones']=['red_base']
        self.assertTrue(self.policy.max_logistics(r,ctx)['remote_heal'])

    def test_empty_local_robot_can_buy_a_small_affordable_batch(self):
        obs=self.obs();obs.update(time=150.,tick=3000)
        obs['teams']['red']['resources']=25
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(ammo=0,pending_ammo=[],last_raw_zones=['red_base'])
        ctx=self.policy.Context(obs,{})
        self.assertEqual(self.policy.max_logistics(r,ctx)['buy_ammo'],{'amount':20,'remote':False})
        self.assertEqual(ctx.budget,5)

    def test_full_health_robot_resumes_without_reaching_supply(self):
        obs=self.obs();obs.update(time=200.,tick=4000)
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=17.1,y=5.8,hp=r['max_hp'],weak=False,grounded=True,last_raw_zones=['blue_central'])
        ctx=self.policy.Context(obs,{'max_recovery':{'3':True}})
        self.policy.max_fighter(r,ctx)
        self.assertFalse(ctx.state['max_recovery']['3'])

    def test_recovery_does_not_cancel_a_committed_jump(self):
        obs=self.obs();obs.update(time=200.,tick=4000)
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(hp=r['max_hp'],weak=False,grounded=True)
        ctx=self.policy.Context(obs,{'max_recovery':{'3':True}})
        self.policy.leg_memory(r,obs,ctx.memory)['nav_jump']={'phase':1}
        with patch.object(self.policy,'max_homeward',return_value={'move':(0,0)}):
            self.policy.max_fighter(r,ctx)
        self.assertTrue(ctx.state['max_recovery']['3'])

    def test_blocked_translation_prefers_to_reverse_when_both_axes_are_clear(self):
        obs=self.obs();r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=12.,y=9.7,heading=0.,vx=0.,vy=0.)
        memory={}
        with patch.object(self.policy,'_route_drive',return_value={'move':(1.,0.),'heading':0.}):
            for t in (10.,11.,12.,12.4):
                obs['time']=t
                fields=self.policy.drive(r,(16.,9.7),obs,memory)
        self.assertLess(fields['move'][0],0.)


if __name__=='__main__':unittest.main()
