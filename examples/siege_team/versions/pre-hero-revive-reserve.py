"""Siege team strategy.

Plan: the aerial robot takes down the enemy outpost from its lane in the first
half minute; the hero deploys on flat ground in our half and shells the enemy
base with 42mm; infantry hunt the enemy hero and escort ours; the engineer
races the tech tree and rebuilds our outpost. The invulnerable aerial robot also
serves the energy rune: it hovers 4 m from our rune face and shoots every lamp
(17mm spread grows with range), while any live infantry only presses rune_start.
The shaft motor is a smooth aperiodic function of match time with four seeded
constants; the published angular velocity and acceleration let the strategy fit
them online and place every bullet with exact gimbal and flight timing, which
earns the large-rune buff (attack x2-3, cooling x3-5) three times per match.
The hero is revived to be ready for each window.
Navigation uses a slope- and clearance-aware grid built at import time, so decisions stay cheap.
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


def astar(clear, start, goal, radius, budget=2400):
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
        changed = dist(m.get("pgoal", (-9, -9)), goal) > .3 or m.get("pslope") != slope
        retry = ctx.t - m.get("ptime", -9) > (4 if path else 1.5)
        if changed or retry:
            if ctx.state.get("_plans", 0) >= 2:
                if not path:return (0.0,0.0),False
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

def lead(shooter,target):
    if 'vx' not in target:return target
    speed=sdk.muzzle_speed(shooter)
    flight=max(.01,dist(pos(shooter),pos(target))/speed)
    point=dict(target)
    for _ in range(2):
        point['x']=target['x']+target.get('vx',0)*flight
        point['y']=target['y']+target.get('vy',0)*flight
        point['z']=target.get('z',0)+target.get('vz',0)*flight
        w=target.get('angular_velocity',(0,0,0));rate=math.sqrt(sum(v*v for v in w))
        if rate>.01:
            a=rate*flight*.5;s=math.sin(a)/rate;ax,ay,az=w[0]*s,w[1]*s,w[2]*s;aw=math.cos(a)
            x,y,z,v=target.get('quaternion',(0,0,0,1))
            point['quaternion']=[aw*x+ax*v+ay*z-az*y,aw*y-ax*z+ay*v+az*x,aw*z+ax*y-ay*x+az*v,aw*v-ax*x-ay*y-az*z]
        pitch=aim_pitch(shooter,point)
        d=max(.01,dist(pos(shooter),pos(point))-shooter.get('muzzle_reach_m',.3)*math.cos(pitch))
        inherited=(shooter.get('vx',0)*(point['x']-shooter['x'])+shooter.get('vy',0)*(point['y']-shooter['y']))/max(d,.01)
        # Drag-adjusted horizontal flight time; independent of decision frequency.
        drag=.009177 if shooter['role']=='hero' else .01994
        flight=(math.exp(drag*d)-1)/(drag*max(1,speed*math.cos(pitch)+inherited))
    return point


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
    fire = (fire_ok and not target.get('invulnerable') and reach and heat_ok(robot) and abs(wrap(actual_yaw-yaw))<yaw_tolerance
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
    timely = wait > 6 or (robot['role']=='hero' and not robot.get('tipped') and ctx.coins>=cost+100)
    window = any(c - 4 <= ctx.t < c + 55 for c in (180, 255, 330))
    if robot["role"] == "hero" and window and ctx.coins >= cost and ctx.t < 410:
        ctx.coins -= cost
        return action(revive=True)
    if timely and ctx.t < 410 and ctx.coins - cost >= reserve:
        ctx.coins -= cost
        return action(revive=True)
    return action()


# ---------------------------------------------------------------- roles
HERO_SPOT = (10.4, 3.6)
HERO_ROUTE = ((4.0, 6.0), (7.0, 4.6))


def buffed(ctx):
    """Our own rune buff is running with a real attack or cooling bonus: spend every second shooting."""
    rune = ctx.obs["runes"][ctx.team]
    return rune["status"] == "active" and (rune["attack"] >= 1.5 or rune["cooling"] >= 2)


def hero(ctx, r):
    m = ctx.mem(1)
    if ctx.tick == 0:
        return action(profile="ranged")
    if not r["alive"]:
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
        elif ctx.t - r["last_damage_time"] > 2 and not buffed(ctx):
            return action(deploy=r["deployed"], fire=False)
    if r["ammo"] == 0 and not r["deployed"] and at_local_shop(ctx, r) and ctx.t >= 1:
        order = buy(ctx, r, 20)
        if order:
            return action(buy_ammo=order)
    if (140 <= ctx.t <= 178 and r["ammo"] < 12 and r["deployed"] and not r["pending_ammo"] and ctx.coins >= 200
            and ctx.econ["purchased_42"] < 100 and disengaged(ctx, r)):
        order = buy(ctx, r, 10, remote=True)
        if order:
            ops["buy_ammo"] = order
    elif r["ammo"] <= 3 and r["deployed"] and not r["pending_ammo"] and ctx.coins >= 150 and ctx.econ["purchased_42"] < 100:
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
        if dist(pos(r),spot)<2.4:k=len(route)-1
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
    tipped = [t for t in sdk.tipped_teammates(ctx.obs) if t["alive"] and t["role"] != "aerial" and dist(pos(r), pos(t)) < 5]
    # Do not abandon the first income unlock or spend the whole match on a wreck.
    if not busy and tipped and not r.get("weak") and 1 in done:
        target = min(tipped, key=lambda t: dist(pos(r), pos(t))-(2 if t["slot"]==1 else 0))
        if m.get("rescue_id") != target["slot"]:
            m["rescue_id"],m["rescue_start"]=target["slot"],ctx.t
        if ctx.t-m["rescue_start"] < 8:
            if dist(pos(r), pos(target)) > .75:
                mv, _ = go(ctx, r, sdk.rescue_point(r, target), slack=.08)
                return action(move=mv, rescue=target["slot"])
            return action(rescue=target["slot"])
    else:
        m.pop("rescue_id",None)
    # Rebuild a fallen outpost: base invulnerability is worth more than income.
    # Tech first: level 3 (25% defence, income) and level 4 (shield, 50%) outweigh a 750 HP outpost that the enemy aerial
    # shoots down again; the engineer rebuilds only once level 3 stands, and not while level 4 is due.
    rebuild_ok = (3 in done and ctx.t < 168) or 4 in done or (3 in done and ctx.t >= 235)
    if (not busy and ctx.my_outpost["hp"] <= 0 and ctx.econ["rebuild_credits"] > 0 and ctx.t < 299
            and not r.get("weak") and rebuild_ok):
        # stand on the floor side of the platform edge: the zone centre sits on a 0.2 m step that tips the chassis
        mv, arrived = go(ctx, r, (outpost_zone["x"], outpost_zone["y"] + (-.7 if team == "red" else .7)), slack=.2)
        return action(move=mv)
    # Difficulty 4 unlocks at 180 s and only one team can run it at a time: be loaded and waiting in the assembly zone.
    start4 = max(180.0, core["retry_at"])
    can4 = 4 not in done and 3 in done and not core["permanent_lock"]
    ready4 = can4 and ctx.t >= start4 - .05
    prep4 = can4 and ctx.t >= start4 - 24
    enemy_core = ctx.obs["assemblies"].get(ctx.enemy) or {}
    enemy_busy = enemy_core.get("stage") in ("moving", "inserting", "buffered")
    need = 2 if (prep4 and not busy) or (busy and core["difficulty"] == 4 and core["inserted_units"] == 0) else 1
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
        if prep4 and not ready4:
            pass                                   # hold both units until difficulty 4 unlocks
        elif level == 4:
            # starting while the other team is mid-assembly interrupts it but delays us 15 s: let them finish first
            if not (enemy_busy and enemy_core.get("difficulty") != 4 and ctx.t < start4 + 4):
                ops["assembly"] = 4
        elif ctx.t >= (level - 1) * 60:
            ops["assembly"] = level
    return action(move=mv, **ops)


AIR_SPOT = (15.0, 2.4)
AIR_PATROL = (13.6, 3.2)


def aerial(ctx, r):
    m = ctx.mem(6)
    rune = ctx.obs["runes"][ctx.team]
    serving = rune_open(ctx) is not None or rune_soon(ctx)
    useful = ctx.outpost["hp"] > 0 or bool(ctx.targets) or ctx.base["armor_open"] or serving
    free = r["support_time"] > 0
    keep = (free or (ctx.coins > 30 and useful)) and r["ammo"] > 0
    if not keep and not r["support_active"]:
        return action(support=False)
    if not keep:
        return action(support=False)
    if serving:
        hover = ctx.p(*RUNE_HOVER)
        mv = (max(-1, min(1, (hover[0] - r["x"]) * .3 - r["vx"] * .4)), max(-1, min(1, (hover[1] - r["y"]) * .3 - r["vy"] * .4)))
        shot = rune_shot(ctx, r, rune, m) if rune["status"] == "activating" else {}
        return action(move=mv, support=True, altitude=2.08, **shot)
    m.pop("plan", None)
    spot = ctx.p(*(AIR_SPOT if ctx.outpost["hp"] > 0 else RUNE_HOVER))
    dx, dy = spot[0] - r["x"], spot[1] - r["y"]
    mv = (max(-1, min(1, dx * .6 - r["vx"] * .4)), max(-1, min(1, dy * .6 - r["vy"] * .4)))
    target, d = choose_target(ctx, r, 13, prefer_structures=ctx.outpost["hp"] > 0)
    if ctx.outpost["hp"] <= 0:
        heroes = [e for e in ctx.targets if e["role"] == "hero" and dist(pos(r), pos(e)) < 17]
        if ctx.base["armor_open"] and ctx.base["hp"] > 0 and dist(pos(r), pos(ctx.base)) < 17:
            # an open armour is the only way the 17mm fire ends the match: finish the base before hunting heroes
            target, d = dict(ctx.base, kind="base"), dist(pos(r), pos(ctx.base))
        elif heroes:
            target = min(heroes, key=lambda e: dist(pos(r), pos(e)))
            d = dist(pos(r), pos(target))
    # The aerial cannot be resupplied: keep the rounds that the activations still to come need.
    hold = r["ammo"] <= rune_reserve(ctx)
    return action(move=mv, support=True, altitude=2.0, **shoot(ctx, r, target, d, fire_ok=not hold))



# ---------------------------------------------------------------- energy rune (aerial shooter, fitted shaft motor)
# The aerial robot cannot be damaged, so it hovers 4 m from our rune face and shoots every lamp (17mm spread grows with
# range, so a close, safe shooter gives the best rings). Any live infantry only presses rune_start. The shaft motor is
# a smooth aperiodic function of match time with four seeded constants (w, p0, p1 and, from 180 s, a); the observation
# publishes its exact angular velocity and acceleration, so the constants are fitted online and every lamp position is
# predicted tick by tick. The gimbal slews at a fixed rate per physics substep and the first shot of a command leaves
# one substep later, so the shot is pre-parked one decision ahead and only its first bullet can reach the lamp.
RUNE_HOVER = (12.4, 3.9)
RUNE_CHANCES = ((0, "small"), (90, "small"), (180, "large"), (255, "large"), (330, "large"))
R_DT, R_SUB = 0.05, 1 / 120
R_TIME_BIAS, R_YAW_BIAS, R_PITCH_BIAS = .045, 0.0, 0.0
R_AWAY, R_TOL = .45, .004
M_K, M_RHO, M_A_SMALL, M_BLEND_S, M_SMALL_MEAN, M_LARGE_AT = .28, .6180339887498948, .32, 3.0, math.pi / 3, 180.0


class RuneMotor:
    """speed(t) = mean(t) + amp(t) * ((1-K) sin(w t + p0) + K sin(RHO w t + p1)); small phase: mean pi/3, amp .32;
    from 180 s (mean, amp) blend with a smoothstep into (2.09 - a, a)."""

    def __init__(self):
        self.samples, self.last_kept, self.dirn = [], -9.0, None
        self.params, self.a, self.angle, self.fit_at, self.resid = None, None, None, -9.0, None

    def configure(self, sim):
        global M_K, M_RHO, M_A_SMALL, M_BLEND_S
        motor = (sim or {}).get("rune_motor") or {}
        M_K = motor.get("secondary_weight", M_K)
        M_RHO = motor.get("secondary_frequency_ratio", M_RHO)
        M_A_SMALL = motor.get("small_amplitude_rad_s", M_A_SMALL)
        M_BLEND_S = motor.get("mode_transition_s", M_BLEND_S)

    @staticmethod
    def blend(t):
        u = min(1.0, max(0.0, (t - M_LARGE_AT) / M_BLEND_S))
        return u * u * (3 - 2 * u), 6 * u * (1 - u) / M_BLEND_S

    def speed(self, t, w, p0, p1, a):
        b, _ = self.blend(t)
        wave = (1 - M_K) * math.sin(w * t + p0) + M_K * math.sin(M_RHO * w * t + p1)
        return M_SMALL_MEAN + (2.09 - a - M_SMALL_MEAN) * b + (M_A_SMALL + (a - M_A_SMALL) * b) * wave

    def observe(self, tick, t, angle, vel, acc):
        if angle is None or vel is None or acc is None:
            return
        self.angle = (tick, angle)
        if self.dirn is None and abs(vel) > 1e-6:
            self.dirn = 1 if vel > 0 else -1
        if self.dirn is None:
            return
        s, c = self.dirn * vel, self.dirn * acc
        if t < M_LARGE_AT - .2 and t - self.last_kept >= .35:
            self.samples.append((t, s, c))
            self.last_kept = t
            if len(self.samples) > 400:
                del self.samples[1::2]
        if t >= M_LARGE_AT + .05 and self.params is not None:
            w, p0, p1 = self.params
            b, _ = self.blend(t)
            wave = (1 - M_K) * math.sin(w * t + p0) + M_K * math.sin(M_RHO * w * t + p1)
            base = M_SMALL_MEAN + b * (2.09 - M_SMALL_MEAN) + M_A_SMALL * (1 - b) * wave
            den = b * (wave - 1)
            if abs(den) > .003:
                a = (s - base) / den
                if .7 < a < 1.1:
                    self.a = a if self.a is None else .8 * self.a + .2 * a

    def _lstsq(self, w, rows):
        mm = [[0.0] * 4 for _ in range(4)]
        yy = [0.0] * 4
        res0 = 0.0
        for t, s, c in rows:
            y1, y2 = (s - M_SMALL_MEAN) / M_A_SMALL, c / M_A_SMALL
            b1 = ((1 - M_K) * math.sin(w * t), (1 - M_K) * math.cos(w * t),
                  M_K * math.sin(M_RHO * w * t), M_K * math.cos(M_RHO * w * t))
            b2 = ((1 - M_K) * w * math.cos(w * t), -(1 - M_K) * w * math.sin(w * t),
                  M_K * M_RHO * w * math.cos(M_RHO * w * t), -M_K * M_RHO * w * math.sin(M_RHO * w * t))
            for b, y in ((b1, y1), (b2, y2)):
                for i in range(4):
                    yy[i] += b[i] * y
                    for j in range(4):
                        mm[i][j] += b[i] * b[j]
                res0 += y * y
        a = [row[:] + [yy[i]] for i, row in enumerate(mm)]
        for c in range(4):
            p = max(range(c, 4), key=lambda q: abs(a[q][c]))
            if abs(a[p][c]) < 1e-12:
                return None, 1e9
            a[c], a[p] = a[p], a[c]
            for q in range(c + 1, 4):
                f = a[q][c] / a[c][c]
                for k in range(c, 5):
                    a[q][k] -= f * a[c][k]
        x = [0.0] * 4
        for q in range(3, -1, -1):
            x[q] = (a[q][4] - sum(a[q][k] * x[k] for k in range(q + 1, 4))) / a[q][q]
        return x, max(res0 - sum(x[i] * yy[i] for i in range(4)), 0.0)

    def fit(self):
        n = len(self.samples)
        if n < 6 or self.samples[-1][0] - self.samples[0][0] < 1.5:
            return False
        rows = self.samples[::max(1, n // 24)]
        best = None
        for i in range(30):
            w = 1.884 + i * .004
            x, r = self._lstsq(w, rows)
            if x is not None and (best is None or r < best[0]):
                best = (r, w)
        lo, hi = best[1] - .004, best[1] + .004
        for _ in range(26):
            m1, m2 = lo + (hi - lo) * .382, lo + (hi - lo) * .618
            if self._lstsq(m1, rows)[1] < self._lstsq(m2, rows)[1]:
                hi = m2
            else:
                lo = m1
        w = (lo + hi) / 2
        x, r = self._lstsq(w, rows)
        if x is None:
            return False
        self.params = (w, math.atan2(x[1], x[0]), math.atan2(x[3], x[2]))
        self.resid, self.fit_at = r, self.samples[-1][0]
        return True

    def ok(self, t):
        """The fitted law explains the published speeds (any other motor makes the plan useless: stay passive)."""
        return (self.params is not None and self.angle is not None and self.resid is not None and self.resid < 1e-6
                and (t < M_LARGE_AT or self.a is not None))

    def angle_at(self, tick_target):
        tick0, angle = self.angle
        a = self.a if self.a is not None else .9
        total = 0.0
        for k in range(tick0, tick_target):
            s = k * R_DT
            total += R_DT * (self.speed(s, *self.params, a) + 4 * self.speed(s + R_DT / 2, *self.params, a)
                             + self.speed(s + R_DT, *self.params, a)) / 6
        return angle + self.dirn * total


RUNE_MOTOR = RuneMotor()


def rune_update(ctx):
    """Feed this decision's rune observation to the motor model."""
    rune = ctx.obs["runes"][ctx.team]
    RUNE_MOTOR.configure(ctx.obs.get("simulation_assumptions"))
    RUNE_MOTOR.observe(ctx.tick, ctx.t, rune.get("angle"), rune.get("angular_velocity"), rune.get("angular_acceleration"))
    if RUNE_MOTOR.params is None:
        if len(RUNE_MOTOR.samples) >= 6:
            RUNE_MOTOR.fit()
    elif ctx.t < M_LARGE_AT - 10 and ctx.t - RUNE_MOTOR.fit_at > 30:
        RUNE_MOTOR.fit()


def to_local(r, yaw, pitch):
    qx, qy, qz, qw = r["quaternion"]
    v = sdk._rotate((-qx, -qy, -qz, qw), (math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), math.sin(pitch)))
    return math.atan2(v[1], v[0]), math.atan2(v[2], math.hypot(v[0], v[1]))


def to_world(r, ly, lp):
    v = sdk._rotate(r["quaternion"], (math.cos(ly) * math.cos(lp), math.sin(ly) * math.cos(lp), math.sin(lp)))
    return math.atan2(v[1], v[0]), math.atan2(v[2], math.hypot(v[0], v[1]))


def lamp_point(ctx, angle, arm):
    g = ctx.obs["arena"]["rune"]
    nx, ny = math.cos(g["axis_yaw"]), math.sin(g["axis_yaw"])
    sgn = 1 if ctx.team == "red" else -1
    th = angle + arm * math.tau / 5
    cc = g["arm_radius_m"]
    return {"x": g["x"] - sgn * g["face_offset_m"] * nx - ny * cc * math.cos(th),
            "y": g["y"] - sgn * g["face_offset_m"] * ny + nx * cc * math.cos(th),
            "z": g["z"] + cc * math.sin(th), "kind": "rune_target"}


def rune_flight(r, point):
    pitch = aim_pitch(r, point)
    d = max(.01, dist(pos(r), pos(point)) - r["muzzle_reach_m"] * math.cos(pitch))
    return (math.exp(.01994 * d) - 1) / (.01994 * max(1.0, 25.0 * math.cos(pitch)))


def rune_shot(ctx, r, rune, m):
    """Pre-park the gimbal one decision ahead, then fire so only the first bullet of the pair can hit a lamp."""
    tick, t = ctx.tick, ctx.t
    lit = [x for x in rune["targets"] if x["lit"]]
    if not lit or not RUNE_MOTOR.ok(t):
        m.pop("plan", None)
        return {}
    now_angle = RUNE_MOTOR.angle_at(tick)
    cur_ly, cur_lp = wrap(r["aim"] - r["heading"]), r["pitch"]
    best = None
    for tg in lit:
        e = abs(wrap(aim_at(r, lamp_point(ctx, now_angle, tg["arm"])) - barrel(r)[0]))
        if best is None or e < best[0]:
            best = (e, tg)
    arm = best[1]["arm"]

    def solve(ticks_ahead):
        t_shot = t + ticks_ahead * R_DT + R_SUB
        p = lamp_point(ctx, now_angle, arm)
        fl = rune_flight(r, p)
        for _ in range(2):
            p = lamp_point(ctx, RUNE_MOTOR.angle_at(int(math.floor((t_shot + fl + R_TIME_BIAS) / R_DT + 1e-9))), arm)
            fl = rune_flight(r, p)
        return aim_at(r, p) + R_YAW_BIAS, aim_pitch(r, p) + R_PITCH_BIAS

    g = ctx.obs["arena"]["rune"]
    hub_yaw = math.atan2(g["y"] - r["y"], g["x"] - r["x"])
    step = sdk.DESIGNS[str(r["slot"])]["turret_yaw_rate_rad_s"] * R_SUB
    y_now, p_now = solve(0)
    ly_t, lp_t = to_local(r, y_now, p_now)
    away = 1 if wrap(y_now - hub_yaw) > 0 else -1
    plan = m.get("plan")
    ready = can_fire(r) and r["heat"] + 20 <= r["max_heat"] and t >= m.get("next", 0)
    if plan and plan["arm"] == arm and plan["tick"] == tick and plan["away"] == away and ready:
        if abs(wrap(cur_ly + away * step - ly_t)) < R_TOL and abs(cur_lp - lp_t) < .004:
            m["next"] = t + .35
            m.pop("plan", None)
            cy, cp = to_world(r, ly_t + away * R_AWAY, lp_t)
            return {"aim": cy, "pitch": cp, "fire": True}
    y_next, p_next = solve(2)
    nly, nlp = to_local(r, y_next, p_next)
    away2 = 1 if wrap(y_next - hub_yaw) > 0 else -1
    m["plan"] = {"arm": arm, "tick": tick + 2, "away": away2}
    py, pp = to_world(r, nly - away2 * step, nlp)
    return {"aim": py, "pitch": pp, "fire": False}


def rune_open(ctx):
    """Chance kind the aerial should serve right now ('small', 'large' or None)."""
    rune = ctx.obs["runes"][ctx.team]
    if rune["status"] == "activating":
        return rune["mode"]
    if rune["large_chances"] > 0 and RUNE_MOTOR.ok(ctx.t):
        return "large"
    if rune["small_chances"] > 0 and ctx.t < 172 and RUNE_MOTOR.ok(ctx.t) and (ctx.outpost["hp"] <= 0 or ctx.t >= 40):
        return "small"
    return None


def rune_soon(ctx):
    """A chance opens within 9 s: stop spending heat and be at the hover point."""
    return any(0 <= c - ctx.t <= 9 and RUNE_MOTOR.ok(ctx.t) for c, kind in RUNE_CHANCES if kind == "large" or c > 0)


def rune_reserve(ctx):
    """Rounds the aerial keeps for the activations still to come (it cannot be resupplied)."""
    rune = ctx.obs["runes"][ctx.team]
    large = rune["large_chances"] + sum(1 for c in (180, 255, 330) if c > ctx.t)
    small = rune["small_chances"] + (1 if ctx.t < 90 else 0) if ctx.t < 172 else 0
    return 26 * large + 14 * small


def rune_ready(ctx, air):
    """The aerial hovers on its mark with a loaded gun, so an activation can start."""
    return (air is not None and RUNE_MOTOR.ok(ctx.t) and air["support_active"] and air["ammo"] >= 26
            and dist(pos(air), ctx.p(*RUNE_HOVER)) < .12 and math.hypot(air["vx"], air["vy"]) < .08
            and air["heat"] + 40 <= air["max_heat"])


def rune_start_ok(ctx):
    rune = ctx.obs["runes"][ctx.team]
    return (ctx.t > 3 and rune["status"] == "idle" and rune_open(ctx) is not None and rune_ready(ctx, ctx.robots.get(6)))


HIGHLAND = ((9.15, 7.5), (10.8, 7.5))


def buff_goal(ctx, r, m, here):
    """Goal while running the highland cards, or None. States: 0 idle, 1 to card 0, 2 to card 1."""
    c0, c1 = ctx.p(*HIGHLAND[0]), ctx.p(*HIGHLAND[1])
    st = m.get("hl", 0)
    if st == 0:
        calm = not any(dist(here, pos(e)) < 10 for e in ctx.targets)
        opening = ctx.t < 20 and not m.get("hl_done")
        refresh = (ctx.t - m.get("hl_last", -99) > 34 and r.get("defense_buff", 0) < .45 and calm
                   and r["hp"] > r["max_hp"] * .5 and dist(here, c0) < 9 and ctx.t > 20)
        if opening or refresh:
            st = m["hl"] = 1
        else:
            return None
    if st == 1:
        if dist(here, c0) < .4:
            st = m["hl"] = 2
            m["hl_t0"] = ctx.t
        elif ctx.t - m.get("hl_try", ctx.t) > 12:
            m["hl"] = 0
            m["hl_done"] = True
            m["hl_last"] = ctx.t
            return None
        else:
            m.setdefault("hl_try", ctx.t)
            return c0
    if st == 2:
        if dist(here, c1) < .45 or ctx.t - m["hl_t0"] > 4.5:
            m["hl"] = 0
            m["hl_done"] = True
            m["hl_last"] = ctx.t
            m.pop("hl_try", None)
            return None
        return c1
    return None


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
        mv, _ = go(ctx, r, ctx.p(3.8, {3:6.65,4:7.5,7:8.35}[slot]))
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
    bg = buff_goal(ctx, r, m, here)
    if bg is not None:
        mv, _ = go(ctx, r, bg, slack=.2)
        return action(move=mv, **shoot(ctx, r, target, d), **ops)
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
        RUNE_MOTOR.__init__()
    _SOLUTIONS.clear()
    state["_plans"] = 0
    ctx = Ctx(obs, state)
    rune_update(ctx)
    live = [x["slot"] for x in obs["robots"] if x["role"] == "infantry" and x["alive"] and not x.get("weak")]
    state["_starter"] = min(live) if live else None
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
    starter = state.get("_starter")
    if starter is not None and str(starter) in actions and rune_start_ok(ctx):
        actions[str(starter)]["rune_start"] = True
    # A wheel-legged robot must turn before accelerating, and keep its legs
    # low on uneven ground. A tipped robot stays still for the engineer.
    for r in obs["robots"]:
        slot = str(r["slot"])
        if slot not in actions or not r["alive"]:
            continue
        command = actions[slot]
        if r.get("tipped") and r["slot"] != 3:
            command["move"] = [0,0]
            command["brake"] = True
        if r["slot"] == 3:
            mv = command.get("move", [0,0])
            if math.hypot(*mv) > .01:
                angle = math.atan2(mv[1],mv[0])
                delta = wrap(angle-r["heading"])
                if abs(delta) > math.pi/2:
                    angle += math.pi
                    delta = wrap(angle-r["heading"])
                command["heading"] = angle
                scale = max(.15, math.cos(delta)**2) * .8
                command["move"] = [v*scale for v in mv]
            command["leg_height"] = .16
            command["brake"] = True
        if math.hypot(*command.get("move",[0,0])) > .3 and r.get("supercap_energy_j",0)>450 and not r.get("tipped"):
            command["power"] = min(160,r["power_limit"]+60)
    for k in [k for k in state if k.startswith("_")]:
        state.pop(k)
    return actions, state
