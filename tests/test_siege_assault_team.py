from tests.strategy_fixtures import STRATEGIES
import contextlib
import importlib.util
import io
import json
import math
import sys
import unittest
from unittest.mock import patch

from rmuc_arena.worker import ACTIONS_LIMIT, SOURCE_LIMIT, STATE_LIMIT
from rmuc_arena import sdk
from rmuc_arena.engine import Match
from rmuc_arena.models import mirrored_lineups
from rmuc_arena.submissions import ROOT, load_submission

LINEUP = {"1": 1, "2": 2, "3": 305, "4": 305, "6": 6, "7": 301}


class SiegeAssaultTeamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("siege_test", STRATEGIES / "siege_assault_team/strategy.py")
        cls.strategy = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"sdk": sdk}):
            spec.loader.exec_module(cls.strategy)

    def observation(self, team="red"):
        with Match(lineups=mirrored_lineups(LINEUP)) as match:
            return match.observation(team)

    def test_manifest_and_initial_commands_fit_the_runtime(self):
        manifest, _ = load_submission(STRATEGIES / "siege_assault_team")
        self.assertEqual(manifest["mode"], "team")
        self.assertEqual(manifest["team_lineup"], LINEUP)
        self.assertLessEqual((STRATEGIES / "siege_assault_team/strategy.py").stat().st_size, SOURCE_LIMIT)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            actions, state = self.strategy.act(self.observation(), None)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(set(actions), {"1", "2", "3", "4", "6", "7"})
        self.assertLessEqual(len(json.dumps(state, allow_nan=False).encode()), STATE_LIMIT)
        self.assertLessEqual(len(json.dumps(actions, allow_nan=False).encode()), ACTIONS_LIMIT)

    def test_rescue_continues_until_fully_upright(self):
        S=self.strategy;obs=self.observation()
        obs.update(tick=2000,time=100)
        obs['teams']['red']['completed_difficulties']=[1,2]
        engineer=next(r for r in obs['robots'] if r['slot']==2)
        # The serial-leg infantry (3, 4) right themselves; the tunnel infantry needs the arm.
        target=next(r for r in obs['robots'] if r['slot']==7)
        target.update(x=engineer['x']+2,y=engineer['y'],tipped=True,upright=0)
        S.MEM.clear()
        with patch.object(S,'go',return_value=((.3,0),False)):
            for time in (100,100.1,101,104):
                obs['time']=time
                self.assertEqual(S.engineer(S.Ctx(obs,{}),engineer).get('rescue'),7)
            target.update(tipped=False,upright=.7)
            self.assertEqual(S.engineer(S.Ctx(obs,{}),engineer).get('rescue'),7)
            target.update(upright=1)
            self.assertNotIn('rescue',S.engineer(S.Ctx(obs,{}),engineer))

    def test_midgame_hero_aims_at_a_reachable_base_beyond_eleven_metres(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2400,time=120)
        obs['outposts']['blue']['hp']=0
        r=next(r for r in obs['robots'] if r['slot']==1)
        r.update(x=S.HERO_SPOT[0],y=S.HERO_SPOT[1],deployed=True,ammo=20)
        S.MEM.clear()
        with patch.object(S,'ballistic_reachable',return_value=True),patch.object(S,'shoot',return_value={}) as shoot:
            S.hero(S.Ctx(obs,{}),r)
        target=shoot.call_args.args[2]
        self.assertEqual(target['kind'],'base')
        self.assertGreater(S.dist(S.pos(r),S.pos(target)),11)
        self.assertTrue(shoot.call_args.kwargs['fire_ok'])

    def test_tipped_infantry_waits_for_the_engineer_before_paid_revival(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2400,time=120)
        obs['teams']['red']['resources']=1000
        r=next(r for r in obs['robots'] if r['slot']==4)
        r.update(alive=False,hp=0,tipped=True,death_time=119,respawn_required=50,respawn_progress=0)
        S.MEM.clear()
        self.assertFalse(S.infantry(S.Ctx(obs,{}),r).get('revive'))
        self.assertTrue(S.infantry(S.Ctx(obs,{'_rescue_revive':4}),r).get('revive'))

    def test_hero_and_engineer_can_exit_the_road_to_the_supply_area(self):
        S=self.strategy
        for team in ('red','blue'):
            ctx=S.Ctx(self.observation(team),{})
            x,y=ctx.p(10.3,13.4)
            for slot in (1,2):
                r=dict(ctx.robots[slot],x=x,y=y)
                self.assertEqual(S.deck_waypoint(ctx,r,{},ctx.p(1.7,12.1)),ctx.p(10.0,14.25))

    def test_completed_road_navigation_restarts_after_falling_to_the_floor(self):
        S=self.strategy
        for team in ('red','blue'):
            ctx=S.Ctx(self.observation(team),{})
            x,y=ctx.p(13.0,13.9);r=dict(ctx.robots[2],x=x,y=y)
            memory={'deck':[(S.DECK_CHAIN[0],S.DECK_CHAIN[-1]),len(S.DECK_CHAIN)]}
            waypoint=S.deck_waypoint(ctx,r,memory,ctx.p(13.34,6.84))
            self.assertEqual(waypoint,ctx.p(*S.DECK_CHAIN[0]))

    def test_a_weak_engineer_returns_to_the_own_supply_area(self):
        S=self.strategy
        for team in ('red','blue'):
            obs=self.observation(team);obs.update(tick=2400,time=120)
            S.MEM.clear();ctx=S.Ctx(obs,{})
            r=ctx.robots[2];r.update(weak=True,hp=25)
            with patch.object(S,'go',return_value=((.3,0),False)) as go:
                command=S.engineer(ctx,r)
            self.assertEqual(go.call_args.args[2],ctx.p(1.7,12.1))
            self.assertNotIn('assembly',command)
            self.assertNotIn('rescue',command)

    def test_third_tech_window_takes_priority_over_a_distant_rescue(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2400,time=120)
        obs['teams']['red']['completed_difficulties']=[1,2]
        S.MEM.clear();ctx=S.Ctx(obs,{})
        r=ctx.robots[2];r.update(carried_units=1)
        target=ctx.robots[4];target.update(x=r['x']+4,y=r['y'],tipped=True,upright=0)
        with patch.object(S,'go',return_value=((.3,0),False)):
            command=S.engineer(ctx,r)
        self.assertEqual(command.get('assembly'),3)
        self.assertNotIn('rescue',command)

    def test_hero_can_push_when_the_engineer_misses_third_tech(self):
        S=self.strategy;obs=self.observation();obs.update(tick=5200,time=260,remaining=160)
        obs['outposts']['blue']['hp']=0
        obs['teams']['red']['completed_difficulties']=[1,2]
        r=next(r for r in obs['robots'] if r['slot']==1);r.update(ammo=10)
        S.MEM.clear();self.assertTrue(S.push_ok(S.Ctx(obs,{}),r))

    def test_open_armour_triggers_a_late_push_without_an_escort(self):
        S=self.strategy;obs=self.observation();obs.update(tick=6700,time=335,remaining=85)
        obs['outposts']['blue']['hp']=0;obs['bases']['blue']['armor_open']=True
        r=next(r for r in obs['robots'] if r['slot']==1)
        r.update(ammo=10,hp=r['max_hp']*.5)
        S.MEM.clear();self.assertTrue(S.push_ok(S.Ctx(obs,{}),r))

    def test_midgame_infantry_pursues_a_hero_in_the_enemy_half(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2400,time=120)
        r=next(r for r in obs['robots'] if r['slot']==3);r.update(x=11.3,y=6.7,ammo=100)
        obs['enemies']=[{'id':'blue-1','role':'hero','x':23,'y':7.5,'z':0,'alive':True,'hp':200}]
        S.MEM.clear();m=S.MEM.setdefault(3,{'fly_done':True})
        with patch.object(S,'go',return_value=((.4,0),False)) as go,patch.object(S,'shoot',return_value={}):
            S.leg_infantry(S.Ctx(obs,{}),r,m,{},0)
        self.assertGreater(go.call_args.args[2][0],19)

    def test_backup_raider_finishes_its_flank_after_the_first_raider_revives(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2000,time=100)
        S.MEM.clear();ctx=S.Ctx(obs,{})
        r=ctx.robots[4];r.update(ammo=100)
        ctx.robots[3]['alive']=False
        with patch.object(S,'fly_route',return_value={'move':(1,0)}) as fly,patch.object(S,'shoot',return_value={}):
            S.leg_infantry(ctx,r,ctx.mem(4),{},1)
            ctx.mem(4)['fly']={'phase':1}
            ctx.robots[3]['alive']=True;ctx.t=101
            S.leg_infantry(ctx,r,ctx.mem(4),{},1)
        self.assertEqual(fly.call_count,2)

    def test_a_moving_hero_keeps_its_heading_control_under_fire(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2400,time=120)
        S.MEM.clear();ctx=S.Ctx(obs,{})
        r=ctx.robots[1];r['last_damage_time']=119.9
        command={'move':(.7,.2)}
        S.evade(ctx,r,command)
        self.assertNotIn('yaw_rate',command)
        self.assertEqual(command['move'],(.7,.2))

    def test_hero_clears_a_fortress_guard_before_attacking_a_closed_base(self):
        S=self.strategy;obs=self.observation();obs.update(tick=5000,time=250)
        obs['outposts']['blue']['hp']=0
        obs['enemies']=[{'id':'blue-7','role':'infantry','alive':True,'hp':200,'x':21.4,'y':7.5}]
        S.MEM.clear();ctx=S.Ctx(obs,{})
        r=ctx.robots[1];r.update(x=23.8,y=4.4,ammo=20)
        with patch.object(S,'go',return_value=((0,0),True)),patch.object(S,'shoot',return_value={}) as shoot:
            S.hero_push(ctx,r,{'departed':True},{})
            self.assertEqual(shoot.call_args.args[2]['id'],'blue-7')
            self.assertTrue(shoot.call_args.kwargs['fire_ok'])
            ctx.base['armor_open']=True
            S.hero_push(ctx,r,{'departed':True},{})
            self.assertEqual(shoot.call_args.args[2]['kind'],'base')

    def test_flight_tilt_does_not_cancel_the_fly_slope(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2400,time=120)
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=16,y=.6,z=.9,vx=3,vy=0,grounded=False,tipped=True)
        S.MEM.clear();m={'fly':{'phase':1,'since':118,'run_at':119,'jumped':True,'jump_at':119.8}}
        command=S.fly_route(S.Ctx(obs,{}),r,m)
        self.assertIsNotNone(command);self.assertGreater(math.hypot(*command['move']),.5)
        self.assertFalse(m.get('fly_done',False))

    def test_wheel_legged_navigation_hops_an_ordinary_road_lip_on_both_sides(self):
        S=self.strategy
        for team in ('red','blue'):
            obs=self.observation(team);obs.update(tick=2400,time=120)
            S.MEM.clear();ctx=S.Ctx(obs,{})
            # Cross the actual floor-to-road lip; (15, 1.6) is flat road.
            r=ctx.robots[3];x,y=ctx.p(8.24,12.7)
            r.update(x=x,y=y,z=sdk.terrain_height(obs['arena'],x,y),vx=0,
                     vy=1.2 if team=='red' else -1.2,grounded=True,tipped=False)
            command,_=S.go(ctx,r,ctx.p(8.24,13.35))
            self.assertIsInstance(command,dict)
            self.assertGreater(command.get('jump',0),0)

    def test_hunting_a_highland_hero_keeps_the_firing_point_on_enemy_floor(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2400,time=120)
        obs['enemies']=[{'id':'blue-1','role':'hero','x':17.6,'y':11.4,'alive':True,'hp':200}]
        S.MEM.clear();ctx=S.Ctx(obs,{})
        goal=S.hunt_goal(ctx,ctx.robots[3],0)
        self.assertGreater(goal[0],20);self.assertLess(S.lift(*goal),.15)

    def test_gripped_wheel_legged_robot_stops_fighting_the_engineer(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2400,time=120,controlled_ids=['3'])
        engineer=next(r for r in obs['robots'] if r['slot']==2)
        engineer.update(rescue_contact=True,rescue_target='red-3')
        r=next(r for r in obs['robots'] if r['slot']==3);r.update(tipped=True)
        S.MEM.clear();S.RUNE_MOTOR.__init__()
        with patch.dict(S.ROLES,infantry=lambda ctx,r:sdk.action(move=(.5,0),jump=.8)):
            commands,_=S.act(obs,{})
        self.assertEqual(commands['3']['move'],[0,0]);self.assertNotIn('jump',commands['3'])

    def test_none_aim_from_sdk_still_scans_the_ground_camera(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2400,time=120,controlled_ids=['3'])
        S.MEM.clear();S.RUNE_MOTOR.__init__()
        with patch.dict(S.ROLES,infantry=lambda ctx,r:sdk.action(move=(.4,0))):
            commands,_=S.act(obs,{})
            first=commands['3']['aim'];self.assertIsNotNone(first)
            obs['time']=120.1
            commands,_=S.act(obs,{})
        self.assertAlmostEqual(S.wrap(commands['3']['aim']-first),.09)

    def test_engineer_coordinates_revival_when_close_to_a_dead_tipped_robot(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2000,time=100,controlled_ids=['2','3'])
        obs['teams']['red']['completed_difficulties']=[1]
        engineer=next(r for r in obs['robots'] if r['slot']==2)
        target=next(r for r in obs['robots'] if r['slot']==3)
        target.update(x=engineer['x']+.7,y=engineer['y'],alive=False,hp=0,tipped=True,upright=0,respawn_progress=0,respawn_required=40)
        obs['teams']['red']['resources']=sdk.instant_revive_cost(target,100)
        S.MEM.clear();S.RUNE_MOTOR.__init__()
        commands,_=S.act(obs,{})
        self.assertEqual(commands['2'].get('rescue'),3)
        self.assertTrue(commands['3'].get('revive'))

    def test_a_robot_waits_for_the_gripper_after_being_assigned_to_rescue(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2400,time=120,controlled_ids=['3'])
        engineer=next(r for r in obs['robots'] if r['slot']==2)
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=engineer['x']+.7,y=engineer['y'],tipped=True)
        S.MEM.clear();S.RUNE_MOTOR.__init__();S.MEM[2]={'rescue_id':3}
        with patch.dict(S.ROLES,infantry=lambda ctx,r:sdk.action(move=(.5,0),fire=True)):
            commands,_=S.act(obs,{})
        self.assertEqual(commands['3']['move'],[0,0]);self.assertFalse(commands['3']['fire'])

    def test_hero_push_routes_a_floor_start_onto_the_highland_before_crossing(self):
        S=self.strategy;obs=self.observation();obs.update(tick=5000,time=250)
        r=next(r for r in obs['robots'] if r['slot']==1);r.update(x=13,y=1.6,ammo=20)
        S.MEM.clear()
        with patch.object(S,'go',return_value=((.2,0),False)) as go,patch.object(S,'shoot',return_value={}):
            S.hero_push(S.Ctx(obs,{}),r,{}, {})
        self.assertEqual(go.call_args.args[2],(12.5,5.3))

    def test_budget_fallback_keeps_movement_without_repeating_purchases(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2400,time=120,controlled_ids=['3'])
        S.MEM.clear();S.RUNE_MOTOR.__init__();S.MEM[3]={'last_command':{'move':[.3,0],'aim':.2}}
        with patch.object(S,'busy',return_value=True),patch.dict(S.ROLES,infantry=lambda ctx,r:self.fail('late role should not run')):
            commands,_=S.act(obs,{})
        self.assertEqual(commands['3']['move'],[.3,0]);self.assertNotIn('buy_ammo',commands['3'])

    def test_fortress_holder_has_cover_and_does_not_evade_out_of_the_zone(self):
        S=self.strategy;obs=self.observation();obs.update(tick=4000,time=200)
        obs['outposts']['blue']['hp']=0
        obs['enemies']=[{'id':'blue-1','role':'hero','x':17.6,'y':11.4,'z':0,'alive':True,'hp':200}]
        S.MEM.clear();ctx=S.Ctx(obs,{})
        r=ctx.robots[3];r.update(x=21.4,y=7.5,ammo=100,last_damage_time=199.5)
        with patch.object(S,'go',return_value=((0,0),True)) as go,patch.object(S,'shoot',return_value={}):
            command=S.leg_infantry(ctx,r,ctx.mem(3),{},0)
            self.assertLess(S.dist(go.call_args.args[2],ctx.p(*S.ENEMY_FORT)),.4)
            S.evade(ctx,r,command);self.assertEqual(tuple(command['move']),(0,0))
            S.leg_infantry(ctx,ctx.robots[4],ctx.mem(4),{},1)
            self.assertGreater(S.dist(go.call_args.args[2],ctx.p(*S.ENEMY_FORT)),1)

    def test_short_paid_revival_does_not_handoff_a_nearly_finished_fortress_hold(self):
        S=self.strategy;obs=self.observation();obs.update(tick=4000,time=200)
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=21.4,y=7.5,alive=False,hp=0,death_time=199.95,fortress_hold=15)
        S.MEM.clear();S.MEM['team']={'holder':3}
        self.assertEqual(S.holder(S.Ctx(obs,{})),3)
        obs['time']=203.1
        self.assertEqual(S.holder(S.Ctx(obs,{})),4)

    def test_ammo_orders_leave_money_for_the_nearly_finished_fortress_holder(self):
        S=self.strategy;obs=self.observation();obs.update(tick=4000,time=200)
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=21.4,y=7.5,fortress_hold=15)
        cost=sdk.instant_revive_cost(r,200);obs['teams']['red']['resources']=cost+150
        S.MEM.clear();ctx=S.Ctx(obs,{})
        order=S.buy(ctx,ctx.robots[1],20,remote=True)
        self.assertEqual(order['amount'],10);self.assertGreaterEqual(ctx.coins,cost)

    def test_a_tipped_holder_keeps_a_nearly_finished_occupation(self):
        S=self.strategy;obs=self.observation();obs.update(tick=4000,time=200)
        r=next(r for r in obs['robots'] if r['slot']==3)
        r.update(x=21.4,y=7.5,tipped=True,fortress_hold=15)
        S.MEM.clear();S.MEM['team']={'holder':3}
        self.assertEqual(S.holder(S.Ctx(obs,{})),3)

    def test_aerial_leaves_the_rune_hover_to_pressure_ground_targets(self):
        S=self.strategy;obs=self.observation();obs.update(tick=2400,time=120)
        obs['outposts']['blue']['hp']=0
        obs['runes']['red'].update(status='idle',small_chances=0,large_chances=0)
        r=next(r for r in obs['robots'] if r['slot']==6);r.update(x=12.4,y=3.9,vx=0,vy=0,ammo=500)
        obs['enemies']=[{'id':'blue-1','role':'hero','x':20,'y':8,'z':0,'alive':True,'hp':200}]
        S.MEM.clear();S.RUNE_MOTOR.__init__()
        with patch.object(S,'shoot',return_value={}) as shoot:
            command=S.aerial(S.Ctx(obs,{}),r)
        self.assertGreater(command['move'][0],0);self.assertLess(command['move'][1],0)
        self.assertEqual(shoot.call_args.args[2]['id'],'blue-1')

    def test_naturally_respawned_hero_seeks_supplies_before_deployment(self):
        obs = self.observation()
        obs["tick"], obs["time"] = 800, 40
        robot = next(r for r in obs["robots"] if r["slot"] == 1)
        robot.update(x=10.4, y=3.6, hp=15, weak=True, ammo=20, deployed=False)
        self.strategy.MEM.clear()
        ctx = self.strategy.Ctx(obs, {})
        with patch.object(self.strategy, "go", return_value=((0, 1), False)) as go:
            command = self.strategy.hero(ctx, robot)
        goal = go.call_args.args[2]
        zone = next(z for z in obs["arena"]["zones"] if z["id"] == "red_supply")
        self.assertTrue(sdk.point_in_polygon(*goal, zone["polygon"]))
        self.assertFalse(command.get("deploy"))
        self.assertFalse(command.get("fire"))

    def test_arc_rejects_resource_station_wall_but_accepts_open_front(self):
        obs = self.observation()
        ctx = self.strategy.Ctx(obs, {})
        robot = dict(ctx.robots[3], x=.9, y=14.2, z=sdk.terrain_height(obs["arena"], .9, 14.2),
                     vx=0, vy=0, vz=0, quaternion=[0, 0, 0, 1])
        target = {"x": 3.1, "y": 14.2, "z": robot["z"]+.43, "kind": "rune_target"}
        self.assertFalse(self.strategy.clear_shot(ctx, robot, target, 0, 0, 2.2))
        robot.update(y=12.1, z=sdk.terrain_height(obs["arena"], .9, 12.1))
        target.update(y=12.1, z=robot["z"]+.43)
        self.assertTrue(self.strategy.clear_shot(ctx, robot, target, 0, 0, 2.2))

    def test_hero_does_not_buy_again_while_delivery_is_pending(self):
        obs = self.observation()
        obs["tick"], obs["time"] = 2000, 100
        obs["teams"]["red"]["resources"] = 1000
        robot = next(r for r in obs["robots"] if r["slot"] == 1)
        robot.update(x=10.4, y=3.6, ammo=1, deployed=True, pending_ammo=[[104, 20]],
                     last_shot_time=90, last_damage_time=90)
        self.strategy.MEM.clear()
        command = self.strategy.hero(self.strategy.Ctx(obs, {}), robot)
        self.assertNotIn("buy_ammo", command)

    def test_paid_revive_preserves_siege_route_progress(self):
        obs = self.observation()
        obs["tick"], obs["time"] = 2400, 120
        obs["teams"]["red"]["resources"] = 2000
        robot = next(r for r in obs["robots"] if r["slot"] == 1)
        robot.update(x=10.4, y=3.6, hp=0, alive=False, ammo=20, respawn_required=40, respawn_progress=0)
        self.strategy.MEM.clear()
        command = self.strategy.hero(self.strategy.Ctx(obs, {}), robot)
        self.assertTrue(command["revive"])
        robot.update(alive=True, hp=robot["max_hp"], weak=False, deployed=False, deploy_at=None)
        with patch.object(self.strategy, "go", return_value=((0, 0), True)) as go:
            command = self.strategy.hero(self.strategy.Ctx(obs, {}), robot)
        self.assertEqual(go.call_args.args[2], self.strategy.HERO_SPOT)
        self.assertTrue(command.get("deploy"))

    def test_moving_target_prediction_includes_visible_rotation(self):
        obs = self.observation()
        shooter = dict(next(r for r in obs["robots"] if r["slot"] == 3), x=5, y=5, vx=0, vy=0, vz=0)
        target = {"id": "blue-4", "x": 10, "y": 5, "z": shooter["z"], "vx": 0, "vy": 2, "vz": 0,
                  "role": "infantry", "quaternion": [0, 0, 0, 1], "angular_velocity": [0, 0, 1],
                  "chassis_size_m": [.54, .54, .17], "armor_center_z_m": .285}
        predicted = self.strategy.lead(shooter, target)
        self.assertGreater(predicted["quaternion"][2], 0)
        self.assertGreater(predicted["y"], target["y"])
        self.assertLess(predicted["y"]-target["y"], .6)

    def test_wheel_leg_turn_reduces_acceleration(self):
        obs = self.observation()
        obs["tick"], obs["time"] = 2, .1
        obs["controlled_ids"] = ["3"]
        robot = next(r for r in obs["robots"] if r["slot"] == 3)
        robot.update(ammo=50, heading=0)
        self.strategy.MEM.clear()
        with patch.object(self.strategy, "go", return_value=((0, 1), False)):
            actions, _ = self.strategy.act(obs, {})
        command = actions["3"]
        self.assertLess(math.hypot(*command["move"]), .35)
        self.assertAlmostEqual(command["heading"], math.pi/2)
        self.assertTrue(.12 <= command["leg_height"] <= .34)

    def test_failed_path_search_is_not_repeated_every_decision(self):
        obs = self.observation()
        obs["tick"], obs["time"] = 200, 10
        robot = next(r for r in obs["robots"] if r["slot"] == 7)
        self.strategy.MEM.clear()
        with patch.object(self.strategy, "line_free", return_value=False), patch.object(self.strategy, "astar", return_value=None) as search:
            self.strategy.go(self.strategy.Ctx(obs, {}), robot, (14, 7.5))
            obs["time"] = 10.1
            self.strategy.go(self.strategy.Ctx(obs, {}), robot, (14, 7.5))
        self.assertEqual(search.call_count, 1)

    def test_path_search_count_limit_also_applies_without_cached_path(self):
        obs = self.observation()
        obs["tick"], obs["time"] = 200, 10
        robot = next(r for r in obs["robots"] if r["slot"] == 7)
        self.strategy.MEM.clear()
        with patch.object(self.strategy, "line_free", return_value=False), patch.object(self.strategy, "astar") as search:
            move, _ = self.strategy.go(self.strategy.Ctx(obs, {"_plans": 2}), robot, (14, 7.5))
        search.assert_not_called()
        self.assertEqual(move, (0, 0))

    def test_an_over_budget_decision_starts_no_path_search(self):
        """The runner disables a team after a single decision over 200 ms: late in a decision, reuse old plans."""
        import time
        obs = self.observation()
        obs["tick"], obs["time"] = 200, 10
        robot = next(r for r in obs["robots"] if r["slot"] == 7)
        self.strategy.MEM.clear()
        with patch.object(self.strategy, "line_free", return_value=False), patch.object(self.strategy, "astar") as search:
            self.strategy.go(self.strategy.Ctx(obs, {"_t0": time.perf_counter() - 1}), robot, (14, 7.5))
            search.assert_not_called()
            self.strategy.go(self.strategy.Ctx(obs, {"_t0": time.perf_counter()}), robot, (14, 7.5))
            search.assert_called_once()

    def test_hero_planner_reaches_flat_siege_positions_on_both_sides(self):
        S = self.strategy
        for team in ("red", "blue"):
            with self.subTest(team=team):
                mirror = lambda p: p if team == "red" else (28-p[0], 15-p[1])
                radius = S.RADIUS["hero"]
                path = S.astar(team, "mec", .4, radius, mirror((1.6, 6.05)), mirror(S.HERO_SPOT), time_budget=None)
                self.assertIsNotNone(path)
                self.assertLess(S.dist(path[-1], mirror(S.HERO_SPOT)), .25)
                clear = S.grid(team, "mec", .4)
                self.assertTrue(all(S.clearance_at(clear, *point) >= radius for point in path))

    def test_planner_modes_match_the_lineup_hardware(self):
        """Wheeled robots reach the deck only by the ramps; wheel-legged robots hop the stair block straight on."""
        S = self.strategy
        for team in ("red", "blue"):
            mirror = lambda p: p if team == "red" else (28-p[0], 15-p[1])
            # Test reachability with the deterministic node budget. The live
            # policy also has a 25 ms wall-clock budget, independent of geometry.
            wheels = S.astar(team, "mec", .4, S.RADIUS["engineer"], mirror((0.98, 13.0)), mirror((13.34, 6.84)), time_budget=None)
            self.assertIsNotNone(wheels, team)
            self.assertTrue(any(S.lift(*p) > .15 and mirror(p)[1] > 12.9 for p in wheels), team)   # via the highway
            legs = S.astar(team, "leg", .4, S.RADIUS["infantry"], mirror((5.0, 7.5)), mirror((21.4, 7.5)), time_budget=None)
            self.assertIsNotNone(legs, team)
            self.assertLess(max(abs(mirror(p)[1] - 7.5) for p in legs), 2.5, team)              # straight over
            around = S.astar(team, "mec", .4, S.RADIUS["infantry"], mirror((8.0, 7.5)), mirror((11.0, 7.5)), time_budget=None)
            self.assertGreater(sum(S.dist(a, b) for a, b in zip(around, around[1:])), 12, team)    # no wheels up the steps

    def test_deck_chain_keeps_wheeled_robots_on_the_validated_route(self):
        S = self.strategy
        for team in ("red", "blue"):
            ctx = S.Ctx(self.observation(team), {})
            engineer = {"x": ctx.p(4.0, 10.5)[0], "y": ctx.p(4.0, 10.5)[1], "slot": 2}
            goal = ctx.p(13.34, 6.84)
            self.assertEqual(S.deck_waypoint(ctx, engineer, {}, goal), ctx.p(*S.DECK_CHAIN[0]), team)
            on_deck = dict(engineer, x=ctx.p(13.0, 7.5)[0], y=ctx.p(13.0, 7.5)[1])
            self.assertIsNone(S.deck_waypoint(ctx, on_deck, {}, goal), team)

    def test_every_reachable_lower_base_panel_gets_a_firing_spot(self):
        S = self.strategy
        for team in ("red", "blue"):
            ctx = S.Ctx(self.observation(team), {})
            spots = S.base_spots(ctx)
            self.assertGreaterEqual(len(spots), 2, team)
            for spot in spots:
                self.assertAlmostEqual(S.dist(spot, S.pos(ctx.base)), 2.1, places=6)
            self.assertEqual(len(set(spots)), len(spots))

    def test_wheel_legged_infantry_climb_the_stairs_and_earn_the_highland_buff(self):
        S = self.strategy
        for team in ('red','blue'):
            S.MEM.clear()
            S.RUNE_MOTOR.__init__()
            with Match(2, 30, "rmuc2026", lineups=mirrored_lineups(LINEUP)) as match:
                state, buffs = None, set()
                while match.time < 22:
                    if match.tick % 2 == 0:
                        actions, state = S.act(match.observation(team), state)
                    match.step({team: actions})
                    buffs |= {e["robot"] for e in match.events if e["type"] == "terrain_buff" and e.get("kind") == "highland"}
                robots = {r["id"]: r for r in match.robots}
                self.assertEqual(buffs, {f'{team}-3',f'{team}-4'})
                for rid in (f'{team}-3',f'{team}-4'):
                    self.assertGreater(robots[rid]["z"], .4, rid)
                    self.assertFalse(robots[rid]["tipped"], rid)
        S.MEM.clear()

    def test_rune_motor_fit_predicts_the_engine_shaft_angle(self):
        S = self.strategy
        S.RUNE_MOTOR.__init__()
        with Match(4, 14, "rmuc2026") as match:                       # even seed: the shaft turns the other way
            truth = {}
            for _ in range(240):
                obs = match.observation("red")
                rune = obs["runes"]["red"]
                truth[obs["tick"]] = rune["angle"]
                S.RUNE_MOTOR.configure(obs["simulation_assumptions"])
                S.RUNE_MOTOR.observe(obs["tick"], obs["time"], rune["angle"], rune["angular_velocity"],
                                     rune["angular_acceleration"])
                if S.RUNE_MOTOR.params is None and len(S.RUNE_MOTOR.samples) >= 6:
                    S.RUNE_MOTOR.fit()
                match.step({})
            self.assertIsNotNone(S.RUNE_MOTOR.params)
            self.assertLess(S.RUNE_MOTOR.resid, 1e-9)
            anchor = S.RUNE_MOTOR.angle[0]
            for _ in range(12):
                obs = match.observation("red")
                truth[obs["tick"]] = obs["runes"]["red"]["angle"]
                match.step({})
            for ahead in (4, 8, 12):
                predicted = S.RUNE_MOTOR.angle_at(anchor + ahead)
                self.assertLess(abs(S.wrap(predicted - truth[anchor + ahead])), 1e-5, ahead)
        S.RUNE_MOTOR.__init__()

    def test_rune_motor_learns_the_large_mode_amplitude_after_180_seconds(self):
        S = self.strategy
        S.RUNE_MOTOR.__init__()
        w, p0, p1, a = 1.93, .8, 2.2, .91
        S.RUNE_MOTOR.params, S.RUNE_MOTOR.dirn, S.RUNE_MOTOR.resid = (w, p0, p1), -1, 0.0
        truth = RuneTruth(S, w, p0, p1, a)
        for tick in range(3600, 3700):
            t = tick * S.R_DT
            S.RUNE_MOTOR.observe(tick, t, truth.angle(tick), -truth.speed(t), -truth.acceleration(t))
        self.assertAlmostEqual(S.RUNE_MOTOR.a, a, places=4)
        S.RUNE_MOTOR.angle = (3699, truth.angle(3699))
        self.assertLess(abs(S.wrap(S.RUNE_MOTOR.angle_at(3710) - truth.angle(3710))), 1e-6)
        S.RUNE_MOTOR.__init__()

    def test_gimbal_frame_conversion_round_trips_on_a_tilted_chassis(self):
        S = self.strategy
        q = [.04, -.03, .6, .8]
        norm = math.sqrt(sum(v * v for v in q))
        robot = {"quaternion": [v / norm for v in q]}
        for yaw, pitch in ((0.3, .2), (-2.5, .5), (3.0, -.1)):
            world = S.to_world(robot, *S.to_local(robot, yaw, pitch))
            self.assertAlmostEqual(S.wrap(world[0] - yaw), 0, places=9)
            self.assertAlmostEqual(world[1], pitch, places=9)

    def test_one_live_infantry_starts_the_rune_only_when_the_aerial_is_ready(self):
        S = self.strategy
        obs = self.observation()
        obs["tick"], obs["time"] = 1200, 60.0
        S.RUNE_MOTOR.__init__()
        S.RUNE_MOTOR.params, S.RUNE_MOTOR.dirn, S.RUNE_MOTOR.resid, S.RUNE_MOTOR.angle = (1.95, .3, .7), -1, 0.0, (1199, .2)
        ctx = S.Ctx(obs, {})
        hover = ctx.p(*S.RUNE_HOVER)
        air = ctx.robots[6]
        air.update(x=hover[0], y=hover[1], vx=0.0, vy=0.0, ammo=300, support_active=True, heat=0.0)
        self.assertEqual(obs["runes"]["red"]["small_chances"], 1)
        self.assertTrue(S.rune_start_ok(ctx))
        for change in ({"x": hover[0] + .5}, {"ammo": 10}, {"vx": .3}, {"support_active": False}):
            moved = dict(air, **change)
            ctx.robots[6] = moved
            self.assertFalse(S.rune_start_ok(ctx), change)
        ctx.robots[6] = air
        obs["runes"]["red"]["small_chances"] = 0
        self.assertFalse(S.rune_start_ok(ctx))
        obs["runes"]["red"]["small_chances"] = 1
        S.MEM.clear()
        actions, _ = S.act(obs, {})
        starters = [slot for slot, command in actions.items() if command.get("rune_start")]
        self.assertEqual(starters, ["3"])
        S.RUNE_MOTOR.__init__()

    def test_aerial_keeps_the_rounds_the_coming_activations_need(self):
        S = self.strategy
        obs = self.observation()
        obs["tick"], obs["time"] = 600, 30.0
        ctx = S.Ctx(obs, {})
        self.assertEqual(S.rune_reserve(ctx), 26 * 3 + 14 * 2)
        obs["time"] = 200.0
        self.assertEqual(S.rune_reserve(S.Ctx(obs, {})), 26 * 2)
        obs["time"] = 340.0
        self.assertEqual(S.rune_reserve(S.Ctx(obs, {})), 0)

    def test_hero_is_revived_instantly_only_inside_a_rune_window_or_when_the_team_is_rich(self):
        S = self.strategy
        obs = self.observation()
        robot = next(r for r in obs["robots"] if r["slot"] == 1)
        robot.update(alive=False, hp=0, level=5, respawn_required=40, respawn_progress=36, tipped=False)
        # (time, coins above the revive price, expected): outside a window 250 coins stay in reserve for ammunition,
        # the aerial's support and the infantry; inside a window the hero is back for the buff at any price
        for seconds, extra, expected in ((100, 50, False), (100, 300, True), (178, 0, True), (230, 0, True), (240, 0, False), (320, 0, False), (330, 0, True)):
            obs["time"] = seconds
            cost = sdk.instant_revive_cost(robot, seconds)
            obs["teams"]["red"]["resources"] = cost + extra
            command = S.revive_or_wait(S.Ctx(obs, {}), robot, 2)
            self.assertEqual(bool(command.get("revive")), expected, (seconds, extra))

    def test_engineer_does_not_leave_the_tech_loop_to_rebuild_before_level_three(self):
        S = self.strategy
        obs = self.observation()
        obs["tick"], obs["time"] = 1200, 60
        obs["outposts"]["red"]["hp"] = 0
        obs["teams"]["red"].update(rebuild_credits=2, completed_difficulties=[1, 2])
        robot = next(r for r in obs["robots"] if r["slot"] == 2)
        S.MEM.clear()
        goals = []
        with patch.object(S, "go", side_effect=lambda ctx, r, goal, **k: (goals.append(goal) or ((0, 0), True))):
            S.engineer(S.Ctx(obs, {}), robot)
        zone = next(z for z in obs["arena"]["zones"] if z["id"] == "red_outpost")
        self.assertTrue(all(S.dist(goal, (zone["x"], zone["y"])) > 1.5 for goal in goals))

    def test_engineer_waits_loaded_in_the_assembly_zone_and_starts_difficulty_four_at_180_s(self):
        S = self.strategy
        obs = self.observation()
        obs["teams"]["red"]["completed_difficulties"] = [1, 2, 3]
        robot = next(r for r in obs["robots"] if r["slot"] == 2)
        zone = next(z for z in obs["arena"]["zones"] if z["id"] == "red_assembly")
        robot.update(x=zone["x"], y=zone["y"], carried_units=2)
        cases = ((165.0, "idle", 3, None), (179.0, "idle", 3, None), (180.0, "idle", 3, 4),
                 (180.1, "inserting", 2, None), (184.5, "inserting", 2, None), (184.6, "idle", 3, 4),
                 (193.0, "inserting", 2, 4))
        for seconds, enemy_stage, enemy_level, expected in cases:
            obs["time"], obs["tick"] = seconds, round(seconds * 20)
            obs["assemblies"]["blue"].update(stage=enemy_stage, difficulty=enemy_level)
            S.MEM.clear()
            with patch.object(S, "go", return_value=((0, 0), True)):
                command = S.engineer(S.Ctx(obs, {}), robot)
            self.assertEqual(command.get("assembly"), expected, (seconds, enemy_stage, enemy_level))
        # the engine refuses a second difficulty-4 run while the other team's runs, so asking costs nothing
        # and the engineer starts the tick the other team's run ends
        obs["time"], obs["tick"] = 190.0, 3800
        obs["assemblies"]["blue"].update(stage="inserting", difficulty=4)
        with patch.object(S, "go", return_value=((0, 0), True)):
            self.assertEqual(S.engineer(S.Ctx(obs, {}), robot).get("assembly"), 4)
        # without two units the engineer fetches them from the resource zone before the unlock
        robot.update(carried_units=1)
        obs["time"], obs["tick"] = 170.0, 3400
        obs["assemblies"]["blue"].update(stage="idle", difficulty=3)
        goals = []
        with patch.object(S, "go", side_effect=lambda ctx, r, goal, **k: (goals.append(goal) or ((0, 0), True))):
            command = S.engineer(S.Ctx(obs, {}), robot)
        resource = next(z for z in obs["arena"]["zones"] if z["id"] == "red_resource")
        self.assertTrue(command.get("pick_unit"))
        self.assertLess(S.dist(goals[-1], (resource["x"], resource["y"])), .5)


class RuneTruth:
    """Reference implementation of the engine's shaft law (rune_motor_rates / rune_motor_integral)."""

    def __init__(self, S, w, p0, p1, a, ticks=3720):
        self.S, self.p, self.a = S, (w, p0, p1), a
        dt, total, self.cumulative = S.R_DT, 0.0, [0.0]
        for k in range(ticks):
            t = k * dt
            total += dt * (self.speed(t) + 4 * self.speed(t + dt / 2) + self.speed(t + dt)) / 6
            self.cumulative.append(total)

    def speed(self, t):
        return self.S.RUNE_MOTOR.speed(t, *self.p, self.a)

    def acceleration(self, t):
        h = 1e-6
        return (self.speed(t + h) - self.speed(t - h)) / (2 * h)

    def angle(self, tick):
        return (-self.cumulative[tick]) % math.tau


if __name__ == "__main__":
    unittest.main()
