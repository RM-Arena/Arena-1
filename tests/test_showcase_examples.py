"""Display sidecars of the shipped examples: showcase.json and profile.json."""
from tests.strategy_fixtures import STRATEGIES
import importlib.util
import json
from pathlib import Path
import unittest

from rmuc_arena import seasons as season_rules
from rmuc_arena.models import model_ids
from rmuc_arena.robot_presets import TACTICS, preset_key
from rmuc_arena.showcase import PROFILE_FILE, SHOWCASE_FILE, example_agent, parse_showcase, validate_profile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = STRATEGIES


def build_script():
    spec = importlib.util.spec_from_file_location("build_robot_presets", ROOT / "scripts/build_robot_presets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ShowcaseExampleTests(unittest.TestCase):
    def test_every_example_with_a_manifest_has_both_sidecars(self):
        for directory in sorted(p.parent for p in EXAMPLES.glob("*/manifest.json")):
            with self.subTest(example=directory.name):
                self.assertTrue((directory / SHOWCASE_FILE).is_file())
                self.assertTrue((directory / PROFILE_FILE).is_file())

    def test_every_showcase_is_valid(self):
        files = sorted(EXAMPLES.glob(f"*/{SHOWCASE_FILE}"))
        self.assertTrue(files)
        for file in files:
            with self.subTest(example=file.parent.name):
                showcase = parse_showcase(file.read_bytes())
                self.assertTrue(showcase["phases"])

    def test_every_profile_is_valid_and_normalised(self):
        files = sorted(EXAMPLES.glob(f"*/{PROFILE_FILE}"))
        self.assertTrue(files)
        for file in files:
            with self.subTest(example=file.parent.name):
                profile = json.loads(file.read_text(encoding="utf-8"))
                self.assertEqual(validate_profile(profile), profile)

    def test_showcase_generator_matches_the_profile_agent(self):
        for file in sorted(EXAMPLES.glob(f"*/{PROFILE_FILE}")):
            showcase_file = file.parent / SHOWCASE_FILE
            if not showcase_file.is_file():
                continue
            with self.subTest(example=file.parent.name):
                agent = json.loads(file.read_text(encoding="utf-8"))["agent"]
                reported = parse_showcase(showcase_file.read_bytes()).get("generated_by")
                if agent["provider"] == "human" or (agent["provider"] == "unknown" and not agent.get("model")):
                    self.assertIsNone(reported)
                else:
                    self.assertEqual(reported, agent)

    def test_preset_sidecars_match_the_build_script(self):
        # Same comparison as `scripts/build_robot_presets.py --check` for the sidecars.
        build = build_script()
        for season in season_rules.seasons():
          for model in season_rules.legal_models(season):
            for tactic in TACTICS:
                directory = EXAMPLES / preset_key(model, tactic, season)
                with self.subTest(preset=directory.name):
                    for name, data in build.sidecars(model, tactic, season).items():
                        self.assertEqual((directory / name).read_bytes(), build.dump(data), name)
                    profile = json.loads((directory / PROFILE_FILE).read_text(encoding="utf-8"))
                    self.assertEqual(profile["agent"], example_agent(season))


if __name__ == "__main__":
    unittest.main()
