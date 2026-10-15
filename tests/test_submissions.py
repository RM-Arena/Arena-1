import json
from pathlib import Path
import tempfile
import unittest

from rmuc_arena.submissions import scaffold, submit, load_submission, assemble, start_training
from tests.showcase_fixture import SHOWCASE_TEXT, write_showcase


class SubmissionTests(unittest.TestCase):
    def new_workspace(self, path, mode="team", robot=None, registry=None):
        result=scaffold(path,mode,robot,registry)
        start_training(result,registry)
        write_showcase(result)
        return result

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.registry = self.root / "host" / "registry.json"

    def test_only_strategy_is_editable_and_snapshot_is_verified(self):
        workspace = self.new_workspace(self.root / "author", registry=self.registry)
        (workspace / "strategy.py").write_text('def act(obs, state):\n    return {}, state\n')
        manifest = submit(workspace, self.root / "v1", self.registry)
        loaded, entries = load_submission(self.root / "v1")
        self.assertEqual(loaded["version"], manifest["version"])
        self.assertEqual(set(entries), {"team"})
        (self.root / "v1" / "strategy.py").write_text('modified')
        with self.assertRaisesRegex(ValueError, "strategy changed"):
            load_submission(self.root / "v1")

    def test_strategy_source_may_reach_512_kib(self):
        from rmuc_arena.submissions import save_submission
        from rmuc_arena.worker import SOURCE_LIMIT
        body = 'def act(obs, state):\n    return {}, state\n'
        for size, accepted in ((300 * 1024, True), (SOURCE_LIMIT + 1, False)):
            source = self.root / f"big{size}.py"
            source.write_text(body + "#" * (size - len(body) - 1) + "\n")
            if accepted:
                save_submission(self.root / f"sub{size}", "team", {"team": source})
            else:
                with self.assertRaisesRegex(ValueError, "512 KiB"):
                    save_submission(self.root / f"sub{size}", "team", {"team": source})

    def test_protected_file_and_new_file_rejected(self):
        workspace = self.new_workspace(self.root / "author", registry=self.registry)
        (workspace / "sdk.py").write_text('modified')
        with self.assertRaisesRegex(ValueError, "Protected file"):
            submit(workspace, self.root / "v1", self.registry)
        (workspace / "extra.py").write_text('extra')
        with self.assertRaisesRegex(ValueError, "unexpected"):
            submit(workspace, self.root / "v2", self.registry)

    def test_symlink_rejected(self):
        workspace = self.new_workspace(self.root / "author", registry=self.registry)
        (workspace / "strategy.py").unlink()
        (workspace / "strategy.py").symlink_to(workspace / "sdk.py")
        with self.assertRaisesRegex(ValueError, "regular file"):
            submit(workspace, self.root / "v1", self.registry)

    def test_six_independent_submissions_assemble(self):
        submissions = []
        for i in (1,2,3,4,6,7):
            workspace = self.new_workspace(self.root / f"author-{i}", "robot", i, self.registry)
            destination = self.root / f"robot-{i}"
            submit(workspace, destination, self.registry)
            submissions.append(destination)
        assemble(submissions, self.root / "squad")
        manifest, entries = load_submission(self.root / "squad")
        self.assertEqual(manifest["mode"], "squad")
        self.assertEqual(set(entries), {str(i) for i in (1,2,3,4,6,7)})
        with self.assertRaisesRegex(ValueError, "robot 1"):
            assemble(list(reversed(submissions)), self.root / "bad")


if __name__ == "__main__":
    unittest.main()
