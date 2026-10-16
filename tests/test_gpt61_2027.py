"""Submission integrity, hardware coverage and the tilted-chassis aiming regression."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from rmuc_arena import sdk, seasons
from rmuc_arena.engine import Match
from rmuc_arena.models import mirrored_lineups
from rmuc_arena.showcase import load_profile, load_showcase
from rmuc_arena.submissions import load_submission

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    value = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'sdk': sdk}):
        spec.loader.exec_module(value)
    return value


class Gpt61Strategies2027Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = module('gpt61_builder', 'scripts/build_gpt61_strategies_2027.py')
        cls.policy = module('gpt61_policy', 'scripts/gpt61_policy_2027.py')
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.entries = Path(cls.temporary.name)
        for name, files in cls.builder.outputs():
            folder = cls.entries / name
            folder.mkdir()
            for filename, data in files.items():
                (folder / filename).write_bytes(data)

    def test_submissions_cover_every_legal_model_and_have_consistent_attribution(self):
        models = set()
        team_models = set()
        for manifest_path in self.entries.glob('*/manifest.json'):
            path = manifest_path.parent
            with self.subTest(entry=path.name):
                manifest, _ = load_submission(path)
                self.assertEqual(manifest['rules_profile'], seasons.rules_profile('2027'))
                profile, showcase = load_profile(path), load_showcase(path)
                self.assertEqual(profile['agent'], self.builder.AGENT)
                self.assertEqual(showcase['generated_by'], self.builder.AGENT)
                if manifest['mode'] == 'adaptive':
                    models.add(manifest['robot'])
                else:
                    team_models.update(manifest['team_lineup'].values())
        self.assertEqual(models, set(seasons.legal_models('2027')))
        self.assertEqual(team_models, set(seasons.legal_models('2027')))

    def test_native_hardware_and_both_sides_produce_owned_json_actions(self):
        lineups = [seasons.default_lineup('2027')] + [value[1] for value in self.builder.LINEUPS.values()]
        for lineup in lineups:
            with Match(seed=91, duration=1, map_name='rmuc2027', lineups=mirrored_lineups(lineup, '2027')) as match:
                for side in ('red', 'blue'):
                    obs = match.observation(side)
                    for style in self.builder.STYLES:
                        with self.subTest(lineup=lineup, side=side, style=style), patch.object(self.policy, 'STYLE', style):
                            actions, state = self.policy.act(obs, None)
                            self.assertEqual(set(actions), set(obs['controlled_ids']))
                            self.assertLess(len(json.dumps(state, allow_nan=False)), 256 * 1024)
                            self.assertLess(len(json.dumps(actions, allow_nan=False)), 16 * 1024)
                            for r in obs['robots']:
                                if r['role'] == 'infantry':
                                    self.assertEqual(actions[str(r['slot'])]['profile'],
                                        {'chassis': r['chassis_profile'], 'weapon': r['weapon_profile']})

    def test_adaptive_policy_controls_only_its_actual_instance_slot(self):
        with Match(seed=17, duration=1, map_name='rmuc2027',
                   lineups=mirrored_lineups(seasons.default_lineup('2027'), '2027')) as match:
            for slot in (1, 3, 4, 6, 7):
                obs = match.observation('red', [slot])
                actions, _ = self.policy.act(obs, None)
                self.assertEqual(set(actions), {str(slot)})

    def test_adaptive_policy_does_not_assume_a_fixed_competition_slot(self):
        with Match(seed=17, duration=1, map_name='rmuc2027',
                   lineups=mirrored_lineups(seasons.default_lineup('2027'), '2027')) as match:
            obs = match.observation('red', [4])
        robot = next(r for r in obs['robots'] if r['slot'] == 4)
        robot.update(slot=91, id='red-91')
        obs['controlled_ids'] = ['91']
        actions, _ = self.policy.act(obs, None)
        self.assertEqual(set(actions), {'91'})

    def test_gimbal_readings_on_a_tilted_chassis_are_not_world_aim_angles(self):
        # A 20-degree body tilt and the opposite local elevation cancel in world space.
        tilt = math.radians(20)
        r = {'aim': 0., 'heading': 0., 'pitch': tilt,
             'quaternion': [0., math.sin(tilt / 2), 0., math.cos(tilt / 2)]}
        yaw, pitch = self.policy.barrel_angles(r)
        self.assertAlmostEqual(yaw, 0., places=8)
        self.assertAlmostEqual(pitch, 0., places=8)
        self.assertGreater(abs(r['pitch'] - pitch), .3)

    def test_guarding_a_lead_does_not_send_both_infantry_into_the_enemy_half(self):
        with Match(seed=17, duration=1, map_name='rmuc2027',
                   lineups=mirrored_lineups(seasons.default_lineup('2027'), '2027')) as match:
            obs = match.observation('red')
        obs['time'], obs['tick'], obs['remaining'] = 350., 7000, 70.
        obs['teams']['red']['control'], obs['teams']['blue']['control'] = 15., 10.
        ctx = self.policy.Context(obs, {})
        self.assertTrue(ctx.hold_lead)
        self.assertLess(self.policy.heavy_post(ctx)[0], 14.)

    def test_default_lineup_uses_the_stable_mecanum_for_the_long_attack_route(self):
        with Match(seed=17, duration=1, map_name='rmuc2027',
                   lineups=mirrored_lineups(seasons.default_lineup('2027'), '2027')) as match:
            obs = match.observation('red')
        ctx = self.policy.Context(obs, {})
        jobs = {r['slot']: self.policy.infantry_job(r, ctx) for r in obs['robots'] if r['role'] == 'infantry'}
        self.assertEqual(jobs, {3: 'flex', 4: 'striker'})

    def test_heavy_finishes_initial_economy_before_a_rescue_detour(self):
        with Match(seed=17, duration=1, map_name='rmuc2027',
                   lineups=mirrored_lineups(seasons.default_lineup('2027'), '2027')) as match:
            obs = match.observation('red')
        obs['time'] = 10.
        heavy = next(r for r in obs['robots'] if r['role'] == 'heavy')
        fallen = next(r for r in obs['robots'] if r['slot'] == 3)
        fallen.update(tipped=True, x=heavy['x'] + 1., y=heavy['y'])
        fields = self.policy.heavy(heavy, self.policy.Context(obs, {}))
        self.assertNotIn('rescue', fields)

    def test_card_edge_and_outpost_card_both_count_as_cover_for_resupply(self):
        for zone in ('red_central', 'red_outpost'):
            with self.subTest(zone=zone):
                self.assertTrue(self.policy.on_outpost_card({'last_raw_zones': [zone]}, 'red'))
                self.assertFalse(self.policy.on_outpost_card({'last_raw_zones': [zone], 'tipped': True}, 'red'))
        self.assertFalse(self.policy.on_outpost_card({'last_raw_zones': ['blue_central']}, 'red'))

    def test_mutually_blocked_central_card_is_not_safe_cover(self):
        robot = {'id': 'red-4', 'team': 'red', 'last_raw_zones': ['red_central']}
        zone = {'occupants': ['red-4'], 'owner': 'blue'}
        ctx = SimpleNamespace(obs={'zones': {'red_central': zone}})
        self.assertFalse(self.policy.on_outpost_card(robot, 'red', ctx))
        zone['owner'] = 'red'
        self.assertTrue(self.policy.on_outpost_card(robot, 'red', ctx))

    def test_both_flank_offsets_stay_inside_the_actual_outpost_card(self):
        with Match(seed=17, duration=1, map_name='rmuc2027',
                   lineups=mirrored_lineups(seasons.default_lineup('2027'), '2027')) as match:
            obs = match.observation('red')
        ctx = self.policy.Context(obs, {})
        for owner in ('red', 'blue'):
            card = next(z for z in obs['arena']['zones'] if z['id'] == owner + '_outpost')
            for flank in (-1, 0, 1):
                point = self.policy.outpost_card_spot(ctx, owner, flank)
                self.assertTrue(sdk.point_in_polygon(*point, card['polygon']))

    def test_catalog_exposes_all_new_entries_with_the_requested_model_name(self):
        from rmuc_arena.server import ArenaService
        service = ArenaService('trusted-local', self.entries, self.entries / 'data', test_mode=True)
        self.addCleanup(service.shutdown)
        teams = service.catalog(season='2027')
        adaptive = service.catalog(modes=('adaptive',), season='2027')
        selected = {**{k: v for k, v in teams.items() if k.startswith('gpt61_')},
                    **{k: v for k, v in adaptive.items() if k.startswith('gpt61_')}}
        expected = {p.name for p in self.entries.iterdir() if (p / 'manifest.json').is_file()}
        self.assertEqual(set(selected), expected | {'gpt61_2027_trident'})
        self.assertTrue(all(v['agent'] == self.builder.AGENT for v in selected.values()))


if __name__ == '__main__':
    unittest.main()
