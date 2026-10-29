import heapq
import math
import unittest
from unittest.mock import Mock

from rmuc_arena import sdk
from rmuc_arena.engine import Match


class NavigationTests(unittest.TestCase):
    def setUp(self):
        sdk._NAV_ROUTE_COSTS.clear()

    def test_route_matches_an_independent_forward_shortest_path(self):
        graph = sdk._prepare_chapter4(sdk._REFERENCE_ARENA, "red")
        nodes, edges, clear, inside = graph
        # The second start is on the highway below the red 10.5 degree end slope.
        for start, goal in [((.43, 13.7), (13.34, 6.84)), ((10.6, 13.4), (12, 5.4))]:
            with self.subTest(start=start, goal=goal):
                initial, terminal = inside(start), inside(goal)
                connections = {i: math.dist(start, p) for i, p in enumerate(nodes) if clear(start, p, initial, True)}
                ends = {i: math.dist(p, goal) for i, p in enumerate(nodes) if clear(p, goal, terminal, True)}
                distances = dict(connections)
                queue = [(cost, i) for i, cost in connections.items()]
                heapq.heapify(queue)
                while queue:
                    cost, i = heapq.heappop(queue)
                    if cost != distances[i]:
                        continue
                    for j, length in edges[i]:
                        if cost + length < distances.get(j, math.inf):
                            distances[j] = cost + length
                            heapq.heappush(queue, (cost + length, j))
                optimum = min(distances.get(i, math.inf) + cost for i, cost in ends.items())
                chosen = sdk._route(graph, start, goal, initial, terminal, True)
                self.assertIsNotNone(chosen)
                remaining = sdk._route_costs(graph, goal, terminal, True)[chosen]
                self.assertAlmostEqual(connections[chosen] + remaining, optimum)

    def test_static_goal_reuses_visibility_connections(self):
        nodes, edges, clear, inside = sdk._prepare_chapter4(sdk._REFERENCE_ARENA, "red")
        tracked = Mock(wraps=clear)
        graph = nodes, edges, tracked, inside
        start, goal = (10.6, 13.4), (12, 5.4)
        sdk._route(graph, start, goal, inside(start), inside(goal), True)
        first = tracked.call_count
        tracked.reset_mock()
        sdk._route(graph, (10.61, 13.4), goal, inside(start), inside(goal), True)
        self.assertGreater(first, len(nodes))
        self.assertLess(tracked.call_count, first / 4)

    def test_2027_tunnel_roofs_block_routes_unless_the_robot_is_folded(self):
        # Only a folded turret fits under the 250-260 mm tunnel roofs: the road tunnel's
        # portal over the top of its ramp stops an unfolded robot, which routes by the road.
        arena = sdk.ARENAS_BY_SEASON["2027"]
        start, goal = (9.32, 11.7), (9.32, 13.6)
        for folded, open_ in ((False, False), (True, True)):
            with self.subTest(folded=folded):
                _, _, clear, _ = sdk._prepare_chapter4(arena, "red", folded)
                self.assertEqual(clear(start, goal, (), True), open_)
        robot = {"team": "red", "role": "infantry", "x": 9.32, "y": 11.7, "speed_reference_mps": 3.9, "transform_progress": 0.0}
        move = sdk.navigate(robot, goal, arena)
        self.assertLess(move[1] / math.hypot(*move), .9)

    def test_robot_pushed_inside_resource_margin_can_leave(self):
        robot = {"team": "red", "role": "engineer", "x": .43, "y": 13.7, "speed_reference_mps": 3.1}
        move = sdk.navigate(robot, (13.34, 6.84), sdk._REFERENCE_ARENA)
        self.assertGreater(move[0], 0)
        self.assertLess(move[1], 0)

    def test_a_heavy_past_the_resource_hub_brakes_then_routes_back_from_the_corner(self):
        # The heavy only has its base power to brake with: arriving at the dispenser flat out
        # carried it past the zone into the corner behind the station. There the only escape
        # waypoint was underfoot and the "already passed" skip hid it, so the chassis sat still
        # for the rest of the match. It has to brake in time, and still have a route home.
        arena = sdk.ARENAS_BY_SEASON["2027"]
        robot = {"team": "blue", "role": "heavy", "x": 26.84, "y": 1.62, "vx": .6, "vy": -1.6,
                 "speed_reference_mps": 3.2, "radius": .389, "transform_progress": 0.0}
        goal = sdk.resource_pickup_point(robot, arena)
        self.assertEqual(sdk.navigate(robot, goal, arena), (0.0, 0.0))
        robot.update(x=27.297, y=.482, vx=0.0, vy=0.0)
        move = sdk.navigate(robot, goal, arena)
        self.assertLess(move[0], -.01, "the corner escape waypoint must not be skipped")

    def test_robot_inside_a_guard_margin_never_closes_in_on_the_guard(self):
        # A hero pushed against the north end of the east guard of the red 10.5 degree end
        # slope used to be sent straight down the ramp into that guard and wedged the lane.
        arena = sdk._REFERENCE_ARENA
        guard = next(w for w in arena["obstacles"] if w["id"] == "central_red_slope_guard_1")
        cx, cy = guard["x"] + guard["w"] / 2, guard["y"] + guard["h"] / 2
        c, s = math.cos(guard["rotation"]), math.sin(guard["rotation"])

        def clearance(point):
            ax = (point[0] - cx) * c + (point[1] - cy) * s
            ay = -(point[0] - cx) * s + (point[1] - cy) * c
            return max(abs(ax) - guard["w"] / 2, abs(ay) - guard["h"] / 2)

        for start in [(12.09, 13.22), (12.12, 13.25), (12.06, 13.18)]:
            with self.subTest(start=start):
                robot = {"team": "red", "role": "hero", "x": start[0], "y": start[1], "speed_reference_mps": 3.6}
                move = sdk.navigate(robot, (13.008, 3.643), arena)
                self.assertGreater(math.hypot(*move), 0)
                step = (start[0] + move[0] * .05, start[1] + move[1] * .05)
                self.assertGreaterEqual(clearance(step), clearance(start) - 1e-9)

    def test_robot_turns_to_its_course_before_driving_onto_road_bumps(self):
        # Rounding the west end of red_kerb_5 leaves a robot facing north 0.4 m before the
        # humps; it must face east before driving on, since it cannot turn on them.
        arena = sdk._REFERENCE_ARENA
        for team, start, goal, sign in (("red", (4.85, 13.31), (11.75, 13.38), 1),
                                        ("blue", (23.15, 1.69), (16.25, 1.62), -1)):
            with self.subTest(team=team):
                robot = {"team": team, "role": "engineer", "x": start[0], "y": start[1], "heading": sign * math.pi / 2,
                         "chassis_type": "mecanum", "speed_reference_mps": 3.1}
                creep = sdk.navigate(robot, goal, arena)
                self.assertLess(math.hypot(*creep), .05)
                self.assertGreater(sign * creep[0], 0)
                robot["heading"] = 0 if sign > 0 else math.pi
                self.assertGreater(sign * sdk.navigate(robot, goal, arena)[0], .9)
                # Wheel-legged robots drive either way round.
                robot.update(heading=math.pi if sign > 0 else 0, chassis_type="wheel_legged")
                self.assertGreater(sign * sdk.navigate(robot, goal, arena)[0], .9)

    def test_robot_nosed_onto_road_bumps_backs_straight_out_holding_its_heading(self):
        # A teammate rounding the kerb end yawed a robot whose front had reached the first
        # hump; it cannot turn there, so turning on the spot left it pinned for the match.
        arena = sdk._REFERENCE_ARENA
        for team, start, goal, sign in (("red", (5.21, 13.4), (11.75, 13.38), 1),
                                        ("blue", (22.79, 1.6), (16.25, 1.62), -1)):
            with self.subTest(team=team):
                heading = .72 if sign > 0 else .72 - math.pi
                robot = {"team": team, "role": "engineer", "x": start[0], "y": start[1], "heading": heading,
                         "chassis_type": "mecanum", "speed_reference_mps": 2.6, "radius": .389}
                move = sdk.navigate(robot, goal, arena)
                self.assertLess(sign * move[0], -.5)
                self.assertAlmostEqual(move[1], 0)
                self.assertEqual(sdk.action(move)["heading"], heading)
                self.assertEqual(sdk.action(move, heading=0)["heading"], 0)
                # With its turning circle clear of the humps it turns on the spot again.
                robot["x"] = start[0] - sign * .45
                creep = sdk.navigate(robot, goal, arena)
                self.assertLess(math.hypot(*creep), .05)
                self.assertNotIn("heading", sdk.action(creep))

    def test_engineer_nosed_onto_the_bumps_at_an_angle_still_crosses(self):
        match = Match(42, 420)
        self.addCleanup(match.close)
        arena = sdk._REFERENCE_ARENA
        frame = match.snapshot()

        def engineer():
            return next(r for r in frame["robots"] if r["team"] == "red" and r["role"] == "engineer")

        for heading in (.72, -.6):
            with self.subTest(heading=heading):
                # Back to the slope top south of the kerb, then onto the first hump at an angle.
                for _ in range(600):
                    robot = engineer()
                    if math.dist((robot["x"], robot["y"]), (4.85, 12.36)) < .2:
                        break
                    frame = match.step({"red": {"2": sdk.action(sdk.navigate(robot, (4.85, 12.36), arena))}})
                for _ in range(300):
                    robot = engineer()
                    if robot["x"] >= 5.2:
                        break
                    ahead = .5 if robot["y"] > 13.3 else 0
                    frame = match.step({"red": {"2": {"move": [ahead, (13.4 - robot["y"]) * 2], "heading": heading}}})
                self.assertGreaterEqual(engineer()["x"], 5.2)
                for _ in range(300):
                    robot = engineer()
                    if robot["x"] > 8.2:
                        break
                    frame = match.step({"red": {"2": sdk.action(sdk.navigate(robot, (11.75, 13.38), arena))}})
                self.assertGreater(engineer()["x"], 8.2, (engineer()["x"], engineer()["y"], engineer()["heading"]))

    def test_robot_keeps_full_command_while_crossing_road_bumps(self):
        # The next waypoint lies just past the humps; slowing for it on them stalls the robot.
        robot = {"team": "red", "role": "hero", "x": 5.6, "y": 13.32, "heading": math.pi,
                 "chassis_type": "mecanum", "speed_reference_mps": 3.6}
        move = sdk.navigate(robot, (4.85, 12.36), sdk._REFERENCE_ARENA)
        self.assertAlmostEqual(math.hypot(*move), 1)
        self.assertLess(move[0], -.9)

    def test_loaded_engineer_crosses_the_road_bumps_after_rounding_the_kerb(self):
        match = Match(42, 420)
        self.addCleanup(match.close)
        arena = sdk._REFERENCE_ARENA
        frame = match.snapshot()

        def engineer():
            return next(r for r in frame["robots"] if r["team"] == "red" and r["role"] == "engineer")

        # Pick a unit, stop on the slope top south of the kerb, then head east over the humps.
        for goal, done in (((0.98, 13.12), lambda r: r["carried_units"] >= 1),
                           ((4.85, 12.36), lambda r: math.dist((r["x"], r["y"]), (4.85, 12.36)) <= .05
                            and math.hypot(r["vx"], r["vy"]) < .02),
                           ((11.75, 13.38), lambda r: r["x"] > 8.2)):
            for _ in range(1200):
                robot = engineer()
                if done(robot):
                    break
                far = math.dist((robot["x"], robot["y"]), goal) > .05
                frame = match.step({"red": {"2": sdk.action(sdk.navigate(robot, goal, arena) if far else (0, 0),
                                                            brake=not far, pick_unit=True)}})
            self.assertTrue(done(engineer()), (goal, engineer()["x"], engineer()["y"]))

    def test_robot_on_the_slope_centreline_still_drives_up_it(self):
        for y in (13.5, 13.0):
            robot = {"team": "red", "role": "hero", "x": 11.9, "y": y, "speed_reference_mps": 3.6}
            move = sdk.navigate(robot, (13.008, 3.643), sdk._REFERENCE_ARENA)
            self.assertLess(move[1], -.9)

    def test_public_structure_armor_guides_aiming_without_selecting_a_heavy_only_panel(self):
        match = Match()
        self.addCleanup(match.close)
        target = dict(match.outposts['blue'], kind='outpost')
        shooter = {'role':'infantry','x':target['x']+2,'y':target['y'],
                   'z':target['z'], 'muzzle_height_m':.45}
        selected = sdk._aim_target(shooter,target)
        plate = next(p for p in target['armor_plates'] if tuple(p['center'])==selected)
        self.assertFalse(plate['heavy_only'])
        self.assertGreater(sum(n*(a-b) for n,a,b in zip(plate['normal'],
            (shooter['x'],shooter['y'],shooter['z']+.45),selected)),0)
        self.assertNotEqual(selected[:2],(target['x'],target['y']))

    def test_explicit_predicted_target_height_overrides_published_stationary_plates(self):
        target={'x':7,'y':4,'aim_z':1.2,'armor_plates':[{'center':[5,6,.2]}]}
        self.assertEqual(sdk._aim_target({'role':'hero'},target),(7,4,1.2))


if __name__ == "__main__":
    unittest.main()
