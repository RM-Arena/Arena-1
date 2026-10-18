"""Beta client metadata remains compatible with strategy-library version gates."""
import json
from pathlib import Path
import re
import unittest

from rmuc_arena import __version__
from rmuc_arena.strategy_library import version_tuple

ROOT = Path(__file__).resolve().parents[1]


class BetaReleaseTests(unittest.TestCase):
    def test_beta_version_ordering_matches_stable_compatibility(self):
        self.assertGreater(version_tuple('0.6.1-beta.1'), version_tuple('0.6.0'))
        self.assertLess(version_tuple('0.6.1-beta.1'), version_tuple('0.6.1'))
        self.assertLess(version_tuple('0.6.1-beta.1'), version_tuple('0.6.1-beta.2'))
        self.assertLess(version_tuple('0.6.1-beta.9'), version_tuple('0.6.1-rc.1'))
        for value in ('0.6', '0.6.1-beta', 'latest', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                version_tuple(value)

    def test_release_metadata_and_changelog_use_the_beta_tag(self):
        package=json.loads((ROOT/'package.json').read_text())
        self.assertEqual(package['version'],__version__)
        self.assertRegex(__version__,r'^\d+\.\d+\.\d+-beta\.\d+$')
        python_version=__version__.replace('-beta.','b')
        self.assertIn(f'version = "{python_version}"',(ROOT/'pyproject.toml').read_text())
        lock=(ROOT/'uv.lock').read_text()
        self.assertIn(f'name = "rmuc-arena"\nversion = "{python_version}"',lock)
        notes=ROOT/'docs/releases'/f'v{__version__}.md'
        self.assertIn('Beta',notes.read_text())
        self.assertIn('v'+__version__,(ROOT/'CHANGELOG.md').read_text())
