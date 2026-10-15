"""经济运营 (siege_economy), derived from siege_team.
保留更多金币给工程与科技核心，推迟英雄决战，减少工程救援分心和无人机付费支出。
Lineup: 1:1, 2:2, 3:305, 4:305, 6:6, 7:301.
"""
import heapq
import math
import time

import sdk
from sdk import action, aim_at, aim_pitch, ballistic_reachable, can_fire, instant_revive_cost, remote_heal_cost

ARENA = sdk._REFERENCE_ARENA
W, H = ARENA["width"], ARENA["height"]
ENEMY = {"red": "blue", "blue": "red"}

# -- terrain grid
RES = 0.1
NX, NY = int(W / RES), int(H / RES)
CRES = 0.2
CX, CY = NX // 2, NY // 2


def _heights():
  return [sdk.terrain_height(ARENA, (i + .5) * RES, (j + .5) * RES) for i in range(NX) for j in range(NY)]


HEIGHT = _heights()


def _steps():
  """Largest height change (m) to a 4-neighbour: < 0.1 is a slope, 0.1-0.45 a step a wheel-legged robot can hop."""
  g = [0.0] * (NX * NY)
  for i in range(NX):
    for j in range(NY):
      h = HEIGHT[i * NY + j]
      g[i * NY + j] = max(abs(h - HEIGHT[a * NY + b]) for a, b in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1))
                if 0 <= a < NX and 0 <= b < NY)
  return g


STEP = _steps()
OVERHEAD = 0.7          # obstacles this far above the ground (rune crossbeam, gearbox) never stop a chassis


def _walls(team, fold):
  """Static blocked cells for one team: walls, no-go areas and structure bodies; tunnel roofs only stop unfolded robots."""
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
    cx, cy = o["x"] + o["w"] / 2, o["y"] + o["h"] / 2
    gap = o.get("bottom", 0) - sdk.terrain_height(ARENA, cx, cy)
    if gap > OVERHEAD:
      continue
    if fold and "roof" in o.get("id", "") and gap > .2:
      continue
    box(cx, cy, o["w"] / 2, o["h"] / 2, o.get("rotation", 0))
  for f in ARENA["forbidden"]:
    if f["kind"] == "base" or f.get("owner") not in (None, team):
      box(f["x"] + f["w"] / 2, f["y"] + f["h"] / 2, f["w"] / 2, f["h"] / 2, 0)
  for x, y in ARENA["outposts"].values():
    box(x, y, .35, .35, 0)
  return blocked


def _clearance(blocked):
  """Chamfer (3-4) distance in metres to the nearest blocked cell or field edge: one forward, one backward pass."""
  d = [0 if blocked[k] else 10 ** 6 for k in range(NX * NY)]
  for e in (1, -1):
    for i in (range(NX) if e > 0 else range(NX - 1, -1, -1)):
      for j in (range(NY) if e > 0 else range(NY - 1, -1, -1)):
        k = i * NY + j
        if not d[k]:
          continue
        v = min(d[k], 3 * (i + 1 if e > 0 else NX - i), 3 * (j + 1 if e > 0 else NY - j))
        if 0 <= i - e < NX:
          b = k - e * NY
          v = min(v, d[b] + 3, d[b - 1] + 4 if j > 0 else v, d[b + 1] + 4 if j < NY - 1 else v)
        if 0 <= j - e < NY:
          v = min(v, d[k - e] + 3)
        d[k] = v
  return [v * RES / 3 for v in d]


_WALLS = {(team, fold): _walls(team, fold) for team in ("red", "blue") for fold in (False, True)}
# Wheel-legged robots hop steps only through the middle of the two stair blocks in front of the fortresses.
_STAIRCELL = bytearray(NX * NY)
for _x0, _x1 in ((8.35, 10.3), (17.7, 19.65)):
  for _i in range(int(_x0 / RES), int(_x1 / RES) + 1):
    for _j in range(int(6.35 / RES), int(8.65 / RES) + 1):
      _STAIRCELL[_i * NY + _j] = 1
_GRIDS = {}


def grid(team, mode, slope):
  """Clearance map for a team, a chassis mode ('mec', 'leg' or 'fold') and a climbable grade (tan)."""
  key = (team, mode, slope)
  if key not in _GRIDS:
    blocked = bytearray(_WALLS[(team, mode == "fold")])
    rise = slope * RES
    for k in range(NX * NY):
      if STEP[k] > (.45 if mode == "leg" and _STAIRCELL[k] else rise):
        blocked[k] = 1
    _GRIDS[key] = _clearance(blocked)
  return _GRIDS[key]


for _team in ("red", "blue"):
  for _mode, _slope in (("mec", .4), ("leg", .4), ("fold", .4)):
    grid(_team, _mode, _slope)

def _hazard():
  """Fine cells on the high side of a drop of 0.1 m or more within 0.3 m (ledges, the jump-ramp gap)."""
  return bytearray(any(HEIGHT[a * NY + b] < HEIGHT[i * NY + j] - .1 for a in range(max(0, i - 3), min(NX, i + 4))
            for b in range(max(0, j - 3), min(NY, j + 4))) for i in range(NX) for j in range(NY))


HAZARD = _hazard()
_HAZCELL = bytearray(CX * CY)
for _I in range(CX):
  for _J in range(CY):
    _k = 2 * _I * NY + 2 * _J
    if HAZARD[_k] or HAZARD[_k + 1] or HAZARD[_k + NY] or HAZARD[_k + NY + 1]:
      _HAZCELL[_I * CY + _J] = 1
_STEPCELL = bytearray(CX * CY)
for _I in range(CX):
  for _J in range(CY):
    _k = 2 * _I * NY + 2 * _J
    if max(STEP[_k], STEP[_k + 1], STEP[_k + NY], STEP[_k + NY + 1]) >= .1:
      _STEPCELL[_I * CY + _J] = 1
_OK = {}


def coarse_map(team, mode, slope, radius):
  """Coarse (0.2 m) cells whose four fine cells all keep `radius` clearance."""
  key = (team, mode, slope, radius)
  if key not in _OK:
    clear = grid(team, mode, slope)
    ok = bytearray(CX * CY)
    for I in range(CX):
      for J in range(CY):
        k = 2 * I * NY + 2 * J
        if min(clear[k], clear[k + 1], clear[k + NY], clear[k + NY + 1]) >= radius:
          ok[I * CY + J] = 1
    _OK[key] = ok
  return _OK[key]


for _team in ("red", "blue"):                       # every planning map used in play, so no decision builds one
  for _mode, _radius in (("mec", .28), ("mec", .25), ("leg", .25), ("fold", .24)):
    coarse_map(_team, _mode, .4, _radius)


def busy(ctx, limit):
  """This decision has already used `limit` seconds (the runner disables a team after one 200 ms miss)."""
  return time.perf_counter() - ctx.state.get("_t0", time.perf_counter()) > limit


def cell(x, y):
  return min(NX - 1, max(0, int(x / RES))), min(NY - 1, max(0, int(y / RES)))


def ground(x, y):
  i, j = cell(x, y)
  return HEIGHT[i * NY + j]


FLOOR_TAN = math.tan(math.radians(ARENA.get("floor_slope_deg", 0)))


def lift(x, y):
  """Height above the tilted floor datum (0 on the floor, 0.2 on the road, 0.4 on the central highland)."""
  return ground(x, y) - max(0.0, min(y, H - y)) * FLOOR_TAN


def clearance_at(clear, x, y):
  i, j = cell(x, y)
  return clear[i * NY + j]


def line_free(clear, a, b, radius, ledges=False):
  """Straight segment keeps `radius` clearance; with ledges=True it must also stay off drop edges."""
  d = math.dist(a, b)
  steps = max(1, int(d / .08))
  for s in range(steps + 1):
    t = s / steps
    x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
    if clearance_at(clear, x, y) < radius:
      return False
    if ledges and s and HAZARD[cell(x, y)[0] * NY + cell(x, y)[1]]:
      return False
  return True


def nearest_ok(ok, x, y, limit=14):
  I, J = int(x / CRES), int(y / CRES)
  best = None
  for r in range(limit + 1):
    for dI in range(-r, r + 1):
      for dJ in (-r, r) if abs(dI) != r else range(-r, r + 1):
        a, b = I + dI, J + dJ
        if 0 <= a < CX and 0 <= b < CY and ok[a * CY + b]:
          d = math.dist(((a + .5) * CRES, (b + .5) * CRES), (x, y))
          if best is None or d < best[0]:
            best = (d, a, b)
    if best:
      return best[1], best[2]
  return None


_NB = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414))


def astar(team, mode, slope, radius, start, goal, budget=6000):
  ok = coarse_map(team, mode, slope, radius)
  clear = grid(team, mode, slope)
  s = nearest_ok(ok, start[0], start[1])
  g = nearest_ok(ok, goal[0], goal[1])
  if s is None or g is None:
    return None
  if s == g:
    return [goal]
  leg = mode == "leg"
  gx, gy = g
  sn, gn = s[0] * CY + s[1], g[0] * CY + g[1]
  openq = [(0.0, 0.0, sn)]
  came = {sn: -1}
  cost = {sn: 0.0}
  found = None
  stop = time.perf_counter() + .025                   # a search never holds a decision for more than 25 ms
  while openq and budget > 0:
    budget -= 1
    if not budget & 255 and time.perf_counter() > stop:
      break
    _, c, n = heapq.heappop(openq)
    if n == gn:
      found = n
      break
    if c > cost[n]:
      continue
    I, J = divmod(n, CY)
    for dI, dJ, w in _NB:
      nI, nJ = I + dI, J + dJ
      if not (0 <= nI < CX and 0 <= nJ < CY):
        continue
      m = nI * CY + nJ
      if not ok[m]:
        continue
      if dI and dJ and not (ok[(I + dI) * CY + J] and ok[I * CY + J + dJ]):
        continue
      k = 2 * nI * NY + 2 * nJ
      nc = c + w * (1.8 if clear[k] - radius < .1 else 1.0)
      if leg and _STEPCELL[m]:
        nc += 5.0
      elif not leg and _HAZCELL[m]:
        nc += 2.0
      if nc < cost.get(m, 1e18):
        cost[m] = nc
        came[m] = n
        dx, dy = abs(nI - gx), abs(nJ - gy)
        heapq.heappush(openq, (nc + max(dx, dy) + .414 * min(dx, dy), nc, m))
  if found is None:
    return None
  path = []
  n = found
  while n != -1:
    I, J = divmod(n, CY)
    path.append(((I + .5) * CRES, (J + .5) * CRES))
    n = came[n]
  path.reverse()
  if clearance_at(clear, goal[0], goal[1]) >= radius:
    path[-1] = goal
  return path


# -- helpers
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

  def in_zone(self, robot, zone_id):
    z = self.zones[zone_id]
    if z.get("polygon"):
      return sdk.point_in_polygon(robot["x"], robot["y"], z["polygon"])
    return dist(pos(robot), (z["x"], z["y"])) <= z["radius"]


# -- motion
RADIUS = {"hero": .28, "engineer": .28, "infantry": .25}


def design(robot):
  return sdk.DESIGNS[str(robot.get("model_slot", robot["slot"]))]


def is_leg(robot):
  return robot.get("chassis_type") == "wheel_legged"


# Stair blocks in red-side coordinates: (axis sign, first edge, second edge, run-up x, y band). Our block is climbed
# toward +x from the fortress side; the enemy block toward -x when coming home from the enemy fortress.
# The run-up starts behind the fortress so the robot crosses it at ~1.65 m/s and hops at speed (a standing start just
# in front of the step is too slow and flips the chassis).
STAIRS = ((1, 8.51, 10.15, 5.2, (6.7, 8.3)), (-1, 19.49, 17.85, 22.8, (6.7, 8.3)))


def stair_climb(ctx, robot, m, goal):
  """Calibrated two-hop climb through the highland crossing cards (retried after a failed hop); None if not needed."""
  rx, ry = ctx.p(*pos(robot))
  gx, gy = ctx.p(*goal)
  z = robot.get("z", .15)                     # body height over the floor datum: ~0.15 floor, ~0.32 step, ~0.48 deck
  h = 0.0 if z < .28 else .2 if z < .4 else .4
  for sgn, e1, e2, run, (lo, hi) in STAIRS:
    st = m.get("stair")
    active = st is not None and st[0] == sgn
    floor = h < .1 and (rx - e1) * sgn < .4 and abs(rx - e1) < 5.5 and 5.3 < ry < 9.7
    step = .14 < h < .27 and (rx - e1) * sgn > 0 and (rx - e2) * sgn < -.3 and 6.2 < ry < 8.8
    wants = (gx - e2) * sgn > .3
    if not active and not ((floor or step) and wants):
      continue
    if not wants:
      m.pop("stair", None)
      MEM.setdefault("team", {}).pop("stair_busy", None)
      return None
    base_heading = 0.0 if sgn * (1 if ctx.team == "red" else -1) > 0 else math.pi
    heading = base_heading
    vref = robot.get("speed_reference_mps") or 4.0
    shared = MEM.setdefault("team", {})
    busy = shared.get("stair_busy")
    if busy and busy[0] != robot["slot"] and ctx.t - busy[1] < 1.0 and not active:
      mv, _ = go(ctx, robot, ctx.p(run - sgn * .6, 8.7), slack=.3, plain=True)   # wait off the lane
      return move_cmd(mv)
    shared["stair_busy"] = (robot["slot"], ctx.t)        # claimed while approaching and climbing
    if not active:
      lane = min(hi, max(lo, m.get("lane", 7.5)))
      start = ctx.p(run if floor else e1 + sgn * .3, lane)
      err = abs(wrap(heading - robot["heading"]))
      still = math.hypot(robot["vx"], robot["vy"]) < .15
      if dist(pos(robot), start) > .12 or err > .08 or not still:
        m["settle"] = ctx.t
        if dist(pos(robot), start) > .12:
          mv, _ = go(ctx, robot, start, slack=.1, plain=True)
          return move_cmd(mv)
        return {"move": (0.0, 0.0), "heading": heading, "leg_height": .2}
      if ctx.t - m.get("settle", ctx.t) < .6:          # start every run-up settled, as calibrated
        return {"move": (0.0, 0.0), "heading": heading, "leg_height": .2}
      st = m["stair"] = [sgn, 0 if floor else 1, ctx.t - (0 if floor else 3), lane]
    lane = st[3]
    # No strafing: steer the heading a little toward the lane so the robot crosses both detection cards.
    heading = wrap(base_heading + sgn * max(-.15, min(.15, 1.2 * (lane - ry))))
    jump_cd = design(robot).get("jump_cooldown_s", .8)
    phase = st[1]
    cmd = {"heading": heading, "leg_height": .2, "power": 200}
    fwd = (math.cos(heading), math.sin(heading))
    lead = max(0.0, robot["vx"] * fwd[0] + robot["vy"] * fwd[1]) * .07 * sgn   # decisions come every 0.1 s
    age = ctx.t - st[2]
    waiting = phase == 1 and age < jump_cd + .1
    stalled = not waiting and age > 1.0 and math.hypot(robot["vx"], robot["vy"]) < .15 and h < .3
    failed = stalled or (phase == 1 and .5 < age < 3 and h < .1) or (phase == 2 and age > .7 and h < .3 and (rx - e2) * sgn < .2)
    if age > 9 or robot.get("tipped") or failed:
      m.pop("stair", None)
      MEM.setdefault("team", {}).pop("stair_busy", None)
      return {"move": (-fwd[0] * .3, -fwd[1] * .3), "heading": heading, "leg_height": .2}
    if phase == 0:
      speed = 1.65
      if (rx + lead - (e1 - sgn * .56)) * sgn >= 0:
        cmd["jump"] = .7
        st[1], st[2] = 1, ctx.t
    elif phase == 1:
      speed = 1.2
      ready = age >= jump_cd + .08
      if ready and (rx + lead - (e2 - sgn * .56)) * sgn >= 0:
        cmd["jump"] = 1.0
        st[1], st[2] = 2, ctx.t
      elif not ready and (rx - (e2 - sgn * .45)) * sgn >= 0:
        speed = 0.0
    else:
      speed = 1.2
      if age > .9 or (rx - e2) * sgn > .9:
        m.pop("stair", None)
        MEM.setdefault("team", {}).pop("stair_busy", None)
    cmd["move"] = (fwd[0] * speed / vref, fwd[1] * speed / vref)
    return cmd
  return None


# Validated wheeled route between our floor and the central highland (red-side coordinates): road ramp, round the
# north side of the tunnel, over the landing pad (clear of the jump-ramp gap), along the highway and up the end slope.
DECK_CHAIN = ((8.24, 10.9), (8.24, 11.6), (8.24, 13.2), (8.5, 14.2), (10.0, 14.25), (10.3, 13.4), (11.9, 13.4), (11.9, 11.2))


def deck_waypoint(ctx, robot, m, goal):
  """Next deck-route point for a wheeled robot moving between a floor side and the highland, else None."""
  rx, ry = ctx.p(*pos(robot))
  gx, gy = ctx.p(*goal)
  hr, hg = lift(*pos(robot)), lift(*goal)
  on_deck = hr > .3 and 10.15 < rx < 17.9
  goal_deck = hg > .3 and 10.15 < gx < 17.9
  on_road = .12 < hr < .3 and ry > 11.3 and rx < 12.7
  enemy = [(W - x, H - y) for x, y in DECK_CHAIN]       # the same route on the enemy side, floor first
  e_road = .12 < hr < .3 and ry < 3.7 and rx > 15.3
  if goal_deck and not on_deck or not on_deck and not on_road and gx > 15.5 and rx < 12.5:
    chain = enemy if rx > 15 else DECK_CHAIN
  elif on_deck and not goal_deck and gx < 12.5 or on_road and not goal_deck and gx < 12.5 and gy < 11.3:
    chain = DECK_CHAIN[::-1]
  elif on_deck and not goal_deck and gx > 15.5 or e_road and not goal_deck and gx > 15.5 and gy > 3.7:
    chain = enemy[::-1]
  else:
    m.pop("deck", None)
    return None
  key = (chain[0], chain[-1])
  st = m.get("deck")
  if st is None or st[0] != key:
    if on_deck and chain[0] in (DECK_CHAIN[-1], enemy[-1]):
      k = 0
    elif chain[0] == DECK_CHAIN[0] and hr < .12 and ry < 11.3 or chain[0] == enemy[0] and hr < .12 and ry > 3.7:
      k = 0
    else:
      k = min(range(len(chain)), key=lambda i: dist((rx, ry), chain[i]))
    st = m["deck"] = [key, k]
  while st[1] < len(chain) and dist((rx, ry), chain[st[1]]) < .25:
    st[1] += 1
  if st[1] >= len(chain):
    return None
  return ctx.p(*chain[st[1]])


def go(ctx, robot, goal, slack=.25, fast=1.0, mode=None, plain=False):
  """Move command toward goal along a planned path; returns (move, arrived) or (command dict, arrived) for hops."""
  m = ctx.mem(robot["slot"])
  here = pos(robot)
  goal = (min(W - .3, max(.3, goal[0])), min(H - .3, max(.3, goal[1])))
  remaining = dist(here, goal)
  leg = is_leg(robot)
  mode = mode or ("leg" if leg else "mec")
  if remaining <= slack:
    m.pop("path", None)
    return (0.0, 0.0), True
  if leg and not plain:
    climb = stair_climb(ctx, robot, m, goal)
    if climb is not None:
      m["moving"] = False
      return climb, False
  if not leg and mode == "mec" and not plain:
    wp = deck_waypoint(ctx, robot, m, goal)
    if wp is not None:
      mv, _ = go(ctx, robot, wp, slack=.2, fast=min(fast, .85), mode=mode, plain=True)
      return mv, False
  radius = .24 if mode == "fold" else RADIUS[robot["role"]]
  slope = .4                      # every chassis here climbs the 20-degree fortress sides, if slowly
  clear = grid(ctx.team, mode, slope)
  # Stuck handling: back away from the obstacle for a moment, then replan.
  hist = m.setdefault("hist", [])
  hist.append((ctx.t, here[0], here[1]))
  while hist and hist[0][0] < ctx.t - 1.6:
    hist.pop(0)
  if m.get("escape_until", -1) > ctx.t:
    ex, ey = m["escape"]
    return (ex, ey), False
  hopping = m.get("stair") is not None
  if len(hist) > 12 and math.dist(hist[0][1:], here) < .12 and m.get("moving") and not hopping:
    a = m.get("dir", 0.0) + math.pi + (0.9 if (ctx.tick // 20) % 2 else -0.9)
    m["escape"] = (math.cos(a) * .7, math.sin(a) * .7)
    m["escape_until"] = ctx.t + .7
    m.pop("path", None)
    hist.clear()
    return m["escape"], False
  ledges = not leg
  if line_free(clear, here, goal, radius * .9, ledges) and (not leg or remaining < 3.5):
    target = goal
  else:
    path = m.get("path")
    changed = dist(m.get("pgoal", (-9, -9)), goal) > .3 or m.get("pkey") != (mode, slope)
    retry = ctx.t - m.get("ptime", -9) > (4 if path else 1.5)
    if changed or retry:
      if ctx.state.get("_plans", 0) >= 2 or busy(ctx, .035):
        if not path:
          return (0.0, 0.0), False
      else:
        ctx.state["_plans"] = ctx.state.get("_plans", 0) + 1
        path = astar(ctx.team, mode, slope, radius, here, goal)
        m["path"], m["pgoal"], m["pkey"], m["ptime"] = path, goal, (mode, slope), ctx.t
    if not path:
      target = goal
    else:
      # Drop passed points, then steer at the farthest visible point within 3 m (no shortcuts across steps).
      while len(path) > 1 and dist(here, path[0]) < .35:
        path.pop(0)
      target = path[0]
      h0 = ground(*here)
      for p in path[1:16]:
        if dist(here, p) > 3.0 or not line_free(clear, here, p, radius * .9, ledges):
          break
        if leg and abs(ground(*p) - h0) > .08:
          target = p
          break
        target = p
  dx, dy = target[0] - here[0], target[1] - here[1]
  n = math.hypot(dx, dy) or 1e-6
  vref = robot.get("speed_reference_mps") or 3.0
  speed = min(1.0, math.sqrt(2 * 1.6 * remaining) / vref) * fast
  if leg and ground(target[0], target[1]) < ground(*here) - .1:
    speed = min(speed, 1.7 / vref)                  # roll off steps gently
  v = math.hypot(robot["vx"], robot["vy"])
  if v > .3:
    turn = (dx * robot["vx"] + dy * robot["vy"]) / (n * v)
    speed *= max(.45, (1 + turn) / 2)
  m["moving"] = speed > .25
  m["dir"] = math.atan2(dy, dx)
  return (dx / n * speed, dy / n * speed), False


def move_cmd(mv):
  """Merge a go() result into action keyword arguments."""
  if isinstance(mv, dict):
    return dict(mv)
  return {"move": mv}


# -- shooting

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
    if dist(pos(e), ctx.p(6.6, 7.5)) < .9:
      score -= 6                                  # capturing our fortress, and it takes double damage there
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
      and abs(actual_pitch-pitch)<pitch_tolerance and not busy(ctx, .09) and clear_shot(ctx, robot, target, yaw, pitch, d))
  return {"aim": yaw, "pitch": pitch, "fire": fire}


# -- economy
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
  reserve = {0: 150, 1: 0, 2: 400}[priority]
  timely = wait > 6 or (robot['role']=='hero' and not robot.get('tipped') and ctx.coins>=cost+100)
  window = any(c - 4 <= ctx.t < c + 55 for c in (180, 255, 330))
  if robot["role"] == "hero" and window and ctx.coins >= cost and ctx.t < 410:
    ctx.coins -= cost
    return action(revive=True)
  if timely and ctx.t < 410 and ctx.coins - cost >= reserve:
    ctx.coins -= cost
    return action(revive=True)
  return action()


# -- roles
HERO_SPOT = (9.4, 3.6)


def buffed(ctx):
  """Our own rune buff is running with a real attack or cooling bonus: spend every second shooting."""
  rune = ctx.obs["runes"][ctx.team]
  return rune["status"] == "active" and (rune["attack"] >= 1.5 or rune["cooling"] >= 2)


PUSH_T, HERO_PUSH = 390.0, True


def push_ok(ctx, r):
  """Late push only with a large-rune attack buff or open enemy armour, an escort at the enemy base, HP and ammo."""
  if not HERO_PUSH or ctx.base["hp"] <= 0 or ctx.outpost["hp"] > 0 or ctx.t < PUSH_T:
    return False
  rune = ctx.obs["runes"][ctx.team]
  boost = rune["status"] == "active" and rune["attack"] >= 1.5
  escort = [x for x in ctx.robots.values() if x["role"] == "infantry" and x["alive"] and not x.get("weak")
       and dist(pos(x), pos(ctx.base)) < 9]
  return bool((boost or ctx.base["armor_open"]) and escort and r["hp"] > r["max_hp"] * .5
        and (r["ammo"] >= 8 or ctx.coins >= 300))


def hero_push(ctx, r, m, ops):
  bx, by = ctx.base["x"], ctx.base["y"]
  spots = base_spots(ctx) or [(bx - 2.1, by)]
  s = min(spots, key=lambda q: dist(pos(r), q))
  goal = (bx + (s[0] - bx) * 1.7, by + (s[1] - by) * 1.7)          # 3.6 m out, facing an exposed panel
  mv, _ = go(ctx, r, goal, slack=.4)
  near = [e for e in ctx.targets if dist(pos(r), pos(e)) < 4.5]
  if near:
    target = min(near, key=lambda e: dist(pos(r), pos(e)))
  else:
    target = dict(ctx.base, kind="base")
  if r["ammo"] < 6 and not r["pending_ammo"] and ctx.coins >= 150 and disengaged(ctx, r):
    order = buy(ctx, r, 10, remote=True)
    if order:
      ops["buy_ammo"] = order
  return action(**move_cmd(mv), deploy=False, **shoot(ctx, r, target, dist(pos(r), pos(target))), **ops)


def hero(ctx, r):
  m = ctx.mem(1)
  if ctx.tick == 0:
    return action(profile="ranged")
  if not r["alive"]:
    return revive_or_wait(ctx, r, 2)
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
  if m.get("push") or push_ok(ctx, r):
    m["push"] = True
    return hero_push(ctx, r, m, ops)
  if r["ammo"] == 0 and not r["deployed"] and r["deploy_at"] is None:
    # Fetch ammo: home first if poor, otherwise straight to the spot and buy remotely there.
    if ctx.coins < 150 or ctx.t < 1:
      mv, _ = go(ctx, r, ctx.p(3.6, 6.2))
      return action(move=mv, deploy=False)
  if not r["deployed"] and r["deploy_at"] is None:
    mv, arrived = go(ctx, r, spot, slack=.2)
    if not arrived:
      target, d = choose_target(ctx, r, 14)
      return action(move=mv, deploy=False, **shoot(ctx, r, target, d, fire_ok=False), **ops)
  targets = structure_targets(ctx, r)
  threat = [e for e in ctx.targets if dist(pos(r), pos(e)) < 7 and e["role"] != "engineer"]
  target = None
  if targets and ballistic_reachable(r, targets[0]) and (targets[0].get("kind") == "outpost" or dist(pos(r), pos(targets[0])) < 11):
    target = targets[0]                     # 42mm is scarce: no long shots at the small base modules
  if threat and (target is None or ctx.outpost["hp"] > 0):
    target = min(threat, key=lambda e: dist(pos(r), pos(e)))
  raiders = [e for e in ctx.targets if dist(pos(e), ctx.p(6.6, 7.5)) < .9]
  if raiders and ctx.my_outpost["hp"] <= 0:
    target = min(raiders, key=lambda e: e["hp"])     # double damage in our fortress: one 42mm hit is 400
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
  # Difficulty 4 unlocks at 180 s and only one team can run it at a time: be loaded and waiting in the assembly zone.
  # From 30 s before the unlock until it is done the engineer never leaves the zone (no rescues, no outpost rebuilds).
  start4 = max(180.0, core["retry_at"])
  can4 = 4 not in done and 3 in done and not core["permanent_lock"]
  l4_window = can4 and start4 - 40 <= ctx.t < start4 + 45
  # A tipped teammate cannot drive and respawning does not right it: grip and right it.
  tried = m.setdefault("tried", {})
  tipped = [t for t in sdk.tipped_teammates(ctx.obs) if t["alive"] and t["role"] != "aerial" and dist(pos(r), pos(t)) < 5
       and abs(lift(*pos(t)) - lift(*pos(r))) < .1 and ctx.t - tried.get(t["slot"], -99) > 40]
  # Do not abandon the first income unlock or spend the whole match on a wreck.
  if not busy and tipped and not r.get("weak") and 3 in done and not l4_window:
    target = min(tipped, key=lambda t: dist(pos(r), pos(t))-(2 if t["slot"]==1 else 0))
    if m.get("rescue_id") != target["slot"]:
      m["rescue_id"],m["rescue_start"]=target["slot"],ctx.t
      tried[target["slot"]] = ctx.t                  # one attempt per robot every 40 s, then back to the tech
    if ctx.t-m["rescue_start"] < 8:
      if dist(pos(r), pos(target)) > .75:
        mv, _ = go(ctx, r, sdk.rescue_point(r, target), slack=.08)
        return action(move=mv, rescue=target["slot"])
      return action(rescue=target["slot"])
  else:
    m.pop("rescue_id",None)
  # Rebuild a fallen outpost only once level 3 stands and not while level 4 is due (tech outweighs a 750 HP outpost).
  rebuild_ok = (3 in done and ctx.t < 168) or 4 in done or (3 in done and ctx.t >= 235)
  if (not busy and ctx.my_outpost["hp"] <= 0 and ctx.econ["rebuild_credits"] > 0 and ctx.t < 299
      and not r.get("weak") and rebuild_ok and not l4_window):
    # stand on the floor side of the platform edge: the zone centre sits on a 0.2 m step that tips the chassis
    mv, arrived = go(ctx, r, (outpost_zone["x"], outpost_zone["y"] + (-.7 if team == "red" else .7)), slack=.2)
    return action(move=mv)
  ready4 = can4 and ctx.t >= start4 - .05
  prep4 = can4 and ctx.t >= start4 - 35
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
  # The plinth's west corner has a lip a mecanum chassis cannot climb at an angle: enter across its south-west face.
  rx, ry = ctx.p(*pos(r))
  if dist(pos(r), (assembly["x"], assembly["y"])) > .9 and ry > 7.2 and rx < 13.2 and lift(*pos(r)) > .3:
    mv, arrived = go(ctx, r, ctx.p(12.15, 6.55), slack=.3)
    arrived = False
  else:
    mv, arrived = go(ctx, r, (assembly["x"], assembly["y"]), slack=.25)
  ops = dict(assembly_insert=True, assembly_translate=True, assembly_rotate=core["target_rotation"], assembly_confirm=True)
  if not busy:
    if prep4 and not ready4:
      pass                                   # hold both units until difficulty 4 unlocks
    elif level == 4:
      # never interrupt the other team mid-assembly (15 s delay, a failure locks level 4 for good)
      if not (enemy_busy and enemy_core.get("difficulty") != 4 and ctx.t < start4 + 12):
        ops["assembly"] = 4
    elif ctx.t >= (level - 1) * 60:
      ops["assembly"] = level
  return action(move=mv, **ops)


AIR_SPOT = (15.0, 2.4)


def aerial(ctx, r):
  m = ctx.mem(6)
  rune = ctx.obs["runes"][ctx.team]
  serving = rune_open(ctx) is not None or rune_soon(ctx)
  useful = ctx.outpost["hp"] > 0 or bool(ctx.targets) or ctx.base["armor_open"] or serving
  free = r["support_time"] > 0
  keep = (free or (ctx.coins > 150 and useful)) and r["ammo"] > 0
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
  hold = r["ammo"] <= rune_reserve(ctx) + 8      # a burst can overshoot by a few rounds
  return action(move=mv, support=True, altitude=2.0, **shoot(ctx, r, target, d, fire_ok=not hold))



# -- energy rune (aerial shooter, fitted shaft motor)
# The invulnerable aerial hovers 4 m from our rune face and shoots every lamp; infantry only press rune_start. The
# shaft speed law (four seeded constants) is fitted online from the published velocity/acceleration, and each shot is
# pre-parked one decision ahead because the gimbal slews per substep and only the first bullet can reach the lamp.
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
  return (air is not None and RUNE_MOTOR.ok(ctx.t) and air["support_active"] and air["ammo"] >= 20
      and dist(pos(air), ctx.p(*RUNE_HOVER)) < .12 and math.hypot(air["vx"], air["vy"]) < .08
      and air["heat"] + 40 <= air["max_heat"])


def rune_start_ok(ctx):
  rune = ctx.obs["runes"][ctx.team]
  return (ctx.t > 3 and rune["status"] == "idle" and rune_open(ctx) is not None and rune_ready(ctx, ctx.robots.get(6)))


# -- infantry
# Red-side coordinates (ctx.p mirrors them for blue).
LEG_POSTS = ((11.3, 6.7), (11.3, 8.3))       # highland lip above our steps; the highland buff point is (10.95, 6.55)
ENEMY_FORT = (21.4, 7.5)                      # enemy fortress centre
TUNNEL_N, TUNNEL_S = (9.39, 14.2), (9.39, 13.1)   # our road tunnel: north mouth on the highway, south card point
GUARD_POST = (7.6, 5.6)                       # covers our fortress, our steps and the hero's lane
ASSAULT_T = 179.0
REFRESH_T = 163.0


def base_spots(ctx):
  """Reachable firing spots 2.1 m in front of each lower base panel, front face first (world coordinates)."""
  bx, by = ctx.base["x"], ctx.base["y"]
  clear = grid(ctx.team, "leg", .4)
  out = []
  for k in range(3):
    a = k * math.tau / 3
    p = (bx + 2.1 * math.cos(a), by + 2.1 * math.sin(a))
    if clearance_at(clear, *p) >= .3:
      out.append(p)
  return sorted(out, key=lambda p: abs(p[0] - W / 2))


def fortress_open(ctx):
  """The enemy fortress can be captured now (after 180 s, enemy outpost down) and their armour is still closed."""
  return ctx.t >= 180 and ctx.outpost["hp"] <= 0 and not ctx.base["armor_open"] and ctx.base["hp"] > 0


def infantry_common(ctx, r, m, ops):
  """Ammo, healing and recovery shared by every infantry; returns an action to use instead, or None."""
  if r["ammo"] < 40 and at_local_shop(ctx, r) and ctx.t >= 1:
    order = buy(ctx, r, 100 if ctx.coins > 400 else 50)
    if order:
      ops["buy_ammo"] = order
  elif r["ammo"] < 15 and not r["pending_ammo"] and disengaged(ctx, r) and ctx.coins > 350:
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
    if r["hp"] >= r["max_hp"] * .8 and not r["weak"]:
      m.pop("recover", None)
    else:
      home = ctx.p(1.6, 11.8 + (r["slot"] - 3) * .2)
      zone = ctx.zones.get(ctx.enemy + "_outpost")
      if (r["weak"] and zone and ctx.outpost["hp"] <= 0 and ctx.t < 297 and ctx.p(*pos(r))[0] > 14
          and dist(pos(r), (zone["x"], zone["y"])) < dist(pos(r), home)):
        c = (zone["x"], zone["y"])             # the destroyed enemy outpost's zone also clears weakness
        k = .72 / max(.01, dist(pos(r), c))     # its ring, not the solid outpost body
        home = (c[0] + (r["x"] - c[0]) * k, c[1] + (r["y"] - c[1]) * k)
      mv, _ = go(ctx, r, home)
      return action(**move_cmd(mv), **ops)
  return None


def leg_infantry(ctx, r, m, ops, index):
  here = pos(r)
  m["lane"] = 7.5
  target, d = choose_target(ctx, r)
  if r["ammo"] == 0 and not ops.get("buy_ammo") and ctx.t < 5:
    mv, _ = go(ctx, r, ctx.p(3.3, 7.5))
    return action(**move_cmd(mv), **ops)
  if ctx.base["armor_open"] and ctx.base["hp"] > 0 and ctx.outpost["hp"] <= 0:
    spots = base_spots(ctx)
    goal = spots[index % len(spots)] if spots else pos(ctx.base)
    base = dict(ctx.base, kind="base")
    bd = dist(here, pos(base))
    close = [e for e in ctx.targets if dist(here, pos(e)) < 3.5]
    if not close and bd < 9:
      target, d = base, bd
    mv, _ = go(ctx, r, goal, slack=.35)
    return action(**move_cmd(mv), **shoot(ctx, r, target, d), **ops)
  pre = ctx.outpost["hp"] <= 0 and not ctx.base["armor_open"] and ctx.base["hp"] > 0
  if (pre and REFRESH_T - 12 <= ctx.t < 200 and r["ammo"] < 120 and not r["pending_ammo"] and not ops.get("buy_ammo")
      and disengaged(ctx, r) and ctx.coins > 300):
    order = buy(ctx, r, 100, remote=True)
    if order:
      ops["buy_ammo"] = order
  if pre and REFRESH_T <= ctx.t < 205 and not m.get("refreshed"):
    # Drop back to our run-up and climb again: the highland crossing gives 50% defence for 30 s, which covers
    # the walk across and most of the 20 s hold in the enemy fortress (where we take double damage).
    rx, ry = ctx.p(*here)
    team = MEM.setdefault("team", {})
    if r.get("crossing_defense_until", 0) > ctx.t + 22 and rx > 9:
      m["refreshed"] = True
      team["refreshed"] = team.get("refreshed", 0) | (1 << index)
    else:
      if r.get("z", .15) < .24 and rx < 8.6:
        m["ref_up"] = True                                     # down: now climb (never turn back mid-climb)
      goal = ctx.p(*ENEMY_FORT) if m.get("ref_up") else ctx.p(7.3, m["lane"])
      mv, _ = go(ctx, r, goal, slack=.3)
      return action(**move_cmd(mv), **shoot(ctx, r, target, d), **ops)
  if pre and m.get("refreshed") and ctx.t < 180:
    mv, _ = go(ctx, r, ctx.p(16.4, 6.9 + .9 * index), slack=.35)          # stage by the enemy steps
    return action(**move_cmd(mv), **shoot(ctx, r, target, d), **ops)
  if fortress_open(ctx) and ctx.t >= ASSAULT_T:
    fort = ctx.p(*ENEMY_FORT)
    mv, _ = go(ctx, r, (fort[0], fort[1] + (.22 if index else -.22)), slack=.12)
    if dist(here, fort) < 1.2:
      near = [e for e in ctx.targets if dist(here, pos(e)) < 8]
      if near:
        target = min(near, key=lambda e: dist(here, pos(e)) + e["hp"] / 80)
        d = dist(here, pos(target))
    return action(**move_cmd(mv), **shoot(ctx, r, target, d), **ops)
  goal = ctx.p(*LEG_POSTS[index % 2])
  hunt = [e for e in ctx.targets if e["role"] == "hero" and dist(goal, pos(e)) < 7]
  if hunt:
    goal = step_toward(pos(hunt[0]), here, 3.5)
  mv, _ = go(ctx, r, goal, slack=.35)
  return action(**move_cmd(mv), **shoot(ctx, r, target, d), **ops)


def tunnel_infantry(ctx, r, m, ops):
  """Fold through our road tunnel once for the 120 s cooling buff, then guard our half."""
  here = pos(r)
  target, d = choose_target(ctx, r)
  st = m.get("tun", 0)
  if r["ammo"] == 0 and not ops.get("buy_ammo") and ctx.t < 5:
    mv, _ = go(ctx, r, ctx.p(3.3, 8.6))
    return action(**move_cmd(mv), **ops)
  if st < 3 and (ctx.t > 70 or ctx.t - m.get("tun_t0", ctx.t) > 40):
    st = m["tun"] = 3                                   # give up: do not waste the opening
  m.setdefault("tun_t0", ctx.t)
  north, south = ctx.p(*TUNNEL_N), ctx.p(*TUNNEL_S)
  folded = r.get("transform_progress", 0) >= .999
  if st == 0:                                             # drive to the north mouth on the highway
    mv, arrived = go(ctx, r, north, slack=.12)
    if arrived:
      st = m["tun"] = 1
    return action(**move_cmd(mv), transform=False, **shoot(ctx, r, target, d), **ops)
  if st == 1:                                             # fold, then run south to the far card and back
    if not folded:
      return action(move=(0, 0), transform=True, **ops)
    # Both cards must be crossed within 3 s: run in briskly and turn back as soon as the far card is reached.
    mv, arrived = go(ctx, r, south, slack=.05, mode="fold", fast=.9)
    if arrived or ctx.p(*here)[1] < TUNNEL_S[1] + .08 or r.get("crossing_cooling_until", 0) > ctx.t + 100:
      st = m["tun"] = 2
    return action(**move_cmd(mv), transform=True, **ops)
  if st == 2:
    if r.get("crossing_cooling_until", 0) > ctx.t + 100:
      st = m["tun"] = 3
    mv, arrived = go(ctx, r, north, slack=.12, mode="fold")
    if arrived:
      st = m["tun"] = 3
    return action(**move_cmd(mv), transform=True, **ops)
  if r.get("transform_progress", 0) > 0:                 # unfold, but back out from under the roof first
    rx, ry = ctx.p(*here)
    if abs(rx - 9.39) < .55 and 12.75 < ry < 13.9:
      mv, _ = go(ctx, r, north, slack=.1, mode="fold")
      return action(**move_cmd(mv), transform=True, **ops)
    return action(move=(0, 0), transform=False, **ops)
  raiders = [e for e in ctx.targets if dist(pos(e), ctx.p(6.6, 7.5)) < 3]
  if ctx.base["armor_open"] and ctx.base["hp"] > 0 and ctx.outpost["hp"] <= 0 and not raiders and not ctx.my_base["armor_open"]:
    spots = base_spots(ctx)
    goal = spots[-1] if spots else pos(ctx.base)
    base = dict(ctx.base, kind="base")
    bd = dist(here, pos(base))
    if bd < 9 and not [e for e in ctx.targets if dist(here, pos(e)) < 3.5]:
      target, d = base, bd
    mv, _ = go(ctx, r, goal, slack=.35)
    return action(**move_cmd(mv), **shoot(ctx, r, target, d), **ops)
  # Guard: our fortress once our outpost is down (50% defence, cooling, reserve ammo), otherwise the guard post.
  goal = ctx.p(6.6, 7.5) if ctx.my_outpost["hp"] <= 0 else ctx.p(*GUARD_POST)
  if target is not None and target.get("kind") is None and d > 6 and dist(goal, pos(target)) < 8:
    goal = step_toward(pos(target), here, 5.5)
  mv, _ = go(ctx, r, goal, slack=.3)
  return action(**move_cmd(mv), **shoot(ctx, r, target, d), **ops)


def infantry(ctx, r):
  slot = r["slot"]
  m = ctx.mem(slot)
  if ctx.tick == 0:
    return action()
  if not r["alive"]:
    if (is_leg(r) and 178 <= ctx.t < 300 and ctx.outpost["hp"] <= 0 and not ctx.base["armor_open"]
        and dist(pos(r), ctx.p(*ENEMY_FORT)) < 1.3 and ctx.coins >= instant_revive_cost(r, ctx.t)):
      ctx.coins -= instant_revive_cost(r, ctx.t)
      return action(revive=True)
    return revive_or_wait(ctx, r, 2)
  ops = {}
  early = infantry_common(ctx, r, m, ops)
  if early is not None:
    return early
  if is_leg(r):
    legs = sorted(x["slot"] for x in ctx.robots.values() if x["role"] == "infantry" and is_leg(x))
    return leg_infantry(ctx, r, m, ops, legs.index(slot) if slot in legs else 0)
  if r.get("transform_allowed"):
    return tunnel_infantry(ctx, r, m, ops)
  target, d = choose_target(ctx, r)
  mv, _ = go(ctx, r, ctx.p(*GUARD_POST), slack=.4)
  return action(**move_cmd(mv), **shoot(ctx, r, target, d), **ops)


def step_toward(target, here, keep):
  d = dist(target, here)
  if d <= keep:
    return here
  t = (d - keep) / d
  return (here[0] + (target[0] - here[0]) * t, here[1] + (target[1] - here[1]) * t)


ROLES = {"hero": hero, "engineer": engineer, "aerial": aerial, "infantry": infantry}


EVADE = True


def evade(ctx, r, command):
  """Under fire: mecanum chassis spin within their turret's slew budget; a wheel-legged robot that is holding
  still rocks back and forth along its axis so the enemy lead keeps missing."""
  hit_recently = ctx.t - r.get("last_damage_time", -99) < 1.2
  if not EVADE or not hit_recently or r.get("tipped") or r.get("deployed") or r["role"] == "engineer":
    return
  if is_leg(r):
    mv = command.get("move", (0, 0))
    if math.hypot(*mv) < .1 and "jump" not in command:
      sgn = 1 if math.sin(ctx.t * 4.5 + r["slot"]) > 0 else -1
      h = r["heading"]
      command["move"] = [math.cos(h) * .32 * sgn, math.sin(h) * .32 * sgn]
      command["heading"] = h
    return
  if r.get("transform_progress", 0) > 0:
    return
  rate = min(5.0, design(r).get("turret_yaw_rate_rad_s", 5) * .75)
  command["yaw_rate"] = rate if (int(ctx.t / 3) + r["slot"]) % 2 else -rate


def act(obs, state):
  state = state if isinstance(state, dict) else {}
  if obs["tick"] == 0:
    MEM.clear()
    RUNE_MOTOR.__init__()
  _SOLUTIONS.clear()
  state["_plans"], state["_t0"] = 0, time.perf_counter()
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
  # A wheel-legged robot must turn before accelerating and keeps its legs low on flat ground;
  # a tipped mecanum robot stays still for the engineer.
  for r in obs["robots"]:
    slot = str(r["slot"])
    if slot not in actions or not r["alive"]:
      continue
    command = actions[slot]
    if r["role"] == "aerial":
      continue
    try:
      evade(ctx, r, command)
    except Exception as error:
      print("evade", slot, repr(error))
    if r.get("tipped") and not is_leg(r):
      command["move"] = [0, 0]
      command["brake"] = True
    if is_leg(r):
      mv = command.get("move", [0, 0])
      if "heading" not in command and math.hypot(*mv) > .01:
        angle = math.atan2(mv[1], mv[0])
        delta = wrap(angle - r["heading"])
        if abs(delta) > math.pi / 2:
          angle += math.pi
          delta = wrap(angle - r["heading"])
        command["heading"] = angle
        scale = max(.15, math.cos(delta) ** 2)
        command["move"] = [v * scale for v in mv]
      command.setdefault("leg_height", .16)
      command["brake"] = True
    if (math.hypot(*command.get("move", [0, 0])) > .3 and r.get("supercap_energy_j", 0) > 450
        and not r.get("tipped") and "power" not in command):
      command["power"] = min(160, r["power_limit"] + 60)
  for k in [k for k in state if k.startswith("_")]:
    state.pop(k)
  return actions, state
