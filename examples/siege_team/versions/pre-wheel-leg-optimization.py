"""Siege team strategy.

Plan: the aerial robot takes down the enemy outpost from its lane in the first
half minute; the hero deploys on flat ground in our half and shells the enemy
base with 42mm; infantry hunt the enemy hero and escort ours; the engineer
races the tech tree and rebuilds our outpost. Navigation uses a slope- and
clearance-aware grid built at import time, so decisions stay cheap.
"""
import heapq
import math

import sdk
from sdk import action, aim_at, aim_pitch, ballistic_reachable, can_fire, instant_revive_cost, remote_heal_cost

ARENA = sdk._REFERENCE_ARENA
W, H = ARENA["width"], ARENA["height"]
ENEMY = {"red": "blue", "blue": "red"}

# ---------------------------------------------------------------- terrain grid
RES = 0.1
NX, NY = int(W / RES), int(H / RES)
CRES = 0.2
CX, CY = NX // 2, NY // 2


def _heights():
    return [sdk.terrain_height(ARENA, (i + .5) * RES, (j + .5) * RES) for i in range(NX) for j in range(NY)]


HEIGHT = _heights()


def _grade():
    g = [0.0] * (NX * NY)
    for i in range(NX):
        base = i * NY
        for j in range(NY):
            h = HEIGHT[base + j]
            worst = 0.0
            if i > 0:
                worst = max(worst, abs(h - HEIGHT[base - NY + j]))
            if i < NX - 1:
                worst = max(worst, abs(h - HEIGHT[base + NY + j]))
            if j > 0:
                worst = max(worst, abs(h - HEIGHT[base + j - 1]))
            if j < NY - 1:
                worst = max(worst, abs(h - HEIGHT[base + j + 1]))
            g[base + j] = worst / RES
    return g


GRADE = _grade()


def _walls(team):
    """Static blocked cells for one team: walls, no-go areas and structure bodies."""
    blocked = bytearray(NX * NY)

    def box(cx, cy, hw, hh, angle):
        c, s = math.cos(angle), math.sin(angle)
        reach = math.hypot(hw, hh)
        for i in range(max(0, int((cx - reach) / RES)), min(NX, int((cx + reach) / RES) + 1)):
            x = (i + .5) * RES - cx
            for j in range(max(0, int((cy - reach) / RES)), min(NY, int((cy + reach) / RES) + 1)):
                y = (j + .5) * RES - cy
                if abs(x * c + y * s) <= hw and abs(-x * s + y * c) <= hh:
                    blocked[i * NY + j] = 1

    for o in ARENA["obstacles"]:
        box(o["x"] + o["w"] / 2, o["y"] + o["h"] / 2, o["w"] / 2, o["h"] / 2, o.get("rotation", 0))
    for f in ARENA["forbidden"]:
        if f["kind"] == "base" or f.get("owner") not in (None, team):
            box(f["x"] + f["w"] / 2, f["y"] + f["h"] / 2, f["w"] / 2, f["h"] / 2, 0)
    for x, y in ARENA["outposts"].values():
        box(x, y, .35, .35, 0)
    return blocked


def _clearance(blocked):
    """Chamfer distance (metres) to the nearest blocked cell or field edge."""
    big = 10 ** 6
    d = [0 if blocked[k] else big for k in range(NX * NY)]
    for i in range(NX):
        for j in range(NY):
            k = i * NY + j
            if not d[k]:
                continue
            v = min(d[k], 3 * (i + 1), 3 * (j + 1))
            if i > 0:
                v = min(v, d[k - NY] + 3)
                if j > 0:
                    v = min(v, d[k - NY - 1] + 4)
                if j < NY - 1:
                    v = min(v, d[k - NY + 1] + 4)
            if j > 0:
                v = min(v, d[k - 1] + 3)
            d[k] = v
    for i in range(NX - 1, -1, -1):
        for j in range(NY - 1, -1, -1):
            k = i * NY + j
            if not d[k]:
                continue
            v = min(d[k], 3 * (NX - i), 3 * (NY - j))
            if i < NX - 1:
                v = min(v, d[k + NY] + 3)
                if j > 0:
                    v = min(v, d[k + NY - 1] + 4)
                if j < NY - 1:
                    v = min(v, d[k + NY + 1] + 4)
            if j < NY - 1:
                v = min(v, d[k + 1] + 3)
            d[k] = v
    return [v * RES / 3 for v in d]


SLOPES = (0.15, 0.2, 0.27, 0.4)      # climbable grade classes (tan of slope)
_GRIDS = {}


def grid(team, slope):
    """Clearance map for a team and climbable grade; built once per class."""
    key = (team, slope)
    if key not in _GRIDS:
        walls = _WALLS[team]
        blocked = bytearray(walls)
        for k in range(NX * NY):
            if GRADE[k] > slope:
                blocked[k] = 1
        _GRIDS[key] = _clearance(blocked)
    return _GRIDS[key]


_WALLS = {team: _walls(team) for team in ("red", "blue")}
for _team in ("red", "blue"):
    for _slope in SLOPES:
        grid(_team, _slope)


def cell(x, y):
    return min(NX - 1, max(0, int(x / RES))), min(NY - 1, max(0, int(y / RES)))


def clearance_at(clear, x, y):
    i, j = cell(x, y)
    return clear[i * NY + j]


def line_free(clear, a, b, radius):
    dist = math.dist(a, b)
    steps = max(1, int(dist / .08))
    for s in range(steps + 1):
        t = s / steps
        if clearance_at(clear, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) < radius:
            return False
    return True


def coarse_ok(clear, I, J, radius):
    if not (0 <= I < CX and 0 <= J < CY):
        return False
    k = 2 * I * NY + 2 * J
    return min(clear[k], clear[k + 1], clear[k + NY], clear[k + NY + 1]) >= radius


def nearest_free(clear, x, y, radius, limit=12):
    I, J = int(x / CRES), int(y / CRES)
    best = None
    for r in range(limit + 1):
        for dI in range(-r, r + 1):
            for dJ in (-r, r) if abs(dI) != r else range(-r, r + 1):
                if coarse_ok(clear, I + dI, J + dJ, radius):
                    p = ((I + dI + .5) * CRES, (J + dJ + .5) * CRES)
                    d = math.dist(p, (x, y))
                    if best is None or d < best[0]:
                        best = (d, I + dI, J + dJ)
        if best:
            return best[1], best[2]
    return None


def astar(clear, start, goal, radius, budget=6000):
    s = nearest_free(clear, start[0], start[1], radius)
    g = nearest_free(clear, goal[0], goal[1], radius)
    if s is None or g is None:
        return None
    if s == g:
        return [goal]
    gx, gy = g
    openq = [(0.0, 0.0, s)]
    came = {s: None}
    cost = {s: 0.0}
    steps = ((1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414))
    found = None
    while openq and budget > 0:
        budget -= 1
        _, c, node = heapq.heappop(openq)
        if node == g:
            found = node
            break
        if c > cost[node]:
            continue
        I, J = node
        for dI, dJ, w in steps:
            nI, nJ = I + dI, J + dJ
            if not coarse_ok(clear, nI, nJ, radius):
                continue
            if dI and dJ and not (coarse_ok(clear, I + dI, J, radius) and coarse_ok(clear, I, J + dJ, radius)):
                continue
            k = 2 * nI * NY + 2 * nJ
            margin = clear[k] - radius
            nc = c + w * (1.0 + (0.8 if margin < .12 else 0.0))
            nxt = (nI, nJ)
            if nc < cost.get(nxt, 1e18):
                cost[nxt] = nc
                came[nxt] = node
                dx, dy = abs(nI - gx), abs(nJ - gy)
                heapq.heappush(openq, (nc + max(dx, dy) + .414 * min(dx, dy), nc, nxt))
    if found is None:
        return None
    path = []
    node = found
    while node is not None:
        path.append(((node[0] + .5) * CRES, (node[1] + .5) * CRES))
        node = came[node]
    path.reverse()
    path[-1] = goal if clearance_at(clear, goal[0], goal[1]) >= radius else path[-1]
    return path


# ---------------------------------------------------------------- helpers
MEM = {}          # per-robot planning memory; lives for the match in this process
def wrap(a):
    return (a + math.pi) % math.tau - math.pi


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def pos(r):
    return (r["x"], r["y"])


class Ctx:
    def __init__(self, obs, state):
        self.obs = obs
        self.state = state
        self.team = obs["team"]
        self.enemy = ENEMY[self.team]
        self.t = obs["time"]
        self.tick = obs["tick"]
        self.econ = obs["teams"][self.team]
        self.coins = self.econ["resources"]
        self.robots = {r["slot"]: r for r in obs["robots"]}
        self.enemies = [e for e in obs["enemies"] if e["alive"]]
        self.targets = [e for e in self.enemies if e.get("targetable", True)]
        self.outpost = obs["outposts"][self.enemy]
        self.base = obs["bases"][self.enemy]
        self.my_outpost = obs["outposts"][self.team]
        self.my_base = obs["bases"][self.team]
        self.zones = {z["id"]: z for z in obs["arena"]["zones"]}
        self.claims = set()

    def p(self, x, y):
        """Red-side coordinates to this team's coordinates."""
        return (x, y) if self.team == "red" else (W - x, H - y)

    def mem(self, slot):
        return MEM.setdefault(slot, {})

    def spend(self, amount):
        if self.coins >= amount:
            self.coins -= amount
            return True
        return False

    def in_zone(self, robot, zone_id):
        z = self.zones[zone_id]
        if z.get("polygon"):
            return sdk.point_in_polygon(robot["x"], robot["y"], z["polygon"])
        return dist(pos(robot), (z["x"], z["y"])) <= z["radius"]


# ---------------------------------------------------------------- motion
RADIUS = {"hero": .41, "engineer": .37, "infantry": .35}


def climb_grade(robot):
    """Steepest grade the chassis can drive up at its present power limit."""
    d = sdk.DESIGNS[str(robot["slot"])]
    power = robot["power_limit"] * (1.25 if robot.get("energy", 0) >= 25000 else 1.0)
    force = min(d["motor_force_max_n"], max(0, power - 3) * d["drive_efficiency"] / .55,
                robot["mass_kg"] * 9.81 * d["tire_friction"] * .8)
    need = force * .85 / (robot["mass_kg"] * 9.81) - d["rolling_resistance"]
    best = SLOPES[0]
    for s in SLOPES:
        if s <= math.tan(math.asin(max(0.0, min(.99, need)))):
            best = s
    return best


def go(ctx, robot, goal, slack=.25, fast=1.0):
    """Move command toward goal along a planned path; returns (move, arrived)."""
    m = ctx.mem(robot["slot"])
    here = pos(robot)
    goal = (min(W - .3, max(.3, goal[0])), min(H - .3, max(.3, goal[1])))
    remaining = dist(here, goal)
    if remaining <= slack:
        m.pop("path", None)
        return (0.0, 0.0), True
    radius = RADIUS[robot["role"]]
    slope = climb_grade(robot)
    clear = grid(ctx.team, slope)
    # Stuck handling: back away from the obstacle for a moment, then replan.
    hist = m.setdefault("hist", [])
    hist.append((ctx.t, here[0], here[1]))
    while hist and hist[0][0] < ctx.t - 1.6:
        hist.pop(0)
    if m.get("escape_until", -1) > ctx.t:
        ex, ey = m["escape"]
        return (ex, ey), False
    if len(hist) > 12 and math.dist(hist[0][1:], here) < .12 and m.get("moving"):
        a = m.get("dir", 0.0) + math.pi + (0.9 if (ctx.tick // 20) % 2 else -0.9)
        m["escape"] = (math.cos(a) * .7, math.sin(a) * .7)
        m["escape_until"] = ctx.t + .7
        m.pop("path", None)
        hist.clear()
        return m["escape"], False
    if line_free(clear, here, goal, radius * .9):
        target = goal
    else:
        path = m.get("path")
        if not path or dist(m.get("pgoal", (-9, -9)), goal) > .3 or m.get("pslope") != slope or ctx.t - m.get("ptime", -9) > 4:
            if ctx.state.get("_plans", 0) >= 2 and path:
                pass
            else:
                ctx.state["_plans"] = ctx.state.get("_plans", 0) + 1
                path = astar(clear, here, goal, radius)
                m["path"], m["pgoal"], m["pslope"], m["ptime"] = path, goal, slope, ctx.t
        if not path:
            target = goal
        else:
            # Drop passed points, then steer at the farthest visible point within 3 m.
            while len(path) > 1 and dist(here, path[0]) < .35:
                path.pop(0)
            target = path[0]
            for p in path[1:16]:
                if dist(here, p) > 3.0 or not line_free(clear, here, p, radius * .9):
                    break
                target = p
    dx, dy = target[0] - here[0], target[1] - here[1]
    n = math.hypot(dx, dy) or 1e-6
    vref = robot.get("speed_reference_mps") or 3.0
    speed = min(1.0, math.sqrt(2 * 1.6 * remaining) / vref) * fast
    v = math.hypot(robot["vx"], robot["vy"])
    if v > .3:
        turn = (dx * robot["vx"] + dy * robot["vy"]) / (n * v)
        speed *= max(.45, (1 + turn) / 2)
    m["moving"] = speed > .25
    m["dir"] = math.atan2(dy, dx)
    return (dx / n * speed, dy / n * speed), False


def hold():
    return (0.0, 0.0)


# ---------------------------------------------------------------- shooting
def lead(shooter, target):
    if "vx" not in target:
        return target
    speed = sdk.muzzle_speed(shooter)
    t = dist(pos(shooter), pos(target)) / speed + .1
    p = dict(target)
    p["x"] += target.get("vx", 0) * t
    p["y"] += target.get("vy", 0) * t
    return p


_SOLUTIONS = {}


def solution(robot, target):
    key = (robot["id"], tuple(robot.get(k, 0) for k in ("x","y","z","vx","vy","vz")),
           sdk.muzzle_speed(robot), tuple(robot.get("quaternion", ())),
           tuple(target.get(k) for k in ("id","x","y","z","vx","vy","vz","kind","armor_open")))
    if key not in _SOLUTIONS:
        point = lead(robot, target)
        _SOLUTIONS[key] = aim_at(robot, point), aim_pitch(robot, point), ballistic_reachable(robot, point)
    return _SOLUTIONS[key]


def heat_ok(robot):
    if not can_fire(robot):
        return False
    if robot["role"] == "hero":
        return True
    return robot["heat"] + 20 <= robot["max_heat"]


def aligned(robot, yaw, distance_):
    tol = max(.012, min(.06, math.atan2(.07, max(distance_, .5))))
    return abs(wrap(yaw - robot["aim"])) < tol


def structure_targets(ctx, robot):
    out = []
    if ctx.outpost["hp"] > 0:
        out.append(dict(ctx.outpost, kind="outpost"))
    elif ctx.base["hp"] > 0 and (robot["role"] == "hero" or ctx.base["armor_open"]):
        out.append(dict(ctx.base, kind="base"))
    return out


def choose_target(ctx, robot, max_range=9.0, prefer_structures=False):
    """Best visible enemy (or structure) for this shooter with a firing solution."""
    best = None
    here = pos(robot)
    for e in ctx.targets:
        d = dist(here, pos(e))
        if d > max_range:
            continue
        score = d + e["hp"] / 60.0
        if e["role"] == "hero":
            score -= 4
        if e["role"] == "engineer":
            score += 2
        if best is None or score < best[0]:
            best = (score, e, d)
    structures = structure_targets(ctx, robot)
    if structures and (best is None or prefer_structures):
        s = structures[0]
        d = dist(here, pos(s))
        if d < (16 if robot["role"] in ("hero", "aerial") else 10):
            return s, d
    return (best[1], best[2]) if best else (None, None)


_WALL_BOXES = [(o["x"]+o["w"]/2, o["y"]+o["h"]/2, o["w"]/2, o["h"]/2,
                math.cos(o.get("rotation", 0)), math.sin(o.get("rotation", 0)),
                o.get("bottom", 0), o["height"]) for o in ARENA["obstacles"]]


def barrel(robot):
    yaw = robot["aim"] - robot["heading"]
    pitch = robot["pitch"]
    v = sdk._rotate(robot["quaternion"], (math.cos(yaw)*math.cos(pitch), math.sin(yaw)*math.cos(pitch), math.sin(pitch)))
    return math.atan2(v[1], v[0]), math.atan2(v[2], math.hypot(v[0], v[1]))


def clear_shot(ctx, robot, target, yaw, pitch, distance_):
    key = (robot["id"], pos(robot), robot["z"], target.get("id"), pos(target), target.get("z"), yaw, pitch, distance_)
    cache = getattr(ctx, "shot_cache", None)
    if cache is None:
        cache = ctx.shot_cache = {}
    if key not in cache:
        cache[key] = _clear_shot(ctx, robot, target, yaw, pitch, distance_)
    return cache[key]


def _clear_shot(ctx, robot, target, yaw, pitch, distance_):
    """Reject arcs blocked by public terrain, walls, or a teammate's chassis."""
    speed = sdk.muzzle_speed(robot)
    direction = (math.cos(yaw)*math.cos(pitch), math.sin(yaw)*math.cos(pitch), math.sin(pitch))
    pivot = sdk._rotate(robot["quaternion"], (0, 0, robot["muzzle_height_m"]))
    reach = robot["muzzle_reach_m"]
    x, y, z = [robot[k]+pivot[i]+direction[i]*reach for i,k in enumerate(("x","y","z"))]
    vx, vy, vz = [direction[i]*speed+robot[k] for i,k in enumerate(("vx","vy","vz"))]
    drag = .009177 if robot["role"] == "hero" else .019941
    step = .025
    until = max(0, distance_ - target.get("radius", .25) - .2)
    origin = (robot["x"], robot["y"])
    for _ in range(180):
        if dist((x,y), origin) >= until:
            return True
        velocity = math.sqrt(vx*vx+vy*vy+vz*vz)
        ax,ay,az = -drag*velocity*vx,-drag*velocity*vy,-9.81-drag*velocity*vz
        old_x,old_y,old_z=x,y,z
        x+=vx*step+.5*ax*step*step; y+=vy*step+.5*ay*step*step; z+=vz*step+.5*az*step*step
        vx+=ax*step; vy+=ay*step; vz+=az*step
        i,j=cell(x,y)
        if z <= HEIGHT[i*NY+j]+.02:
            return False
        for cx,cy,hw,hh,c,ss,bottom,height in _WALL_BOXES:
            if min(z,old_z)>bottom+height+.02 or max(z,old_z)<bottom-.02:
                continue
            start_x=(old_x-cx)*c+(old_y-cy)*ss
            start_y=-(old_x-cx)*ss+(old_y-cy)*c
            delta_x=(x-old_x)*c+(y-old_y)*ss
            delta_y=-(x-old_x)*ss+(y-old_y)*c
            low,high=0.0,1.0
            for position,delta,lower,upper in ((start_x,delta_x,-hw-.015,hw+.015),
                                              (start_y,delta_y,-hh-.015,hh+.015),
                                              (old_z,z-old_z,bottom-.02,bottom+height+.02)):
                if abs(delta)<1e-9:
                    if position<lower or position>upper:
                        low=2.0
                        break
                else:
                    entry,exit=sorted(((lower-position)/delta,(upper-position)/delta))
                    low,high=max(low,entry),min(high,exit)
                    if low>high:
                        break
            if low<=high:
                return False
        for friend in ctx.robots.values():
            if friend["id"] != robot["id"] and friend["role"] != "aerial" and friend["z"] < z < friend["z"]+.55 and (x-friend["x"])**2+(y-friend["y"])**2 < .25**2:
                return False
    return False


def shoot(ctx, robot, target, d, fire_ok=True):
    """aim/pitch/fire for a target; fire only when settled on it."""
    if target is None:
        return {}
    yaw, pitch, reach = solution(robot, target)
    actual_yaw, actual_pitch = barrel(robot)
    yaw_tolerance = max(.012, min(.05, .07/max(d,.5)))
    pitch_tolerance = max(.006, min(.04, .05/max(d,.5)))
    fire = (fire_ok and reach and heat_ok(robot) and abs(wrap(actual_yaw-yaw))<yaw_tolerance
            and abs(actual_pitch-pitch)<pitch_tolerance and clear_shot(ctx, robot, target, yaw, pitch, d))
    return {"aim": yaw, "pitch": pitch, "fire": fire}


# ---------------------------------------------------------------- economy
def buy(ctx, robot, rounds, remote=False):
    kind = 42 if robot["role"] == "hero" else 17
    cap = 100 if kind == 42 else 1000
    bought = ctx.econ["purchased_42" if kind == 42 else "purchased_17"]
    batch = (10 if remote else 1) if kind == 42 else (100 if remote else 10)
    unit = 150 if remote else 10
    rounds = min(rounds, cap - bought - ctx.state.get("_bought%d" % kind, 0))
    rounds -= rounds % batch
    afford = int(ctx.coins // unit) * batch
    rounds = min(rounds, afford)
    if rounds <= 0:
        return None
    cost = rounds // batch * unit
    ctx.coins -= cost
    ctx.state["_bought%d" % kind] = ctx.state.get("_bought%d" % kind, 0) + rounds
    return {"amount": rounds, "remote": remote}


def at_local_shop(ctx, robot):
    if robot.get("weak"):
        return False
    for zid in (ctx.team + "_base", ctx.team + "_supply"):
        if ctx.in_zone(robot, zid):
            return True
    return ctx.my_outpost["hp"] > 0 and ctx.in_zone(robot, ctx.team + "_outpost")


def disengaged(ctx, robot):
    return ctx.t - robot["last_shot_time"] >= 6.05 and ctx.t - robot["last_damage_time"] >= 6.05


def revive_or_wait(ctx, robot, priority):
    """Dead robots revive with coins when it is worth it."""
    cost = instant_revive_cost(robot, ctx.t)
    wait = robot["respawn_required"] - robot["respawn_progress"]
    reserve = {0: 0, 1: 120, 2: 250}[priority]
    if wait > 6 and ctx.t < 410 and ctx.coins - cost >= reserve:
        ctx.coins -= cost
        return action(revive=True)
    return action()


# ---------------------------------------------------------------- roles
HERO_SPOT = (10.4, 3.6)
HERO_ROUTE = ((4.0, 6.0), (7.0, 4.6))


def hero(ctx, r):
    m = ctx.mem(1)
    if ctx.tick == 0:
        return action(profile="ranged")
    if not r["alive"]:
        m.pop("wp", None)
        return revive_or_wait(ctx, r, 0)
    ops = {}
    spot = ctx.p(*HERO_SPOT)
    if r["weak"]:
        m["recover"] = True
    if m.get("recover"):
        if r["hp"] >= r["max_hp"] * .85:
            m.pop("recover", None)
            m.pop("wp", None)
        else:
            mv, _ = go(ctx, r, ctx.p(1.7, 12.1), slack=.3)
            return action(move=mv, deploy=False)
    if r["hp"] < r["max_hp"] * .6 and r["pending_heal"] is None and ctx.coins >= remote_heal_cost(ctx.t) + 50:
        if disengaged(ctx, r):
            ctx.coins -= remote_heal_cost(ctx.t)
            ops["remote_heal"] = True
        elif ctx.t - r["last_damage_time"] > 2:
            return action(deploy=r["deployed"], fire=False)
    if r["ammo"] == 0 and not r["deployed"] and at_local_shop(ctx, r) and ctx.t >= 1:
        order = buy(ctx, r, 20)
        if order:
            return action(buy_ammo=order)
    if r["ammo"] <= 3 and r["deployed"] and not r["pending_ammo"] and ctx.coins >= 150 and ctx.econ["purchased_42"] < 100:
        if not disengaged(ctx, r):
            return action(deploy=True, fire=False)
        order = buy(ctx, r, 30 if ctx.coins > 750 else 20 if ctx.coins > 450 else 10, remote=True)
        if order:
            ops["buy_ammo"] = order
    if r["ammo"] == 0 and not r["deployed"] and r["deploy_at"] is None:
        # Fetch ammo: home first if poor, otherwise straight to the spot and buy remotely there.
        if ctx.coins < 150 or ctx.t < 1:
            mv, _ = go(ctx, r, ctx.p(3.6, 6.2))
            return action(move=mv, deploy=False)
    if not r["deployed"] and r["deploy_at"] is None:
        k = m.get("wp", 0)
        route = [ctx.p(*p) for p in HERO_ROUTE] + [spot]
        while k < len(route) - 1 and dist(pos(r), route[k]) < .6:
            k += 1
        m["wp"] = k
        mv, arrived = go(ctx, r, route[k], slack=.2 if k == len(route) - 1 else .5)
        if not arrived or k < len(route) - 1:
            target, d = choose_target(ctx, r, 14)
            return action(move=mv, deploy=False, **shoot(ctx, r, target, d, fire_ok=False), **ops)
    targets = structure_targets(ctx, r)
    threat = [e for e in ctx.targets if dist(pos(r), pos(e)) < 7 and e["role"] != "engineer"]
    target = None
    if targets and ballistic_reachable(r, targets[0]):
        target = targets[0]
    if threat and (target is None or ctx.outpost["hp"] > 0):
        target = min(threat, key=lambda e: dist(pos(r), pos(e)))
    d = dist(pos(r), pos(target)) if target else 0
    return action(deploy=True, **shoot(ctx, r, target, d), **ops)


def engineer(ctx, r):
    m = ctx.mem(2)
    if not r["alive"]:
        return revive_or_wait(ctx, r, 1)
    team = ctx.team
    core = ctx.obs["assemblies"][team]
    done = ctx.econ["completed_difficulties"]
    busy = core["stage"] in ("moving", "inserting", "buffered")
    resource = ctx.zones[team + "_resource"]
    assembly = ctx.zones[team + "_assembly"]
    outpost_zone = ctx.zones[team + "_outpost"]
    # A tipped teammate cannot drive and respawning does not right it: grip and right it.
    tipped = [t for t in sdk.tipped_teammates(ctx.obs) if t["role"] != "aerial" and dist(pos(r), pos(t)) < 8]
    if not busy and tipped and not r.get("weak"):
        target = min(tipped, key=lambda t: dist(pos(r), pos(t)))
        if dist(pos(r), pos(target)) > .8:
            mv, _ = go(ctx, r, sdk.rescue_point(r, target), slack=.1)
            return action(move=mv, rescue=target["slot"])
        return action(rescue=target["slot"])
    # Rebuild a fallen outpost: base invulnerability is worth more than income.
    if (not busy and ctx.my_outpost["hp"] <= 0 and ctx.econ["rebuild_credits"] > 0 and ctx.t < 299
            and not r.get("weak")):
        mv, arrived = go(ctx, r, (outpost_zone["x"], outpost_zone["y"]), slack=.3)
        return action(move=mv)
    ready4 = 4 not in done and 3 in done and ctx.t >= 178 and not core["permanent_lock"] and ctx.t >= core["retry_at"]
    need = 2 if (ready4 and not busy) or (busy and core["difficulty"] == 4 and core["inserted_units"] == 0) else 1
    in_resource = dist(pos(r), (resource["x"], resource["y"])) <= resource["radius"] - .05
    if not busy and (r["carried_units"] < need or (in_resource and r["carried_units"] < 2)):
        mv, _ = go(ctx, r, (resource["x"], resource["y"] - (.15 if team == "red" else -.15)), slack=.15)
        return action(move=mv, pick_unit=True)
    level = 1
    for d in (1, 2, 3):
        if ctx.t >= (d - 1) * 60 - .5 and (d == 1 or d - 1 in done):
            level = d
    if ready4 and r["carried_units"] >= 2:
        level = 4
    # Wait for the next unlock instead of spending the unit on a repeat when it is close.
    nxt = level + 1
    if level < 3 and nxt not in done and (nxt - 1) * 60 - ctx.t < 12 and level in done:
        level = nxt
    mv, arrived = go(ctx, r, (assembly["x"], assembly["y"]), slack=.25)
    ops = dict(assembly_insert=True, assembly_translate=True, assembly_rotate=core["target_rotation"], assembly_confirm=True)
    if not busy:
        if ctx.t >= (level - 1) * 60:
            ops["assembly"] = level
    return action(move=mv, **ops)


AIR_SPOT = (15.0, 2.4)
AIR_PATROL = (13.6, 3.2)


def aerial(ctx, r):
    m = ctx.mem(6)
    useful = ctx.outpost["hp"] > 0 or bool(ctx.targets) or ctx.base["armor_open"]
    free = r["support_time"] > 0
    keep = (free or (ctx.coins > 30 and useful)) and r["ammo"] > 0
    if not keep and not r["support_active"]:
        return action(support=False)
    if not keep:
        return action(support=False)
    spot = ctx.p(*(AIR_SPOT if ctx.outpost["hp"] > 0 else AIR_PATROL))
    dx, dy = spot[0] - r["x"], spot[1] - r["y"]
    mv = (max(-1, min(1, dx * .6 - r["vx"] * .4)), max(-1, min(1, dy * .6 - r["vy"] * .4)))
    target, d = choose_target(ctx, r, 13, prefer_structures=ctx.outpost["hp"] > 0)
    if ctx.outpost["hp"] <= 0:
        heroes = [e for e in ctx.targets if e["role"] == "hero" and dist(pos(r), pos(e)) < 17]
        if heroes:
            target = min(heroes, key=lambda e: dist(pos(r), pos(e)))
            d = dist(pos(r), pos(target))
        elif ctx.base["armor_open"]:
            target, d = dict(ctx.base, kind="base"), dist(pos(r), pos(ctx.base))
    return action(move=mv, support=True, altitude=2.0, **shoot(ctx, r, target, d))


def infantry(ctx, r):
    slot = r["slot"]
    m = ctx.mem(slot)
    if ctx.tick == 0:
        return action(profile={"chassis": "power", "weapon": "cooling"})
    if not r["alive"]:
        return revive_or_wait(ctx, r, 2)
    ops = {}
    here = pos(r)
    # Ammo: buy locally when possible, remotely when far away and rich.
    if r["ammo"] < 40 and at_local_shop(ctx, r) and ctx.t >= 1:
        order = buy(ctx, r, 100 if ctx.coins > 400 else 50)
        if order:
            ops["buy_ammo"] = order
    elif r["ammo"] < 15 and not r["pending_ammo"] and disengaged(ctx, r) and ctx.coins > 450:
        order = buy(ctx, r, 100, remote=True)
        if order:
            ops["buy_ammo"] = order
    if (r["hp"] < r["max_hp"] * .45 and disengaged(ctx, r) and r["pending_heal"] is None
            and ctx.coins > remote_heal_cost(ctx.t) + 200):
        ctx.coins -= remote_heal_cost(ctx.t)
        ops["remote_heal"] = True
    if r["weak"]:
        m["recover"] = True
    if m.get("recover"):
        if r["hp"] >= r["max_hp"] * .8:
            m.pop("recover", None)
        else:
            mv, _ = go(ctx, r, ctx.p(1.6, 11.8 + (slot-3)*.2))
            return action(move=mv, **ops)
    if r["ammo"] == 0 and not ops.get("buy_ammo"):
        mv, _ = go(ctx, r, ctx.p(3.6, 7.5 + (slot - 4) * .5))
        target, d = choose_target(ctx, r)
        return action(move=mv, **shoot(ctx, r, target, d, fire_ok=False), **ops)
    target, d = choose_target(ctx, r)
    # Default posts: guard our hero's flank, watch the centre, hunt their hero.
    hero_spot = ctx.p(*HERO_SPOT)
    posts = {3: ctx.p(15.6, 5.5), 4: ctx.p(HERO_SPOT[0], HERO_SPOT[1]+1.4), 7: ctx.p(15.5, 9.5)}
    goal = posts[slot]
    hunt = [e for e in ctx.targets if e["role"] == "hero"]
    if hunt and slot in (3, 7):
        e = hunt[0]
        goal = (e["x"] + (2.5 if ctx.team == "blue" else -2.5) * 0, e["y"])
        goal = step_toward(pos(e), here, 3.5)
    elif ctx.base["armor_open"] and ctx.outpost["hp"] <= 0 and slot != 4:
        goal = ctx.p(21.7, 6.3 if slot == 3 else 8.7)
    elif slot == 7 and ctx.outpost["hp"] <= 0 and ctx.t >= 180:
        goal = ctx.p(21.4, 7.5)
    elif slot != 4 and target is not None and target.get("kind") is None and d > 5.5:
        goal = step_toward(pos(target), here, 5.0)
    mv, _ = go(ctx, r, goal, slack=.4)
    return action(move=mv, **shoot(ctx, r, target, d), **ops)


def step_toward(target, here, keep):
    d = dist(target, here)
    if d <= keep:
        return here
    t = (d - keep) / d
    return (here[0] + (target[0] - here[0]) * t, here[1] + (target[1] - here[1]) * t)


ROLES = {"hero": hero, "engineer": engineer, "aerial": aerial, "infantry": infantry}


def act(obs, state):
    state = state if isinstance(state, dict) else {}
    if obs["tick"] == 0:
        MEM.clear()
    _SOLUTIONS.clear()
    state["_plans"] = 0
    ctx = Ctx(obs, state)
    actions = {}
    for robot in sorted(obs["robots"], key=lambda r: r["slot"]):
        slot = str(robot["slot"])
        if slot not in obs["controlled_ids"]:
            continue
        try:
            actions[slot] = ROLES[robot["role"]](ctx, robot)
        except Exception as error:  # never let one robot's bug disable the team
            print("error", slot, repr(error))
            actions[slot] = action()
    for k in [k for k in state if k.startswith("_")]:
        state.pop(k)
    return actions, state
