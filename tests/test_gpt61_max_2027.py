"""Behavior and integrity checks for the Sol Max serial-leg submission."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from rmuc_arena import sdk
from rmuc_arena.engine import Match
from rmuc_arena.models import mirrored_lineups, robot_models
from rmuc_arena.showcase import load_profile, load_showcase
from rmuc_arena.submissions import load_submission

ROOT = Path(__file__).resolve().parents[1]


class SolMax2027Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('max_builder', ROOT / 'scripts/build_gpt61_max_2027.py')
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)
        cls.policy = types.ModuleType('max_policy')
        with patch.dict(sys.modules, {'sdk': sdk}):
            exec(cls.builder.source(), cls.policy.__dict__)
        with Match(seed=211, duration=1, map_name='rmuc2027',
                   lineups=mirrored_lineups(cls.builder.LINEUP, '2027')) as match:
            cls.observations = {team: match.observation(team) for team in ('red', 'blue')}

    def obs(self, side='red'):
        return json.loads(json.dumps(self.observations[side]))

    def test_reproducible_submission_and_explicit_author(self):
        folder = ROOT / 'examples' / self.builder.NAME
        manifest, _ = load_submission(folder)
        self.assertEqual(manifest['team_lineup'], self.builder.LINEUP)
        self.assertEqual(load_profile(folder)['agent'], self.builder.AGENT)
        self.assertEqual(load_profile(folder)['author'], 'GPT-6.1-Sol-Max')
        self.assertEqual(load_showcase(folder)['generated_by'], self.builder.AGENT)
        models = robot_models()
        self.assertEqual([models[str(self.builder.LINEUP[s])]['leg_type'] for s in ('3', '4', '7')],
                         ['serial', 'serial', 'serial'])
        for name, data in self.builder.output().items():
            self.assertEqual((folder / name).read_bytes(), data)

    def test_finite_owned_actions_on_both_sides_and_late_game(self):
        for side in ('red', 'blue'):
            for time in (0., 1.1, 60., 301., 419.):
                with self.subTest(side=side, time=time):
                    obs = self.obs(side)
                    obs.update(time=time, tick=int(time * 20))
                    obs['teams'][side]['resources'] = 800
                    actions, state = self.policy.act(obs, {})
                    self.assertEqual(set(actions), set(obs['controlled_ids']))
                    self.assertLess(len(json.dumps(actions, allow_nan=False)), 16 * 1024)
                    self.assertLess(len(json.dumps(state, allow_nan=False)), 256 * 1024)
                    self.assertNotIn('leg_height', actions['1'])

    def test_shared_budget_does_not_double_spend(self):
        obs = self.obs()
        obs.update(time=2., tick=40)
        obs['teams']['red']['resources'] = 150
        ctx = self.policy.Context(obs, {})
        a, b = [r for r in obs['robots'] if r['slot'] in (3, 4)]
        for r in (a, b):
            r.update(ammo=0, pending_ammo=[], last_raw_zones=['red_base'])
        self.assertEqual(self.policy.max_logistics(a, ctx)['buy_ammo']['amount'], 100)
        self.assertEqual(self.policy.max_logistics(b, ctx)['buy_ammo']['amount'],50)
        self.assertEqual(ctx.budget, 0)

    def test_purchase_cap_allows_last_local_batch(self):
        obs = self.obs()
        obs.update(time=2., tick=40)
        obs['teams']['red'].update(resources=800, purchased_17=990)
        ctx = self.policy.Context(obs, {})
        r = next(r for r in obs['robots'] if r['slot'] == 3)
        r.update(ammo=0, pending_ammo=[], last_raw_zones=['red_base'])
        self.assertEqual(self.policy.max_logistics(r, ctx)['buy_ammo']['amount'], 10)
        self.assertNotIn('buy_ammo', self.policy.max_logistics(r, ctx))
        self.assertEqual(ctx.ammo_remaining, 0)

    def test_jump_launches_before_the_edge_and_respects_cooldown(self):
        for side in ('red', 'blue'):
            obs = self.obs(side)
            obs.update(time=6., tick=120)
            r = next(r for r in obs['robots'] if r['slot'] == 3)
            r.update(x=8.7 if side == 'red' else 19.3, y=6.9 if side == 'red' else 8.1,
                     grounded=True, heading=0 if side == 'red' else math.pi)
            ctx = self.policy.Context(obs, {})
            self.policy.leg_memory(r, obs, ctx.memory)['entry'] = {'phase': 3, 'since': 5., 'began': 1.}
            fields = self.policy.highland_entry(r, ctx)
            self.assertEqual(fields['leg_height'], .12)
            self.assertEqual(fields['jump'], 1.)
            self.assertNotIn('jump', self.policy.highland_entry(r, ctx))

    def test_base_cover_triggers_before_the_heavy_dies(self):
        obs = self.obs()
        obs.update(time=150., tick=3000)
        heavy = next(r for r in obs['robots'] if r['slot'] == 1)
        heavy['hp'] = heavy['max_hp'] * .4
        r = next(r for r in obs['robots'] if r['slot'] == 4)
        r.update(x=10.85, y=8.3)
        ctx = self.policy.Context(obs, {})
        self.policy.leg_memory(r, obs, ctx.memory)['entry_done'] = True
        self.policy.max_fighter(r, ctx)
        self.assertTrue(ctx.state['base_cover'])

    def test_weak_recovery_on_the_home_half_does_not_walk_toward_the_enemy(self):
        for side in ('red', 'blue'):
            obs = self.obs(side)
            r = next(r for r in obs['robots'] if r['slot'] == 3)
            r['x'], r['y'] = self.policy.local_point(side, (12.4, 9.7))
            r['weak'] = True
            ctx = self.policy.Context(obs, {})
            with patch.object(self.policy, 'max_hold', return_value={}) as hold:
                self.policy.max_homeward(r, self.policy.max_local(ctx, (3.8, 8.15)), ctx)
            destination = self.policy.local_point(side, hold.call_args.args[1])
            self.assertLess(destination[0], 12.4)

    def test_lost_home_outpost_takes_priority_over_an_entrenched_enemy_base(self):
        obs = self.obs()
        obs.update(time=150., tick=3000)
        obs['positions']['red_outpost']['controller'] = 'blue'
        obs['positions']['blue_outpost']['controller'] = 'red'
        obs['positions']['blue_base']['active'] = ['blue']
        r = next(r for r in obs['robots'] if r['slot'] == 3)
        r.update(x=17.05, y=6.7)
        ctx = self.policy.Context(obs, {})
        self.policy.leg_memory(r, obs, ctx.memory)['entry_done'] = True
        with patch.object(self.policy, 'max_homeward', return_value={'move': (0, 0)}) as homeward:
            self.policy.max_fighter(r, ctx)
        homeward.assert_called_once()
        self.assertLess(homeward.call_args.args[1][0], 14.)

    def test_base_guard_only_retires_after_a_teammate_activates_the_card(self):
        obs = self.obs()
        obs.update(time=150., tick=3000)
        r = next(r for r in obs['robots'] if r['slot'] == 1)
        r.update(hp=80., x=1.05, y=7.5, launcher='fitted_locked')
        friend = next(r for r in obs['robots'] if r['slot'] == 4)
        friend['last_raw_zones'] = ['red_base']
        obs['zones']['red_base']['occupants'] = [r['id']]
        ctx = self.policy.Context(obs, {})
        with patch.object(self.policy, 'max_hold', return_value={}) as hold:
            self.policy.max_guard(r, ctx)
            self.assertEqual(hold.call_args.args[1], (1.05, 7.5))
            obs['zones']['red_base']['occupants'] = [r['id'], friend['id']]
            self.policy.max_guard(r, ctx)
            self.assertEqual(hold.call_args.args[1], ctx.zone('red', 'supply'))

    def test_completed_base_handoff_reopens_the_infantry_highland_route(self):
        obs = self.obs()
        obs.update(time=200., tick=4000)
        heavy = next(r for r in obs['robots'] if r['slot'] == 1)
        heavy.update(last_raw_zones=['red_base'], hp=heavy['max_hp'])
        r = next(r for r in obs['robots'] if r['slot'] == 4)
        r.update(x=3.8, y=8.15)
        ctx = self.policy.Context(obs, {'base_cover': True})
        memory = self.policy.leg_memory(r, obs, ctx.memory)
        memory['entry_done'] = True
        self.policy.max_fighter(r, ctx)
        self.assertFalse(ctx.state['base_cover'])
        self.assertNotIn('entry_done', memory)

    def test_last_home_anchor_does_not_withdraw_for_low_health_alone(self):
        obs = self.obs()
        obs.update(time=150., tick=3000)
        r = next(r for r in obs['robots'] if r['slot'] == 4)
        r.update(hp=r['max_hp'] * .2, x=11.4, y=10.5, last_raw_zones=['red_outpost'])
        obs['zones']['red_outpost']['occupants'] = [r['id']]
        ctx = self.policy.Context(obs, {})
        self.policy.leg_memory(r, obs, ctx.memory)['entry_done'] = True
        self.policy.max_fighter(r, ctx)
        self.assertFalse(ctx.state['max_recovery']['4'])

    def test_empty_sentry_collects_free_ammo_when_the_front_is_covered_and_quiet(self):
        obs = self.obs()
        obs.update(time=120., tick=2400, enemies=[])
        ally = next(r for r in obs['robots'] if r['slot'] == 3)
        ally.update(last_raw_zones=['blue_central'], x=17.15, y=9.15)
        obs['zones']['blue_central'].update(owner='red', occupants=[ally['id']])
        sentry = next(r for r in obs['robots'] if r['slot'] == 7)
        sentry['ammo'] = 0
        ctx = self.policy.Context(obs, {})
        self.policy.max_fighter(sentry, ctx)
        self.assertTrue(ctx.state['max_recovery']['7'])

    def test_cover_blocks_wasteful_shots(self):
        obs = self.obs()
        ctx = self.policy.Context(obs, {})
        r = next(r for r in obs['robots'] if r['slot'] == 3)
        r.update(x=4.2, y=7.5, z=.15, quaternion=[0, 0, 0, 1])
        target = {'x': 1., 'y': 7.5, 'aim_z': .4}
        self.assertFalse(self.policy.max_shot_clear(r, target, ctx))

    def test_teammate_blocks_fire_but_clear_lane_does_not(self):
        obs = self.obs()
        r = next(r for r in obs['robots'] if r['slot'] == 3)
        friend = next(r for r in obs['robots'] if r['slot'] == 4)
        r.update(x=4.0, y=5.0, z=.15, quaternion=[0, 0, 0, 1])
        friend.update(x=5.0, y=5.0, z=.15)
        target = {'x': 6., 'y': 5., 'aim_z': .5}
        ctx = self.policy.Context(obs, {})
        self.assertFalse(self.policy.max_shot_clear(r, target, ctx))
        friend['y'] = 8.
        self.assertTrue(self.policy.max_shot_clear(r, target, ctx))

    def test_tipped_robot_does_not_jump_or_fire(self):
        obs = self.obs()
        obs.update(time=6., tick=120)
        r = next(r for r in obs['robots'] if r['slot'] == 3)
        r.update(tipped=True, grounded=True, x=8.5, y=6.9)
        actions, _ = self.policy.act(obs, {})
        self.assertEqual(actions['3']['move'], [0, 0])
        self.assertFalse(actions['3']['fire'])
        self.assertNotIn('jump', actions['3'])

    def test_all_six_serial_legs_cross_and_return_to_supply_in_the_actual_engine(self):
        states = {side: {} for side in ('red', 'blue')}
        crossed = {}
        returned = {}
        invalid = []
        with Match(seed=211, duration=50, map_name='rmuc2027',
                   lineups=mirrored_lineups(self.builder.LINEUP, '2027')) as match:
            while match.status != 'finished':
                if match.tick % 2 == 0:
                    commands = {}
                    for side, state in states.items():
                        obs = match.observation(side)
                        ctx = self.policy.Context(obs, state)
                        commands[side] = {}
                        for r in obs['robots']:
                            if r['slot'] not in (3, 4, 7):
                                continue
                            x, _ = self.policy.local_point(side, (r['x'], r['y']))
                            if obs['time'] < 15 and x > 10.75:
                                crossed.setdefault(r['id'], obs['time'])
                            if obs['time'] >= 15:
                                supply = ctx.zone(side, 'supply')
                                fields = self.policy.max_homeward(r, supply, ctx)
                                if self.policy.distance(r, supply) < .8:
                                    returned.setdefault(r['id'], obs['time'])
                            else:
                                fields = self.policy.highland_entry(r, ctx) or {'move': (0, 0), 'brake': True}
                            commands[side][str(r['slot'])] = sdk.action(**fields)
                frame = match.step(commands)
                invalid.extend(e for e in frame['events'] if e['type'] == 'invalid_action')
        self.assertEqual(set(crossed), {f'{s}-{n}' for s in states for n in (3, 4, 7)})
        self.assertLessEqual(max(crossed.values()), 15.)
        self.assertEqual(set(returned), set(crossed),
            [(r['id'], round(r['x'], 2), round(r['y'], 2), states[r['team']].get('max_routes'),
              states[r['team']].get('stuck', {}).get('serial', {}).get(str(r['slot'])))
             for r in frame['robots'] if r['slot'] in (3, 4, 7)])
        # The safer end-ramp route is longer than the opening jump. Keep a
        # bounded return for all six robots queued into the same corridor.
        self.assertLessEqual(max(returned.values()), 48.)
        self.assertFalse(invalid)


if __name__ == '__main__':
    unittest.main()
