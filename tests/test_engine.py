import json
import random
import unittest

from rmuc_arena.engine import DT, Match, arena_map


class RustTransportTests(unittest.TestCase):
    def test_authoritative_engine_is_rust_and_timestep_is_20hz(self):
        with Match(duration=1) as match:
            self.assertEqual(match.snapshot()["engine"], "rust")
            self.assertEqual(match.snapshot()["api_version"], 3)
            for _ in range(20):
                match.step({})
            self.assertEqual(match.time, 1)
            self.assertEqual(match.status, "finished")
            self.assertEqual(DT, .05)

    def test_same_seed_and_trace_produce_identical_frames_and_hash(self):
        rng = random.Random(12)
        with Match(seed=42, duration=5) as a, Match(seed=42, duration=5) as b:
            for _ in range(100):
                commands = {team: {str(i): {"move": [rng.uniform(-1,1),rng.uniform(-1,1)],
                            "aim": rng.uniform(-4,4), "fire": True, "skill": True} for i in range(1,8)} for team in ("red","blue")}
                self.assertEqual(a.step(commands), b.step(commands))
            self.assertEqual(a.digest(), b.digest())

    def test_observations_are_slot_scoped_and_do_not_leak_enemy_stats(self):
        with Match() as m:
            obs = m.observation("red", [3])
            self.assertEqual(obs["controlled_ids"], ["3"])
            self.assertEqual(len(obs["robots"]), 6)
            self.assertEqual(obs["enemies"], [])
            self.assertEqual(obs["policy_dt"], .1)
            self.assertIn("heat", obs["robots"][0])
            self.assertIn("energy", obs["robots"][0])
            self.assertEqual(obs["roster"],[1,2,3,4,6,7])

    def test_compiled_map_matches_public_sdk_geometry(self):
        for name in ("rmuc2026",):
            with Match(map_name=name) as m:
                self.assertEqual(m.arena, arena_map(name))
                self.assertTrue(any(t["kind"]=="ramp" for t in m.arena["terrain"]))

    def test_large_and_malformed_actions_do_not_crash_rust(self):
        with Match() as m:
            m.step({"red":{"1":{"move":[10**500,0],"aim":10**500,"fire":"yes"},"9":{}}})
            self.assertEqual(m.tick,1)
            self.assertEqual(len([e for e in m.events if e["type"]=="invalid_action"]),4)

    def test_finish_and_invalid_initialization(self):
        with Match() as m:
            m.finish(None,"stopped")
            self.assertEqual(m.reason,"stopped")
            digest=m.digest()
            m.step({"red":{"1":{"fire":True}}})
            self.assertEqual(m.digest(),digest)
        with self.assertRaises(ValueError):
            Match(map_name="missing")


if __name__ == "__main__":
    unittest.main()
