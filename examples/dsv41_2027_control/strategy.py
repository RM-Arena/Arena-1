"""DeepSeek V4.1 Flash Max RMUC 2027 controller.

A control-position controller for the 2027 ruleset. Everything is read from the
documented observation: no hidden state, no network, no threads.

Strategic layer
    * Control degree only grows while one team holds *both* outpost positions, and a
      position is active while any of its two buff cards carries a robot. A single
      parked robot therefore keeps a whole position, which is why anchors hold cards
      instead of chasing firefights.
    * The two cards of a position are a strip on the central highland plus the outpost
      card below it, so one robot standing where the cards meet denies the position to
      the enemy and keeps it for the team at the same time.
    * A base is immune while its owner fully holds its own outpost position, so
      breaking the enemy anchor is the prerequisite for every structure kill.

STYLE selects the tactical variant; the mechanism layer underneath is identical.
"""
import math
from sdk import (action, aim_at, assembly_work_point, ballistic_reachable, can_fire,
                 drones, instant_revive_cost, navigate, rescue_point, resource_pickup_point,
                 terrain_height, tipped_teammates, workbench_point, zone_center,
                 muzzle_speed, point_in_polygon, _aim_target, _prepare_chapter4, _rotate)

STYLE = "chain"

STEP_ORDER = ("positioning", "inserting", "lifting", "flipping", "rotating", "verifying", "complete")

# ---- Card geometry, written for the red end; blue is the 180-degree image --------
# The outpost cards are real buff-card outlines; the central cards are the long
# diagonal strips on the highland. A "seam" stand sits where the two cards of one
# position meet, so one chassis activates both.
OUTPOST_CARDS = {
    "red_outpost": ((11.43, 12.00), ((10.35, 10.38), (11.18, 10.38), (11.95, 12.30), (11.00, 12.30), (10.35, 11.30))),
    "blue_outpost": ((16.57, 3.00), ((17.65, 4.62), (16.82, 4.62), (16.05, 2.70), (17.00, 2.70), (17.65, 3.70))),
}
# Verified interior points of the two long strips (they are only 0.8 m wide, so the
# stand has to sit on the centre line rather than on a naive card centre).
CENTRAL_STAND = {"red_central": (10.90, 7.00), "blue_central": (17.10, 8.00)}
# Where the outpost card and the central strip come closest: one chassis here keeps
# both cards active, which is the cheapest possible hold on a position.
SEAM_STAND = {"red_outpost": (11.35, 12.01), "blue_outpost": (16.65, 2.99)}
# A second, offset stand on the same outpost card: the pedestal occupies the card
# centre, so a partner parks uphill of it instead of stacking on the seam.
PARTNER_STAND = {"red_outpost": (11.05, 11.70), "blue_outpost": (16.95, 3.30)}

def wrap(angle):
    return (angle + math.pi) % math.tau - math.pi


def distance(robot, point):
    return math.hypot(robot['x'] - point[0], robot['y'] - point[1])


def other(team):
    return 'blue' if team == 'red' else 'red'


def mirror(point, team):
    return point if team == 'red' else (28.0 - point[0], 15.0 - point[1])


def card_polygon(name, team):
    polygon = OUTPOST_CARDS[name][1] if name in OUTPOST_CARDS else None
    return polygon if team == 'red' or polygon is None else [(28.0 - x, 15.0 - y) for x, y in polygon]


def on_card(name, point, team):
    polygon = card_polygon(name, team)
    return True if polygon is None else point_in_polygon(point[0], point[1], polygon)


def post(name, team, variant=0):
    """A stand for `name`: 0 the seam (`bedrock`) where both of its cards meet, which is
    the cheapest possible hold; 1 the outpost card beside its pedestal; 2 the central
    strip; 3 a partner stand on the same outpost card, clear of the pedestal."""
    if variant == 3 and name in PARTNER_STAND:
        return mirror(PARTNER_STAND[name], team)
    if variant == 2 and name in CENTRAL_STAND:
        return mirror(CENTRAL_STAND[name], team)
    if variant == 1 and name in OUTPOST_CARDS:
        return mirror(OUTPOST_CARDS[name][0], team)
    if name in SEAM_STAND:
        return mirror(SEAM_STAND[name], team)
    return mirror(OUTPOST_CARDS[name][0] if name in OUTPOST_CARDS else CENTRAL_STAND[name], team)


def holds(name, point, team):
    """Does a chassis at `point` keep the position of card `name` active?"""
    mate = name.replace('_central', '_outpost') if name.endswith('_central') else name.replace('_outpost', '_central')
    return on_card(name, point, team) or on_card(mate, point, team)


# ---- Movement ------------------------------------------------------------------

def unstick(robot, move, memory, now):
    """A chassis that pushes on without moving or turning for 1.5 s backs off at an
    angle for 0.7 s, keeping its heading: a chassis cannot yaw on road bumps."""
    m = memory.setdefault(str(robot['slot']), {'trail': [], 'tries': 0})
    if now < m.get('until', -1):
        return {'move': m['escape'], 'heading': m['heading']}
    trail = m['trail']
    if math.hypot(*move) < .01:
        trail.clear()
        return {'move': move}
    trail.append([now, robot['x'], robot['y'], robot['heading']])
    while now - trail[0][0] > 1.5:
        trail.pop(0)
    turned = abs(wrap(robot['heading'] - trail[0][3]))
    if now - trail[0][0] < 1.4 or distance(robot, trail[0][1:3]) > .1 or turned > .15:
        return {'move': move}
    m['tries'] += 1
    angle = math.atan2(move[1], move[0]) + math.pi + (.9 if (robot['slot'] + m['tries']) % 2 else -.9)
    m.update(escape=[.7 * math.cos(angle), .7 * math.sin(angle)], until=now + .7, heading=robot['heading'])
    trail.clear()
    return {'move': m['escape'], 'heading': m['heading']}


def straight(robot, goal, pace=1.0):
    dx, dy = goal[0] - robot['x'], goal[1] - robot['y']
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return (0.0, 0.0)
    speed = pace * min(1.0, length * 2 / max(.5, robot.get('speed_reference_mps', 3.0)))
    return (dx / length * speed, dy / length * speed)


def heading_move(robot, point, pace=1.0):
    """Point the chassis at a waypoint and drive: on open ground a straight run is
    faster than weaving between kerb ends, and the bump guard still overrides it."""
    course = math.atan2(point[1] - robot['y'], point[0] - robot['x'])
    heading = course
    if abs(wrap(course + math.pi - robot['heading'])) < abs(wrap(course - robot['heading'])):
        heading = course + math.pi
    error = abs(wrap(heading - robot['heading']))
    speed = pace * max(.10, math.cos(min(error, math.pi / 2)) ** 2)
    return {'move': (math.cos(course) * speed, math.sin(course) * speed), 'heading': heading, 'brake': True}


def drive(robot, goal, obs, memory, tolerance=.30, pace=1.0):
    """Steer to `goal`: ask the public router for a heading, fall back to the direct
    course when it reports nothing, and after three seconds without closing the distance
    push straight at the goal, because a kerb or a hump band needs a full command."""
    if goal is None or distance(robot, goal) <= tolerance:
        return {'move': (0, 0), 'brake': True}
    gap = distance(robot, goal)
    trace = memory.setdefault('gap', {}).setdefault(str(robot['slot']), {})
    if gap < trace.get('best', 1e9) - .35:
        trace.update(best=gap, since=obs['time'], force=0)
    patience = obs['time'] - trace.get('since', obs['time']) > 3.0
    move = straight(robot, goal, pace)
    if not patience:
        heading = first_step(robot, goal, obs)
        if math.hypot(*heading) > .3:
            move = heading
    elif trace.get('force', 0) < 8:
        trace['force'] = trace.get('force', 0) + 1
        move = straight(robot, goal, 1.0)
    fields = unstick(robot, move, memory, obs['time'])
    if math.hypot(robot['vx'], robot['vy']) < .35 and math.hypot(*fields['move']) > .2:
        fields['power'] = 200
    return fields


def straight(robot, goal, pace=1.0):
    dx, dy = goal[0] - robot['x'], goal[1] - robot['y']
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return (0.0, 0.0)
    speed = pace * min(1.0, length * 2 / max(.5, robot.get('speed_reference_mps', 3.0)))
    return (dx / length * speed, dy / length * speed)


def first_step(robot, goal, obs):
    """The heading to drive on this decision.

    The SDK router solves the field - it publishes a waypoint graph and the clearance
    test that decides whether a leg is drivable - but `navigate` returns a zero vector
    both when no route exists and when the next waypoint is barely a metre away, so a
    caller cannot tell "go straight" from "I give up". This repeats the same public
    search and then hands the leg to the caller one waypoint at a time, nearest first.
    """
    arena = obs['arena']
    if arena.get('layout_revision') is None:
        return navigate(robot, goal, arena)
    graph = _build_graph(arena, robot['team'])
    if graph is None:
        return navigate(robot, goal, arena)
    nodes, edges, clear, inside = graph
    start, target = (robot['x'], robot['y']), tuple(goal)
    # Obstacles the goal overlaps never block reaching it, and a robot pushed inside an
    # obstacle's inflated margin may leave or pass it but not close in on it. These are
    # the router's own two escape hatches, reused here.
    near_goal = inside(target)
    guarded = inside(start, True)
    for strict in (True, False):
        for near_start in ((guarded, set(guarded)) if guarded else (guarded,)):
            ignore = {**near_start, **dict.fromkeys(near_goal)} if isinstance(near_start, dict) \
                else set(near_start) | near_goal
            if clear(start, target, ignore, strict):
                return straight(robot, goal, 1.0)
            picked = _route_step(graph, start, target, ignore, strict)
            if picked is not None:
                return straight(robot, picked, 1.0)
    return navigate(robot, goal, arena)


def _route_step(graph, start, goal, ignore, strict):
    """The next waypoint to steer for, nearest visible one first, preferring waypoints
    that still have a route to the goal. The router's own `_route` walks candidates in
    increasing start-plus-cost order; that picks a waypoint the robot has already passed
    when a cost tie makes an earlier one cheaper, and the chassis then turns around and
    oscillates. Ordering by distance instead keeps the robot moving forward, which on
    this field is what gets it off a kerb or through a tunnel mouth."""
    import heapq
    nodes, edges, clear = graph[:3]
    key = (id(graph), (round(goal[0], 1), round(goal[1], 1)), frozenset(ignore), strict)
    costs = _ROUTE_CACHE.get(key)
    if costs is None:
        costs = {i: math.dist(node, goal) for i, node in enumerate(nodes) if clear(node, goal, ignore, strict)}
        queue = [(cost, index) for index, cost in costs.items()]
        heapq.heapify(queue)
        while queue:
            cost, index = heapq.heappop(queue)
            if cost != costs[index]:
                continue
            for other, length in edges[index]:
                if cost + length < costs.get(other, float('inf')):
                    costs[other] = cost + length
                    heapq.heappush(queue, (cost + length, other))
        if len(_ROUTE_CACHE) >= 96:
            _ROUTE_CACHE.pop(next(iter(_ROUTE_CACHE)))
        _ROUTE_CACHE[key] = costs
    visible = [(math.dist(start, node), index) for index, node in enumerate(nodes) if clear(start, node, ignore, strict)]
    visible.sort()
    for _, index in visible:
        if index in costs:
            return nodes[index]
    # No waypoint with a route is visible: head for the nearest one anyway, which is how
    # a robot boxed in behind a plinth or a tunnel mouth gets out.
    for _, index in visible:
        return nodes[index]
    return None


def _build_graph(arena, team):
    """Waypoints, drivable links, the clearance test and the inflated-footprint test,
    built once per team per match from public arena data and cached."""
    key = (id(arena), team)
    if key in _GRAPH_CACHE:
        return _GRAPH_CACHE[key]
    try:
        graph = _prepare_chapter4(arena, team)
    except Exception:
        graph = None
    if len(_GRAPH_CACHE) >= 4:
        _GRAPH_CACHE.pop(next(iter(_GRAPH_CACHE)))
    _GRAPH_CACHE[key] = graph
    return graph


_GRAPH_CACHE = {}
_ROUTE_CACHE = {}


def rise_ahead(robot, obs, lookahead=.55):
    """Height difference just in front of the bumper: a kerb lip needs a hop, and the
    public terrain datum is the only height source a strategy has."""
    dx, dy = math.cos(robot['heading']), math.sin(robot['heading'])
    here = terrain_height(obs['arena'], robot['x'], robot['y'])
    return terrain_height(obs['arena'], robot['x'] + dx * lookahead, robot['y'] + dy * lookahead) - here


# Kerb access points: (x, y, heading) from which a jumping chassis hops the 0.2-0.4 m
# kerb between the low deck and the central highland, written for red and mirrored for
# blue. Every ramp that reaches 0.3 m lies inside the highland already, so a lineup with
# no jumping chassis cannot stand on a central strip at all.
KERBS = {
    "red": ((9.45, 12.60, 0.0), (9.45, 11.00, 0.0), (9.60, 9.20, 0.0), (9.70, 7.20, 0.0), (10.40, 4.20, 0.0)),
}
KERBS['blue'] = tuple((28.0 - x, 15.0 - y, math.pi) for x, y, _h in KERBS['red'])


def can_jump(robot, obs):
    """Only a model whose public design has jumping legs may hop; a mecanum chassis
    that tries is what tips over next to a kerb."""
    model = obs.get('robot_models', {}).get(str(robot.get('model_slot'))) or {}
    return bool(model.get('capabilities', {}).get('jump'))


def hop(robot, ctx, fields):
    """Jump a kerb lip. Only a healthy, moving chassis hops: a tipped robot that cannot
    self-right costs more than a late anchor, and the heavy robot's rescue trip costs it
    the whole technical opening."""
    memory = ctx.state.setdefault('jump', {}).setdefault(str(robot['slot']), {'last': -10.})
    if not can_jump(robot, ctx.obs) or robot.get('tipped') or robot.get('weak'):
        return False
    if robot['hp'] < robot['max_hp'] * .7 or ctx.time < 2.0 or not robot.get('grounded', True):
        return False
    if ctx.time - memory.get('last', -10.) < 1.4:
        return False
    fields.update(jump=1.0, power=180, leg_height=.22)
    memory['last'] = ctx.time
    return True


def climb(robot, ctx, fields):
    """Drive a kerb access point, square up on it and hop onto the highland. Runs before
    the ordinary router because a deadlock in front of a kerb never clears by itself."""
    if not can_jump(robot, ctx.obs) or robot.get('tipped') or robot.get('weak'):
        return None
    if robot['hp'] < robot['max_hp'] * .7 or not robot.get('grounded', True):
        return None
    memory = ctx.state.setdefault('climb', {}).setdefault(str(robot['slot']), {})
    if memory.get('done') and ctx.time - memory.get('at', -99) > 25:
        memory.pop('done', None)
    if memory.get('done'):
        return None
    approach = min(KERBS[ctx.team], key=lambda k: distance(robot, (k[0], k[1])))
    gap = distance(robot, approach[:2])
    if gap < 1.6 and memory.get('at') is None:
        memory['at'] = ctx.time
    if memory.get('at') is None:
        return None
    if ctx.time - memory['at'] > 7.0:
        memory['done'] = True
        memory.pop('at', None)
        return None
    if gap > .5:
        step = drive(robot, approach[:2], ctx.obs, ctx.memory, .26)
        step['heading'] = approach[2]
        return step
    fields['move'] = (math.cos(approach[2]) * .95, math.sin(approach[2]) * .95)
    fields['heading'] = approach[2]
    fields['brake'] = True
    hop(robot, ctx, fields)
    return fields


def route(robot, ctx, job, goal, tolerance=.45, pace=1.0):
    """Close on the goal. A kerb climb is attempted only after five seconds without
    closing the distance, because a card that can be reached by driving would otherwise
    be traded for a detour to the nearest kerb access point."""
    memory = ctx.state.setdefault('lane', {}).setdefault(str(robot['slot']), {})
    gap = distance(robot, goal)
    if gap < memory.get('best_goal', 1e9) - .3:
        memory.update(best_goal=gap, since_goal=ctx.time)
    if ctx.time - memory.get('since_goal', ctx.time) > 5.0 and can_jump(robot, ctx.obs):
        step = climb(robot, ctx, {})
        if step is not None:
            return step
    fields = drive(robot, goal, ctx.obs, ctx.memory, tolerance, pace)
    rise = rise_ahead(robot, ctx.obs)
    if .13 <= rise <= .5 and memory.get('rise_since') is None:
        memory['rise_since'] = ctx.time
    elif not .13 <= rise <= .5:
        memory.pop('rise_since', None)
    if memory.get('rise_since') is not None and ctx.time - memory['rise_since'] > 1.2:
        hop(robot, ctx, fields)
    return fields


def face(robot, point, memory=None):
    if memory is not None and memory.get('facing') is not None:
        return memory['facing']
    course = math.atan2(point[1] - robot['y'], point[0] - robot['x'])
    if abs(wrap(course + math.pi - robot['heading'])) < abs(wrap(course - robot['heading'])):
        course += math.pi
    if memory is not None:
        memory['facing'] = course
    return course


# ---- Targeting -----------------------------------------------------------------

class Context:
    """Facts every role reads in one decision, plus the tracked structure spin."""

    def __init__(self, obs, state):
        self.obs, self.state = obs, state
        self.team = obs['team']
        self.enemy = other(self.team)
        self.arena = obs['arena']
        self.time = obs['time']
        self.remaining = obs.get('remaining', 420 - obs['time'])
        self.economy = obs['teams'][self.team]
        self.rival = obs['teams'][self.enemy]
        self.coins = self.economy['resources']
        self.positions = obs.get('positions', {})
        self.memory = state.setdefault('stuck', {})
        self.rotation = state.setdefault('spin', {})
        self.lead = self.economy.get('control', 0) - self.rival.get('control', 0)
        self.spin = {}
        for site, outpost in obs['outposts'].items():
            previous = self.rotation.get(site)
            self.spin[site] = 0.0 if outpost.get('rotation_stopped') or not previous else \
                wrap(outpost['rotation'] - previous[1]) / max(.001, self.time - previous[0])
            self.rotation[site] = [self.time, outpost['rotation']]
        self.holders = {}
        for mate in obs['robots']:
            for zone in mate.get('last_raw_zones', []):
                self.holders.setdefault(zone, []).append(mate['slot'])

    def zone(self, team, kind):
        return zone_center(self.arena, f'{team}_{kind}')

    def position(self, name):
        return self.positions.get(name) or {}

    def controls(self, name, team=None, full=False):
        p = self.position(name)
        return p.get('controller') == (team or self.team) and (not full or p.get('control') == 'full')

    def progress(self, name):
        """Capture progress on this position; at 5 s the holder loses it."""
        return float(self.position(name).get('progress') or 0.0)

    def occupied(self, name, exclude=None):
        return [slot for slot in self.holders.get(name, []) if slot != exclude]

    def enemy_base_vulnerable(self):
        return not self.controls(f'{self.enemy}_outpost', self.enemy, full=True) \
            and self.obs['bases'][self.enemy]['hp'] > 0

    def hostile_outpost(self):
        """The outpost worth shooting: the enemy's, or ours once they rebuilt it."""
        for site in (self.enemy, self.team):
            o = self.obs['outposts'][site]
            if o['hp'] > 0 and o.get('owner', site) != self.team:
                return dict(o, kind='outpost', site=site)
        return None

    def enemy_holds_own(self):
        return self.controls(f'{self.enemy}_outpost', self.enemy, full=True)

    def losing_home(self):
        """The home position is not fully ours, or is being taken right now."""
        if not self.controls(f'{self.team}_outpost', full=True):
            return True
        return self.progress(f'{self.team}_outpost') > .6


def structure_target(robot, ctx):
    """Prefer the outpost; the base only once its outpost position is broken."""
    outpost = ctx.hostile_outpost()
    if outpost:
        flight = max(0., distance(robot, (outpost['x'], outpost['y'])) - .3) / max(1., muzzle_speed(robot) * .86)
        turn = ctx.spin.get(outpost['site'], 0.0) * (flight + .12)
        c, s = math.cos(turn), math.sin(turn)
        plates = []
        for p in outpost.get('armor_plates', []):
            dx, dy = p['center'][0] - outpost['x'], p['center'][1] - outpost['y']
            nx, ny = p['normal'][:2]
            x, y = outpost['x'] + dx * c - dy * s, outpost['y'] + dx * s + dy * c
            normal = (nx * c - ny * s, nx * s + ny * c)
            facing = (robot['x'] - x) * normal[0] + (robot['y'] - y) * normal[1]
            plates.append((facing, {'x': x, 'y': y, 'aim_z': p['center'][2]}))
        target = max(plates, key=lambda pair: pair[0])[1] if plates else outpost
        if ballistic_reachable(robot, target):
            return target
    if ctx.enemy_base_vulnerable():
        base = dict(ctx.obs['bases'][ctx.enemy], kind='base')
        if ballistic_reachable(robot, base):
            return base
    return None


def enemy_target(robot, ctx, reach):
    """Focus the cheapest kill: low health, no defensive buff, already close."""
    candidates = []
    for e in ctx.obs['enemies']:
        if not e['alive'] or not e.get('targetable', True) or e.get('invulnerable'):
            continue
        gap = distance(robot, (e['x'], e['y']))
        if gap > reach:
            continue
        score = e['hp'] * (1 + e.get('defense_buff', 0)) + gap * 22
        if e['role'] == 'sentry':
            score -= 60
        if e['role'] == 'heavy' and e.get('launcher') not in ('fitted', 'installed'):
            score += 220
        if e.get('weak'):
            score -= 40
        candidates.append((score, e))
    for _, target in sorted(candidates, key=lambda pair: pair[0])[:3]:
        if ballistic_reachable(robot, target):
            return target
    return None


def drone_target(robot, ctx, reach=3.0):
    best = None
    for d in ctx.obs.get('enemy_drones', []):
        if d['state'] != 'flying' or math.hypot(d['vx'], d['vy']) > 2.5:
            continue
        gap = distance(robot, (d['x'], d['y']))
        if gap <= reach and (best is None or gap < best[0]):
            best = (gap, {'x': d['x'], 'y': d['y'], 'z': d['z'], 'aim_z': d['z']})
    return best[1] if best else None


def barrel_angles(robot):
    """Observation gimbal angles are body-relative; commands are world angles."""
    yaw, pitch = robot['aim'] - robot['heading'], robot.get('pitch', 0)
    v = _rotate(robot.get('quaternion', (0, 0, 0, 1)),
                (math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), math.sin(pitch)))
    return math.atan2(v[1], v[0]), math.atan2(v[2], math.hypot(v[0], v[1]))


def firing_solution(robot, target):
    """Flight time, drag and inherited chassis velocity solved together."""
    point = _aim_target(robot, target)
    speed = muzzle_speed(robot)
    mass, radius = (.0445, .02125) if robot['role'] == 'heavy' else (.0032, .0084)
    drag = .5 * 1.225 * .47 * math.pi * radius * radius / mass
    pivot = _rotate(robot.get('quaternion', (0, 0, 0, 1)), (0, 0, robot.get('muzzle_height_m', .45)))
    ox, oy, oz = robot['x'] + pivot[0], robot['y'] + pivot[1], robot.get('z', 0) + pivot[2]
    reach = robot.get('muzzle_reach_m', .22)
    flight = math.hypot(point[0] - ox, point[1] - oy) / speed
    yaw, pitch = 0., 0.
    for _ in range(2):
        lead = flight + .025
        tx = point[0] + target.get('vx', 0) * lead
        ty = point[1] + target.get('vy', 0) * lead
        tz = point[2] + target.get('vz', 0) * lead
        dx, dy = tx - ox, ty - oy
        gap = max(.05, math.hypot(dx, dy))
        ux, uy = dx / gap, dy / gap
        along = robot.get('vx', 0) * ux + robot.get('vy', 0) * uy
        across = -robot.get('vx', 0) * uy + robot.get('vy', 0) * ux

        def trajectory(angle):
            horizontal = speed * math.cos(angle)
            if horizontal <= abs(across):
                return -100., 0.
            vx = math.sqrt(horizontal * horizontal - across * across) + along
            vz = speed * math.sin(angle) + robot.get('vz', 0)
            x, z, elapsed = reach * math.cos(angle), oz + reach * math.sin(angle), 0.
            dt = 1 / 120
            for _ in range(420):
                velocity = math.hypot(vx, vz)
                ax, az = -drag * velocity * vx, -9.81 - drag * velocity * vz
                xn, zn = x + vx * dt + .5 * ax * dt * dt, z + vz * dt + .5 * az * dt * dt
                if xn >= gap:
                    fraction = (gap - x) / max(1e-8, xn - x)
                    return z + (zn - z) * fraction, elapsed + dt * fraction
                x, z, elapsed = xn, zn, elapsed + dt
                vx, vz = vx + ax * dt, vz + az * dt
                if vx <= 0 or z < oz - 8:
                    break
            return -100., elapsed

        low, high = -math.pi / 12, math.pi / 4
        if trajectory(high)[0] < tz:
            return None
        for _ in range(11):
            middle = (low + high) / 2
            if trajectory(middle)[0] < tz:
                low = middle
            else:
                high = middle
        pitch = (low + high) / 2
        _, flight = trajectory(pitch)
        yaw = math.atan2(dy, dx) - math.asin(max(-.99, min(.99, across / (speed * math.cos(pitch)))))
    return yaw, pitch


def heat_room(robot):
    """The engine refuses a shot only above max_heat + 100; the SDK is stricter and
    stops at max_heat. Fire while a two-round margin survives, or for a kill shot."""
    shot = 100 if robot['role'] == 'heavy' else 10
    return robot['heat'] + 2 * shot <= robot['max_heat'] + (0 if robot['role'] == 'heavy' else 10)


def weapon(robot, ctx, reach=9.0, structures=True, drones_too=True):
    """aim/pitch/fire fields: robots first, then drones, then structures."""
    target = enemy_target(robot, ctx, reach)
    if target is None and drones_too and robot['role'] != 'heavy':
        target = drone_target(robot, ctx)
    if target is None and structures:
        target = structure_target(robot, ctx)
    if target is None:
        front = ctx.zone(ctx.enemy, 'central')
        return {'aim': math.atan2(front[1] - robot['y'], front[0] - robot['x']) + .5 * math.sin(ctx.time * .8),
                'fire': False}
    solution = firing_solution(robot, target)
    if solution is None:
        return {'aim': aim_at(robot, target), 'fire': False}
    aim, pitch = solution
    cone = max(.012, min(.035, .065 / max(1., distance(robot, (target['x'], target['y'])))))
    actual_aim, actual_pitch = barrel_angles(robot)
    aligned = abs(wrap(aim - actual_aim)) < cone and abs(pitch - actual_pitch) < .025
    lethal = target.get('hp', 400) <= (200 if robot['role'] == 'heavy' else 20)
    fire = aligned and can_fire(robot) and (heat_room(robot) or lethal)
    return {'aim': aim, 'pitch': pitch, 'fire': fire}


# ---- Logistics -----------------------------------------------------------------

def can_buy_here(robot, ctx):
    """Local exchange on own shop cards or a fully controlled outpost; contact lasts 2 s."""
    contacts = set(robot.get('last_raw_zones', []))
    contacts.update(zone for zone, last in robot.get('zone_contacts', {}).items() if ctx.time - last <= 2)
    if any(f'{ctx.team}_{kind}' in contacts for kind in ('base', 'supply', 'high_point')):
        return True
    if any(f'{owner}_outpost' in contacts and ctx.controls(f'{owner}_outpost', full=True)
           for owner in (ctx.team, ctx.enemy)):
        return True
    for kind in ('base', 'supply', 'high_point'):
        if distance(robot, ctx.zone(ctx.team, kind)) < (1.6 if kind == 'base' else 1.0):
            return True
    for owner in (ctx.team, ctx.enemy):
        if ctx.controls(f'{owner}_outpost', full=True) and distance(robot, ctx.zone(owner, 'outpost')) < .85:
            return True
    return False


def disengaged(robot, now):
    return now - max(robot.get('last_shot_time', -99), robot.get('last_damage_time', -99)) >= 6.2


def at_home_shop(robot, ctx):
    return any(zone in set(robot.get('last_raw_zones', [])) for zone in
               (f'{ctx.team}_base', f'{ctx.team}_supply', f'{ctx.team}_high_point')) \
        or distance(robot, ctx.zone(ctx.team, 'base')) < 1.6


def ammo_fields(robot, ctx, low, local_amount, remote_amount, reserve, preload=0):
    """Buy locally when an exchange is reachable, remotely once disengaged. The heavy
    robot's 42 mm share is capped at 100 rounds for the whole match, so its reserve
    stays high. `preload` fills an empty magazine before the first push."""
    if robot['ammo'] >= (preload if ctx.time < 25 else low) or ctx.time < .6 or robot.get('pending_ammo'):
        return {}
    unit = 10 if robot['role'] == 'heavy' else 1
    if can_buy_here(robot, ctx) and ctx.coins >= local_amount * unit + reserve:
        return {'buy_ammo': {'amount': local_amount, 'remote': False}}
    if disengaged(robot, ctx.time) and ctx.coins >= 150 + reserve:
        return {'buy_ammo': {'amount': remote_amount, 'remote': True}}
    return {}


def revive_fields(robot, ctx, reserve=150):
    cost = instant_revive_cost(robot, ctx.time)
    return {'revive': ctx.time < 335 and ctx.coins >= cost + reserve}


def recovery_goal(robot, ctx, low=.30, high=.82):
    """Latch a withdrawal until healed. A fully controlled outpost card heals like the
    supply zone and keeps the position active while doing it."""
    memory = ctx.state.setdefault('recovery', {})
    key = str(robot['slot'])
    if robot['weak'] or robot['hp'] < robot['max_hp'] * low:
        memory[key] = True
    if robot['hp'] >= robot['max_hp'] * high and not robot['weak']:
        memory.pop(key, None)
    if not memory.get(key):
        return None
    occupied = set(robot.get('last_raw_zones', []))
    if f'{ctx.team}_supply' in occupied or any(f'{owner}_outpost' in occupied and
                                               ctx.controls(f'{owner}_outpost', full=True)
                                               for owner in (ctx.team, ctx.enemy)):
        return (robot['x'], robot['y'])
    goals = [ctx.zone(ctx.team, 'supply'), post(f'{ctx.team}_outpost', ctx.team, 1)]
    for owner in (ctx.team, ctx.enemy):
        if ctx.controls(f'{owner}_outpost', full=True):
            goals.append(post(f'{owner}_outpost', ctx.team, 1))
    return min(goals, key=lambda p: distance(robot, p))


# ---- Anchors -------------------------------------------------------------------

def anchor(robot, ctx, job, stand, gun_reach=9.0, tolerant=.55, structures=True):
    """Hold one buff card: walk the approach lane, then stay on `stand` under brake and
    shoot from it. Standing still on the card is what keeps the position active and what
    drains an enemy hold, so an anchor never leaves the card for a firefight."""
    memory = ctx.state.setdefault('anchor', {}).setdefault(str(robot['slot']), {})
    gap = distance(robot, stand)
    fields = {}
    if gap > tolerant:
        fields.update(route(robot, ctx, job, stand, tolerance=min(.45, max(.14, gap * .35))))
    else:
        fields['move'] = (0, 0)
        fields['brake'] = True
        fields['heading'] = face(robot, ctx.zone(ctx.enemy, 'central'), memory)
    if gun_reach > 0:
        fields.update(weapon(robot, ctx, reach=gun_reach, structures=structures))
    memory['on_post'] = gap <= tolerant + .3
    return fields, memory['on_post']


def home_stand(ctx):
    return post(f'{ctx.team}_outpost', ctx.team, 0)


def away_stand(ctx):
    """The seam unless a teammate already sits on it, otherwise the partner stand: the
    two forward anchors then cover both corners of the enemy card instead of stacking."""
    if ctx.holders.get(f'{ctx.enemy}_outpost'):
        return post(f'{ctx.enemy}_outpost', ctx.team, 3)
    return post(f'{ctx.enemy}_outpost', ctx.team, 0)


def home_covered(ctx):
    return ctx.controls(f'{ctx.team}_outpost', full=True) and not ctx.losing_home()


# ---- Heavy robot ---------------------------------------------------------------

UNLOCK = {1: 0, 2: 60, 3: 120, 4: 180}


def heavy(robot, ctx):
    """The heavy robot has no gun until level 3, so its opening buys the only things it
    can buy without one: levels 1-3, which raise team income and unlock the launcher, and
    then the modular 42 mm itself, which makes it the team's only structure gun. It steps
    onto the home card only when that position is actually being taken, because the
    infantry own that job and a detour costs the whole technical opening."""
    core = ctx.obs['assemblies'][ctx.team]
    busy = core['stage'] in ('moving', 'inserting') or robot.get('carried_units', 0) > 0 \
        or robot.get('launcher') in ('unlocked', 'installing')
    if ctx.losing_home() and not busy:
        fields, _ = anchor(robot, ctx, 'home', home_stand(ctx), gun_reach=0, tolerant=.6)
        return fields
    return heavy_works(robot, ctx, ctx.state.setdefault('heavy', {}))


def heavy_works(robot, ctx, memory):
    obs, team = ctx.obs, ctx.team
    done = ctx.economy.get('completed_difficulties', [])
    core = obs['assemblies'][team]
    active = core['stage'] in ('moving', 'inserting')
    work = assembly_work_point(robot, ctx.arena)
    if robot['weak']:
        return drive(robot, ctx.zone(team, 'supply'), obs, ctx.memory)
    launcher = robot.get('launcher', 'locked')
    if active and distance(robot, work) < 1.2:
        return assemble(robot, ctx, core, work)
    # 2027 has no engineer: this arm is the only rescue on the field. Each attempt
    # gets 25 s and a wedged robot is retried once its 75 s record expires.
    attempts = memory.setdefault('rescue', {})
    for key, started in list(attempts.items()):
        if ctx.time - started > 75:
            del attempts[key]
    tipped = [t for t in tipped_teammates(obs)
              if (1 in done or ctx.time > 60) and t['role'] != 'aerial' and t['slot'] != robot['slot']
              and distance(robot, (t['x'], t['y'])) < 12 and ctx.time - attempts.get(t['id'], ctx.time) < 25]
    if tipped and launcher != 'installing':
        target = min(tipped, key=lambda t: distance(robot, (t['x'], t['y'])))
        attempts.setdefault(target['id'], ctx.time)
        far = distance(robot, (target['x'], target['y'])) > .8
        fields = drive(robot, rescue_point(robot, target), obs, ctx.memory, .1) if far \
            else {'move': (0, 0), 'brake': True}
        fields['rescue'] = target['slot']
        return fields
    if launcher in ('unlocked', 'installing'):
        bench = workbench_point(robot, ctx.arena)
        if distance(robot, bench) <= .25:
            fields = {'move': (0, 0), 'brake': True, 'install_launcher': True}
            fields.update(ammo_fields(robot, ctx, 8, 20, 10, 100))
            return fields
        return drive(robot, bench, obs, ctx.memory, .2)
    armed = launcher in ('fitted', 'installed')
    # Level 4 buys 50 % structure defense for the rest of the match, worth two trips
    # only while there is time to finish it.
    want_four = armed and 4 not in done and not memory.get('l4_tried') and ctx.time < 285
    if want_four and robot['carried_units'] < 2 and ctx.economy.get('energy_units_left', 0) > 0 \
            and distance(robot, resource_pickup_point(robot, ctx.arena)) < 3:
        return pick(robot, ctx)
    if want_four and robot['carried_units'] >= 2:
        return start_assembly(robot, ctx, 4, core, work, memory)
    if armed:
        return heavy_combat(robot, ctx)
    wanted = next((d for d in (1, 2, 3) if d not in done), None)
    if wanted is None:
        return heavy_combat(robot, ctx)
    units_left = ctx.economy.get('energy_units_left', 0)
    if robot['carried_units'] == 0 or (robot['carried_units'] < 2 and units_left > 0
                                       and distance(robot, resource_pickup_point(robot, ctx.arena)) < 1.0):
        if units_left <= 0 and robot['carried_units'] == 0:
            return heavy_combat(robot, ctx)
        return pick(robot, ctx)
    return start_assembly(robot, ctx, wanted, core, work, memory)


def pick(robot, ctx):
    """Collect one energy unit. The engine grants a unit only after a four-phase arm
    sequence that lasts about 0.85 s and cancels the moment the chassis leaves the
    resource zone, so the robot parks on the approach point and keeps the request set
    for the whole sequence: a drifting chassis never finishes a grip."""
    goal = resource_pickup_point(robot, ctx.arena)
    station = next(f for f in ctx.arena['field_geometry']['fixtures']
                   if f['kind'] == 'resource' and f['team'] == ctx.team)
    gap = distance(robot, goal)
    heading = math.atan2(station['pick_dir'][1], station['pick_dir'][0])
    # The gripper reaches about 0.85 m from the chassis centre, so the chassis has to be
    # within about 0.25 m of the approach point before the arm can close on the unit.
    # Approach at a walk and park there: a grip cancels the moment the chassis moves.
    if gap <= .22:
        return {'move': (0, 0), 'brake': True, 'pick_unit': True, 'heading': heading}
    fields = drive(robot, goal, ctx.obs, ctx.memory, .18, pace=.45)
    fields['pick_unit'] = gap < .8
    fields['heading'] = heading
    return fields


def dock_heading(ctx):
    origin = ctx.arena['assembly_frames'][ctx.team]['origin']
    plinth = zone_center(ctx.arena, ctx.team + '_assembly')
    return math.atan2(origin[1] - plinth[1], origin[0] - plinth[0])


def start_assembly(robot, ctx, level, core, work, memory):
    gap = distance(robot, work)
    if gap > .16:
        fields = drive(robot, work, ctx.obs, ctx.memory, .1)
        move = fields['move']
        pace = math.hypot(*move)
        # Keep enough pace up the plinth bevel; a creeping approach stalls on it.
        if gap < 1 and 0 < pace < .25:
            fields['move'] = (move[0] / pace * .25, move[1] / pace * .25)
        return fields
    fields = {'move': (0, 0), 'brake': True, 'heading': dock_heading(ctx)}
    if ctx.time + 1e-6 >= UNLOCK[level] and core['stage'] not in ('moving', 'inserting'):
        fields['assembly'] = level
        if level == 4:
            memory['l4_tried'] = True
    return fields


def assemble(robot, ctx, core, work):
    fields = {'move': (0, 0) if distance(robot, work) < .16
              else drive(robot, work, ctx.obs, ctx.memory, .1)['move'],
              'brake': True, 'heading': dock_heading(ctx), 'assembly_insert': True,
              'assembly_lift': True, 'assembly_flip': True, 'assembly_confirm': True}
    cores = core.get('cores') or [{'core': 0, 'operation': core.get('operation'),
                                   'target_rotation': core.get('target_rotation', 0)}]
    if core['difficulty'] == 4 and len(cores) == 2:
        if robot.get('arm_count', 1) >= 2:
            fields['assembly_core'] = 2
            fields['assembly_rotate'] = cores[0]['target_rotation']
            return fields
        # One arm: finish the core that is furthest along before switching.
        def rank(c):
            return (STEP_ORDER.index(c['operation']) if c['operation'] in STEP_ORDER else 0,
                    c.get('operation_progress', 0), c['core'])
        open_cores = [c for c in cores if c['operation'] != 'complete'] or cores
        verifying = [c for c in open_cores if c['operation'] == 'verifying']
        chosen = min(verifying or open_cores, key=rank)
        fields['assembly_core'] = chosen['core']
        fields['assembly_rotate'] = chosen['target_rotation']
        return fields
    fields['assembly_rotate'] = cores[0].get('target_rotation', core.get('target_rotation', 0))
    return fields


def heavy_combat(robot, ctx):
    """After the launcher is fitted the heavy robot is the team's only structure gun.
    42 mm has a 0.2 s armor interval and 100 heat a shot with 100 cooling, so the firing
    rhythm is set by heat, not by the trigger: it fires when a shot fits and holds fire
    when it does not."""
    fields = {}
    fields.update(ammo_fields(robot, ctx, 4, 20, 10, 60))
    if robot['ammo'] == 0 and not robot.get('pending_ammo') and not fields:
        return drive(robot, ctx.zone(ctx.team, 'supply'), ctx.obs, ctx.memory)
    if robot['hp'] < robot['max_hp'] * .3:
        fields.update(drive(robot, ctx.zone(ctx.team, 'supply'), ctx.obs, ctx.memory))
        return fields
    memory = ctx.state.setdefault('heavy', {})
    goal = memory.get('post') or heavy_post(ctx)
    fields.update(drive(robot, goal, ctx.obs, ctx.memory, .5))
    fields.update(weapon(robot, ctx, reach=16.0))
    return fields


def heavy_post(ctx):
    """The assembly deck overlooks both outpost cards and the centre crossing, and a
    42 mm arc from there reaches every structure the team is trying to break."""
    return mirror((13.90, 9.60), ctx.team)


# ---- Infantry ------------------------------------------------------------------

def infantry(robot, ctx):
    """Slot 3 works the enemy position, slot 4 holds the home one. Both are card
    anchors: they shoot from their card and stay on it, because standing there is what
    keeps the position active and what drains the enemy's hold. Either one breaks off to
    retake home, because losing home also strips the base of its immunity."""
    obs, team = ctx.obs, ctx.team
    fields = {}
    if obs['tick'] == 0:
        fields['profile'] = {'chassis': robot['chassis_profile'], 'weapon': robot['weapon_profile']}
    fields.update(ammo_fields(robot, ctx, 25, 120, 100, 100, preload=110))
    if at_home_shop(robot, ctx) and robot['ammo'] < 100 and not robot.get('pending_ammo'):
        fields.update(drive(robot, ctx.zone(team, 'base'), obs, ctx.memory, 1.0))
        return fields
    recovery = recovery_goal(robot, ctx)
    if recovery:
        fields.update(drive(robot, recovery, obs, ctx.memory, .2))
        fields.update(weapon(robot, ctx, reach=7, structures=False))
        return fields
    if ctx.time < 1.2:
        return fields
    if not home_covered(ctx):
        held, _ = anchor(robot, ctx, 'home', home_stand(ctx), gun_reach=9.0)
        fields.update(held)
        return fields
    held, on_post = anchor(robot, ctx, 'away', away_stand(ctx), gun_reach=9.0)
    fields.update(held)
    if robot['ammo'] == 0 and not robot.get('pending_ammo') and not fields.get('buy_ammo'):
        fields['fire'] = False
    # A quiet capture card is the safest place to receive a remote heal.
    if robot['hp'] < robot['max_hp'] * .72 and disengaged(robot, ctx.time) and not robot.get('pending_heal') \
            and ctx.coins >= 180 and on_post:
        fields['remote_heal'] = True
    return fields


# ---- Sentry --------------------------------------------------------------------

def sentry(robot, ctx):
    """400 HP, 300 rounds, and a 3x cooling multiplier in attack posture against a 0.5
    damage reduction in defense. Attack therefore deals about 1.6x the net damage of
    defense and can fire without pause, so the sentry lives in attack posture and only
    ducks into defense when it is being focused below a quarter of its health. It holds
    the mid deck, where its arc covers both outpost cards and the centre crossing."""
    obs, team = ctx.obs, ctx.team
    fields = {}
    fields.update(ammo_fields(robot, ctx, 45, 100, 100, 50))
    recovery = recovery_goal(robot, ctx, .30, .80)
    if recovery and not ctx.losing_home():
        fields.update(drive(robot, recovery, obs, ctx.memory, .25))
        fields.update(weapon(robot, ctx, reach=11, structures=True))
        return posture(robot, ctx, fields, 'move' if robot['ammo'] == 0 else 'attack')
    job, stand = sentry_post(ctx)
    held, on_post = anchor(robot, ctx, job, stand, gun_reach=11.0)
    fields.update(held)
    threatened = ctx.time - robot.get('last_damage_time', -99) < 2.5
    focused = sum(1 for e in obs['enemies'] if e['alive'] and distance(robot, (e['x'], e['y'])) < 7)
    panic = threatened and focused >= 2 and robot['hp'] < robot['max_hp'] * .28
    if panic:
        wanted = 'defense'
    elif robot['ammo'] > 0 and any(e['alive'] and not e.get('invulnerable') and distance(robot, (e['x'], e['y'])) < 11
                                   for e in obs['enemies']):
        wanted = 'attack'
    elif not on_post and distance(robot, stand) > 4.5:
        wanted = 'move'
    else:
        wanted = 'attack'
    # The enhanced budget is 15 s for the whole match: spend it on a fight that matters.
    enhanced = wanted == 'attack' and robot['ammo'] >= 60 and focused >= 1 and \
        (robot['hp'] < robot['max_hp'] * .7 or focused >= 2)
    return posture(robot, ctx, fields, wanted, enhanced)


def sentry_post(ctx):
    """The outpost card is the stand that counts: it keeps the home position active from
    the low deck side and its pedestal gives cover, so the sentry holds it rather than
    trading the hold for a slightly better firing line."""
    return 'home', home_stand(ctx)


def posture(robot, ctx, fields, wanted, enhanced=False):
    if ctx.time >= (robot.get('posture_ready_at') or 0):
        if wanted != robot.get('posture'):
            fields['posture'] = wanted
        if bool(robot.get('posture_enhanced')) != enhanced:
            fields['posture_enhanced'] = enhanced
    return fields


# ---- Aerial system -------------------------------------------------------------

def aerial(robot, ctx):
    """Four drones, three strikes each and 200 damage a strike: keep every airframe
    cycling. Each drone takes the nearest plate it can already reach instead of
    waiting for one chosen bearing, and re-docks only at the battery floor."""
    team = ctx.team
    memory = ctx.state.setdefault('aerial', {})
    hangar = ctx.arena['hangars'][team]
    plates = aerial_target(ctx)
    fleet = [d for d in drones(robot) if d['state'] != 'disabled']
    commands = {}
    for d in fleet:
        key = str(d['index'])
        if d['state'] == 'down':
            commands[key] = {}
        elif not plates or d['battery_wh'] < .45:
            commands[key] = {} if d['state'] == 'docked' else {'dock': True}
        elif d['state'] == 'docked':
            commands[key] = {'launch': True}
        else:
            commands[key] = fly(d, plates, ctx)
    return {'drones': commands}


def aerial_target(ctx):
    """Every armor plate the team is allowed to strike, enemy outpost first and the enemy
    base next. A drone picks from this list by distance each decision, so it never holds a
    bearing while a closer plate is free: the 0.2 s armor interval, not the approach
    angle, is what limits strike rate."""
    plates = []
    for owner, outpost in ctx.obs['outposts'].items():
        if outpost['hp'] > 0 and outpost.get('owner', owner) != ctx.team:
            plates += [p for p in outpost.get('armor_plates', [])]
    base = ctx.obs['bases'][ctx.enemy]
    if base['hp'] > 0 and ctx.enemy_base_vulnerable():
        plates += [p for p in base.get('armor_plates', [])]
    return plates


def fly(drone, plates, ctx):
    """Aim at the nearest plate, hover just outside its face, then fly straight through
    its plane. Re-selecting the plate every decision replaces a timed dash: with four
    airframes and three strikes each, throughput comes from never pausing."""
    plate = min(plates, key=lambda p: math.dist((drone['x'], drone['y'], drone['z']), p['center']))
    normal = plate['normal']
    flat = math.hypot(normal[0], normal[1]) or 1.0
    ux, uy = normal[0] / flat, normal[1] / flat
    cx, cy, cz = plate['center']
    ahead = (drone['x'] - cx) * ux + (drone['y'] - cy) * uy
    lateral = abs((drone['x'] - cx) * -uy + (drone['y'] - cy) * ux)
    if ahead > .12 and lateral < .12 and abs(drone['z'] - cz) < .12:
        # On the plate's axis and in front of it: commit.
        return {'move': [round(-ux, 3), round(-uy, 3), round((cz - drone['z']) * 2, 3)]}
    return {'goto': [round(cx + ux * .45, 3), round(cy + uy * .45, 3), round(cz, 3)]}


# ---- Entry --------------------------------------------------------------------

ROLES = {'heavy': heavy, 'infantry': infantry, 'sentry': sentry, 'aerial': aerial}


def decide(robot, ctx):
    if robot['role'] != 'aerial' and not robot['alive']:
        return revive_fields(robot, ctx, 100 if robot['role'] == 'heavy' else 200)
    return ROLES[robot['role']](robot, ctx)


def pause_tipped(robot, fields):
    """Stop pushing while tipped: a rescue or the chassis' own righting takes over."""
    if robot['role'] == 'aerial' or not robot['alive']:
        return fields
    if robot.get('tipped'):
        fields.update(move=(0, 0), brake=True, fire=False)
        fields.pop('power', None)
    return fields


def act(obs, state):
    state = dict(state or {})
    ctx = Context(obs, state)
    commands = {}
    for robot in obs['robots']:
        slot = str(robot['slot'])
        if slot not in obs['controlled_ids']:
            continue
        commands[slot] = action(**pause_tipped(robot, decide(robot, ctx)))
    state['ticks'] = state.get('ticks', 0) + 1
    return commands, state
