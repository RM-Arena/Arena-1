"""Published difficulty ladder and generator source remain in agreement."""
import json
from pathlib import Path
import unittest
from scripts.exchange_difficulties import ASSEMBLY_DIFFICULTIES

ROOT=Path(__file__).resolve().parents[1]
class ExchangeDifficultyTests(unittest.TestCase):
    def test_authoring_profiles_equal_public_rules(self):
        data=json.loads((ROOT/'config/rules.json').read_text())
        self.assertEqual(data['simulation_assumptions']['assembly_difficulties'],ASSEMBLY_DIFFICULTIES)
        self.assertEqual(data['official']['assembly']['difficulty_4_secondary_insert_window_s'],3)
        for index,profile in enumerate(ASSEMBLY_DIFFICULTIES):
            bounds=data['official']['assembly']['pose_ranges']['1' if index==0 else '2-4']
            for axis,interval in profile['pose_ranges'].items():
                self.assertGreaterEqual(interval[0],bounds[axis][0]);self.assertLessEqual(interval[1],bounds[axis][1])
