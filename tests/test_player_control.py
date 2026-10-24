"""First-person manual takeover: a pilot overrides one robot while its team strategy keeps playing."""
import math
from pathlib import Path
import tempfile
import time
import unittest

from fastapi.testclient import TestClient
from rmuc_arena.server import create_app

ACTION = {"move": [1, 0], "aim": 0.0, "pitch": 0.0, "fire": True}


class PlayerControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.app = create_app("trusted-local", root / "submissions", root / "data", test_mode=True)
        self.client = TestClient(self.app)
        self.arena = self.app.state.arena
        self.addCleanup(self.arena.shutdown)

    def start_match(self, duration=4):
        response = self.client.post("/api/start", json={"duration": duration})
        self.assertEqual(response.status_code, 200, response.text)
        deadline = time.monotonic() + 30
        while self.arena.battle is None and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertIsNotNone(self.arena.battle, "the battle never started")
        return response.json()["match_id"]

    def test_a_pilot_command_reaches_the_engine_and_is_replayed(self):
        match_id = self.start_match()
        response = self.client.post("/api/player", json={"team": "red", "slot": 1, "action": ACTION})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["player"], {"team": "red", "slot": 1})
        self.assertEqual(self.arena.state()["player"], {"team": "red", "slot": 1})
        # The strategy tick still runs; the pilot's command replaces its action for that slot.
        deadline, recorded = time.monotonic() + 3, False
        while time.monotonic() < deadline and not recorded:
            recorded = any((entry.get("red") or {}).get("1", {}).get("move") == [1, 0] for entry in self.arena.battle.actions)
            time.sleep(.02)
        self.assertTrue(recorded, "the pilot's command never reached the engine")
        deadline = time.monotonic() + 30
        while self.arena.state()["busy"] and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertIsNone(self.arena.state()["player"])
        replay = self.client.get("/api/replays/" + match_id).json()
        moves = [(entry.get("red") or {}).get("1", {}).get("move") for entry in replay["actions"]]
        self.assertIn([1, 0], moves)

    def test_a_silent_pilot_coasts_then_hands_the_robot_back(self):
        self.start_match()
        self.assertEqual(self.client.post("/api/player", json={"team": "blue", "slot": 3, "action": ACTION}).status_code, 200)
        # A short gap keeps the robot manual: it brakes instead of being driven by its strategy.
        time.sleep(1)
        coasting = self.arena.battle._manual_commands().get("blue", {}).get("3")
        self.assertIsNotNone(coasting, "a piloted robot fell back to its strategy after a brief gap")
        self.assertEqual(coasting["move"], [0.0, 0.0])
        self.assertTrue(coasting["brake"])
        self.assertFalse(coasting["fire"])
        # Silence for the full timeout returns it to the strategy.
        time.sleep(2)
        self.assertEqual(self.arena.battle._manual_commands(), {})

    def test_aerial_robots_cannot_be_piloted(self):
        self.start_match()
        for team in ("red", "blue"):
            response = self.client.post("/api/player", json={"team": team, "slot": 6, "action": ACTION})
            self.assertEqual(response.status_code, 409, response.text)
            self.assertIn("空中机器人", response.json()["detail"])
        self.assertEqual(self.arena.state()["player"], None)
        # Releasing an unpiloted robot is always harmless.
        self.assertEqual(self.client.post("/api/player", json={"team": "red", "slot": 6, "action": None}).status_code, 200)

    def test_aim_assist_points_the_gimbal_at_the_armour(self):
        self.start_match()
        self.assertEqual(self.client.post("/api/player", json={"team": "red", "slot": 3, "action": ACTION, "assist": "blue-4"}).status_code, 200)
        battle = self.arena.battle
        robot = next(r for r in battle.match.robots if r["id"] == "red-3")
        enemy = next(r for r in battle.match.robots if r["id"] == "blue-4")
        # Put the pair on the open red half: at the spawn line the central highland covers the
        # target plate, and the assist must refuse that shot (the visibility test below).
        robot.update(x=3.2, y=6.15, z=.2, vx=0., vy=0., vz=0.)
        enemy.update(x=7.2, y=6.15, z=.2, vx=0., vy=0., vz=0.)
        # The assist replaces the pilot's own angles with the engine's ballistic solution.
        held = battle._manual_commands()
        action = held.get("red", {}).get("3")
        self.assertIsNotNone(action, "the assisted command was not held")
        self.assertAlmostEqual(action["aim"], math.atan2(enemy["y"] - robot["y"], enemy["x"] - robot["x"]), delta=.25)
        # Inside ten metres the elevation is the full engine solution.
        from rmuc_arena import sdk
        solved = sdk.aim_pitch(robot, enemy)
        self.assertAlmostEqual(action["pitch"], solved, places=9)
        self.assertNotEqual(action["pitch"], ACTION["pitch"], "the assist must replace the pilot's pitch")
        # An enemy id outside the field, or one of our own robots, leaves the pilot's own angles alone.
        self.client.post("/api/player", json={"team": "red", "slot": 3, "action": ACTION, "assist": "red-4"})
        self.assertEqual(self.arena.battle._manual_commands()["red"]["3"]["aim"], ACTION["aim"])

    def test_sight_blocked_catches_a_thin_wall(self):
        """A 0.15 m barrier must block the assist, not slip between ray samples."""
        from rmuc_arena import runner
        arena = {
            "name": "test", "width": 28, "height": 15, "floor_slope_deg": 0, "terrain": [],
            "obstacles": [{"x": 11.3, "y": 6.5, "w": .15, "h": 2, "height": 1, "bottom": 0, "rotation": 0}],
        }
        self.assertTrue(runner.sight_blocked(arena, (10, 7.5, .6), (14, 7.5, .6)))
        self.assertFalse(runner.sight_blocked({**arena, "obstacles": []}, (10, 7.5, .6), (14, 7.5, .6)))

    def test_a_lobbed_shot_waits_for_the_launcher_to_climb(self):
        """A lobbed round is held until the muzzle is actually on the solved arc.

        The gun slews in the engine, so a trigger pressed on the same tick as the order would send
        the shell off at the shallow angle the launcher still had — the round that drops into the
        ground a few metres in front of the robot instead of onto the reticle.
        """
        from rmuc_arena import sdk
        self.start_match()
        battle = self.arena.battle
        robot = next(r for r in battle.match.robots if r["role"] == "heavy")
        slot = str(robot["slot"])
        robot.update(launcher="installed", ammo=max(5, robot["ammo"]), heat=0.0, max_heat=300.0, vx=0.0, vy=0.0, vz=0.0,
                     quaternion=[0.0, 0.0, 0.0, 1.0], pitch=0.0)
        heading = robot["heading"]
        point = [robot["x"] + 12 * math.cos(heading), robot["y"] + 12 * math.sin(heading), 0.2]
        solved = sdk.lob_aim(robot, point)
        self.assertIsNotNone(solved, "the solver has to reach a point twelve metres out")
        yaw, elevation = solved
        self.assertLess(elevation, math.radians(45), "吊射是平射弹道，不该抬到高抛角")
        self.assertGreater(elevation, math.radians(2), "十二米的落点要有一点仰角")
        action = {**ACTION, "move": [0, 0], "aim_point": point}
        battle.set_manual(robot["team"], int(slot), dict(action))
        held = battle._manual_commands()[robot["team"]][slot]
        self.assertFalse(held["fire"], "the round left before the launcher climbed")
        self.assertAlmostEqual(held["pitch"], elevation, delta=1e-6)
        self.assertGreater(battle.lob_ready[(robot["team"], slot)], time.monotonic())
        # Once the climb is over the same held trigger fires, without a new order from the pilot.
        battle.lob_ready[(robot["team"], slot)] = 0.0
        held = battle._manual_commands()[robot["team"]][slot]
        self.assertTrue(held["fire"], "the queued round never left")

    def test_the_runner_refuses_a_shot_that_would_overheat(self):
        """The engine adds heat after firing, so the runner drops a shot that no longer fits."""
        self.start_match()
        battle = self.arena.battle
        robot = next(r for r in battle.match.robots if r["id"] == "red-3")
        robot["ammo"] = max(1, robot["ammo"])
        battle.set_manual("red", 3, dict(ACTION))
        robot["heat"] = 0
        self.assertTrue(battle._manual_commands()["red"]["3"]["fire"])
        robot["heat"] = robot["max_heat"]
        self.assertFalse(battle._manual_commands()["red"]["3"]["fire"])

    def test_a_far_target_keeps_only_80_percent_of_the_solved_pitch(self):
        """Past ten metres the assist trims the solved elevation by 20 % instead of floating."""
        from rmuc_arena import runner, sdk
        self.start_match()
        robots = {(r["team"], str(r["slot"])): dict(r) for r in self.arena.battle.match.robots}
        red = robots[("red", "3")]
        red.update(x=6.0, y=7.5, z=.2, vx=0., vy=0., vz=0.)
        target = robots[("blue", "4")]
        target.update(x=26.0, y=7.5, z=.2, vx=0., vy=0., vz=0., aim_z=.5)
        far = runner.aim_assist(red, "blue-4", robots, None, 0.0)
        self.assertIsNotNone(far)
        solved = sdk.aim_pitch(red, target)
        self.assertGreater(solved, .05, "a 17 mm shot needs elevation")
        self.assertAlmostEqual(far[1], solved * .8, places=9)
        # Inside ten metres the full engine solution is used.
        target["x"] = 10.0
        near = runner.aim_assist(red, "blue-4", robots, None, 0.0)
        self.assertIsNotNone(near)
        self.assertAlmostEqual(near[1], sdk.aim_pitch(red, target), places=9)

    def test_a_pilot_can_buy_ammo_in_the_supply_zone(self):
        match_id = self.start_match(duration=5)
        # Red 1 starts on its base pad, so the engine accepts a local purchase at list price.
        # Team income only lands after the first second, so keep pressing like a pilot would.
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.client.post("/api/player", json={"team": "red", "slot": 1,
                                                  "action": {**ACTION, "move": [0, 0], "fire": False,
                                                             "buy_ammo": {"remote": False}}})
            time.sleep(.1)
        deadline = time.monotonic() + 30
        while self.arena.state()["busy"] and time.monotonic() < deadline:
            time.sleep(.02)
        replay = self.client.get("/api/replays/" + match_id).json()
        orders = [a for entry in replay["actions"] for a in [(entry.get("red") or {}).get("1") or {}] if "buy_ammo" in a]
        self.assertTrue(orders, "the pilot's ammo order was not recorded")
        red1 = next(r for r in replay["frames"][-1]["robots"] if r["id"] == "red-1")
        self.assertGreater(red1["ammo"], 0, "the local purchase should have loaded the launcher")

    def test_a_step_climb_command_is_accepted_for_a_climbing_chassis(self):
        self.start_match()
        # The step-climbing infantry (slot 3) may send `climb`; the folding infantry (slot 4) may
        # not. Both go through the same endpoint the cockpit uses.
        response = self.client.post("/api/player", json={"team": "red", "slot": 3,
                                                        "action": {**ACTION, "climb": 1}})
        self.assertEqual(response.status_code, 200, response.text)
        held = self.arena.battle._manual_commands()["red"]["3"]
        self.assertEqual(held.get("climb"), 1)
        # An unsupported field is still rejected, so a stale client cannot smuggle anything in.
        response = self.client.post("/api/player", json={"team": "red", "slot": 3,
                                                        "action": {**ACTION, "teleport": True}})
        self.assertEqual(response.status_code, 409, response.text)

    def test_aim_assist_targets_structures_and_never_shoots_through_terrain(self):
        from rmuc_arena import runner, sdk
        self.start_match()
        battle = self.arena.battle
        arena = battle.match.arena
        robots = {(r["team"], str(r["slot"])): r for r in battle.match.robots}
        structures = {f"{team}_base": {**base, "kind": "base"} for team, base in battle.match.bases.items()}
        for team, outpost in (battle.match.outposts or {}).items():
            structures[f"{team}_outpost"] = {**outpost, "kind": "outpost"}
        robot = dict(robots[("red", "3")])
        outpost = structures["blue_outpost"]
        robot.update(x=outpost["x"] - 6.0, y=outpost["y"], z=.2)
        view = math.atan2(outpost["y"] - robot["y"], outpost["x"] - robot["x"])
        aimed = runner.aim_assist(robot, "blue_outpost", robots, arena, view, structures)
        self.assertIsNotNone(aimed, "the outpost armour should be assistable")
        plate = sdk._aim_target(robot, outpost)
        self.assertAlmostEqual(aimed[0], math.atan2(plate[1] - robot["y"], plate[0] - robot["x"]), delta=.3)
        # The central deck is solid: a line at deck height is blocked, so no assist reaches through it.
        self.assertTrue(runner.sight_blocked(arena, (9.0, 7.5, .1), (18.0, 7.5, .1)))
        self.assertFalse(runner.sight_blocked(arena, (9.0, 7.5, 1.4), (18.0, 7.5, 1.4)))

    def test_aim_assist_uses_an_outposts_actual_owner(self):
        """A rebuilt outpost belongs to its new team, not to the half of the field it stands on."""
        from rmuc_arena import runner
        self.start_match()
        battle = self.arena.battle
        arena = battle.match.arena
        robots = {(r["team"], str(r["slot"])): r for r in battle.match.robots}
        structures = {f"{team}_base": {**base, "kind": "base"} for team, base in battle.match.bases.items()}
        for team, outpost in (battle.match.outposts or {}).items():
            structures[f"{team}_outpost"] = {**outpost, "kind": "outpost"}
        outpost = structures["blue_outpost"]
        # Red rebuilt the blue outpost: it is now a red structure.
        outpost["owner"] = "red"
        red = dict(robots[("red", "3")])
        red.update(x=outpost["x"] - 6.0, y=outpost["y"], z=.2)
        view = math.atan2(outpost["y"] - red["y"], outpost["x"] - red["x"])
        self.assertIsNone(
            runner.aim_assist(red, "blue_outpost", robots, arena, view, structures),
            "a pilot must not assist their own rebuilt outpost",
        )
        blue = dict(robots[("blue", "3")])
        blue.update(x=outpost["x"] - 6.0, y=outpost["y"], z=.2)
        self.assertIsNotNone(
            runner.aim_assist(blue, "blue_outpost", robots, arena, view, structures),
            "the other team must be able to assist the outpost it lost",
        )

    def test_one_ammo_order_waits_for_a_tick_the_rulebook_reads(self):
        self.start_match()
        battle = self.arena.battle
        # The rulebook only reads orders on even ticks, so an order that rides on a single 50 ms
        # command would be dropped half the time; the runner holds it until a tick it is read.
        battle.set_manual("red", 3, {**ACTION, "buy_ammo": {"remote": True}})
        battle.match._frame["tick"] = 7
        self.assertNotIn("buy_ammo", battle._manual_commands()["red"]["3"])
        battle.match._frame["tick"] = 8
        self.assertIn("buy_ammo", battle._manual_commands()["red"]["3"])
        # Delivered once: the next tick must not buy a second batch.
        battle.match._frame["tick"] = 10
        self.assertNotIn("buy_ammo", battle._manual_commands()["red"]["3"])

    def test_a_pilot_spins_the_chassis_while_the_gimbal_holds_the_aim(self):
        """小陀螺: `yaw_rate` turns the hull under a gimbal that keeps the commanded world aim."""
        self.start_match(duration=6)
        action = {**ACTION, "move": [0, 0], "fire": False, "aim": 1.2, "yaw_rate": 3}
        self.assertEqual(self.client.post("/api/player", json={"team": "red", "slot": 4, "action": action}).status_code, 200)
        battle = self.arena.battle
        pose = lambda: next(r for r in battle.match.robots if r["id"] == "red-4")
        start, turned = pose()["heading"], 0.0
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            self.client.post("/api/player", json={"team": "red", "slot": 4, "action": action})
            turned = max(turned, abs((pose()["heading"] - start + math.pi) % (2 * math.pi) - math.pi))
            if turned > .6:
                break
            time.sleep(.05)
        self.assertGreater(turned, .6, "the chassis never spun")
        # The gimbal keeps aiming where the pilot asked, so the crosshair does not wander while spinning.
        drift = abs((pose()["aim"] - action["aim"] + math.pi) % (2 * math.pi) - math.pi)
        self.assertLess(drift, .35, "the gimbal lost the aim while the chassis spun")
        held = battle._manual_commands()["red"]["4"]
        self.assertAlmostEqual(held["yaw_rate"], 3, delta=.01)
        self.assertEqual(held["move"], [0.0, 0.0], "spinning in place must not drive the chassis")

    def test_releasing_and_validating_a_takeover(self):
        self.assertEqual(self.client.post("/api/player", json={"team": "red", "slot": 1, "action": ACTION}).status_code, 409)
        self.start_match()
        self.assertEqual(self.client.post("/api/player", json={"team": "red", "slot": 8, "action": ACTION}).status_code, 409)
        self.assertEqual(self.client.post("/api/player", json={"team": "red", "slot": 1, "action": {"teleport": True}}).status_code, 409)
        self.assertEqual(self.client.post("/api/player", json={"team": "red", "slot": 0, "action": ACTION}).status_code, 422)
        self.assertEqual(self.client.post("/api/player", json={"team": "red", "slot": 1, "action": ACTION}).status_code, 200)
        released = self.client.post("/api/player", json={"team": "red", "slot": 1, "action": None})
        self.assertEqual(released.status_code, 200, released.text)
        self.assertIsNone(released.json()["player"])
        self.assertIsNone(self.arena.state()["player"])


if __name__ == "__main__":
    unittest.main()
