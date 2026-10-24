import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from rmuc_arena.battle_settings import BattleSettings, defaults, normalize
from rmuc_arena.cli import verify_replay
from rmuc_arena.engine import Match
from rmuc_arena.runner import Battle
from rmuc_arena.server import create_app
from rmuc_arena.submissions import ROOT


class BattleSettingsTests(unittest.TestCase):
    def test_defaults_normalize_validation_and_season_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            store = BattleSettings(path)
            self.assertEqual(store.get('2027')['overrides'], {})
            self.assertEqual(defaults('2027')['projectile_spread_half_angle_deg.17mm'], 0.3)
            changed = {'projectile_spread_half_angle_deg.17mm': 0}
            store.save('2027', changed)
            self.assertEqual(BattleSettings(path).get('2027')['overrides'], changed)
            self.assertEqual(store.get('2026')['overrides'], {})
            store.save('2027', {})
            self.assertEqual(store.get('2027')['values'], defaults('2027'))
        for bad in ({'gravity': 9}, {'projectile_spread_half_angle_deg.17mm': -1},
                    {'projectile_spread_half_angle_deg.17mm': float('nan')},
                    {'projectile_spread_half_angle_deg.17mm': True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize(bad, '2027')
        with self.assertRaises(ValueError):
            normalize({'drone_impact.recovery_s': 1}, '2026')

    def test_engine_observations_and_replay_keep_custom_parameters(self):
        settings = {'projectile_spread_half_angle_deg.17mm': 0,
                    'assembly_difficulties.0.confirm_hold_s': 1.5}
        with tempfile.TemporaryDirectory() as directory:
            with Battle(ROOT/'examples/claude_opus55_xhigh_2027_team', ROOT/'examples/claude_opus55_xhigh_2027_hold',
                        duration=1, sandbox='trusted-local', battle_settings=settings) as battle:
                sim = battle.match.observation('red')['simulation_assumptions']
                self.assertEqual(sim['projectile_spread_half_angle_deg']['17mm'], 0)
                self.assertEqual(sim['assembly_difficulties'][0]['confirm_hold_s'], 1.5)
                self.assertTrue(battle.metadata['test_match'])
                battle.run()
                path = Path(directory)/'replay.json'
                battle.save(path)
            self.assertEqual(verify_replay(path)['verified_ticks'], 20)
            replay = json.loads(path.read_text())
            self.assertEqual(replay['metadata']['battle_settings'], settings)
        with Match(map_name='rmuc2027') as match:
            self.assertEqual(match.snapshot()['simulation_assumptions']['projectile_spread_half_angle_deg']['17mm'], 0.3)
        with self.assertRaises(ValueError):
            Match(map_name='rmuc2027', battle_settings={'projectile_spread_half_angle_deg.17mm': 100})

    def test_server_uses_frozen_settings_without_rating_custom_games(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app('trusted-local', Path(directory)/'submissions', Path(directory)/'data', test_mode=True)
            service = app.state.arena
            try:
                client = TestClient(app)
                settings = {'projectile_spread_half_angle_deg.17mm': 0}
                self.assertEqual(client.post('/api/battle-settings', json={'season': '2027', 'values': settings}).status_code, 200)
                response = client.post('/api/start', json={'duration': 1})
                self.assertEqual(response.status_code, 200, response.text)
                match_id = response.json()['match_id']
                client.post('/api/battle-settings', json={'season': '2027', 'values': {}})
                service.thread.join(timeout=30)
                self.assertFalse(service.thread.is_alive())
                record = service.store.match(match_id)
                self.assertEqual(record['metadata']['battle_settings'], settings)
                self.assertTrue(record['metadata']['test_match'])
                self.assertEqual(service.store.leaderboard(), [])
                self.assertNotIn('battle_settings', service.settings.get('2027')['overrides'])
                bad = client.post('/api/battle-settings', json={'season': '2027', 'values': {'not-a-setting': 1}})
                self.assertEqual(bad.status_code, 400)
            finally:
                service.shutdown()
                app.state.training.shutdown()
