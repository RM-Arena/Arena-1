import math
import random
import unittest

from rmuc_arena.legacy_engine import Match, segment_box, segment_circle


class LegacyReplayEngineTests(unittest.TestCase):
    def test_deterministic_recorded_commands(self):
        first, second = Match(123, 20), Match(123, 20)
        rng = random.Random(8)
        for _ in range(200):
            actions = {team: {str(i): {"move": [rng.uniform(-1, 1), rng.uniform(-1, 1)],
                        "aim": rng.random() * math.tau, "fire": True, "skill": True} for i in range(1, 8)}
                       for team in ("red", "blue")}
            self.assertEqual(first.step(actions), second.step(actions))
        self.assertEqual(first.digest(), second.digest())
        self.assertEqual(first.status, "finished")

    def test_visibility_and_individual_fields(self):
        m = Match()
        # Only robot 1 can see this enemy. All friends are still public to robot 2.
        m.robots[0].x, m.robots[0].y = 20, 2
        m.robots[7].x, m.robots[7].y = 23, 2
        team = m.observation("red")
        individual = m.observation("red", [2])
        self.assertIn("blue-1", [r["id"] for r in team["enemies"]])
        self.assertNotIn("blue-1", [r["id"] for r in individual["enemies"]])
        self.assertEqual(len(individual["robots"]), 7)
        self.assertEqual(individual["controlled_ids"], ["2"])
        self.assertNotIn("ammo", team["enemies"][0])
        # A wall blocks robot 1's line of sight even at close range.
        m.robots[0].x, m.robots[0].y = 11, 7
        m.robots[7].x, m.robots[7].y = 15, 7
        self.assertEqual(m.observation("red", [1])["enemies"], [])

    def test_invalid_actions_fail_closed_and_velocity_clamps(self):
        m = Match()
        m.step({"red": {"1": {"move": [float("nan"), 0], "aim": float("inf"), "fire": "yes"},
                        "2": {"move": [100, 100]}, "99": {}}})
        self.assertEqual((m.robots[0].x, m.robots[0].y), (3.5, 3))
        self.assertEqual(m.robots[0].ammo, 36)
        self.assertLessEqual(math.hypot(m.robots[1].x - 3.5, m.robots[1].y - 6), 3.2 * .1 + 1e-8)
        self.assertEqual(sum(e["type"] == "invalid_action" for e in m.events), 4)

    def test_swept_projectile_damage_and_cooldown(self):
        m = Match()
        a, b = m.robots[0], m.robots[7]
        a.x, a.y, b.x, b.y = 20, 2, 22, 2
        m.step({"red": {"1": {"aim": 0, "fire": True}}})
        self.assertEqual(b.hp, b.max_hp - 60)
        self.assertEqual(a.ammo, 35)
        m.step({"red": {"1": {"aim": 0, "fire": True}}})
        self.assertEqual(a.ammo, 35)
        self.assertEqual(b.hp, b.max_hp - 60)

    def test_wall_stops_projectile(self):
        m = Match()
        a, b = m.robots[0], m.robots[7]
        a.x, a.y, b.x, b.y = 11, 7, 15, 7
        for _ in range(10):
            m.step({"red": {"1": {"aim": 0, "fire": True}}})
        self.assertEqual(b.hp, b.max_hp)

    def test_collision_geometry_and_robots_remain_separate(self):
        m = Match(duration=30)
        m.robots[0].x, m.robots[0].y = 11, 7
        for _ in range(100):
            m.step({"red": {str(i): {"move": [1, 0]} for i in range(1, 8)}})
            living = [r for r in m.robots if r.alive]
            for i, a in enumerate(living):
                self.assertFalse(m.blocked(a.x, a.y, a.radius))
                for b in living[i + 1:]:
                    self.assertGreaterEqual(math.hypot(a.x - b.x, a.y - b.y), a.radius + b.radius - 1e-5)
        self.assertLessEqual(m.robots[0].x, 12 - m.robots[0].radius + 1e-6)

    def test_capture_economy_skill_and_timeout(self):
        m = Match(duration=25)
        m.robots[0].x, m.robots[0].y = 20, 12
        m.robots[0].hp = 200
        m.robots[1].x, m.robots[1].y = 18, 12
        m.step({"red": {"2": {"skill": True}}})
        self.assertEqual(m.robots[0].hp, 245)
        for _ in range(249):
            m.step({})
        self.assertEqual(m.zones["center"]["owner"], "red")
        self.assertEqual(m.robots[0].level, 2)
        self.assertEqual(m.winner, "red")
        self.assertEqual(m.reason, "timeout")

    def test_base_and_elimination_results(self):
        m = Match()
        m.bases["blue"]["hp"] = 0
        m.step({})
        self.assertEqual((m.winner, m.reason), ("red", "base_destroyed"))
        m = Match()
        for r in m.robots:
            if r.team == "red":
                r.alive, r.hp = False, 0
        m.step({})
        self.assertEqual((m.winner, m.reason), ("blue", "elimination"))

    def test_swept_intersections(self):
        self.assertAlmostEqual(segment_circle(0, 0, 10, 0, 5, 0, 1), .4)
        self.assertAlmostEqual(segment_box(0, 0, 10, 0, {"x": 3, "y": -1, "w": .1, "h": 2}), .3)
        self.assertIsNone(segment_circle(0, 0, 10, 0, 5, 3, 1))

    def test_extreme_integer_action_cannot_crash_match(self):
        m = Match()
        m.step({"red": {"1": {"move": [10**500, 0], "aim": 10**500}}})
        self.assertEqual(m.tick, 1)
        self.assertEqual(sum(e["type"] == "invalid_action" for e in m.events), 2)


if __name__ == "__main__":
    unittest.main()
