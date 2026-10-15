"""Public strategy API; this is the only arena code mounted in a policy sandbox.

Implement act(observation, state) -> (actions, new_state).
Actions are keyed by robot slot, e.g. {"1": action(...)}. In robot mode only
observation['controlled_ids'] is accepted. State must be JSON serializable.
"""
import math
from typing import Any, Literal, TypedDict


class RobotState(TypedDict, total=False):
    id: str
    slot: int
    team: str
    role: str
    x: float
    y: float
    z: float
    vx: float
    vy: float
    hp: float
    max_hp: float
    ammo: int
    aim: float
    heat: float
    energy: float
    alive: bool


class Action(TypedDict, total=False):
    move: list[float]
    aim: float | None
    pitch: float
    fire: bool
    skill: bool
    upgrade: Literal["damage", "armor", "mobility"]


class Observation(TypedDict):
    api_version: int
    seed: int
    tick: int
    time: float
    dt: float
    policy_dt: float
    remaining: float
    team: str
    controlled_ids: list[str]
    robots: list[RobotState]
    enemies: list[RobotState]
    arena: dict[str, Any]
    bases: dict[str, Any]
    teams: dict[str, Any]
    zones: dict[str, Any]
    projectiles: list[dict[str, Any]]
    specs: dict[str, Any]

API_VERSION = 2


def action(move=(0.0, 0.0), aim=None, fire=False, skill=False, pitch=0.04, upgrade=None):
    """World-space velocity intent in [-1, 1]; aim is an angle in radians.

    +x goes toward blue's base; +y goes toward the south side of the map.
    Aim None retains the current turret angle. Shooting is a moving projectile.
    Skill activates a temporary shield (engineer: heals nearby teammates).
    """
    result = {"move": list(move), "aim": aim, "pitch": pitch, "fire": fire, "skill": skill}
    if upgrade is not None:
        result["upgrade"] = upgrade
    return result


def aim_pitch(robot, target, speed=30):
    """Approximate ballistic elevation, including relative terrain height."""
    d = max(0.1, distance(robot, target))
    height = target.get("z", 0) + 0.55 - robot.get("z", 0) - 0.78
    return max(-0.3, min(0.5, math.atan2(height, d) + 9.81 * d / (2 * speed * speed)))


def intercept(robot, target, speed=30):
    """Lead a moving visible enemy using its public velocity."""
    t = distance(robot, target) / speed
    point = dict(target)
    point["x"] += target.get("vx", 0) * t
    point["y"] += target.get("vy", 0) * t
    return point


def toward(robot, point):
    dx, dy = point[0] - robot["x"], point[1] - robot["y"]
    distance = math.hypot(dx, dy)
    return (dx / distance, dy / distance) if distance > 0.05 else (0.0, 0.0)


def aim_at(robot, target):
    return math.atan2(target["y"] - robot["y"], target["x"] - robot["x"])


def distance(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def nearest_enemy(robot, observation):
    enemies = [r for r in observation["enemies"] if r["alive"]]
    return min(enemies, key=lambda r: (distance(robot, r), r["id"]), default=None)


def navigate(robot, point, arena):
    """Small obstacle-aware helper; strategies can replace it with pathfinding.

    Follow the cheapest collision-free waypoint graph around expanded wall
    corners. The public geometry is identical for every strategy.
    """
    import heapq

    margin = robot.get("radius", 0.48) + 0.18
    for platform in arena.get("terrain", []):
        if platform.get("kind") != "platform":
            continue
        inside_goal = platform["x"] <= point[0] <= platform["x"] + platform["w"] and platform["y"] <= point[1] <= platform["y"] + platform["h"]
        inside_robot = platform["x"] <= robot["x"] <= platform["x"] + platform["w"] and platform["y"] <= robot["y"] <= platform["y"] + platform["h"]
        if inside_goal and not inside_robot:
            ramps = [t for t in arena["terrain"] if t.get("kind") == "ramp" and abs(t.get("elevation", 0) - platform["elevation"]) < .01]
            if ramps:
                ramp = min(ramps, key=lambda t: math.hypot(robot["x"] - (t["x"] + t["w"] / 2), robot["y"] - (t["y"] + t["h"] / 2)))
                in_ramp = ramp["x"] - .1 <= robot["x"] <= ramp["x"] + ramp["w"] + .1 and ramp["y"] <= robot["y"] <= ramp["y"] + ramp["h"]
                if not in_ramp:
                    point = (ramp["x"] + .1 if ramp["direction"] > 0 else ramp["x"] + ramp["w"] - .1, max(ramp["y"] + margin, min(point[1], ramp["y"] + ramp["h"] - margin)))
    walls = [{"x": w["x"] - margin, "y": w["y"] - margin,
              "w": w["w"] + margin * 2, "h": w["h"] + margin * 2}
             for w in arena["obstacles"]]

    def clear(a, b):
        for w in walls:
            lo, hi = 0.0, 1.0
            for p, d, low, high in ((a[0], b[0] - a[0], w["x"], w["x"] + w["w"]),
                                    (a[1], b[1] - a[1], w["y"], w["y"] + w["h"])):
                if abs(d) < 1e-9:
                    if not low < p < high:
                        lo = 2
                        break
                else:
                    aa, bb = sorted(((low - p) / d, (high - p) / d))
                    lo, hi = max(lo, aa), min(hi, bb)
            if lo < hi and hi > 0 and lo < 1:
                return False
        return True

    start, goal = (robot["x"], robot["y"]), tuple(point)
    if clear(start, goal):
        return toward(robot, goal)
    nodes = [start, goal]
    for w in walls:
        for x in (w["x"] - 0.03, w["x"] + w["w"] + 0.03):
            for y in (w["y"] - 0.03, w["y"] + w["h"] + 0.03):
                if margin < x < arena["width"] - margin and margin < y < arena["height"] - margin:
                    nodes.append((x, y))
    queue, best = [(0.0, 0, [])], {0: 0.0}
    while queue:
        cost, node, path = heapq.heappop(queue)
        if cost > best[node]:
            continue
        if node == 1:
            return toward(robot, nodes[path[0]])
        for i, candidate in enumerate(nodes):
            if i == node or not clear(nodes[node], candidate):
                continue
            distance_ = math.dist(nodes[node], candidate)
            new_cost = cost + distance_
            if new_cost < best.get(i, float("inf")):
                best[i] = new_cost
                heapq.heappush(queue, (new_cost, i, path + [i]))
    return (0.0, 0.0)
