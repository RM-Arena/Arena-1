"""DeepSeek Flash RMUC 2027 split-anchor controller.

The 2027 timeout is decided by control degree first, and a base position pays
+3/s while needing only one body on either of its two cards.  This card splits
the five robots into two anchors and two home guards:

``sentry``  2771 sentry and ``infantry`` 2731 cross together and camp the far
            side of the enemy base card.  The sentry tanks the dive; the
            infantry keeps the card occupied if the sentry goes down.

``home``    2732 holds our central card, which denies the opponent's outpost
            pair, and collapses to our base card when a diver reaches it.
            2711 heavy anchors the base card itself: 400-600 HP behind 50%
            base-card defense, and a body that blocks the base approach.

``aerial``  2761 hangar keeps hitting the hostile outpost, so the opponent
            cannot keep a full outpost pair either.

The result is a +3/s clock on the enemy base while our own +3 and the opponent's
+1 are denied.  The controller reuses the shared public 17 mm/42 mm solver,
public observation only, and the same content-addressed submission format.
"""
import math
from sdk import (action, aim_at, aim_pitch, assembly_work_point, ballistic_reachable, can_fire,
                 drones, instant_revive_cost, navigate, rescue_point, resource_pickup_point,
                 tipped_teammates, workbench_point, zone_center, muzzle_speed, point_in_polygon, _aim_target, _rotate)

STYLE = "pair"

STEP_ORDER = ("positioning", "inserting", "lifting", "flipping", "rotating", "verifying", "complete")


def wrap(angle):
    return (angle + math.pi) % math.tau - math.pi


def distance(robot, point):
    return math.hypot(robot['x'] - point[0], robot['y'] - point[1])


def other(team):
    return 'blue' if team == 'red' else 'red'


def unstick(robot, move, memory, now):
    """Action fields for `move`; a robot that pushes on without moving or turning for 1.5 s
    backs off at an angle for 0.7 s, keeping its heading (a chassis cannot turn on bumps)."""
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


def drive(robot, goal, obs, memory, tolerance=.35):
    """Navigate to `goal`; scale the command down near the waypoint so the router's own
    bump handling and turn-in-place are not overridden by a full-speed command."""
    if goal is None or distance(robot, goal) <= tolerance:
        return {'move': (0, 0), 'brake': True}
    fields = unstick(robot, navigate(robot, goal, obs['arena']), memory, obs['time'])
    if math.hypot(robot['vx'], robot['vy']) < .3 and math.hypot(*fields['move']) > .2:
        fields['power'] = 200
    return fields


class Context:
    """Per-decision facts every role reads."""

    def __init__(self, obs, state):
        self.obs, self.state = obs, state
        self.team = obs['team']
        self.enemy = other(self.team)
        self.arena = obs['arena']
        self.time = obs['time']
        self.economy = obs['teams'][self.team]
        self.coins = self.economy['resources']
        gap = self.economy.get('control', 0) - obs['teams'][self.enemy].get('control', 0)
        threshold = .15 if STYLE == 'control' else 1.0 if obs.get('remaining', 420) < 150 else 5.0
        self.hold_lead = gap > threshold
        self.positions = obs.get('positions', {})
        self.memory = state.setdefault('stuck', {})
        self.rotation = state.setdefault('target_rotation', {})
        self.spin = {}
        for site, outpost in obs['outposts'].items():
            previous = self.rotation.get(site)
            self.spin[site] = 0.0 if outpost.get('rotation_stopped') or not previous else \
                wrap(outpost['rotation'] - previous[1]) / max(.001, self.time - previous[0])
            self.rotation[site] = [self.time, outpost['rotation']]

    def zone(self, team, kind):
        return zone_center(self.arena, f'{team}_{kind}')

    def controls(self, name, team=None, full=False):
        p = self.positions.get(name)
        return bool(p) and p['controller'] == (team or self.team) and (not full or p['control'] == 'full')

    def enemy_base_vulnerable(self):
        """A base takes no damage while its owner fully controls its own outpost position."""
        return not self.controls(f'{self.enemy}_outpost', self.enemy, full=True) and self.obs['bases'][self.enemy]['hp'] > 0

    def hostile_outpost(self):
        """The outpost to attack: the enemy's, or ours if the enemy rebuilt it as theirs.
        `site` names the outpost by the side it stands on."""
        for site in (self.enemy, self.team):
            o = self.obs['outposts'][site]
            if o['hp'] > 0 and o.get('owner', site) != self.team:
                return dict(o, kind='outpost', site=site)
        return None


def structure_target(robot, ctx):
    outpost = ctx.hostile_outpost()
    if outpost:
        # Aim where a rotating plate will be when the projectile arrives.
        flight = max(0, distance(robot, (outpost['x'], outpost['y'])) - .3) / (muzzle_speed(robot) * .86)
        turn = ctx.spin.get(outpost['site'], 0) * flight
        c, s = math.cos(turn), math.sin(turn)
        plates = []
        for p in outpost.get('armor_plates', []):
            dx, dy = p['center'][0] - outpost['x'], p['center'][1] - outpost['y']
            nx, ny = p['normal'][:2]
            x, y = outpost['x'] + dx * c - dy * s, outpost['y'] + dx * s + dy * c
            normal = (nx * c - ny * s, nx * s + ny * c)
            score = ((robot['x'] - x) * normal[0] + (robot['y'] - y) * normal[1])
            plates.append((score, {'x': x, 'y': y, 'aim_z': p['center'][2]}))
        target = max(plates, key=lambda p: p[0])[1] if plates else outpost
        if ballistic_reachable(robot, target):
            return target
    if ctx.enemy_base_vulnerable():
        base = dict(ctx.obs['bases'][ctx.enemy], kind='base')
        if ballistic_reachable(robot, base):
            return base
    return None


def enemy_target(robot, ctx, reach):
    """Focus exposed, low-health combat robots instead of splitting damage into tanks."""
    candidates = []
    for e in ctx.obs['enemies']:
        if not e['alive'] or not e.get('targetable', True) or e.get('invulnerable'):
            continue
        d = distance(robot, (e['x'], e['y']))
        if d <= reach:
            score = e['hp'] * (1 + e.get('defense_buff', 0)) + d * 24
            if e['role'] == 'sentry':
                score -= 90
            if e['role'] == 'heavy' and e.get('launcher') not in ('fitted', 'installed'):
                score += 180
            candidates.append((score, e))
    for _, target in sorted(candidates, key=lambda p: p[0])[:3]:
        if ballistic_reachable(robot, target):
            return target
    return None


def drone_target(robot, ctx, reach=5.0):
    """A hovering or slow enemy aerial robot close enough to shoot at its guard."""
    best = None
    for d in ctx.obs.get('enemy_drones', []):
        if d['state'] != 'flying' or math.hypot(d['vx'], d['vy']) > 2.5:
            continue
        gap = distance(robot, (d['x'], d['y']))
        if gap <= reach and (best is None or gap < best[0]):
            best = (gap, {'x': d['x'], 'y': d['y'], 'z': d['z'], 'aim_z': d['z']})
    return best[1] if best else None


def weapon(robot, ctx, reach=9.0, structures=True, drones_too=True):
    """aim/pitch/fire fields: robots first, then drones, then structures."""
    target = enemy_target(robot, ctx, reach)
    if target is None and drones_too and robot['role'] != 'heavy':
        target = drone_target(robot, ctx, reach=3.0)
    if target is None and structures:
        target = structure_target(robot, ctx)
    if target is None:
        front = ctx.zone(ctx.enemy, 'central')
        return {'aim': math.atan2(front[1] - robot['y'], front[0] - robot['x']) + .5 * math.sin(ctx.time * .8), 'fire': False}
    solution = firing_solution(robot, target)
    if solution is None:
        return {'aim': aim_at(robot, target), 'fire': False}
    aim, pitch = solution
    heavy = robot['role'] == 'heavy'
    cone = max(.012, min(.035, .065 / max(1, distance(robot, (target['x'], target['y'])))))
    actual_aim, actual_pitch = barrel_angles(robot)
    aligned = abs(wrap(aim - actual_aim)) < cone and abs(pitch - actual_pitch) < .025
    # 17 mm keeps a 20-heat margin: one decision can fire two rounds.
    fire = aligned and can_fire(robot) and (heavy or robot['heat'] + 20 <= robot['max_heat'])
    return {'aim': aim, 'pitch': pitch, 'fire': fire}


def barrel_angles(robot):
    """Observation gimbal angles are relative to the moving chassis, commands are world angles."""
    yaw, pitch = robot['aim'] - robot['heading'], robot.get('pitch', 0)
    v = _rotate(robot.get('quaternion', (0, 0, 0, 1)),
                (math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), math.sin(pitch)))
    return math.atan2(v[1], v[0]), math.atan2(v[2], math.hypot(v[0], v[1]))


def firing_solution(robot, target):
    """Solve flight time and lead together, including drag and inherited chassis velocity.

    Uses the same public pellet masses, drag model and integration step as the SDK.
    Iterating flight time avoids the linear d/v approximation at moving armor plates.
    """
    point = _aim_target(robot, target)
    speed = muzzle_speed(robot)
    mass, radius = (.0445, .02125) if robot['role'] == 'heavy' else (.0032, .0084)
    drag = .5 * 1.225 * .47 * math.pi * radius * radius / mass
    pivot = _rotate(robot.get('quaternion', (0, 0, 0, 1)), (0, 0, robot.get('muzzle_height_m', .45)))
    ox, oy, oz = robot['x'] + pivot[0], robot['y'] + pivot[1], robot.get('z', 0) + pivot[2]
    reach = robot.get('muzzle_reach_m', .22)
    flight = math.hypot(point[0] - ox, point[1] - oy) / speed
    yaw, pitch = 0., 0.
    for iteration in range(2):
        lead = flight + .025
        tx, ty = point[0] + target.get('vx', 0) * lead, point[1] + target.get('vy', 0) * lead
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


def can_buy_here(robot, ctx):
    """Local exchange on own shop cards or a fully controlled outpost; contact lasts 2 s."""
    contacts = set(robot.get('last_raw_zones', []))
    contacts.update(zone for zone, last in robot.get('zone_contacts', {}).items() if ctx.time - last <= 2)
    if any(f'{ctx.team}_{kind}' in contacts for kind in ('base', 'supply', 'high_point')):
        return True
    if any(f'{owner}_outpost' in contacts and ctx.controls(f'{owner}_outpost', full=True) for owner in (ctx.team, ctx.enemy)):
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


def ammo_fields(robot, ctx, low, local_amount, remote_amount, reserve):
    """Buy ammo when low: locally where allowed, otherwise remotely once disengaged."""
    if robot['ammo'] >= low or ctx.time < 1.05 or robot.get('pending_ammo'):
        return {}
    unit = 10 if robot['role'] == 'heavy' else 1
    if can_buy_here(robot, ctx) and ctx.coins >= local_amount * unit + reserve:
        return {'buy_ammo': {'amount': local_amount, 'remote': False}}
    if disengaged(robot, ctx.time) and ctx.coins >= 150 + reserve:
        return {'buy_ammo': {'amount': remote_amount, 'remote': True}}
    return {}


def revive_fields(robot, ctx, reserve=150):
    cost = instant_revive_cost(robot, ctx.time)
    return {'revive': ctx.time < 330 and ctx.coins >= cost + reserve}


# ---- Heavy robot ---------------------------------------------------------------------------

UNLOCK = {1: 0, 2: 60, 3: 120, 4: 180}


def heavy(robot, ctx):
    # Home anchor: body-block the base card; technology is traded for the raid.
    obs, team = ctx.obs, ctx.team
    if robot.get('weak'):
        return drive(robot, ctx.zone(team, 'supply'), obs, ctx.memory)
    goal = (1.2, 7.5) if team == 'red' else (26.8, 7.5)
    fields = drive(robot, goal, obs, ctx.memory, .25)
    fields.update(weapon(robot, ctx, reach=12))
    return fields


def heavy_tech(robot, ctx):
    obs, team = ctx.obs, ctx.team
    memory = ctx.state.setdefault('heavy', {})
    if STYLE == 'heavy':
        return heavy_anchor(robot, ctx, memory)
    done = ctx.economy.get('completed_difficulties', [])
    core = obs['assemblies'][team]
    stage = core['stage']
    active = stage in ('moving', 'inserting')
    work = assembly_work_point(robot, ctx.arena)
    if robot['weak']:
        return drive(robot, ctx.zone(team, 'supply'), obs, ctx.memory)
    launcher = robot.get('launcher', 'locked')
    if active and distance(robot, work) < 1.2:
        return assemble(robot, ctx, core, work)
    # 2027 has no engineer: the heavy robot's arm rights a tipped teammate close by. Each
    # attempt gets 25 s, after the initial technology income is established;
    # a wedged robot is skipped until the 75 s attempt record expires.
    attempts = memory.setdefault('rescue', {})
    for key, started in list(attempts.items()):
        if ctx.time - started > 75:
            del attempts[key]
    tipped = [t for t in tipped_teammates(obs) if (1 in done or ctx.time > 60) and t['role'] != 'aerial' and t['slot'] != robot['slot']
              and distance(robot, (t['x'], t['y'])) < 12 and ctx.time - attempts.get(t['id'], ctx.time) < 25]
    if tipped and launcher != 'installing':
        target = min(tipped, key=lambda t: distance(robot, (t['x'], t['y'])))
        attempts.setdefault(target['id'], ctx.time)
        far = distance(robot, (target['x'], target['y'])) > .8
        fields = drive(robot, rescue_point(robot, target), obs, ctx.memory, .1) if far else {'move': (0, 0), 'brake': True}
        fields['rescue'] = target['slot']
        return fields
    if launcher in ('unlocked', 'installing'):
        bench = workbench_point(robot, ctx.arena)
        if distance(robot, bench) <= .25:
            fields = {'move': (0, 0), 'brake': True, 'install_launcher': True}
            # The workbench stands in the supply zone: buy 42 mm while the module goes on.
            fields.update(ammo_fields(robot, ctx, 8, 20, 10, 100))
            return fields
        return drive(robot, bench, obs, ctx.memory, .2)
    armed = launcher in ('fitted', 'installed')
    # Level 4 (50% team defense) once, with two units, while there is time to finish it.
    level_four = armed and 4 not in done and not memory.get('l4_tried') and ctx.time < 285
    if level_four and robot['carried_units'] < 2 and ctx.economy.get('energy_units_left', 0) > 0 \
            and distance(robot, resource_pickup_point(robot, ctx.arena)) < 3:
        return pick(robot, ctx)                      # the hub stands beside the workbench
    if level_four and robot['carried_units'] >= 2:
        return start_assembly(robot, ctx, 4, core, work, memory)
    if armed:
        return heavy_combat(robot, ctx)
    # Economy: levels 1-3 unlock the launcher, raise the infantry level cap and add income.
    wanted = next((d for d in (1, 2, 3) if d not in done), None)
    if wanted is None:
        return heavy_combat(robot, ctx)
    units_left = ctx.economy.get('energy_units_left', 0)
    if robot['carried_units'] == 0 or (robot['carried_units'] < 2 and units_left > 0 and distance(robot, resource_pickup_point(robot, ctx.arena)) < 1.0):
        if units_left <= 0 and robot['carried_units'] == 0:
            return heavy_combat(robot, ctx)
        return pick(robot, ctx)
    return start_assembly(robot, ctx, wanted, core, work, memory)


def heavy_anchor(robot, ctx, memory):
    """The heavy robot as the base anchor: no assembly, just the long walk to the enemy
    base card. The sentry keeps the home anchor, so the team trades technology and the
    42 mm for +3 control per second from the base position."""
    obs, team = ctx.obs, ctx.team
    if robot.get('weak'):
        goal = ctx.zone(team, 'supply')
        return drive(robot, goal, obs, ctx.memory, .3)
    if f'{ctx.enemy}_base' not in set(robot.get('last_raw_zones', [])):
        fields, _ = follow(robot, mirror_route(BASE_ROUTE_RED, team), ctx)
        return fields
    return {'move': (0, 0), 'brake': True}


def pick(robot, ctx):
    goal = resource_pickup_point(robot, ctx.arena)
    if distance(robot, goal) <= .12:
        station = next(f for f in ctx.arena['field_geometry']['fixtures'] if f['kind'] == 'resource' and f['team'] == ctx.team)
        return {'move': (0, 0), 'brake': True, 'pick_unit': True,
                'heading': math.atan2(station['pick_dir'][1], station['pick_dir'][0])}
    fields = drive(robot, goal, ctx.obs, ctx.memory, .1)
    fields['pick_unit'] = distance(robot, goal) < .6
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
        # Keep enough pace up the plinth bevel; a creeping approach stalls on its slope.
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
    fields = {'move': (0, 0) if distance(robot, work) < .16 else drive(robot, work, ctx.obs, ctx.memory, .1)['move'],
              'brake': True, 'heading': dock_heading(ctx), 'assembly_insert': True, 'assembly_lift': True,
              'assembly_flip': True, 'assembly_confirm': True}
    cores = core.get('cores') or [{'core': 0, 'operation': core.get('operation'), 'target_rotation': core.get('target_rotation', 0)}]
    if core['difficulty'] == 4 and len(cores) == 2:
        if robot.get('arm_count', 1) >= 2:
            fields['assembly_core'] = 2
            fields['assembly_rotate'] = cores[0]['target_rotation']
            return fields
        # One arm: work the core that is behind, finishing a confirmation before switching.
        def rank(c):
            return (STEP_ORDER.index(c['operation']) if c['operation'] in STEP_ORDER else 0, c.get('operation_progress', 0), c['core'])
        open_cores = [c for c in cores if c['operation'] != 'complete'] or cores
        verifying = [c for c in open_cores if c['operation'] == 'verifying']
        chosen = min(verifying or open_cores, key=rank)
        fields['assembly_core'] = chosen['core']
        fields['assembly_rotate'] = chosen['target_rotation']
        return fields
    fields['assembly_rotate'] = cores[0].get('target_rotation', core.get('target_rotation', 0))
    return fields


def heavy_post(ctx):
    """Firing position on the central deck, beside the plinth and facing the enemy end."""
    team = ctx.team
    x, y = (12.0, 9.6) if STYLE == 'fortress' or ctx.hold_lead else (14.9, 5.0)
    return (x, y) if team == 'red' else (28 - x, 15 - y)


def heavy_combat(robot, ctx):
    obs = ctx.obs
    fields = {}
    fields.update(ammo_fields(robot, ctx, 3, 20, 10, 60))
    if robot['ammo'] == 0 and not robot.get('pending_ammo') and not fields:
        # Out of 42 mm and coins: hold at the supply zone, where the heavy robot is invulnerable.
        return drive(robot, ctx.zone(ctx.team, 'supply'), obs, ctx.memory)
    if robot['hp'] < robot['max_hp'] * .3:
        fields.update(drive(robot, ctx.zone(ctx.team, 'supply'), obs, ctx.memory))
        return fields
    fields.update(drive(robot, heavy_post(ctx), obs, ctx.memory, .5))
    fields.update(weapon(robot, ctx, reach=12.0))
    return fields


# ---- Infantry ------------------------------------------------------------------------------

def enemy_base_camp_spot(ctx):
    """The far-side pocket on the enemy base buff card.

    The position needs presence on either card and pays +3 control per second. The far
    side is outside the forbidden base body and screened from the central deck by the
    base itself, so one anchor can keep the temporary capture unseen.
    """
    return (27.10, 7.50) if ctx.enemy == 'blue' else (0.90, 7.50)


# The published north approach to the enemy central card, measured from the red spawn.
CENTRAL_RUSH_RED = [(4.55, 12.62), (5.31, 13.56), (7.16, 13.93), (10.38, 13.94),
                    (12.0, 12.2), (14.49, 10.19), (17.1, 8.6)]

BASE_ROUTE_RED = [(9.6, 4.7), (8.9, 2.2), (12.9, 3.3), (17.4, 1.1), (19.75, 2.7),
                  (21.0, 2.5), (22.4, 3.0), (22.8, 5.1), (24.1, 4.8), (26.8, 4.4), (27.1, 7.5)]


def mirror_route(route, team, offset=0.0):
    return [p if team == 'red' else (28.0 - p[0], 15.0 - p[1]) for p in route]


def follow(robot, route, ctx, tolerance=.7):
    """Advance through a waypoint list. Returns (fields, arrived-at-last)."""
    m = ctx.state.setdefault('route', {}).setdefault(str(robot['slot']), {'i': 0})
    i = max(0, min(m.get('i', 0), len(route) - 1))
    goal = route[i]
    if distance(robot, goal) < tolerance and i < len(route) - 1:
        i += 1
        m['i'] = i
        goal = route[i]
    fields = drive(robot, goal, ctx.obs, ctx.memory, .18)
    return fields, i == len(route) - 1 and distance(robot, route[-1]) < 1.1


def own_central_spot(ctx):
    return ctx.zone(ctx.team, 'central')


def on_position_card(robot, owner):
    """True while the chassis is inside either buff card of an outpost position."""
    return bool(set(robot.get('last_raw_zones', [])) & {f'{owner}_central', f'{owner}_outpost'})


def infantry_job(robot, ctx):
    """Slot 4 (the 200 HP mecanum infantry) raids the enemy base card; slot 3 takes the
    enemy outpost position. The split is fixed by role rather than by a speed sort so the
    fragile, faster wheel-legged chassis is not the one sent alone across the map."""
    return 'flex' if robot['slot'] == 4 else 'striker'


def outpost_card_spot(ctx, owner, side=0):
    """A standing point on an outpost buff card, on the deck side away from the kerb."""
    x, y = ctx.obs['outposts'][owner]['x'], ctx.obs['outposts'][owner]['y']
    toward = (14 - x, 7.5 - y)
    length = math.hypot(*toward) or 1
    ux, uy = toward[0] / length, toward[1] / length
    card = next(z for z in ctx.arena['zones'] if z['id'] == f'{owner}_outpost')
    # Inset the real card's corners. The old 0.62 m ring could intersect the
    # physical outpost pedestal even when the target centre lay inside the card.
    polygon = card.get('polygon')
    if polygon:
        points = [(px * .75 + x * .25, py * .75 + y * .25) for px, py in polygon]
        points = [p for p in points if point_in_polygon(*p, polygon)]
        points.sort(key=lambda p: (p[0] - x) * ux + (p[1] - y) * uy, reverse=True)
        if points:
            return points[min(2 if side > 0 else 0, len(points) - 1)]
    return (x + ux * .8, y + uy * .8)


def infantry(robot, ctx):
    obs, team, enemy = ctx.obs, ctx.team, ctx.enemy
    fields = {}
    if obs['tick'] == 0:
        fields['profile'] = {'chassis': robot['chassis_profile'], 'weapon': robot['weapon_profile']}
    fields.update(ammo_fields(robot, ctx, 25, 120, 100, 120))
    recovery = recovery_goal(robot, ctx)
    if recovery:
        fields.update(drive(robot, recovery, obs, ctx.memory, .2))
        fields.update(weapon(robot, ctx, reach=7, structures=False))
        return fields
    if ctx.time < 1.2:
        return fields
    job = infantry_job(robot, ctx)
    side = 1 if robot['slot'] % 2 else -1
    own = ctx.controls(f'{team}_outpost')
    theirs = ctx.controls(f'{enemy}_outpost')
    if STYLE == 'pair' and robot['slot'] == 3:
        if robot.get('weak'):
            goal = ctx.zone(team, 'supply')
            fields.update(drive(robot, goal, obs, ctx.memory, .3))
        elif f'{enemy}_base' not in set(robot.get('last_raw_zones', [])):
            fields.update(follow(robot, mirror_route(BASE_ROUTE_RED, team), ctx)[0])
        else:
            fields.update({'move': (0, 0), 'brake': True})
        fields.update(weapon(robot, ctx, reach=9))
        if robot['hp'] < robot['max_hp'] * .55 and ctx.coins >= 180 and not robot.get('pending_heal'):
            fields['remote_heal'] = True
        return fields
    if STYLE in ('sentry', 'heavy', 'pair') and robot['slot'] in (3, 4):
        base = obs['bases'][team]
        home = (0.90, 7.50) if team == 'red' else (27.10, 7.50)
        # The red lane reaches the enemy base card earlier; the blue lane fights
        # longer on the home side, so blue keeps the central card unless a diver
        # is already inside the base pocket.
        limit = 4.5 if team == 'red' else 8.0
        near_home = [e for e in obs['enemies'] if e['alive'] and not e.get('invulnerable')
                     and e.get('role') != 'aerial'
                     and distance(e, (base['x'], base['y'])) < limit]
        if robot.get('weak'):
            goal = ctx.zone(team, 'supply')
            fields.update(drive(robot, goal, obs, ctx.memory, .3))
        elif not ctx.controls(f'{team}_base') or near_home:
            fields.update(drive(robot, home, obs, ctx.memory, .18))
        elif not on_position_card(robot, team):
            fields.update(drive(robot, own_central_spot(ctx), obs, ctx.memory, .25))
        else:
            fields.update({'move': (0, 0), 'brake': True})
        fields.update(weapon(robot, ctx, reach=9))
        if robot['hp'] < robot['max_hp'] * .55 and ctx.coins >= 180 and not robot.get('pending_heal'):
            fields['remote_heal'] = True
        return fields
    if STYLE == 'fortress' or ctx.hold_lead:
        goal = outpost_card_spot(ctx, team, side) if job == 'striker' else (ctx.zone(team, 'central')[0], ctx.zone(team, 'central')[1] + (-1.2 if team == 'red' else 1.2))
    elif not own:
        goal = outpost_card_spot(ctx, team, side) if job == 'striker' else ctx.zone(team, 'central')
    elif not ctx.controls(f'{team}_outpost', full=True) and not sentry_holds(ctx) and job == 'flex':
        goal = ctx.zone(team, 'central')
    elif theirs:
        # Preserve the captured outpost while the other infantry opens the base.
        # Leaving a temporary point with nobody on either card gives it away in 5 s.
        if job == 'flex' and ctx.time >= 180 and enemy_point_covered(ctx, robot['slot']):
            goal = ctx.zone(enemy, 'fortress')
        else:
            goal = outpost_card_spot(ctx, enemy, side) if job == 'striker' else ctx.zone(enemy, 'central')
    elif STYLE == 'pressure':
        goal = outpost_card_spot(ctx, enemy, side)
    elif job == 'striker':
        goal = outpost_card_spot(ctx, enemy, side)
    else:
        goal = ctx.zone(enemy, 'central')
    fields.update(drive(robot, goal, obs, ctx.memory, .20))
    fields.update(weapon(robot, ctx, reach=9))
    if robot.get('ammo', 0) == 0 and not robot.get('pending_ammo') and not fields.get('buy_ammo'):
        fields['fire'] = False
    # A quiet capture point is a safe place to receive a remote heal, without giving up control.
    if robot['hp'] < robot['max_hp'] * .72 and disengaged(robot, ctx.time) and not robot.get('pending_heal') \
            and ctx.coins >= 180 and distance(robot, goal) < .7:
        fields['remote_heal'] = True
    return fields




def enemy_point_covered(ctx, excluded):
    return any(r['slot'] != excluded and r['alive'] and not r.get('weak') and r['role'] != 'aerial'
               and r['hp'] >= r['max_hp'] * .4
               and on_outpost_card(r, ctx.enemy, ctx) for r in ctx.obs['robots'])


def on_outpost_card(robot, owner, ctx=None):
    """Count occupied, eligible cards; a mutually blocked central card is not cover."""
    if robot.get('tipped'):
        return False
    contacts = set(robot.get('last_raw_zones', [])) & {f'{owner}_central', f'{owner}_outpost'}
    if ctx is None:
        return bool(contacts)
    for card in contacts:
        zone = ctx.obs.get('zones', {}).get(card, {})
        if robot['id'] not in zone.get('occupants', []):
            continue
        if card.endswith('_central') and zone.get('owner') != robot['team']:
            continue
        return True
    return False


def recovery_goal(robot, ctx):
    """Latch recovery until healed; use a friendly, fully controlled outpost when closer."""
    memory = ctx.state.setdefault('recovery', {})
    key = str(robot['slot'])
    if robot['weak'] or robot['hp'] < robot['max_hp'] * .24:
        memory[key] = True
    if robot['hp'] >= robot['max_hp'] * .85 and not robot['weak']:
        memory.pop(key, None)
    if not memory.get(key):
        return None
    occupied = set(robot.get('last_raw_zones', []))
    if f'{ctx.team}_supply' in occupied or any(f'{owner}_outpost' in occupied and
            ctx.controls(f'{owner}_outpost', full=True) for owner in (ctx.team, ctx.enemy)):
        return (robot['x'], robot['y'])
    goals = [ctx.zone(ctx.team, 'supply')]
    for owner in (ctx.team, ctx.enemy):
        if ctx.controls(f'{owner}_outpost', full=True):
            goals.append(outpost_card_spot(ctx, owner))
    return min(goals, key=lambda p: distance(robot, p))


def sentry_holds(ctx):
    """An eligible own sentry is standing on either card of the home outpost position."""
    return any(r['role'] == 'sentry' and r['alive'] and not r['weak'] and on_outpost_card(r, ctx.team, ctx) for r in ctx.obs['robots'])


# ---- Sentry --------------------------------------------------------------------------------

def sentry_home(robot, ctx):
    """Hold the home central card; the heavy robot is the base anchor in this card."""
    obs, team = ctx.obs, ctx.team
    fields = {}
    fields.update(ammo_fields(robot, ctx, 45, 100, 100, 60))
    if robot.get('weak'):
        fields.update(drive(robot, ctx.zone(team, 'supply'), obs, ctx.memory, .3))
        fields.update(weapon(robot, ctx, reach=9, structures=False))
        return fields
    goal = ctx.zone(team, 'central')
    if not on_position_card(robot, team):
        fields.update(drive(robot, goal, obs, ctx.memory, .25))
    else:
        fields.update({'move': (0, 0), 'brake': True})
    fields.update(weapon(robot, ctx, reach=10))
    threatened = ctx.time - robot.get('last_damage_time', -99) < 2.5
    if robot['hp'] < robot['max_hp'] * .35 and threatened:
        wanted = 'defense'
    elif robot['ammo'] > 0 and any(e['alive'] and not e.get('invulnerable') and distance(robot, (e['x'], e['y'])) < 10 for e in obs['enemies']):
        wanted = 'attack'
    else:
        wanted = 'defense'
    if wanted != robot.get('posture') and ctx.time >= (robot.get('posture_ready_at') or 0):
        fields['posture'] = wanted
    enhanced = wanted == 'defense' and robot['hp'] < robot['max_hp'] * .3 and threatened
    if bool(robot.get('posture_enhanced')) != enhanced and ctx.time >= (robot.get('posture_ready_at') or 0):
        fields['posture_enhanced'] = enhanced
    return fields


def sentry(robot, ctx):
    """Base raider and anchor.

    The enemy base position pays +3 control per second and needs presence on only one of
    its two cards. The sentry is the one chassis that can cross the map alone, sit on the
    far side of the base card and survive a dive long enough to matter. It defends while
    moving through enemy ground, recovers at home when a death leaves it weak, and only
    takes attack posture at the card when nothing is shooting at it.
    """
    obs, team = ctx.obs, ctx.team
    fields = {}
    fields.update(ammo_fields(robot, ctx, 40, 100, 100, 80))
    if robot.get('weak'):
        recovery = ctx.zone(team, 'supply')
        if distance(robot, recovery) > .6:
            fields.update(drive(robot, recovery, obs, ctx.memory, .3))
        else:
            fields.update({'move': (0, 0), 'brake': True})
        fields.update(weapon(robot, ctx, reach=9, structures=False))
        fields.update({'posture': 'defense'})
        return fields
    goal = enemy_base_camp_spot(ctx)
    on_card = f'{ctx.enemy}_base' in set(robot.get('last_raw_zones', []))
    if not on_card:
        fields.update(follow(robot, mirror_route(BASE_ROUTE_RED, team), ctx)[0])
        fields.update(weapon(robot, ctx, reach=9, structures=False))
    else:
        fields.update({'move': (0, 0), 'brake': True})
        fields.update(weapon(robot, ctx, reach=10))
    threatened = ctx.time - robot.get('last_damage_time', -99) < 2.5
    near = any(e['alive'] and not e.get('invulnerable') and distance(robot, (e['x'], e['y'])) < 12
               for e in obs['enemies'])
    if on_card:
        wanted = 'attack' if (not threatened and robot['hp'] > robot['max_hp'] * .6
                              and any(e['alive'] and not e.get('invulnerable')
                                      and distance(robot, (e['x'], e['y'])) < 9 for e in obs['enemies'])) else 'defense'
    else:
        wanted = 'defense' if (near or threatened) else 'move'
    if wanted != robot.get('posture') and ctx.time >= (robot.get('posture_ready_at') or 0):
        fields['posture'] = wanted
    enhanced = wanted == 'defense' and threatened and robot['hp'] < robot['max_hp'] * .55
    if bool(robot.get('posture_enhanced')) != enhanced and ctx.time >= (robot.get('posture_ready_at') or 0):
        fields['posture_enhanced'] = enhanced
    return fields


# ---- Aerial robot system -----------------------------------------------------------------

DASH_STANDOFF = .45   # hold this far outside the armor ring, then dash
DASH_TIME = .32       # seconds from the hold point to the plate
DASH_TOLERANCE = .13  # radians of lead error accepted when launching a dash


def aerial(robot, ctx):
    obs, team = ctx.obs, ctx.team
    memory = ctx.state.setdefault('aerial', {})
    hangar = ctx.arena['hangars'][team]
    target = aerial_target(ctx, memory)
    commands = {}
    fleet = [d for d in drones(robot) if d['state'] != 'disabled']
    for k, d in enumerate(fleet):
        key = str(d['index'])
        if d['state'] == 'down':
            commands[key] = {'launch': True} if target else {}
            continue
        if target is None or d['battery_wh'] < .5:
            if d['state'] != 'docked':
                commands[key] = {'dock': True}
            continue
        if d['state'] == 'docked':
            commands[key] = {'launch': True}
            continue
        exit_point = gantry_exit(hangar, target, ctx)
        m = memory.setdefault(d['id'], {'mode': 'exit'})
        if m['mode'] == 'exit':
            if math.hypot(d['x'] - exit_point[0], d['y'] - exit_point[1]) > .2:
                commands[key] = {'goto': [exit_point[0], exit_point[1], 2.0]}
                continue
            m['mode'] = 'approach'
        commands[key] = ram(d, target, k, len(fleet), ctx.time, memory, (hangar['x'], hangar['y']))
    return {'drones': commands}


def aerial_target(ctx, memory):
    """The rotating outpost first; the enemy base once it can be damaged (guard: outposts only)."""
    obs = ctx.obs
    own = obs['outposts'][ctx.team]
    outpost = dict(own, kind='outpost', site=ctx.team) if (STYLE == 'fortress' or ctx.hold_lead) and own['hp'] > 0 and own.get('owner', ctx.team) != ctx.team else ctx.hostile_outpost()
    if outpost:
        track_spin(memory, outpost['site'], outpost, ctx.time)
        return dict(outpost, spin=memory.get('spin', {}).get(outpost['site'], 0.0))
    if ctx.enemy_base_vulnerable():
        return dict(obs['bases'][ctx.enemy], kind='base', spin=0.0)
    return None


def track_spin(memory, owner, outpost, now):
    last = memory.setdefault('rotation', {}).get(owner)
    if last and now > last[0] and not outpost.get('rotation_stopped'):
        memory.setdefault('spin', {})[owner] = wrap(outpost['rotation'] - last[1]) / (now - last[0])
    elif outpost.get('rotation_stopped'):
        memory.setdefault('spin', {})[owner] = 0.0
    memory['rotation'][owner] = [now, outpost['rotation']]


def gantry_exit(hangar, target, ctx):
    """Leave the hangar sideways: its platform sits beside a rune-gantry post."""
    rune = ctx.arena['rune']
    axis = (hangar['x'] - rune['x'], hangar['y'] - rune['y'])
    length = math.hypot(*axis) or 1
    side = (-axis[1] / length, axis[0] / length)
    toward = (target['x'] - hangar['x'], target['y'] - hangar['y'])
    if side[0] * toward[0] + side[1] * toward[1] < 0:
        side = (-side[0], -side[1])
    return (hangar['x'] + side[0] * .6, hangar['y'] + side[1] * .6)


def ram(d, target, k, n, now, memory, hangar):
    """Hold outside the armor of `target` at a fixed bearing; dash when a plate turns into
    line `DASH_TIME` ahead. Each robot takes its own plate and bearing."""
    plates = sorted(target.get('armor_plates', []), key=lambda p: p['face'])
    if not plates:
        return {'goto': [hangar[0], hangar[1], 2.0]}
    cx, cy = target['x'], target['y']
    m = memory.setdefault(d['id'], {'mode': 'approach'})
    if target['spin'] == 0:
        plate = plates[k % len(plates)]
        bearing = math.atan2(plate['normal'][1], plate['normal'][0])
        radius = math.hypot(plate['center'][0] - cx, plate['center'][1] - cy)
        anchor = (plate['center'][0] - math.cos(bearing) * radius, plate['center'][1] - math.sin(bearing) * radius)
    else:
        plate = plates[k % len(plates)]
        bearing = math.atan2(hangar[1] - cy, hangar[0] - cx) + (k - (n - 1) / 2) * .9
        radius = math.hypot(plate['center'][0] - cx, plate['center'][1] - cy)
        anchor = (cx, cy)
    hold = (anchor[0] + math.cos(bearing) * (radius + DASH_STANDOFF), anchor[1] + math.sin(bearing) * (radius + DASH_STANDOFF),
            plate['center'][2])
    if m['mode'] == 'dash' and now < m['until']:
        return {'move': m['dir']}
    if m['mode'] == 'dash':
        m.update(mode='retreat', until=now + .4)
    if m['mode'] == 'retreat' and now < m['until']:
        return {'move': [math.cos(bearing), math.sin(bearing), 0]}
    m['mode'] = 'approach'
    if math.hypot(d['x'] - anchor[0], d['y'] - anchor[1]) < radius + .15:
        return {'move': [math.cos(bearing), math.sin(bearing), 0]}
    gap = math.dist((d['x'], d['y'], d['z']), hold)
    if gap > .07 or math.hypot(d['vx'], d['vy']) > .35:
        return {'goto': [round(v, 3) for v in hold]}
    facing = math.atan2(plate['normal'][1], plate['normal'][0]) + target['spin'] * DASH_TIME
    if abs(wrap(facing - bearing)) <= DASH_TOLERANCE:
        m.update(mode='dash', until=now + DASH_TIME + .15,
                 dir=[-math.cos(bearing), -math.sin(bearing), round((plate['center'][2] - d['z']) * 3, 3)])
        return {'move': m['dir']}
    return {'goto': [round(v, 3) for v in hold]}


# ---- Entry ---------------------------------------------------------------------------------

ROLES = {'heavy': heavy, 'infantry': infantry, 'sentry': sentry, 'aerial': aerial}


def decide(robot, ctx):
    if robot['role'] != 'aerial' and not robot['alive']:
        camper = ('heavy' if STYLE == 'heavy' else 'sentry')
        if robot['role'] == camper and ctx.time < 390:
            cost = instant_revive_cost(robot, ctx.time)
            return {'revive': ctx.coins >= cost + 20}
        return revive_fields(robot, ctx, 100 if robot['role'] == 'heavy' else 200)
    return ROLES[robot['role']](robot, ctx)


def pause_tipped(robot, fields):
    """Stop pushing while tipped, allowing rescue or the chassis' own righting mechanism."""
    if robot['role'] == 'aerial' or not robot['alive']:
        return fields
    if robot.get('tipped'):
        fields.update(move=(0, 0), brake=True, fire=False)
        fields.pop('power', None)
        return fields
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
