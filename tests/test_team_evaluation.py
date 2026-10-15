import importlib.util
from pathlib import Path
import tempfile
import unittest

from rmuc_arena.submissions import ROOT, load_submission, save_submission


class EvaluationSnapshotTests(unittest.TestCase):
    def test_directory_is_frozen_before_a_multi_game_run(self):
        spec = importlib.util.spec_from_file_location("team_eval", ROOT / "scripts/evaluate_team.py")
        evaluation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(evaluation)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            code = root / "source.py"
            original = 'def act(obs, state):\n    return {}, state\n'
            code.write_text(original)
            entry = root / "entry"
            manifest = save_submission(entry, "team", {"team": code})
            cache = root / "cache"
            cache.mkdir()
            frozen = evaluation.snapshot(entry, cache)
            (entry / "strategy.py").write_text('def act(obs, state):\n    return {}, 42\n')
            frozen_manifest, files = load_submission(frozen)
            self.assertEqual(frozen_manifest["version"], manifest["version"])
            self.assertEqual(files["team"].read_text(), original)


if __name__ == "__main__":
    unittest.main()
