import heapq
import math
import time
import sdk
from sdk import action, aim_at, aim_pitch, ballistic_reachable, can_fire, instant_revive_cost, remote_heal_cost
ARENA = sdk._REFERENCE_ARENA
W, H = ARENA["width"], ARENA["height"]
ENEMY = {"red": "blue", "blue": "red"}
RES = 0.1
NX, NY = int(W / RES), int(H / RES)
CRES = 0.2
CX, CY = NX // 2, NY // 2

def _heights():
  return [sdk.terrain_height(ARENA, (i + .5) * RES, (j + .5) * RES) for i in range(NX) for j in range(NY)]
HEIGHT = _heights()

def _steps():
  g = [0.0] * (NX * NY)
  for i in range(NX):
    for j in range(NY):
      h = HEIGHT[i * NY + j]
      g[i * NY + j] = max(abs(h - HEIGHT[a * NY + b]) for a, b in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1))
        if 0 <= a < NX and 0 <= b < NY)
  return g
STEP = _steps()
OVERHEAD = 0.7

def _walls(team, fold):
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
    if f["kind"] in ("base","pad","highway") or f.get("owner") not in (None, team):
      box(f["x"] + f["w"] / 2, f["y"] + f["h"] / 2, f["w"] / 2, f["h"] / 2, 0)
  for x, y in ARENA["outposts"].values():
    box(x, y, .35, .35, 0)
  return blocked

def _clearance(blocked):
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
_STAIRCELL = bytearray(NX * NY)
for _x0, _x1 in ((8.35, 10.3), (17.7, 19.65)):
  for _i in range(int(_x0 / RES), int(_x1 / RES) + 1):
    for _j in range(int(6.35 / RES), int(8.65 / RES) + 1):
      _STAIRCELL[_i * NY + _j] = 1
BUMPS = bytearray(NX*NY)
for _t in ARENA['terrain']:
  if _t['kind']=='bumps':
    for _i in range(max(0,int(_t['x']/RES)-1),min(NX,int((_t['x']+_t['w'])/RES)+2)):
      for _j in range(max(0,int(_t['y']/RES)-1),min(NY,int((_t['y']+_t['h'])/RES)+2)):
        BUMPS[_i*NY+_j]=1
_GRIDS = {}

def grid(team, mode, slope):
  key = (team, mode, slope)
  if key not in _GRIDS:
    blocked = bytearray(_WALLS[(team, mode == "fold")])
    rise = slope * RES
    for k in range(NX * NY):
      if STEP[k] > ((.45 if _STAIRCELL[k] else .22) if mode == "leg" else .095 if BUMPS[k] else rise):
        blocked[k] = 1
    _GRIDS[key] = _clearance(blocked)
  return _GRIDS[key]
for _team in ("red", "blue"):
  for _mode, _slope in (("mec", .4), ("leg", .4), ("fold", .4)):
    grid(_team, _mode, _slope)

def _hazard():
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
for _team in ("red", "blue"):
  for _mode, _radius in (("mec", .28), ("mec", .25), ("leg", .25), ("fold", .24)):
    coarse_map(_team, _mode, .4, _radius)

def busy(ctx, limit):
  return time.perf_counter() - ctx.state.get("_t0", time.perf_counter()) > limit

def cell(x, y):
  return min(NX - 1, max(0, int(x / RES))), min(NY - 1, max(0, int(y / RES)))

def ground(x, y):
  i, j = cell(x, y)
  return HEIGHT[i * NY + j]
FLOOR_TAN = math.tan(math.radians(ARENA.get("floor_slope_deg", 0)))

def lift(x, y):
  return ground(x, y) - max(0.0, min(y, H - y)) * FLOOR_TAN

def clearance_at(clear, x, y):
  i, j = cell(x, y)
  return clear[i * NY + j]

def line_free(clear, a, b, radius, ledges=False):
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
  stop = time.perf_counter() + .025
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
MEM = {}

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
    self.reserve=max((instant_revive_cost(r,self.t) for r in self.robots.values() if r['role']=='infantry' and r.get('fortress_hold',0)>8 and dist(pos(r),self.p(21.4,7.5))<1.3),default=0) if not self.base['armor_open'] else 0
    old=MEM.setdefault('team',{}).get('op_angle')
    self.omega=wrap(self.outpost['rotation']-old[1])/(self.t-old[0]) if old and self.t>old[0] else 0
    MEM['team']['op_angle']=(self.t,self.outpost['rotation'])
    seen = MEM.setdefault('team', {}).setdefault('seen', {})
    for e in self.targets:
      seen[e['id']] = (self.t, dict(e))
    self.sightings = [e for t, e in seen.values() if self.t-t < 8]
  def p(self, x, y):
    return (x, y) if self.team == "red" else (W - x, H - y)
  def mem(self, slot):
    return MEM.setdefault(slot, {})
  def in_zone(self, r, zone_id):
    z = self.zones[zone_id]
    if z.get("polygon"):
      return sdk.point_in_polygon(r["x"], r["y"], z["polygon"])
    return dist(pos(r), (z["x"], z["y"])) <= z["radius"]
RADIUS = {"hero": .28, "engineer": .28, "infantry": .25}

def design(r):
  return sdk.DESIGNS[str(r.get("model_slot", r["slot"]))]

def is_leg(r):
  return r.get("chassis_type") == "wheel_legged"
STAIRS = ((1, 8.51, 10.15, 5.2, (7.5, 8.6)), (-1, 19.49, 17.85, 22.8, (6.4, 6.4)))

def stair_climb(ctx, r, m, goal):
  rx, ry = ctx.p(*pos(r))
  gx, gy = ctx.p(*goal)
  h = lift(*pos(r))
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
    vref = r.get("speed_reference_mps") or 4.0
    shared = MEM.setdefault("team", {})
    busy = shared.get("stair_busy")
    # The centre lane crosses both highland cards (0.5 defence for 30 s) but runs over the fortress
    # hexagon (y 6.93-8.07): take the side lane while anyone stands in it, and always on their side.
    fort = ctx.p(6.6 if sgn > 0 else 21.4, 7.5)
    held = any(x.get("id") != r["id"] and x.get("alive", True) and dist(pos(x), fort) < 1.2 for x in list(ctx.robots.values()) + ctx.targets)
    lane = hi if held else lo
    start = ctx.p(run if floor else e1 + sgn * .3, lane)
    # Only a robot on the stairs or lined up at the start holds them, and nobody queues for more than 6 s.
    if not active and (m.get("queued") is None or ctx.t - m["queued"] > 15):
      m["queued"] = ctx.t
    if busy and busy[0] != r["slot"] and ctx.t - busy[1] < 1.0 and not active and ctx.t - m["queued"] < 6:
      mv, _ = go(ctx, r, ctx.p(run - sgn * .6, 15 - hi), slack=.3, plain=True)
      return move_cmd(mv)
    if active or dist(pos(r), start) < .5:
      shared["stair_busy"] = (r["slot"], ctx.t)
    if not active:
      err = abs(wrap(heading - r["heading"]))
      still = math.hypot(r["vx"], r["vy"]) < .15
      if dist(pos(r), start) > .12 or err > .08 or not still:
        m["settle"] = ctx.t
        if dist(pos(r), start) > .12:
          mv, _ = go(ctx, r, start, slack=.1, plain=True)
          return move_cmd(mv)
        m["moving"] = False
        return {"move": (0.0, 0.0), "heading": heading, "leg_height": .26}
      if ctx.t - m.get("settle", ctx.t) < .6:
        return {"move": (0.0, 0.0), "heading": heading, "leg_height": .26}
      st = m["stair"] = [sgn, 0 if floor else 1, ctx.t - (0 if floor else 3), lane]
      m.pop("queued", None)
    lane = st[3]
    heading = wrap(base_heading + sgn * max(-.15, min(.15, 1.2 * (lane - ry))))
    jump_cd = design(r).get("jump_cooldown_s", .8)
    phase = st[1]
    cmd = {"heading": heading, "leg_height": .26, "power": 200}
    fwd = (math.cos(heading), math.sin(heading))
    lead = max(0.0, r["vx"] * fwd[0] + r["vy"] * fwd[1]) * .07 * sgn
    age = ctx.t - st[2]
    waiting = phase == 1 and age < jump_cd + .1
    stalled = not waiting and age > 1.0 and math.hypot(r["vx"], r["vy"]) < .15 and h < .3
    failed = stalled or (phase == 1 and .5 < age < 3 and h < .1) or (phase == 2 and age > .7 and h < .3 and (rx - e2) * sgn < .2)
    if age > 9 or r.get("tipped") or failed:
      m.pop("stair", None)
      MEM.setdefault("team", {}).pop("stair_busy", None)
      return {"move": (-fwd[0] * .3, -fwd[1] * .3), "heading": heading, "leg_height": .26}
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
DECK_CHAIN = ((7.75,11.0),(7.6,12.0),(6.2,12.0),(4.7,12.2),(4.7,13.6),(10.3,13.4),(11.9,13.4),(11.9,11.35))

def deck_waypoint(ctx, r, m, goal):
  rx, ry = ctx.p(*pos(r))
  gx, gy = ctx.p(*goal)
  hr, hg = lift(*pos(r)), lift(*goal)
  on_deck = hr > .3 and 10.15 < rx < 17.9
  goal_deck = hg > .3 and 10.15 < gx < 17.9
  on_road = .12 < hr < .3 and ry > 11.3 and rx < 13.3
  enemy = [(W - x, H - y) for x, y in DECK_CHAIN]
  e_road = .12 < hr < .3 and ry < 3.7 and rx > 14.7
  goal_road=.12<hg<.3 and gy>11.3 and gx<13.3
  if goal_deck and not on_deck or goal_road and not on_deck and not on_road or not on_deck and not on_road and gx > 15.5 and rx < 12.5:
    chain = enemy if rx > 15 else DECK_CHAIN
  elif on_deck and not goal_deck and gx < 12.5 or on_road and not goal_deck and gx < 12.5 and hg < .12:
    chain = DECK_CHAIN[::-1]
  elif on_deck and not goal_deck and gx > 15.5 or e_road and not goal_deck and gx > 15.5 and gy > 3.7:
    chain = enemy[::-1]
  else:
    m.pop("deck", None)
    return None
  key = (chain[0], chain[-1])
  st = m.get("deck")
  if st is None or st[0] != key or st[1]>=len(chain):
    if on_deck and chain[0] in (DECK_CHAIN[-1], enemy[-1]):
      k = 0
    elif chain[0] == DECK_CHAIN[0] and not on_road or chain[0] == enemy[0] and not e_road:
      k = 0
    elif on_road or e_road:
      x,y=(rx,ry) if on_road else (W-rx,H-ry)
      forward=chain[0] in (DECK_CHAIN[0],enemy[0])
      k=(4 if x<5.1 and y<13.3 else 5 if x<10.6 else 6) if forward else (4 if x<5.1 else 3 if x<10.6 else 2)
    else:
      k = min(range(len(chain)), key=lambda i: dist((rx, ry), chain[i]))
    st = m["deck"] = [key, k]
  while st[1] < len(chain) and dist((rx, ry), chain[st[1]]) < .25:
    st[1] += 1
  if st[1] >= len(chain):
    return None
  return ctx.p(*chain[st[1]])

def go(ctx, r, goal, slack=.25, fast=1.0, mode=None, plain=False):
  m = ctx.mem(r["slot"])
  here = pos(r)
  goal = (min(W - .3, max(.3, goal[0])), min(H - .3, max(.3, goal[1])))
  gap = dist(here, goal)
  leg = is_leg(r)
  mode = mode or ("leg" if leg else "mec")
  if gap <= slack:
    m.pop("path", None)
    return (0.0, 0.0), True
  if leg and not plain:
    climb = stair_climb(ctx, r, m, goal)
    if climb is not None:
      if m.get("stair"):
        m["moving"] = False
      return climb, False
  if not leg and mode == "mec" and not plain:
    wp = deck_waypoint(ctx, r, m, goal)
    if wp is not None:
      mv, _ = go(ctx, r, wp, slack=.2, fast=min(fast, .85), mode=mode, plain=True)
      return mv, False
  radius = .24 if mode == "fold" else RADIUS[r["role"]]
  slope = .4
  clear = grid(ctx.team, mode, slope)
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
  if line_free(clear, here, goal, radius * .9, ledges) and (not leg or gap < 3.5):
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
  vref = r.get("speed_reference_mps") or 3.0
  speed = min(1.0, math.sqrt(2 * 1.6 * gap) / vref) * fast
  if leg and ground(target[0], target[1]) < ground(*here) - .1:
    speed = min(speed, 1.7 / vref)
  v = math.hypot(r["vx"], r["vy"])
  if v > .3:
    turn = (dx * r["vx"] + dy * r["vy"]) / (n * v)
    speed *= max(.45, (1 + turn) / 2)
  m["moving"] = speed > .25
  m["dir"] = math.atan2(dy, dx)
  if leg and r_grounded(r):
    rise=ground(here[0]+dx/n*.5,here[1]+dy/n*.5)-ground(*here)
    edge=max(STEP[cell(here[0]+dx/n*s,here[1]+dy/n*s)[0]*NY+cell(here[0]+dx/n*s,here[1]+dy/n*s)[1]] for s in (.2,.3,.4,.5,.6))
    forward=(r['vx']*dx+r['vy']*dy)/n
    if .12<rise<.30 and edge>.11 and forward>.8 and ctx.t-m.get('hop_at',-99)>design(r).get('jump_cooldown_s',.8)+.1:
      m['hop_at']=ctx.t
      return {'move':(dx/n*speed,dy/n*speed),'jump':1.0,'power':200,'leg_height':.26},False
  return (dx / n * speed, dy / n * speed), False

def r_grounded(r):
  return r.get('grounded') and not r.get('tipped')

def move_cmd(mv):
  if isinstance(mv, dict):
    return dict(mv)
  return {"move": mv}

def fly_route(ctx, r, m):
  if not is_leg(r) or m.get('fly_done'):return None
  lane=sdk.fly_slope_lane(ctx.obs['arena'],ctx.team)
  lip,crest=lane['lip'],lane['crest']
  dx,dy=crest[0]-lip[0],crest[1]-lip[1]
  length=math.hypot(dx,dy);ux,uy=dx/length,dy/length
  card=ctx.zones[ctx.team+'_fly_0']
  start=(card['x']-ux*.65,card['y']-uy*.65)
  st=m.setdefault('fly',{'phase':0,'since':ctx.t})
  if (r.get('tipped') and r.get('grounded') and not auto_right(r)) or ctx.t-st['since']>45:
    m['fly_done']=True;m.pop('fly',None);return None
  shared=MEM.setdefault('team',{});lock=shared.get('fly_busy')
  angle=math.atan2(uy,ux);leg=.22
  if st['phase']==0:
    if lift(*pos(r))>.3:
      mv,_=go(ctx,r,ctx.p(11.9,13.4),slack=.2)
      return move_cmd(mv)
    # From our floor the road is a 0.19 m ledge a 305 straddles or tips on, and its ramp end leads
    # across the bump strip (x 5.2-7.6), which it cannot climb from rest: take the stairs to the
    # highland and come down to the road by the deck east of the bumps.
    rx,ry=ctx.p(*pos(r))
    if ry<12.8 and rx<10.5:
      mv,_=go(ctx,r,ctx.p(*LEG_POSTS[1]),slack=.3)
      return move_cmd(mv)
    mv,arrived=go(ctx,r,start,slack=.15)
    if not arrived:return move_cmd(mv)
    if lock and lock[0]!=r['slot'] and ctx.t-lock[1]<1.5:
      return {'move':(0,0),'heading':angle}
    shared['fly_busy']=(r['slot'],ctx.t)
    if abs(wrap(r['heading']-angle))>.1 or math.hypot(r['vx'],r['vy'])>.2 or sum(w*w for w in r['angular_velocity'])>.36 or r['upright']<.97:
      st['settle']=ctx.t
      return {'move':(0,0),'heading':angle,'leg_height':leg}
    if ctx.t-st.setdefault('settle',ctx.t)<.4:return {'move':(0,0),'heading':angle,'leg_height':leg}
    st['phase'],st['run_at']=1,ctx.t
  shared['fly_busy']=(r['slot'],ctx.t)
  cross=(r['x']-lip[0])*(-uy)+(r['y']-lip[1])*ux
  correction=max(-.35,min(.35,-cross*1.5))
  speed=min(1,max(.05,((r['vx']*ux+r['vy']*uy)+1.1)/r['speed_reference_mps'])) if auto_right(r) else 1
  cmd={'move':((ux-uy*correction)*speed,(uy+ux*correction)*speed),'power':200,'leg_height':leg,'brake':True}
  end=ctx.zones[ctx.team+'_fly_1']
  passed=(r['x']-end['x'])*ux+(r['y']-end['y'])*uy>1
  if passed and r.get('grounded'):
    m['fly_done']=True;m.pop('fly',None);shared.pop('fly_busy',None)
  elif ctx.t-st['run_at']>12:
    m['fly_done']=True;m.pop('fly',None);shared.pop('fly_busy',None);return None
  return cmd

def hunt_goal(ctx, r, index):
  # Once their outpost has fallen the enemy fortress is defended: no flanking behind the
  # hero through it, no chasing a hero sitting in it, patrols at least 6 m away.
  active=ctx.outpost['hp']<=0
  fort=ctx.p(*ENEMY_FORT)
  heroes = [e for e in ctx.sightings if e['role']=='hero' and not (active and dist(pos(e),fort)<4)]
  if heroes:
    e = min(heroes,key=lambda e:dist(pos(r),pos(e)))
    ex,ey=ctx.p(*pos(e))
    if ex<19.7 and not active:
      return ctx.p(20.4+index*.55,min(13.8,max(1.2,ey+(.8 if index else -.8))))
    q = step_toward(pos(e),pos(r),3.2+index*.35)
    if dist(q,pos(r)) < .4:
      a = math.atan2(r['y']-e['y'],r['x']-e['x'])+(.32 if index else -.32)
      q = (e['x']+3.3*math.cos(a),e['y']+3.3*math.sin(a))
    return q
  if active:
    return ctx.p(18.3, 1.9 if (int(ctx.t/14)+index)%2 else 13.1)
  return ctx.p(20.5+1.2*index, 5.0 if (int(ctx.t/14)+index)%2 else 10.0)

def auto_right(r):
  return 'hip_angle' in r and r.get('alive') and r.get('powered',True)

def holder(ctx):
  team = MEM.setdefault('team',{})
  assigned=ctx.robots.get(team.get('holder'))
  if assigned and (assigned['alive'] or ctx.t-assigned.get('death_time',-99)<3) and assigned.get('fortress_hold',0)>8 and dist(pos(assigned),ctx.p(*ENEMY_FORT))<1.2:
    return assigned['slot']
  if assigned and not assigned['alive'] and ctx.t-assigned.get('death_time',-99)<2 and dist(pos(assigned),ctx.p(*ENEMY_FORT))<1.2:
    return assigned['slot']
  live = [r for r in ctx.robots.values() if r['role']=='infantry' and is_leg(r) and r['alive'] and not r['weak'] and not r.get('tipped')]
  old = next((r for r in live if r['slot']==team.get('holder')),None)
  if old is not None:
    return old['slot']
  if not live:
    team.pop('holder',None);return None
  fort = ctx.p(*ENEMY_FORT)
  best = min(live,key=lambda r:dist(pos(r),fort)-r.get('fortress_hold',0)*2-r['hp']/r['max_hp']*3)
  team['holder'] = best['slot']
  return best['slot']

def rescue(ctx, r, m, busy_core):
  tried = m.setdefault('tried',{})
  active = ctx.robots.get(m.get('rescue_id'))
  if active is not None:
    stable=sum(v*v for v in active.get('angular_velocity',(0,0,0)))<.64
    payable=ctx.coins>=instant_revive_cost(active,ctx.t)
    if auto_right(active) or (not active['alive'] and not payable) or (active.get('upright',1)>=.93 and stable and not r.get('rescue_contact')) or ctx.t-m['rescue_start']>32:
      tried[active['slot']] = ctx.t
      m.pop('rescue_id',None);active=None
  if active is None and not busy_core and not r.get('weak'):
    candidates = [t for t in sdk.tipped_teammates(ctx.obs) if (t['alive'] or ctx.coins>=instant_revive_cost(t,ctx.t)) and t['id']!=r['id'] and t['role']!='aerial'
      and dist(pos(r),pos(t))<15 and ctx.t-tried.get(t['slot'],-99)>12]
    if candidates and (1 in ctx.econ['completed_difficulties'] or ctx.t>35):
      active = min(candidates,key=lambda t:dist(pos(r),pos(t))-(3 if t['slot']==1 else 0))
      m['rescue_id'],m['rescue_start'] = active['slot'],ctx.t
  if active is None or busy_core:
    return None
  if not active['alive'] and dist(pos(r),pos(active))<1.1:
    ctx.state['_rescue_revive']=active['slot']
  if r.get('rescue_contact'):
    return action(move=(0,0),brake=True,rescue=active['slot'])
  goal = sdk.rescue_point(r,active,.70)
  if dist(pos(r),pos(active))>.78:
    mv,_ = go(ctx,r,goal,slack=.06,fast=.8)
    return action(**move_cmd(mv),rescue=active['slot'])
  return action(move=(0,0),brake=True,rescue=active['slot'])

def lead(r,target):
  if target.get('kind')=='outpost' and target.get('armor_plates'):
    angle=target.get('omega',0)*dist(pos(r),pos(target))/sdk.muzzle_speed(r)
    c,s=math.cos(angle),math.sin(angle);target=dict(target,armor_plates=[dict(p,center=[target['x']+c*(p['center'][0]-target['x'])-s*(p['center'][1]-target['y']),target['y']+s*(p['center'][0]-target['x'])+c*(p['center'][1]-target['y']),p['center'][2]],normal=[c*p['normal'][0]-s*p['normal'][1],s*p['normal'][0]+c*p['normal'][1],p['normal'][2]]) for p in target['armor_plates']])
  if 'vx' not in target:return target
  speed=sdk.muzzle_speed(r)
  flight=max(.01,dist(pos(r),pos(target))/speed)
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
    pitch=aim_pitch(r,point)
    d=max(.01,dist(pos(r),pos(point))-r.get('muzzle_reach_m',.3)*math.cos(pitch))
    inherited=(r.get('vx',0)*(point['x']-r['x'])+r.get('vy',0)*(point['y']-r['y']))/max(d,.01)
    drag=.009177 if r['role']=='hero' else .01994
    flight=(math.exp(drag*d)-1)/(drag*max(1,speed*math.cos(pitch)+inherited))
  return point
_SOLUTIONS = {}

def solution(r, target):
  key = (r["id"], tuple(r.get(k, 0) for k in ("x","y","z","vx","vy","vz")),
    sdk.muzzle_speed(r), tuple(r.get("quaternion", ())),
    tuple(target.get(k) for k in ("id","x","y","z","vx","vy","vz","kind","armor_open")))
  if key not in _SOLUTIONS:
    point = lead(r, target)
    _SOLUTIONS[key] = aim_at(r, point), aim_pitch(r, point), ballistic_reachable(r, point)
  return _SOLUTIONS[key]

def heat_ok(r):
  if not can_fire(r):
    return False
  if r["role"] == "hero":
    return True
  return r["heat"] + 20 <= r["max_heat"]

def structure_targets(ctx, r):
  out = []
  if ctx.outpost["hp"] > 0:
    out.append(dict(ctx.outpost, kind="outpost",omega=ctx.omega if not ctx.outpost.get('rotation_stopped') else 0))
  elif ctx.base["hp"] > 0 and (r["role"] == "hero" or ctx.base["armor_open"]):
    out.append(dict(ctx.base, kind="base"))
  return out

def choose_target(ctx, r, max_range=9.0, prefer_structures=False):
  best = None
  here = pos(r)
  for e in ctx.targets:
    d = dist(here, pos(e))
    if d > max_range:
      continue
    score = d + e["hp"] / 60.0
    if e["role"] == "hero":
      score -= 6
    if e["hp"] < 60:
      score -= 2
    if dist(pos(e), ctx.p(6.6, 7.5)) < .9:
      score -= 6
    if e["role"] == "engineer":
      score += 2
    if best is None or score < best[0]:
      best = (score, e, d)
  structures = structure_targets(ctx, r)
  if structures and (best is None or prefer_structures):
    s = structures[0]
    d = dist(here, pos(s))
    if d < (16 if r["role"] in ("hero", "aerial") else 10):
      return s, d
  return (best[1], best[2]) if best else (None, None)
_WALL_BOXES = [(o["x"]+o["w"]/2, o["y"]+o["h"]/2, o["w"]/2, o["h"]/2,
  math.cos(o.get("rotation", 0)), math.sin(o.get("rotation", 0)),
  o.get("bottom", 0), o["height"]) for o in ARENA["obstacles"]]

def barrel(r):
  yaw = r["aim"] - r["heading"]
  pitch = r["pitch"]
  v = sdk._rotate(r["quaternion"], (math.cos(yaw)*math.cos(pitch), math.sin(yaw)*math.cos(pitch), math.sin(pitch)))
  return math.atan2(v[1], v[0]), math.atan2(v[2], math.hypot(v[0], v[1]))

def clear_shot(ctx, r, target, yaw, pitch, distance_):
  key = (r["id"], pos(r), r["z"], target.get("id"), pos(target), target.get("z"), yaw, pitch, distance_)
  cache = getattr(ctx, "shot_cache", None)
  if cache is None:
    cache = ctx.shot_cache = {}
  if key not in cache:
    cache[key] = _clear_shot(ctx, r, target, yaw, pitch, distance_)
  return cache[key]

def _clear_shot(ctx, r, target, yaw, pitch, distance_):
  speed = sdk.muzzle_speed(r)
  direction = (math.cos(yaw)*math.cos(pitch), math.sin(yaw)*math.cos(pitch), math.sin(pitch))
  pivot = sdk._rotate(r["quaternion"], (0, 0, r["muzzle_height_m"]))
  reach = r["muzzle_reach_m"]
  x, y, z = [r[k]+pivot[i]+direction[i]*reach for i,k in enumerate(("x","y","z"))]
  vx, vy, vz = [direction[i]*speed+r[k] for i,k in enumerate(("vx","vy","vz"))]
  drag = .009177 if r["role"] == "hero" else .019941
  step = .025
  until = max(0, distance_ - target.get("radius", .25) - .2)
  origin = (r["x"], r["y"])
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
      if friend["id"] != r["id"] and friend["role"] != "aerial" and friend["z"] < z < friend["z"]+.55 and (x-friend["x"])**2+(y-friend["y"])**2 < .25**2:
        return False
  return False

def shoot(ctx, r, target, d, fire_ok=True):
  if target is None:
    return {}
  if busy(ctx,.075):
    return {'aim':aim_at(r,target),'pitch':barrel(r)[1],'fire':False}
  yaw, pitch, reach = solution(r, target)
  actual_yaw, actual_pitch = barrel(r)
  yaw_tolerance = max(.012, min(.05, .07/max(d,.5)))
  pitch_tolerance = max(.006, min(.04, .05/max(d,.5)))
  fire = (fire_ok and not target.get('invulnerable') and reach and heat_ok(r) and abs(wrap(actual_yaw-yaw))<yaw_tolerance
    and abs(actual_pitch-pitch)<pitch_tolerance and not busy(ctx, .09) and clear_shot(ctx, r, target, yaw, pitch, d))
  return {"aim": yaw, "pitch": pitch, "fire": fire}

def buy(ctx, r, rounds, remote=False):
  kind = 42 if r["role"] == "hero" else 17
  cap = (60 if ctx.t<230 else 100) if kind == 42 else 1000
  bought = ctx.econ["purchased_42" if kind == 42 else "purchased_17"]
  batch = (10 if remote else 1) if kind == 42 else (100 if remote else 10)
  unit = 150 if remote else 10
  rounds = min(rounds, cap - bought - ctx.state.get("_bought%d" % kind, 0))
  rounds -= rounds % batch
  afford = int(max(0,ctx.coins-ctx.reserve) // unit) * batch
  rounds = min(rounds, afford)
  if rounds <= 0:
    return None
  cost = rounds // batch * unit
  ctx.coins -= cost
  ctx.state["_bought%d" % kind] = ctx.state.get("_bought%d" % kind, 0) + rounds
  return {"amount": rounds, "remote": remote}

def at_local_shop(ctx, r):
  if r.get("weak"):
    return False
  for zid in (ctx.team + "_base", ctx.team + "_supply"):
    if ctx.in_zone(r, zid):
      return True
  return ctx.my_outpost["hp"] > 0 and ctx.in_zone(r, ctx.team + "_outpost")

def disengaged(ctx, r):
  return ctx.t - r["last_shot_time"] >= 6.05 and ctx.t - r["last_damage_time"] >= 6.05

def revive_or_wait(ctx, r, priority):
  cost = instant_revive_cost(r, ctx.t)
  wait = r["respawn_required"] - r["respawn_progress"]
  reserve = {0: 0, 1: 120, 2: 250}[priority]
  if r['role']=='infantry':
    if dist(pos(r),ctx.p(*ENEMY_FORT))<6 and r.get('fortress_hold',0)<10 and nest(ctx):
      return action()
    reserve=0 if ctx.p(*pos(r))[0]>14 or ctx.state.get('_rescue_revive')==r['slot'] else min(reserve,100)
  if r.get('fortress_hold',0)<=8:reserve+=ctx.reserve
  timely = wait > 6 or (r['role']=='hero' and not r.get('tipped') and ctx.coins>=cost+100)
  window = any(c - 4 <= ctx.t < c + 55 for c in (180, 255, 330))
  if r["role"] == "hero" and window and ctx.coins >= cost and ctx.t < 410:
    ctx.coins -= cost
    return action(revive=True)
  if timely and ctx.t < 410 and ctx.coins - cost >= reserve:
    ctx.coins -= cost
    return action(revive=True)
  return action()
HERO_SPOT = (13.8, 2.8)
# Once the enemy outpost falls the hero snipes the base from low ground that neither their fortress
# nor their highland can see (their defenders otherwise kill it at HERO_SPOT): the pocket is 16 m
# from our supply zone, the south-road corridor 7 m down the ramp from HERO_SPOT (35 m to the pocket).
SNIPE_SPOTS = ((12.65, 1.65), (13.75, 1.7))

def buffed(ctx):
  rune = ctx.obs["runes"][ctx.team]
  return rune["status"] == "active" and (rune["attack"] >= 1.5 or rune["cooling"] >= 2)
PUSH_T = 215.0

def push_ok(ctx, r):
  if ctx.base["hp"] <= 0 or ctx.outpost["hp"] > 0 :
    return False
  escort = [x for x in ctx.robots.values() if x["role"] == "infantry" and x["alive"] and not x.get("weak")
    and dist(pos(x), pos(ctx.base)) < 9]
  late = ctx.obs.get('remaining',420-ctx.t)<95
  ready=ctx.t>=240 and 3 in ctx.econ['completed_difficulties'] and r['hp']>r['max_hp']*.65
  # With their armour closed a push never landed a hit in self-play and cost 3-4 hero deaths, while the
  # snipe spot keeps scoring base hits from 14 m: push only into an open base.
  return bool(ctx.t>=PUSH_T and ctx.base['armor_open'] and (escort or late or ready)
    and r['hp']>r['max_hp']*(.2 if late else .35) and (r['ammo']>=3 or ctx.coins>=150))

def hero_push(ctx, r, m, ops):
  bx, by = ctx.base["x"], ctx.base["y"]
  spots = [p for p in base_spots(ctx) if .4<bx+(p[0]-bx)*1.7<W-.4] or [(bx-2.1,by)]
  s=m.setdefault('face',min(spots,key=lambda q:dist(pos(r),q)+4*max(0,7-dist((bx+(q[0]-bx)*1.7,by+(q[1]-by)*1.7),ctx.p(*ENEMY_FORT)))))
  goal = (bx + (s[0] - bx) * 1.7, by + (s[1] - by) * 1.7)
  flight = fly_route(ctx,r,m) if ctx.base['armor_open'] and is_leg(r) else None
  if not is_leg(r) and not m.get('departed'):
    rx,ry=ctx.p(*pos(r))
    if lift(*pos(r))>.3 and 10.15<rx<17.9:
      m['departed']=True
    else:
      goal=ctx.p(12.5,5.3)
  mv, _ = go(ctx,r,goal,slack=.35) if flight is None else (flight,False)
  near = [e for e in ctx.targets if dist(pos(r), pos(e)) < 4.5]
  if ctx.outpost['hp']>0:
    target=dict(ctx.outpost,kind='outpost')
  elif near and (dist(pos(r),pos(ctx.base))>5 or r['hp']<r['max_hp']*.3):
    target = min(near, key=lambda e: dist(pos(r), pos(e)))
  else:
    target = dict(ctx.base, kind="base")
  if r["ammo"] < 12 and not r["pending_ammo"] and ctx.coins >= 150 and disengaged(ctx, r):
    order = buy(ctx, r, 20 if ctx.coins>=450 else 10, remote=True)
    if order:
      ops["buy_ammo"] = order
  ready_fire=dist(pos(r),pos(ctx.base))<5 or (r['hp']<r['max_hp']*.3 and near)
  return action(**move_cmd(mv), deploy=False, **shoot(ctx, r, target, dist(pos(r), pos(target)),fire_ok=ready_fire and flight is None and not r.get('deployed')), **ops)

def hero(ctx, r):
  m = ctx.mem(1)
  if ctx.tick == 0:
    return action(profile="ranged")
  if not r["alive"]:
    m.pop("snipe", None)
    return revive_or_wait(ctx, r, 2)
  ops = {}
  if r["weak"]:
    m["recover"] = True
  if m.get("recover"):
    if r["hp"] >= r["max_hp"] * .85:
      m.pop("recover", None)
      m.pop("wp", None)
      m.pop('departed',None)
    else:
      m.pop("snipe", None)
      mv, _ = go(ctx, r, ctx.p(1.7, 12.1), slack=.3)
      return action(move=mv, deploy=False)
  if ctx.outpost["hp"] > 0:
    spot = ctx.p(*HERO_SPOT)
  else:
    m.setdefault("snipe", 1 if ground(*pos(r)) > .3 else 0)
    spot = ctx.p(*SNIPE_SPOTS[m["snipe"]])
  if r["hp"] < r["max_hp"] * .6 and r["pending_heal"] is None and ctx.coins >= remote_heal_cost(ctx.t) + 50 + ctx.reserve:
    if disengaged(ctx, r):
      ctx.coins -= remote_heal_cost(ctx.t)
      ops["remote_heal"] = True
  if r["ammo"] == 0 and not r["deployed"] and at_local_shop(ctx, r) and ctx.t >= 1:
    order = buy(ctx, r, 20)
    if order:
      return action(buy_ammo=order)
  if ctx.t<1:return action(deploy=False)
  if r["ammo"] <= 3 and r["deployed"] and not r["pending_ammo"] and ctx.coins >= 150 and ctx.econ["purchased_42"] < 100:
    if not disengaged(ctx, r):
      return action(deploy=True, fire=False)
    order = buy(ctx, r, 30 if ctx.coins > 750 else 20 if ctx.coins > 450 else 10, remote=True)
    if order:
      ops["buy_ammo"] = order
  if m.get("push") or push_ok(ctx, r):
    m["push"] = True
    return hero_push(ctx, r, m, ops)
  if r['deployed'] and dist(pos(r),spot)>.45:
    mv,_=go(ctx,r,spot,slack=.2)
    target,d=choose_target(ctx,r,16)
    return action(**move_cmd(mv),deploy=False,**shoot(ctx,r,target,d,fire_ok=False),**ops)
  if r["ammo"] == 0 and not r["deployed"] and r["deploy_at"] is None:
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
  if targets and ballistic_reachable(r, targets[0]):
    target = targets[0]
  if threat and (target is None or ctx.outpost["hp"] > 0):
    target = min(threat, key=lambda e: dist(pos(r), pos(e)))
  raiders = [e for e in ctx.targets if dist(pos(e), ctx.p(6.6, 7.5)) < .9]
  if raiders and ctx.my_outpost["hp"] <= 0:
    target = min(raiders, key=lambda e: e["hp"])
  d = dist(pos(r), pos(target)) if target else 0
  reserve = target and target.get('kind')=='base' and not ctx.base['armor_open'] and ctx.econ['purchased_42']>=80 and r['ammo']<=8 and not buffed(ctx) and ctx.t<290
  return action(deploy=True, **shoot(ctx,r,target,d,fire_ok=not reserve), **ops)

def engineer(ctx, r):
  m = ctx.mem(2)
  if not r["alive"]:
    return revive_or_wait(ctx, r, 1)
  if r.get('weak'):
    m['recover']=True;m.pop('rescue_id',None)
  if m.get('recover'):
    if not r.get('weak') and r['hp']>=r['max_hp']*.8:
      m.pop('recover',None)
    else:
      zone=ctx.zones[ctx.team+'_supply']
      mv,_=go(ctx,r,(zone['x'],zone['y']),slack=.25)
      return action(**move_cmd(mv))
  team = ctx.team
  core = ctx.obs["assemblies"][team]
  done = ctx.econ["completed_difficulties"]
  busy = core["stage"] in ("moving", "inserting", "buffered")
  resource = ctx.zones[team + "_resource"]
  assembly = ctx.zones[team + "_assembly"]
  outpost_zone = ctx.zones[team + "_outpost"]
  start4 = max(180.0, core["retry_at"])
  can4 = 4 not in done and 3 in done and not core["permanent_lock"]
  l4_window = can4 and start4 - 30 <= ctx.t < start4 + 45
  saving = rescue(ctx,r,m,busy)
  if saving is not None:
    return saving
  rebuild_ok = (3 in done and ctx.t < 168) or 4 in done or (3 in done and ctx.t >= 235)
  if (not busy and ctx.my_outpost["hp"] <= 0 and ctx.econ["rebuild_credits"] > 0 and ctx.t < 299
    and not r.get("weak") and rebuild_ok and not l4_window):
    mv, arrived = go(ctx, r, (outpost_zone["x"], outpost_zone["y"] + (-.7 if team == "red" else .7)), slack=.2)
    return action(move=mv)
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
  nxt = level + 1
  if level < 3 and nxt not in done and (nxt - 1) * 60 - ctx.t < 12 and level in done:
    level = nxt
  rx, ry = ctx.p(*pos(r))
  if dist(pos(r), (assembly["x"], assembly["y"])) > .9 and ry > 7.2 and rx < 13.2 and lift(*pos(r)) > .3:
    mv, arrived = go(ctx, r, ctx.p(12.15, 6.55), slack=.3)
    arrived = False
  else:
    mv, arrived = go(ctx, r, sdk.assembly_work_point(r, ctx.obs["arena"]), slack=.06)
  ops = dict(assembly_insert=True, assembly_translate=True, assembly_rotate=core["target_rotation"], assembly_confirm=True)
  if not busy:
    if prep4 and not ready4:
      pass
    elif level == 4:
      if not (enemy_busy and enemy_core.get("difficulty") != 4 and ctx.t < start4 + 12):
        ops["assembly"] = 4
    elif ctx.t >= (level - 1) * 60:
      ops["assembly"] = level
  return action(move=mv, brake=arrived, **ops)

def aerial(ctx, r):
  m = ctx.mem(6)
  rune = ctx.obs['runes'][ctx.team]
  chance = rune_open(ctx) is not None and ctx.t>=m.get('rune_retry',0)
  serving = rune['status']=='activating' or rune_soon(ctx) or chance
  if serving and rune['status']=='idle':
    since = m.setdefault('rune_visit',ctx.t)
    if ctx.t-since>18 and not rune_soon(ctx):
      m['rune_retry']=ctx.t+16;m.pop('rune_visit',None);serving=False
  elif rune['status']!='idle':
    m.pop('rune_visit',None)
  keep = (r['support_time']>0 or ctx.coins>40+ctx.reserve) and r['ammo']>0
  if not keep:
    return action(support=False)
  if serving:
    hover = ctx.p(*RUNE_HOVER)
    mv = (max(-1,min(1,(hover[0]-r['x'])*.3-r['vx']*.4)),max(-1,min(1,(hover[1]-r['y'])*.3-r['vy']*.4)))
    shot = rune_shot(ctx,r,rune,m) if rune['status']=='activating' and not busy(ctx,.075) else {}
    return action(move=mv,support=True,altitude=2.08,**shot)
  m.pop('plan',None)
  target,d = choose_target(ctx,r,17,prefer_structures=ctx.outpost['hp']>0)
  ground_targets = [e for e in ctx.targets if e['role']!='aerial' and dist(pos(r),pos(e))<17]
  if ctx.outpost['hp']<=0 and ground_targets:
    target = min(ground_targets,key=lambda e:dist(pos(r),pos(e))+e['hp']/100-(5 if e['role']=='hero' else 0))
    d = dist(pos(r),pos(target))
  if ctx.outpost['hp']<=0 and ctx.base['armor_open'] and (ctx.base['hp']<1800 or not ground_targets):
    target = dict(ctx.base,kind='base');d=dist(pos(r),pos(target))
  spot = ctx.p(*( (13.9,2.4) if ctx.outpost['hp']>0 else (13.7,3.45)))
  if target and target.get('kind') is None:
    ex,ey = ctx.p(*pos(target))
    x = min(13.7,max(.6,ex-7.2))
    spot = ctx.p(x,min(3.45,max(.5,ey)))
  lane = ctx.obs['arena']['flight_lanes'][ctx.team]
  spot = (min(lane['max_x']-.2,max(lane['min_x']+.2,spot[0])),spot[1])
  mv = (max(-1,min(1,(spot[0]-r['x'])*.3-r['vx']*.4)),max(-1,min(1,(spot[1]-r['y'])*.3-r['vy']*.4)))
  hold = r['ammo']<=rune_reserve(ctx)+6
  cadence = target is not None and target.get('kind')=='outpost' or ctx.t-r.get('last_shot_time',-99) >= (.32 if d is not None and d<9 else .5)
  return action(move=mv,support=True,altitude=2.08,**shoot(ctx,r,target,d,fire_ok=not hold and cadence))
RUNE_HOVER = (12.4, 3.9)
RUNE_CHANCES = ((0, "small"), (90, "small"), (180, "large"), (255, "large"), (330, "large"))
R_DT, R_SUB = 0.05, 1 / 120
R_TIME_BIAS, R_YAW_BIAS, R_PITCH_BIAS = .045, 0.0, 0.0
R_AWAY, R_TOL = .45, .004
M_K, M_RHO, M_A_SMALL, M_BLEND_S, M_SMALL_MEAN, M_LARGE_AT = .28, .6180339887498948, .32, 3.0, math.pi / 3, 180.0

class RuneMotor:
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
    rows = self.samples[::max(1, math.ceil(n / 24))]
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
  rune = ctx.obs["runes"][ctx.team]
  if rune["status"] == "activating":
    return rune["mode"]
  if rune["large_chances"] > 0 and RUNE_MOTOR.ok(ctx.t):
    return "large"
  if rune["small_chances"] > 0 and ctx.t < 172 and RUNE_MOTOR.ok(ctx.t) and (ctx.outpost["hp"] <= 0 or ctx.t >= 40):
    return "small"
  return None

def rune_soon(ctx):
  return any(0 <= c - ctx.t <= 9 and RUNE_MOTOR.ok(ctx.t) for c, kind in RUNE_CHANCES if kind == "large" or c > 0)

def rune_reserve(ctx):
  rune = ctx.obs["runes"][ctx.team]
  large = rune["large_chances"] + sum(1 for c in (180, 255, 330) if c > ctx.t)
  small = rune["small_chances"] + (1 if ctx.t < 90 else 0) if ctx.t < 172 else 0
  return 26 * large + 14 * small

def rune_ready(ctx, air):
  return (air is not None and RUNE_MOTOR.ok(ctx.t) and air["support_active"] and air["ammo"] >= 20
    and dist(pos(air), ctx.p(*RUNE_HOVER)) < .12 and math.hypot(air["vx"], air["vy"]) < .08
    and air["heat"] + 40 <= air["max_heat"])

def rune_start_ok(ctx):
  rune = ctx.obs["runes"][ctx.team]
  return (ctx.t > 3 and rune["status"] == "idle" and rune_open(ctx) is not None and rune_ready(ctx, ctx.robots.get(6)))
LEG_POSTS = ((11.3, 6.7), (11.3, 8.3))
ENEMY_FORT = (21.4, 7.5)
TUNNEL_N, TUNNEL_S = (9.39, 13.5), (9.39, 11.9)
GUARD_POST = (7.6, 5.6)

def base_spots(ctx):
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
  return ctx.t >= 180 and ctx.outpost["hp"] <= 0 and not ctx.base["armor_open"] and ctx.base["hp"] > 0

def infantry_common(ctx, r, m, ops):
  if auto_right(r):
    if r.get('self_righting') or (r.get('tipped') and math.hypot(r['vx'],r['vy'])<.7 and abs(r['vz'])<.5):
      m['righting_at']=ctx.t;m.pop('stair',None)
    if ctx.t-m.get('righting_at',-99)<.5:
      return action(move=(0,0),brake=True,fire=False)
  if r["ammo"] < 40 and at_local_shop(ctx, r) and ctx.t >= 1:
    order = buy(ctx, r, 100 if ctx.coins > 400 else 50)
    if order:
      ops["buy_ammo"] = order
  elif not r["pending_ammo"] and disengaged(ctx, r):
    key=r["ammo"]<15 or 140<=ctx.t<185 or ctx.base["armor_open"]
    if r["ammo"]<(60 if key else 40) and ctx.coins>=150+ctx.reserve+(0 if key else 150):
      order = buy(ctx, r, 100, remote=True)
      if order:
        ops["buy_ammo"] = order
  if (r["hp"] < r["max_hp"] * .45 and disengaged(ctx, r) and r["pending_heal"] is None
    and ctx.coins > remote_heal_cost(ctx.t) + 100 + ctx.reserve):
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
      if (r["weak"] and zone and ctx.outpost["hp"] <= 0 and ctx.my_outpost["hp"] > 0 and ctx.t < 297 and ctx.p(*pos(r))[0] > 14
        and dist(pos(r), (zone["x"], zone["y"])) < dist(pos(r), home)):
        zx, zy = ctx.p(zone["x"], zone["y"])
        home = ctx.p(zx - .5, zy + .5)
      mv, _ = go(ctx, r, home)
      return action(**move_cmd(mv), **ops)
  return None

def ammo_left(r):
  return r['ammo']+sum(a for _,a in r.get('pending_ammo') or ())

def foes(ctx,q,rad):
  return [e for e in ctx.targets if e['role']!='engineer' and dist(pos(e),q)<rad]

def power(rs):
  return sum(x['hp']/max(1,x['max_hp'])*(1.6 if x['role']=='hero' else 1) for x in rs)

def guard_slot(ctx):
  if 'guard' not in ctx.__dict__:
    h=ctx.robots.get(1);ctx.guard=None;ctx.near_hero=[]
    if h and h['alive']:
      ctx.near_hero=sorted(foes(ctx,pos(h),6.5),key=lambda e:dist(pos(e),pos(h)))
      c=[x for x in ctx.robots.values() if x['role']=='infantry' and x['alive'] and not x['weak'] and ammo_left(x)>=20
        and x['hp']>x['max_hp']*.38 and dist(pos(x),pos(h))<12 and ctx.p(*pos(x))[0]<16 and not ctx.mem(x['slot']).get('holding') and not ctx.mem(x['slot']).get('fly')]
      if ctx.near_hero and c:ctx.guard=min(c,key=lambda x:dist(pos(x),pos(h)))['slot']
  return ctx.guard

def nest(ctx):
  # After their outpost falls the enemy fortress gives defenders 50% defence and reserve
  # ammo while attackers inside take double damage: keep out while a defender is around, or for a
  # minute after one of ours fell there (its killers often stand outside the hexagon or fly).
  if ctx.outpost['hp']>0:
    return False
  fort=ctx.p(*ENEMY_FORT)
  team=MEM.setdefault('team',{})
  for x in ctx.robots.values():
    if not x['alive'] and x['role']=='infantry' and dist(pos(x),fort)<4:
      team['fort_loss']=max(team.get('fort_loss',-99),x.get('death_time',ctx.t))
  if ctx.t-team.get('fort_loss',-99)<60:
    return True
  seen=team.get('seen',{})
  return any(ctx.t-t<40 and e['role'] in ('infantry','hero') and dist(pos(e),fort)<3 for t,e in seen.values())

def prey(ctx,r):
  if ammo_left(r)<30 or r['hp']<r['max_hp']*.5:return None
  fort=ctx.p(*ENEMY_FORT);guarded=nest(ctx)
  c=[e for e in ctx.targets if e['role']=='hero' and dist(pos(e),pos(r))<10 and not (guarded and dist(pos(e),fort)<9.5)]
  if not c:return None
  e=min(c,key=lambda e:dist(pos(e),pos(r)))
  ours=[x for x in ctx.robots.values() if x['alive'] and x['role'] in('hero','infantry') and dist(pos(x),pos(e))<8]
  return e if e.get('deployed') or e['hp']<e['max_hp']*.5 or power(ours)>=power(foes(ctx,pos(e),5)) else None

def tactics(ctx,r,m,ops,target,d):
  if ctx.t<20 or m.get('fly') or m.get('stair') or m.get('deck'):return None
  here=pos(r)
  have=ammo_left(r)+ops.get('buy_ammo',{}).get('amount',0);low=have<(12 if ctx.base['armor_open'] else 25);hurt=r['hp']<r['max_hp']*.38
  if (low or hurt) and not m.get('holding') and r.get('fortress_hold',0)<=6:
    near=foes(ctx,here,8)
    broke=low and not r['pending_ammo'] and ctx.coins<150+ctx.reserve and not ops.get('buy_ammo') or hurt and r['pending_heal'] is None and ctx.coins<remote_heal_cost(ctx.t)+ctx.reserve
    mv,_=go(ctx,r,ctx.p(1.6,11.8+(r['slot']-3)*.2) if broke else ctx.p(*LEG_POSTS[r['slot']%2]) if near or ctx.p(*here)[0]>12 else here,slack=.3)
    close=[e for e in near if dist(here,pos(e))<3.2]
    t=min(close,key=lambda e:dist(here,pos(e))) if close else target
    return action(**move_cmd(mv),**shoot(ctx,r,t,dist(here,pos(t)) if t else 0,fire_ok=bool(close)),**ops)
  if guard_slot(ctx)==r['slot']:
    e,h=ctx.near_hero[0],ctx.robots[1];k=min(1,1.6/max(.1,dist(pos(e),pos(h))))
    mv,_=go(ctx,r,(h['x']+(e['x']-h['x'])*k,h['y']+(e['y']-h['y'])*k),slack=.3)
    return action(**move_cmd(mv),**shoot(ctx,r,e,dist(here,pos(e))),**ops)
  e=None if fortress_open(ctx) and holder(ctx)==r['slot'] else prey(ctx,r)
  if e:
    mv,_=go(ctx,r,step_toward(pos(e),here,3.0),slack=.3)
    return action(**move_cmd(mv),**shoot(ctx,r,e,dist(here,pos(e))),**ops)
  return None

def leg_infantry(ctx, r, m, ops, index):
  here = pos(r)
  target,d = choose_target(ctx,r,11)
  tac=tactics(ctx,r,m,ops,target,d)
  m['holding']=False
  if tac:return tac
  if index==1 and r.get('fortress_hold',0)<8 and ctx.my_base['armor_open'] and any(dist(pos(e),pos(ctx.my_base))<8 for e in ctx.targets):
    mv,_=go(ctx,r,ctx.p(7.5,7.2),slack=.2)
    return action(**move_cmd(mv),**shoot(ctx,r,target,d),**ops)
  if r['ammo']==0 and not ops.get('buy_ammo') and ctx.t<5:
    mv,_ = go(ctx,r,ctx.p(3.3,7.5))
    return action(**move_cmd(mv),**ops)
  if ctx.base['armor_open'] and ctx.base['hp']>0 and ctx.outpost['hp']<=0:
    spots=base_spots(ctx)
    goal=spots[index%len(spots)] if spots else pos(ctx.base)
    base=dict(ctx.base,kind='base');bd=dist(here,pos(base))
    if bd<9:
      target,d=base,bd
    mv,_=go(ctx,r,goal,slack=.25)
    return action(**move_cmd(mv),**shoot(ctx,r,target,d),**ops)
  guarded=nest(ctx)
  if fortress_open(ctx) and not guarded:
    fort=ctx.p(*ENEMY_FORT)
    primary=holder(ctx)
    keeper=ctx.robots.get(primary,{})
    backup=not any(e['role']=='hero' for e in ctx.targets) or keeper.get('fortress_hold',0)>10
    if primary==r['slot'] or backup:
      goal=(fort[0]+(-.26 if index==0 else .26)+(.12*math.sin(ctx.t*4) if dist(here,fort)<.6 else 0),fort[1]+(-.16 if index==0 else .16))
      mv,_=go(ctx,r,goal,slack=.07)
      m['holding']=dist(here,fort)<.6
      return action(**move_cmd(mv),**shoot(ctx,r,target,d),**ops)
    goal=hunt_goal(ctx,r,index) if any(e['role']=='hero' for e in ctx.sightings) else ctx.p(20.6,5+index*4)
    mv,_=go(ctx,r,goal,slack=.35)
    return action(**move_cmd(mv),**shoot(ctx,r,target,d),**ops)
  if ctx.outpost['hp']<=0 and 158<=ctx.t<180 and not guarded:
    mv,_=go(ctx,r,ctx.p(20.8,6+index*3),slack=.3)
    return action(**move_cmd(mv),**shoot(ctx,r,target,d),**ops)
  other=ctx.robots.get(3,{})
  if index==1 and ctx.t>90 and (not other.get('alive',True) or other.get('tipped') and not auto_right(other)):m['raid']=True
  raider=index==0 or m.get('raid',False)
  if index==1 and not raider and ctx.t<158:
    goal=ctx.p(14.4+.35*math.sin(ctx.t*.35),8.0+.3*math.cos(ctx.t*.35))
    if ctx.my_outpost['hp']<=0 and any(dist(pos(e),ctx.p(6.6,7.5))<2.5 for e in ctx.targets):
      goal=ctx.p(7.5,7.2)
    mv,_=go(ctx,r,goal,slack=.18)
    return action(**move_cmd(mv),**shoot(ctx,r,target,d),**ops)
  if raider and ctx.t>=60:
    if ctx.t<150:
      flight=fly_route(ctx,r,m)
      if flight is not None:
        return action(**flight,**shoot(ctx,r,target,d,fire_ok=False),**ops)
    goal=hunt_goal(ctx,r,index)
    if guarded and dist(goal,ctx.p(*ENEMY_FORT))<9.5:
      goal=ctx.p(*LEG_POSTS[index%2])
  else:
    goal=ctx.p(*LEG_POSTS[index%2])
  mv,_=go(ctx,r,goal,slack=.3)
  return action(**move_cmd(mv),**shoot(ctx,r,target,d),**ops)

def tunnel_infantry(ctx, r, m, ops):
  here = pos(r)
  target, d = choose_target(ctx, r)
  st = m.get("tun", 0)
  if r["ammo"] == 0 and not ops.get("buy_ammo") and ctx.t < 5:
    mv, _ = go(ctx, r, ctx.p(3.3, 8.6))
    return action(**move_cmd(mv), **ops)
  if st < 3 and (ctx.t > 70 or ctx.t - m.get("tun_t0", ctx.t) > 40):
    st = m["tun"] = 3
  m.setdefault("tun_t0", ctx.t)
  north, south = ctx.p(*TUNNEL_N), ctx.p(*TUNNEL_S)
  folded = r.get("transform_progress", 0) >= .999
  if st == 0:
    mv, arrived = go(ctx, r, north, slack=.12)
    if arrived:
      st = m["tun"] = 1
    return action(**move_cmd(mv), transform=False, **shoot(ctx, r, target, d), **ops)
  if st == 1:
    if not folded:
      return action(move=(0, 0), transform=True, **ops)
    mv=(max(-.3,min(.3,(south[0]-r['x'])*1.5)),max(-.8,min(.8,(south[1]-r['y'])*1.2)))
    if dist(here,south)<.08 or ctx.p(*here)[1]<TUNNEL_S[1]+.08:
      st = m["tun"] = 3
    return action(**move_cmd(mv), transform=True, **ops)
  if r.get("transform_progress", 0) > 0:
    rx, ry = ctx.p(*here)
    if abs(rx - 9.39) < .55 and 12.0 < ry < 13.3:
      mv, _ = go(ctx, r, min((north,south),key=lambda q:dist(here,q)), slack=.1, mode="fold")
      return action(**move_cmd(mv), transform=True, **ops)
    return action(move=(0, 0), transform=False, **ops)
  tac=tactics(ctx,r,m,ops,target,d)
  if tac:return tac
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
      and dist(pos(r), ctx.p(*ENEMY_FORT)) < 1.3 and r.get("fortress_hold", 0) >= 10 and ctx.coins >= instant_revive_cost(r, ctx.t)):
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

def evade(ctx, r, command):
  hit_recently = ctx.t - r.get("last_damage_time", -99) < 1.2
  threatened=hit_recently or any(e['role']=='hero' and dist(pos(e),pos(r))<9 for e in ctx.targets)
  if not threatened or r.get("tipped") or r.get("deployed") or r["role"] == "engineer":
    return
  if ctx.t-ctx.mem(r['slot']).get('righting_at',-99)<.5:return
  if ctx.mem(r['slot']).get('deck') or BUMPS[cell(r['x'],r['y'])[0]*NY+cell(r['x'],r['y'])[1]]:return
  if ctx.mem(r['slot']).get('holding') or ctx.mem(r['slot']).get('fly') or ctx.mem(r['slot']).get('stair'):
    return
  if r['role']=='hero' and ctx.mem(1).get('push') and dist(pos(r),pos(ctx.base))<6:return
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
  for r in sorted(obs["robots"], key=lambda r: r["slot"]):
    slot = str(r["slot"])
    if slot not in obs["controlled_ids"]:
      continue
    if busy(ctx,.11):
      actions[slot]=action(**ctx.mem(r['slot']).get('last_command',{}))
      continue
    try:
      actions[slot] = ROLES[r["role"]](ctx, r)
    except Exception as error:
      print("error", slot, repr(error))
      actions[slot] = action()
  starter = state.get("_starter")
  if starter is not None and str(starter) in actions and rune_start_ok(ctx):
    actions[str(starter)]["rune_start"] = True
  for r in obs["robots"]:
    slot = str(r["slot"])
    if slot not in actions or not r["alive"]:
      continue
    command = actions[slot]
    if r["role"] == "aerial":
      continue
    if command.get('aim') is None and r['role']!='engineer':
      facing = math.atan2(command.get('move',[0,0])[1],command.get('move',[0,0])[0]) if math.hypot(*command.get('move',[0,0]))>.1 else (0 if ctx.team=='red' else math.pi)
      command['aim']=wrap(facing+ctx.t*.9+r['slot']*1.5)
      command['pitch']=.03
    try:
      evade(ctx, r, command)
    except Exception as error:
      print("evade", slot, repr(error))
    saving=ctx.robots.get(2,{})
    attached=saving.get('rescue_contact') and saving.get('rescue_target') in (r['id'],r['slot'],str(r['slot']))
    assigned=ctx.mem(2).get('rescue_id')==r['slot'] and saving and dist(pos(saving),pos(r))<1.1
    if (r.get("tipped") and not is_leg(r)) or attached or assigned:
      command["move"] = [0, 0]
      command["brake"] = True
      command.pop('jump',None)
      command['fire']=False
    if is_leg(r):
      mv = command.get("move", [0, 0])
      flight=ctx.mem(r['slot']).get('fly',{}).get('phase')==1
      if not flight and "heading" not in command and math.hypot(*mv) > .01:
        angle = math.atan2(mv[1], mv[0])
        delta = wrap(angle - r["heading"])
        if abs(delta) > math.pi / 2:
          angle += math.pi
          delta = wrap(angle - r["heading"])
        command["heading"] = angle
        scale = max(.15, math.cos(delta) ** 2)
        command["move"] = [v * scale for v in mv]
      command.setdefault("leg_height", design(r)["leg_nominal_m"])
      command["brake"] = True
    if (math.hypot(*command.get("move", [0, 0])) > .3 and r.get("supercap_energy_j", 0) > 450
      and not r.get("tipped") and "power" not in command and not BUMPS[cell(r["x"],r["y"])[0]*NY+cell(r["x"],r["y"])[1]]):
      command["power"] = min(160, r["power_limit"] + 60)
  for k in [k for k in state if k.startswith("_")]:
    state.pop(k)
  for slot,command in actions.items():
    ctx.mem(int(slot))['last_command']={k:v for k,v in command.items() if k in ('move','aim','pitch','heading','deploy','support','altitude','transform','leg_height','brake','rescue') and v is not None}
  return actions, state
