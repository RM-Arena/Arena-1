"""GPT-6.1 Sol xhigh RMUC 2027 controller.

Built from the project's public mechanism baseline. The tactical layer adds
coordinated control-point assignments, fire discipline, replenishment and
role-aware combat. All information comes from the documented observation.
This file is embedded verbatim in self-contained, hashed submissions.
"""
import math
from sdk import (action, aim_at, aim_pitch, assembly_work_point, ballistic_reachable, can_fire,
                 drones, instant_revive_cost, navigate, rescue_point, resource_pickup_point,
                 tipped_teammates, workbench_point, zone_center, muzzle_speed, point_in_polygon, _aim_target, _rotate)

STYLE = "control"

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
    """Navigate to `goal`. The chassis draws on its supercap (`power`) while it is slow
    under a move order: the 2027 heavy robot has only 50 W for slopes and steps."""
    if goal is None or distance(robot, goal) <= tolerance:
        return {'move': (0, 0)}
    fields = unstick(robot, navigate(robot, goal, obs['arena']), memory, obs['time'])
    # Spend the supercap only when stalled (a slope or step); the referee firmware already
    # backs the drive on the road bumps, and a drained cap would strand the robot there.
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
    obs, team = ctx.obs, ctx.team
    memory = ctx.state.setdefault('heavy', {})
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

def infantry_job(robot, ctx):
    """striker: take the enemy outpost position; flex: shoot structures and escort; guard."""
    mates = sorted((r for r in ctx.obs['robots'] if r['role'] == 'infantry'),
                   key=lambda r: (r.get('chassis_type') == 'wheel_legged' and not
                       ctx.obs['robot_models'].get(str(r.get('model_slot')), {}).get('capabilities', {}).get('self_righting'),
                       -r.get('speed_reference_mps', 0), r['slot']))
    return 'striker' if mates and robot['slot'] == mates[0]['slot'] else 'flex'


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

def sentry(robot, ctx):
    obs, team = ctx.obs, ctx.team
    memory = ctx.state.setdefault('sentry', {})
    fields = {}
    # Holding the card matters more than rations: while our outpost position is held only
    # by our presence, leaving it for 5 s hands it to the enemy. Ammo is bought remotely;
    # the rations are collected when the sentry has to heal at the supply zone anyway.
    covered = any(r['alive'] and not r['weak'] and r['slot'] != robot['slot'] and r['role'] != 'aerial'
                  and r['hp'] >= r['max_hp'] * .4 and on_outpost_card(r, team, ctx) for r in obs['robots'])
    if robot['ammo'] < 30 and ctx.time > 20:
        memory['resupply'] = True
    if robot['ammo'] >= 100:
        memory.pop('resupply', None)
    recovery = recovery_goal(robot, ctx)
    if recovery and (covered or ctx.controls(f'{team}_outpost', full=True)):
        goal = recovery
    elif memory.get('resupply') and ctx.controls(f'{team}_outpost', full=True):
        goal = outpost_card_spot(ctx, team)
    elif memory.get('resupply') and robot['ammo'] == 0 and covered:
        goal = ctx.zone(team, 'supply')
    elif STYLE == 'pressure' and covered and ctx.controls(f'{team}_outpost', full=True):
        goal = ctx.zone(ctx.enemy, 'central')
    else:
        goal = ctx.zone(team, 'central')
        if STYLE == 'fortress':
            goal = (goal[0], goal[1] + (1.1 if team == 'red' else -1.1))
        own_card = obs.get('zones', {}).get(f'{team}_central', {})
        opposite = obs.get('zones', {}).get(f'{ctx.enemy}_central', {})
        if own_card.get('owner') != team and opposite.get('owner') == ctx.enemy:
            goal = outpost_card_spot(ctx, team, 1)
    moving = distance(robot, goal) > .6
    fields.update(drive(robot, goal, obs, ctx.memory, .3))
    shot = weapon(robot, ctx, reach=10)
    fields.update(shot)
    threatened = ctx.time - robot.get('last_damage_time', -99) < 2.0
    if robot['hp'] < robot['max_hp'] * .5 and threatened:
        wanted = 'defense'
    elif robot['ammo'] > 0 and any(e['alive'] and not e.get('invulnerable') and distance(robot, (e['x'], e['y'])) < 9 for e in obs['enemies']):
        wanted = 'attack'
    elif moving and distance(robot, goal) > 4:
        wanted = 'move'
    else:
        wanted = 'defense'
    if wanted != robot.get('posture') and ctx.time >= (robot.get('posture_ready_at') or 0):
        fields['posture'] = wanted
    enhanced = wanted == 'defense' and robot['hp'] < robot['max_hp'] * .3 and threatened
    if wanted == 'attack' and robot['ammo'] >= 120 and sum(e['alive'] and distance(robot, (e['x'], e['y'])) < 5 for e in obs['enemies']) >= 2:
        enhanced = True
    if bool(robot.get('posture_enhanced')) != enhanced and ctx.time >= (robot.get('posture_ready_at') or 0):
        fields['posture_enhanced'] = enhanced
    memory['last'] = wanted
    # The sentry holds the card without ammo too, so it rebuys remotely with a small reserve.
    fields.update(ammo_fields(robot, ctx, 40, 100, 100, 50))
    if robot['hp'] < robot['max_hp'] * .7 and disengaged(robot, ctx.time) and not robot.get('pending_heal') and ctx.coins >= 180:
        fields['remote_heal'] = True
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


"""Triple serial-leg assault layer, appended to the standalone 2027 controller.

The two 305 infantry and 2772 sentry deliberately contest forward ground while
healthy. Public observations alone drive the bounded highland jump sequence.
"""
from sdk import terrain_height

_CoreContext = Context
_core_drive = drive
_core_heavy = heavy


class Context(_CoreContext):
    def __init__(self, obs, state):
        super().__init__(obs, state)
        # A small control lead never recalls healthy assault units.
        self.hold_lead = False


def local_point(team, point):
    return point if team == 'red' else (28 - point[0], 15 - point[1])


def serial_leg(robot, obs):
    model = obs['robot_models'].get(str(robot.get('model_slot')), {})
    return model.get('leg_type') == 'serial'


def leg_memory(robot, obs, memory):
    return memory.setdefault('serial', {}).setdefault(str(robot['slot']), {'last_jump': -10.})


def pointed_move(robot, goal, speed):
    dx, dy = goal[0] - robot['x'], goal[1] - robot['y']
    d = math.hypot(dx, dy)
    if d < .12:
        return {'move': (0, 0), 'brake': True}
    course = math.atan2(dy, dx)
    heading = course
    if abs(wrap(course + math.pi - robot['heading'])) < abs(wrap(course - robot['heading'])):
        heading += math.pi
    error = abs(wrap(heading - robot['heading']))
    pace = min(speed, d * 2) / robot['speed_reference_mps']
    pace *= max(.08, math.cos(min(error, math.pi / 2)) ** 2)
    return {'move': (dx / d * pace, dy / d * pace), 'heading': heading, 'brake': True}


def highland_entry(robot, ctx):
    """Once per deployment: run-up, square up, crouch and hop over both kerbs.

    The approach skirts the fortress. Three distinct lanes and a sentry delay
    avoid queueing on one landing. A 17 s attempt limit releases a failed route.
    """
    m = leg_memory(robot, ctx.obs, ctx.memory)
    if not robot['alive']:
        m.pop('entry', None)
        return None
    if robot.get('weak') or robot['hp'] < robot['max_hp'] * .55:
        m['entry_done'] = True
        return None
    x, y = local_point(ctx.team, (robot['x'], robot['y']))
    if m.get('entry_done') or x > 11.2:
        m['entry_done'] = True
        return None
    # Respawning behind the frontline opens another bounded attempt.
    if 'entry' not in m:
        m['entry'] = {'phase': 0, 'since': ctx.time, 'began': ctx.time}
    q = m['entry']
    if ctx.time - q['began'] > 17:
        m['entry_done'] = True
        return None
    slot = robot['slot']
    row = 8.85 if slot == 4 else 6.15
    lane = {3: 7.0, 4: 8.1, 7: 7.55}.get(slot, 7.55)
    if slot == 7 and ctx.time < 2.5:
        return {'move': (0, 0), 'brake': True, 'leg_height': .18}
    if q['phase'] == 0:
        goal = (7.8, row)
        if math.hypot(x - goal[0], y - goal[1]) < .25:
            q.update(phase=1, since=ctx.time)
    elif q['phase'] == 1:
        goal = (8.25, lane)
        if math.hypot(x - goal[0], y - goal[1]) < .25:
            q.update(phase=2, since=ctx.time)
    elif q['phase'] == 2:
        if ctx.time - q['since'] >= .7:
            q.update(phase=3, since=ctx.time)
        return {'move': (0, 0), 'heading': 0 if ctx.team == 'red' else math.pi,
                'brake': True, 'leg_height': .18}
    else:
        goal = (11.55, lane)
        if x > 11.2:
            m['entry_done'] = True
            return None
    fields = pointed_move(robot, local_point(ctx.team, goal), 1.65 if q['phase'] < 2 else 1.2)
    fields.update(leg_height=.18, power=180)
    if q['phase'] == 3 and 8.7 < x < 10.6 and robot.get('grounded') and ctx.time - m['last_jump'] > 1.15:
        fields['jump'] = 1.
        m['last_jump'] = ctx.time
    return fields


def road_exit(robot, obs):
    """Leave a bump band along the current axle before attempting any turn.

    Heading toward the field boundary is rejected; reverse is valid for these
    serial legs. This also avoids indefinite spinning at the far corner.
    """
    band = next((t for t in obs['arena'].get('terrain', []) if t.get('kind') == 'bumps' and
                 t['x'] - .20 < robot['x'] < t['x'] + t['w'] + .20 and
                 t['y'] - .20 < robot['y'] < t['y'] + t['h'] + .20), None)
    if band is None:
        return None
    owner = 'red' if band['id'].startswith('red_') else 'blue'
    x, y = local_point(owner, (robot['x'], robot['y']))
    # Normalize either side's public 2027 road band, including the enemy side
    # encountered on a fortress assault. Its north edge is the field boundary.
    if not (5.05 < x < 7.85 and 12.71 < y < 15.):
        return None
    sign = 1 if owner == 'red' else -1
    hx, hy = math.cos(robot['heading']) * sign, math.sin(robot['heading']) * sign
    candidates = []
    for direction in (1, -1):
        dx, dy = hx * direction, hy * direction
        hits = []
        if dx > 1e-5: hits.append(((7.95 - x) / dx, 'exit'))
        if dx < -1e-5: hits.append(((4.95 - x) / dx, 'exit'))
        if dy < -1e-5: hits.append(((12.60 - y) / dy, 'exit'))
        if dy > 1e-5: hits.append(((14.70 - y) / dy, 'boundary'))
        hits = [(max(0., d), kind) for d, kind in hits if d > -.3]
        if hits:
            d, kind = min(hits)
            if kind == 'exit': candidates.append((d, direction))
    if not candidates:
        return None
    _, direction = min(candidates)
    # Bumps require full command; creeping at a waypoint can strand the wheels.
    pace = 1.
    return {'move': (direction * math.cos(robot['heading']) * pace,
                     direction * math.sin(robot['heading']) * pace),
            'heading': robot['heading'], 'brake': True, 'leg_height': .245}


def drive(robot, goal, obs, memory, tolerance=.25):
    fields = _core_drive(robot, goal, obs, memory, tolerance)
    if not serial_leg(robot, obs):
        return fields
    fields.update(leg_height=.245, brake=True)
    escape = road_exit(robot, obs)
    if escape is not None and goal is not None and distance(robot, goal) > tolerance:
        return escape
    move = fields['move']
    length = math.hypot(*move)
    if length < .01 or robot.get('tipped'):
        return fields
    # Explicit bump escape headings supplied by the SDK must survive this layer.
    heading = fields.get('heading', getattr(move, 'heading', None))
    course = math.atan2(move[1], move[0])
    if heading is None:
        heading = min((course, course + math.pi), key=lambda h: abs(wrap(h - robot['heading'])))
        error = abs(wrap(heading - robot['heading']))
        pace = min(length, 2.65 / robot['speed_reference_mps']) * max(.08, math.cos(min(error, math.pi / 2)) ** 2)
        fields['move'] = (move[0] / length * pace, move[1] / length * pace)
    fields['heading'] = heading
    ux, uy = move[0] / length, move[1] / length
    ground = terrain_height(obs['arena'], robot['x'], robot['y'])
    ahead = terrain_height(obs['arena'], robot['x'] + ux * .55, robot['y'] + uy * .55)
    m = leg_memory(robot, obs, memory)
    rise = ahead - ground
    if abs(rise) > .10:
        fields['leg_height'] = .18
        pace = min(math.hypot(*fields['move']), 1.5 / robot['speed_reference_mps'])
        fields['move'] = (ux * pace, uy * pace)
    aligned = abs(wrap(fields['heading'] - robot['heading'])) < .20
    healthy = not robot.get('weak') and robot['hp'] >= robot['max_hp'] * .55
    if .12 <= rise <= .31 and healthy and aligned and robot.get('grounded') \
            and math.hypot(robot['vx'], robot['vy']) > .45 and obs['time'] - m['last_jump'] > 1.15 \
            and goal is not None and distance(robot, goal) > .8:
        fields.update(jump=1., power=180)
        m['last_jump'] = obs['time']
    return fields


def recovery_goal(robot, ctx):
    """Withdraw below 32%; stay in recovery until 80% to avoid yo-yo retreats."""
    memory = ctx.state.setdefault('recovery', {})
    key = str(robot['slot'])
    if robot.get('weak') or robot['hp'] < robot['max_hp'] * .32:
        memory[key] = True
    if robot['hp'] >= robot['max_hp'] * .80 and not robot.get('weak'):
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
            goals.append(outpost_card_spot(ctx, owner, 1 if robot['slot'] == 7 else 0))
    return min(goals, key=lambda p: distance(robot, p))


def assault_goal(robot, ctx):
    """Three forward assignments; a single nearest unit recaptures a lost home point."""
    slot = robot['slot']
    anchor = next((r for r in ctx.obs['robots'] if r['role'] == 'heavy' and r['alive'] and not r.get('weak')), None)
    anchor_close = anchor is not None and distance(anchor, outpost_card_spot(ctx, ctx.team)) < 2.
    if not ctx.controls(f'{ctx.team}_outpost') and not anchor_close:
        available = [r for r in ctx.obs['robots'] if r['role'] in ('infantry', 'sentry') and r['alive']
                     and not r.get('weak') and r['hp'] >= r['max_hp'] * .4]
        home = outpost_card_spot(ctx, ctx.team)
        guard = min(available, key=lambda r: (distance(r, home), r['slot']), default=robot)
        if slot == guard['slot']:
            return home
    if slot == 3:
        return outpost_card_spot(ctx, ctx.enemy)
    if slot == 4:
        if ctx.time >= 180 and ctx.controls(f'{ctx.enemy}_outpost') and enemy_point_covered(ctx, slot):
            return ctx.zone(ctx.enemy, 'fortress')
        return ctx.zone(ctx.enemy, 'central')
    # Sentry takes a separate approach to the outpost and covers its infantry partner.
    if ctx.controls(f'{ctx.enemy}_outpost') and not any(r['slot'] == 4 and r['alive'] and
            on_outpost_card(r, ctx.enemy, ctx) for r in ctx.obs['robots']):
        return ctx.zone(ctx.enemy, 'central')
    return outpost_card_spot(ctx, ctx.enemy, 1)


def assault(robot, ctx):
    fields = {}
    if ctx.obs['tick'] == 0 and robot['role'] == 'infantry':
        fields['profile'] = {'chassis': robot['chassis_profile'], 'weapon': robot['weapon_profile']}
    fields.update(ammo_fields(robot, ctx, 35, 120, 100, 80 if robot['role'] == 'infantry' else 40))
    recovery = recovery_goal(robot, ctx)
    goal = recovery or assault_goal(robot, ctx)
    entry = None if recovery else highland_entry(robot, ctx)
    if ctx.time < 1.2:
        fields.update(move=(0, 0))
    else:
        fields.update(entry if entry is not None else drive(robot, goal, ctx.obs, ctx.memory, .22))
    fields.update(weapon(robot, ctx, reach=10 if robot['role'] == 'sentry' else 9, structures=not bool(recovery)))
    if robot['hp'] < robot['max_hp'] * .78 and disengaged(robot, ctx.time) \
            and not robot.get('pending_heal') and ctx.coins >= 180:
        fields['remote_heal'] = True
    if robot['role'] == 'sentry':
        threatened = ctx.time - robot.get('last_damage_time', -99) < 2
        fighting = any(e['alive'] and distance(robot, (e['x'], e['y'])) < 9 for e in ctx.obs['enemies'])
        wanted = 'defense' if recovery and threatened else 'attack' if fighting else 'move' if distance(robot, goal) > 3 else 'defense'
        if ctx.time >= (robot.get('posture_ready_at') or 0):
            if wanted != robot.get('posture'):
                fields['posture'] = wanted
            enhanced = wanted == 'attack' and robot['ammo'] > 120 and robot['hp'] > robot['max_hp'] * .55 and fighting
            if bool(robot.get('posture_enhanced')) != enhanced:
                fields['posture_enhanced'] = enhanced
    return fields


def heavy_post(ctx):
    # The outpost card remains eligible when the opposite central card is blocked.
    return outpost_card_spot(ctx, ctx.team)


def heavy_anchor(robot, ctx):
    """A fourth ground unit anchors home so all three serial legs can attack.

    A technology trip costs too much uncontested control with this all-forward
    lineup. Fit the timed launcher only when the home point is fully secured.
    """
    recovery = recovery_goal(robot, ctx)
    if recovery:
        return drive(robot, recovery, ctx.obs, ctx.memory, .2)
    if robot.get('launcher') in ('unlocked', 'installing') and ctx.controls(f'{ctx.team}_outpost', full=True):
        bench = workbench_point(robot, ctx.arena)
        fields = drive(robot, bench, ctx.obs, ctx.memory, .2)
        if distance(robot, bench) < .25:
            fields.update(move=(0, 0), brake=True, install_launcher=True)
            fields.update(ammo_fields(robot, ctx, 8, 20, 10, 60))
        return fields
    goal = heavy_post(ctx)
    fields = drive(robot, goal, ctx.obs, ctx.memory, .20)
    if robot.get('launcher') in ('fitted', 'installed'):
        fields.update(ammo_fields(robot, ctx, 3, 20, 10, 60))
        fields.update(weapon(robot, ctx, reach=12))
    return fields


ROLES.update(infantry=assault, sentry=assault, heavy=heavy_anchor)

_core_decide = decide


def decide(robot, ctx):
    if robot['role'] in ('infantry', 'sentry') and not robot['alive']:
        m = leg_memory(robot, ctx.obs, ctx.memory)
        m.pop('entry', None)
        m.pop('entry_done', None)
    return _core_decide(robot, ctx)


"""GPT-6.1-Sol-Max serial-leg competition controller.

Uses the public GPT controller and serial-leg locomotion as a mechanical base.
The allocation, combat, logistics and recovery layer below is authored for this
submission; it reads only the normal policy observation.
"""

_max_base_context = Context
_max_base_drive = drive


def max_clear(start, goal, arena, team):
    """Fast segment checks against public solid geometry, with downhill access.

    The generic router rejects a 30 cm drop as well as a 30 cm climb. Serial
    legs can step off the deck safely; sending them around the road instead
    strands them in its humps. Uphill edges still require the jump controller.
    """
    dx, dy = goal[0] - start[0], goal[1] - start[1]
    walls = [w for w in arena['obstacles'] if 'roof' not in w.get('id', '') or '_tunnel_roof' in w['id']]
    walls += [w for w in arena['forbidden'] if w['kind'] in ('base', 'dart_station')
              or w.get('owner') not in (None, team)]
    for wall in walls:
        angle = wall.get('rotation', 0)
        c, s = math.cos(angle), math.sin(angle)
        cx, cy = wall['x'] + wall['w'] / 2, wall['y'] + wall['h'] / 2
        ax, ay = (start[0] - cx) * c + (start[1] - cy) * s, \
                 -(start[0] - cx) * s + (start[1] - cy) * c
        vx, vy = dx * c + dy * s, -dx * s + dy * c
        hw, hh = wall['w'] / 2 + .29, wall['h'] / 2 + .29
        # A robot pushed into the clearance margin must be able to leave it.
        if abs(ax) < hw and abs(ay) < hh:
            if max(abs(ax + vx) - hw, abs(ay + vy) - hh) > max(abs(ax) - hw, abs(ay) - hh):
                continue
        lo, hi = 0., 1.
        for p, d, half in ((ax, vx, hw), (ay, vy, hh)):
            if abs(d) < 1e-9:
                if not -half < p < half:
                    lo = 2.
                    break
            else:
                a, b = sorted(((-half - p) / d, (half - p) / d))
                lo, hi = max(lo, a), min(hi, b)
        if lo < hi and hi > 0 and lo < 1:
            return False
    count = max(1, math.ceil(math.hypot(dx, dy) / .2))
    previous = terrain_height(arena, *start)
    for i in range(1, count + 1):
        height = terrain_height(arena, start[0] + dx * i / count, start[1] + dy * i / count)
        if height - previous > .13 or previous - height > .45:
            return False
        previous = height
    return True


def drive(robot, goal, obs, memory, tolerance=.25):
    if serial_leg(robot, obs) and goal is not None and distance(robot, goal) > tolerance:
        escape = road_exit(robot, obs)
        if escape is not None:
            return escape
    if serial_leg(robot, obs) and goal is not None and \
            max_clear((robot['x'], robot['y']), goal, obs['arena'], robot['team']):
        fields = pointed_move(robot, goal, 2.6)
        fields.update(leg_height=.245, brake=True)
        return fields
    return _max_base_drive(robot, goal, obs, memory, tolerance)


class Context(_max_base_context):
    def __init__(self, obs, state):
        super().__init__(obs, state)
        self.hold_lead = False
        self.budget = self.coins
        self.ammo_remaining = max(0, 1000 - self.economy.get('purchased_17', 0))


def max_local(ctx, point):
    return local_point(ctx.team, point)


def max_hold(robot, goal, ctx, tolerance=.18):
    if distance(robot, goal) < tolerance:
        fields = {'move': (0, 0), 'brake': True}
        if serial_leg(robot, ctx.obs):
            fields['leg_height'] = .245
        return fields
    return drive(robot, goal, ctx.obs, ctx.memory, tolerance)


def highland_entry(robot, ctx):
    """Crouch before the run-up and launch before the first vertical edge.

    Late jumps collide with the first step, and .18 m legs do not tuck enough
    to clear the rim reliably. The two infantry approach separate sides of
    the fortress; the sentry follows in the middle after the first wave.
    """
    m = leg_memory(robot, ctx.obs, ctx.memory)
    x, y = local_point(ctx.team, (robot['x'], robot['y']))
    if m.get('entry_done') or x > 10.75:
        m['entry_done'] = True
        return None
    q = m.setdefault('entry', {'phase': 0, 'since': ctx.time, 'began': ctx.time})
    if ctx.time - q['began'] > 24:
        m['entry_done'] = True
        return None
    lane = {3: 6.9, 4: 8.1, 7: 7.5}[robot['slot']]
    row = q.setdefault('row', 9.15 if y > 8.6 else 6.05)
    heading = 0 if ctx.team == 'red' else math.pi
    if robot['slot'] == 7 and ctx.time < 4:
        return {'move': (0, 0), 'brake': True, 'leg_height': .12}
    if q['phase'] == 0:
        if x < 4.2 and y > 10.5:
            fields = pointed_move(robot, max_local(ctx, (3.0, 10.0)), 1.8)
            fields.update(leg_height=.245, brake=True)
            return fields
        goal = (7.95, row)
        if math.hypot(x - goal[0], y - goal[1]) < .22:
            q.update(phase=1, since=ctx.time)
    elif q['phase'] == 1:
        goal = (8.0, lane)
        if math.hypot(x - goal[0], y - goal[1]) < .20:
            q.update(phase=2, since=ctx.time)
    elif q['phase'] == 2:
        if ctx.time - q['since'] >= .8:
            q.update(phase=3, since=ctx.time)
        return {'move': (0, 0), 'heading': heading, 'brake': True, 'leg_height': .12}
    else:
        goal = (11.55, lane)
    fields = pointed_move(robot, max_local(ctx, goal), 2.2 if q['phase'] == 3 else 2.0)
    fields.update(leg_height=.12, power=180, brake=True)
    if q['phase'] == 3:
        fields['heading'] = heading
        if robot.get('grounded') and 8.65 < x < 10.65 and ctx.time - m['last_jump'] > 1.1:
            fields['jump'] = 1.
            m['last_jump'] = ctx.time
    return fields


def max_logistics(robot, ctx):
    """Reserve shared coins immediately so simultaneous orders cannot overspend."""
    fields = {}
    cost = 50 + math.ceil(ctx.time / 60 * 20)
    reserve=0 if robot['role']=='heavy' and robot['hp']<robot['max_hp']*.6 else 100
    contacts=set(robot.get('last_raw_zones',[]))
    free_heal=f'{ctx.team}_supply' in contacts or any(f'{owner}_outpost' in contacts and ctx.controls(f'{owner}_outpost',full=True) for owner in (ctx.team,ctx.enemy))
    if not free_heal and robot['hp'] < robot['max_hp'] * .70 and disengaged(robot, ctx.time) \
            and not robot.get('pending_heal') and ctx.budget >= cost + reserve:
        fields['remote_heal'] = True
        ctx.budget -= cost
    if robot['role'] == 'heavy':
        return fields
    if robot['ammo'] < 25 and not robot.get('pending_ammo') and ctx.time >= 1.05:
        local = can_buy_here(robot, ctx)
        ammo_reserve=0 if local and robot['ammo']==0 else 50
        affordable=max(0,int(ctx.budget-ammo_reserve)//10*10)
        amount = min(100,ctx.ammo_remaining//10*10,affordable) if local else 100
        price = amount if local else 150
        if (local or disengaged(robot, ctx.time)) and ctx.budget >= price + ammo_reserve \
                and 0 < amount <= ctx.ammo_remaining:
            fields['buy_ammo'] = {'amount': amount, 'remote': not local}
            ctx.budget -= price
            ctx.ammo_remaining -= amount
    return fields


def max_shot_clear(robot, target, ctx):
    """Reject shots into terrain, solid cover and teammates before spending ammo."""
    tx, ty, tz = _aim_target(robot, target)
    ox, oy = robot['x'], robot['y']
    oz = robot.get('z', 0) + _rotate(robot.get('quaternion', (0, 0, 0, 1)),
        (0, 0, robot.get('muzzle_height_m', .47)))[2]
    length = math.hypot(tx - ox, ty - oy)
    if length < .35:
        return True
    flight = length / (muzzle_speed(robot) * .88)
    arc = .5 * 9.81 * flight * flight
    def height(u):
        return oz + (tz - oz) * u + arc * u * (1 - u)
    walls = list(ctx.arena['obstacles'])
    walls += [dict(w, bottom=0, height=1.1) for w in ctx.arena['forbidden'] if w['kind'] == 'base']
    dx, dy = tx - ox, ty - oy
    for w in walls:
        c, s = math.cos(w.get('rotation', 0)), math.sin(w.get('rotation', 0))
        cx, cy = w['x'] + w['w'] / 2, w['y'] + w['h'] / 2
        ax, ay = (ox - cx) * c + (oy - cy) * s, -(ox - cx) * s + (oy - cy) * c
        vx, vy = dx * c + dy * s, -dx * s + dy * c
        lo, hi = .22 / length, 1. - .05 / length
        for p, v, half in ((ax, vx, w['w'] / 2 + .012), (ay, vy, w['h'] / 2 + .012)):
            if abs(v) < 1e-9:
                if abs(p) > half:
                    lo = 2
                    break
            else:
                a, b = sorted(((-half - p) / v, (half - p) / v))
                lo, hi = max(lo, a), min(hi, b)
        if lo < hi:
            bottom, top = w.get('bottom', 0), w.get('bottom', 0) + w.get('height', 0)
            if any(bottom - .015 <= height(u) <= top + .015 for u in (lo, (lo + hi) / 2, hi)):
                return False
    for i in range(1, max(2, math.ceil(length / .3))):
        u = i / max(2, math.ceil(length / .3))
        if height(u) < terrain_height(ctx.arena, ox + dx * u, oy + dy * u) + .015:
            return False
    for friend in ctx.obs['robots']:
        if friend['id'] == robot['id'] or friend['role'] == 'aerial' or not friend['alive']:
            continue
        u = ((friend['x'] - ox) * dx + (friend['y'] - oy) * dy) / (length * length)
        if .04 < u < .96 and math.hypot(ox + dx * u - friend['x'], oy + dy * u - friend['y']) < .25 \
                and friend.get('z', 0) <= height(u) <= friend.get('z', 0) + .53:
            return False
    return True


def weapon(robot, ctx, reach=9., structures=False, drones_too=False):
    candidates = []
    for enemy in ctx.obs['enemies']:
        if not enemy['alive'] or enemy.get('invulnerable') or not enemy.get('targetable', True):
            continue
        gap = distance(robot, (enemy['x'], enemy['y']))
        if gap > reach:
            continue
        on_card = any(enemy['id'] in zone.get('occupants', []) for key, zone in ctx.obs['zones'].items()
            if key in (f'{ctx.team}_base', f'{ctx.team}_central', f'{ctx.enemy}_central'))
        score = enemy['hp'] + gap * 18 - (180 if on_card else 0)
        candidates.append((score, enemy))
    for _, target in sorted(candidates, key=lambda item: item[0]):
        if not max_shot_clear(robot, target, ctx):
            continue
        solution = firing_solution(robot, target)
        if solution is None:
            continue
        aim, pitch = solution
        actual_aim, actual_pitch = barrel_angles(robot)
        cone = max(.004, min(.05, .055 / max(.5, distance(robot, (target['x'], target['y'])))))
        aligned = abs(wrap(aim - actual_aim)) < cone and abs(pitch - actual_pitch) < cone
        # A policy command lasts two 50 ms frames. Reserve both 17 mm rounds,
        # including when a posture change reduces cooling before the shots.
        margin = 100 if robot['role'] == 'heavy' else 20
        fire = aligned and can_fire(robot) and robot['heat'] + margin <= robot['max_heat']
        return {'aim': aim, 'pitch': pitch, 'fire': fire}
    return {'fire': False}


def max_guard(robot, ctx):
    # Reach the protected rear receiver before the first enemy wave. Taking
    # the module trip first leaves the base open against fast native chassis.
    if ctx.time < 8:
        points = [max_local(ctx, p) for p in ((3.85, 5.8), (1.05, 5.8), (1.05, 7.5))]
        opening = ctx.state.setdefault('opening_base', {'i': 0, 'heading': robot['heading']})
        while opening['i'] < 2 and distance(robot, points[opening['i']]) < .2:
            opening['i'] += 1
        goal = points[opening['i']]
        dx, dy = goal[0] - robot['x'], goal[1] - robot['y']
        gap = math.hypot(dx, dy)
        pace = min(1.8, gap * 3) / robot['speed_reference_mps']
        return {'move': (dx / max(.01, gap) * pace, dy / max(.01, gap) * pace),
                'heading': opening['heading'], 'power': 200, 'brake': True}
    fields = max_logistics(robot, ctx)
    launcher = robot.get('launcher', 'locked')
    relief = any(r['slot'] != robot['slot'] and r['alive'] and not r.get('weak')
        and r['id'] in ctx.obs['zones'].get(f'{ctx.team}_base', {}).get('occupants', [])
        for r in ctx.obs['robots'])
    at_supply=f'{ctx.team}_supply' in robot.get('last_raw_zones',[])
    fitting=ctx.state.setdefault('launcher_trip',{})
    late_install=at_supply and relief and not robot.get('weak') and robot['hp']>=robot['max_hp']*.8 \
        and ctx.time>25 and ctx.time>=fitting.get('retry_at',0)
    if late_install:
        fitting.setdefault('since',ctx.time)
        if ctx.time-fitting['since']>8.:
            fitting.update(retry_at=ctx.time+45.);fitting.pop('since',None);late_install=False
    elif not at_supply:fitting.pop('since',None)
    if late_install and launcher in ('locked', 'unlocked', 'installing'):
        bench = workbench_point(robot, ctx.arena)
        fields.update(drive(robot, bench, ctx.obs, ctx.memory, .16))
        if distance(robot,bench)<1.5:fields['heading']=math.pi/2 if ctx.team=='red' else -math.pi/2
        if distance(robot, bench) < .24:
            fields.update(move=(0, 0), brake=True, install_launcher=True)
        return fields
    goal = max_local(ctx, (1.05, 7.5))
    recovering = ctx.state.setdefault('guard_recover', False)
    if robot.get('weak') or robot['hp'] < robot['max_hp'] * .28:
        recovering = True
    if robot['hp'] >= robot['max_hp'] * .85 and not robot.get('weak'):
        recovering = False
    ctx.state['guard_recover'] = recovering
    relief = any(r['slot'] != robot['slot'] and r['alive'] and not r.get('weak')
        and r['id'] in ctx.obs['zones'].get(f'{ctx.team}_base', {}).get('occupants', [])
        for r in ctx.obs['robots'])
    if recovering and relief:
        goal = ctx.zone(ctx.team, 'supply')
    fields.update(max_hold(robot, goal, ctx, .22))
    if launcher in ('fitted', 'installed'):
        if robot['ammo'] < 3 and can_buy_here(robot, ctx) and ctx.budget >= 100 \
                and ctx.economy.get('purchased_42', 0) <= 95:
            fields['buy_ammo'] = {'amount': 5, 'remote': False}
            ctx.budget -= 50
        fields.update(weapon(robot, ctx, reach=10, structures=False, drones_too=False))
    return fields


def max_route(robot, ctx, name, points):
    memory = ctx.state.setdefault('max_routes', {}).setdefault(str(robot['slot']), {})
    if memory.get('name') != name:
        memory.update(name=name, i=0, began=ctx.time)
    route = [max_local(ctx, p) for p in points]
    index = memory['i']
    while index + 1 < len(route) and distance(robot, route[index]) < .55:
        index += 1
    memory['i'] = index
    fields = max_hold(robot, route[index], ctx)
    x, _ = local_point(ctx.team, (robot['x'], robot['y']))
    if name == 'base' and index == 3 and 17.0 < x < 19.0:
        fields = pointed_move(robot, route[index], 2.2)
        fields.update(leg_height=.12, brake=True, power=180)
        m = leg_memory(robot, ctx.obs, ctx.memory)
        if robot.get('grounded') and ctx.time - m['last_jump'] > 1.1:
            fields['jump'] = 1.
            m['last_jump'] = ctx.time
    return fields


def max_homeward(robot, goal, ctx):
    x, y = local_point(ctx.team, (robot['x'], robot['y']))
    m = leg_memory(robot, ctx.obs, ctx.memory)
    if x < 9.2:
        m.pop('home_exit', None)
        if 4.2 < x and y > 11.4:
            return max_hold(robot, max_local(ctx, (4.4 if x < 5.0 else 8.3, 10.0)), ctx)
        return max_hold(robot, goal, ctx)
    exit_state = m.get('home_exit')
    if exit_state and (exit_state.get('fallback') or ctx.time - exit_state.get('began', ctx.time) > 8.):
        exit_state['fallback'] = True
        if distance(robot, goal) < .6:
            m.pop('home_exit', None)
            return max_hold(robot, goal, ctx)
        return max_route(robot, ctx, 'home_safe', [(12.0, 10.0), (12.0, 12.2),
            (12.0, 13.5), (10.8, 13.6), (8.2, 13.6), (8.2, 11.7), (8.2, 10.0),
            (4.4, 10.0), local_point(ctx.team, goal)])
    if x < 9.2 or (x < 9.9 and not m.get('home_exit')):
        m.pop('home_exit', None)
        return max_hold(robot, goal, ctx)
    if 9.9 < x < 12.5 and y >= 9.8:
        return max_hold(robot, max_local(ctx, (11.1, 9.7)), ctx)
    if 9.2 < x < (12.5 if m.get('home_exit') else 11.5) and 6.0 < y < 9.8:
        q = m.setdefault('home_exit', {'phase': 0, 'since': ctx.time, 'began': ctx.time})
        lane = {3: 6.9, 4: 8.1, 7: 7.5}[robot['slot']]
        waiting = q['phase'] < 2 and any(r['slot'] < robot['slot'] and r['slot'] in (3, 4, 7)
            and leg_memory(r, ctx.obs, ctx.memory).get('home_exit')
            and not leg_memory(r, ctx.obs, ctx.memory)['home_exit'].get('fallback')
            and 9.2 < local_point(ctx.team, (r['x'], r['y']))[0] < 12.5
            for r in ctx.obs['robots'])
        if waiting:
            q['began'] += ctx.obs.get('policy_dt', .1)
            return {'move': (0, 0), 'leg_height': .12, 'brake': True}
        if q['phase'] == 0:
            center = max_local(ctx, (12.15, lane))
            fields = pointed_move(robot, center, 1.5)
            fields.update(leg_height=.12, brake=True)
            if distance(robot, center) < .2:
                q.update(phase=1, since=ctx.time)
            return fields
        if q['phase'] == 1:
            heading = math.pi if ctx.team == 'red' else 0.
            if ctx.time - q['since'] > .65 and abs(wrap(heading - robot['heading'])) < .12:
                q.update(phase=2, since=ctx.time)
            return {'move': (0, 0), 'leg_height': .12, 'brake': True, 'heading': heading}
        fields = pointed_move(robot, max_local(ctx, (8.0, lane)), 2.2)
        fields.update(leg_height=.12, brake=True, power=180)
        if robot.get('grounded') and x < 10.7 and ctx.time - m['last_jump'] > 1.1:
            fields['jump'] = 1.
            m['last_jump'] = ctx.time
        return fields
    if x > 11.5:
        # A natural revive happens at the wreck, including on our half of the
        # deck. Do not send that robot back to the far-side route entrance.
        if x < 15.5:
            return max_hold(robot, max_local(ctx, (11.1, 9.7)), ctx)
        return max_route(robot, ctx, 'homeward', [(16.4, 9.7), (11.1, 9.7), (10.9, 8.3)])
    leg_memory(robot, ctx.obs, ctx.memory).pop('home_exit', None)
    return max_hold(robot, goal, ctx)


def max_fighter(robot, ctx):
    fields = max_logistics(robot, ctx)
    if ctx.obs['tick'] == 0 and robot['role'] == 'infantry':
        fields['profile'] = {'chassis': 'hp', 'weapon': 'cooling'}
    recovery = ctx.state.setdefault('max_recovery', {})
    key = str(robot['slot'])
    recovering = recovery.get(key, False)
    due_grants = int(ctx.time // 60) - robot.get('supply_grants_taken', 0)
    covered = any(r['slot'] != robot['slot'] and r['alive'] and not r.get('weak')
        and r['hp'] > r['max_hp'] * .6 and on_outpost_card(r, ctx.enemy, ctx)
        for r in ctx.obs['robots'])
    on_home = on_outpost_card(robot, ctx.team, ctx)
    on_front = on_outpost_card(robot, ctx.enemy, ctx)
    home_relief = any(r['slot'] != robot['slot'] and r['alive'] and not r.get('weak')
        and r['hp'] > r['max_hp'] * .6 and on_outpost_card(r, ctx.team, ctx)
        for r in ctx.obs['robots'])
    expendable = (not on_home or home_relief) and (not on_front or covered)
    if robot.get('weak') or robot['hp'] < robot['max_hp'] * .24 and expendable:
        recovering = True
    if robot['role'] == 'sentry' and robot['ammo'] < 20 and due_grants > 0 \
            and (covered or home_relief):
        recovering = True
    supply = max_supply_point(robot, ctx)
    needs_grant = robot['role'] == 'sentry' and robot['ammo'] < 100 and due_grants > 0
    contacts = set(robot.get('last_raw_zones', []))
    local_heal = any(f'{owner}_outpost' in contacts and ctx.controls(f'{owner}_outpost', full=True)
                     for owner in (ctx.team, ctx.enemy))
    if recovering and robot['hp'] >= robot['max_hp'] * .85 and not robot.get('weak') \
            and (robot['role'] != 'sentry' or robot['ammo'] >= 100 or due_grants <= 0) \
            and robot.get('grounded',True) \
            and not leg_memory(robot,ctx.obs,ctx.memory).get('nav_jump') \
            and not leg_memory(robot,ctx.obs,ctx.memory).get('rim_hop'):
        recovering = False
        leg_memory(robot, ctx.obs, ctx.memory).clear()
        leg_memory(robot, ctx.obs, ctx.memory)['last_jump'] = -10.
        ctx.state.get('max_routes', {}).pop(key, None)
    recovery[key] = recovering
    if recovering:
        hospitals = [supply]
        if not needs_grant:
            hospitals.extend(outpost_card_spot(ctx, owner) for owner in (ctx.team, ctx.enemy)
                             if ctx.controls(f'{owner}_outpost', full=True))
        hospital = (robot['x'], robot['y']) if local_heal and not needs_grant else min(hospitals, key=lambda p: distance(robot, p))
        fields.update(max_homeward(robot, hospital, ctx))
    elif ctx.time < 1.2:
        fields.update(move=(0, 0), brake=True)
    else:
        entry = highland_entry(robot, ctx)
        if entry is not None:
            fields.update(entry)
        elif robot['slot'] == 4:
            heavy_robot = next((r for r in ctx.obs['robots'] if r['role'] == 'heavy'), None)
            cover = ctx.state.get('base_cover', False)
            was_covering = cover
            if not ctx.controls(f'{ctx.team}_base') or heavy_robot is None or not heavy_robot['alive'] \
                    or heavy_robot.get('weak') or heavy_robot['hp'] < heavy_robot['max_hp'] * .5 \
                    or ctx.state.get('guard_recover'):
                cover = True
            if heavy_robot is not None and heavy_robot['alive'] and not heavy_robot.get('weak') \
                    and (heavy_robot['hp'] >= heavy_robot['max_hp'] * .8 or
                         ctx.state.get('guard_secure') and heavy_robot['hp']>=heavy_robot['max_hp']*.2) \
                    and f'{ctx.team}_base' in heavy_robot.get('last_raw_zones', []):
                cover = False
            ctx.state['base_cover'] = cover
            if was_covering and not cover:
                m = leg_memory(robot, ctx.obs, ctx.memory)
                m.pop('entry_done', None)
                m.pop('entry', None)
            goal = max_local(ctx, (3.8, 8.15) if cover else (10.8, 9.25))
            fields.update(max_homeward(robot, goal, ctx) if cover else max_hold(robot, goal, ctx))
        elif robot['slot'] == 7:
            fields.update(max_hold(robot, max_local(ctx, (17.4, 8.1)), ctx))
        else:
            # Do not sink a healthy infantry into a base card kept active by
            # an entrenched defender. Win the two-outpost clock with a 2-v-1
            # force first; take the +3 route when the public card is vacated.
            enemy_base_active = ctx.enemy in ctx.positions.get(f'{ctx.enemy}_base', {}).get('active', [])
            route = ctx.state.get('max_routes', {}).get(str(robot['slot']), {})
            committed = route.get('name') in ('base', 'base_flank') and route.get('i', 0) >= 1 \
                and (ctx.time - route.get('began', ctx.time) < 65 or ctx.controls(f'{ctx.enemy}_base'))
            if not committed and enemy_base_active and not ctx.controls(f'{ctx.team}_outpost') \
                    and ctx.controls(f'{ctx.enemy}_outpost'):
                fields.update(max_homeward(robot, max_local(ctx, (10.85, 7.3)), ctx)
                    if local_point(ctx.team, (robot['x'], robot['y']))[0] > 11.5
                    else max_hold(robot, max_local(ctx, (10.85, 7.3)), ctx))
            elif not committed and enemy_base_active:
                fields.update(max_hold(robot, max_local(ctx, (17.1, 5.8)), ctx))
            else:
                # The end ramp and the narrow corridor between the enemy
                # tunnel and road humps avoid the defended central card.
                fields.update(max_route(robot, ctx, 'base_flank',
                    [(11.8, 5.3), (16.2, 3.0), (16.2, 1.0), (19.7, 1.0),
                     (19.7, 3.4), (20.0, 4.85), (23.7, 4.85), (26.8, 4.4), (27.0, 7.5)]))
    fields.update(weapon(robot, ctx, reach=10, structures=False, drones_too=False))
    if robot['role'] == 'sentry':
        fighting = bool(fields.get('fire')) or any(e['alive'] and not e.get('invulnerable')
            and distance(robot, (e['x'], e['y'])) < 8 for e in ctx.obs['enemies'])
        wanted = 'attack' if fighting and robot['hp'] > robot['max_hp'] * .60 else 'defense'
        if math.hypot(*fields.get('move', (0, 0))) > .05 and not fighting:
            wanted = 'move'
        if ctx.time >= (robot.get('posture_ready_at') or 0):
            fields['posture'] = wanted
            fields['posture_enhanced'] = wanted == 'defense' and \
                ctx.time - robot.get('last_damage_time', -99) < 1 and robot['hp'] < robot['max_hp'] * .60
    return fields


ROLES.update(heavy=max_guard, infantry=max_fighter, sentry=max_fighter)


def revive_fields(robot, ctx, reserve=150):
    cost = instant_revive_cost(robot, ctx.time)
    affordable = ctx.time < 350 and ctx.budget >= cost + 180
    if affordable:
        ctx.budget -= cost
    if not robot['alive']:
        ctx.state.get('max_routes', {}).pop(str(robot['slot']), None)
    return {'revive': affordable}


"""Public-geometry routing for serial legs; embedded by the Sol Max builder."""
import heapq
from sdk import ARENAS_BY_SEASON, _terrain_surface


class SerialRoadmap:
    def __init__(self, arena, team):
        self.arena, self.team = arena, team
        margin = .29
        self.boxes = []
        walls = [w for w in arena['obstacles'] if 'roof' not in w.get('id', '') or '_tunnel_roof' in w['id']]
        walls += [w for w in arena['forbidden'] if w['kind'] in ('base', 'dart_station', 'highway') or w.get('owner') not in (None, team)]
        self.circles=[(x,y,.62) for x,y in arena['outposts'].values()]
        walls += [dict(x=t['x'],y=t['y'],w=t['w'],h=t['h']) for t in arena['terrain'] if t['kind']=='bumps']
        for w in walls:
            angle = w.get('rotation', 0)
            self.boxes.append((w['x']+w['w']/2,w['y']+w['h']/2,
                w['w']/2+margin,w['h']/2+margin,math.cos(angle),math.sin(angle)))
        self.tiles = {}
        for t in arena['terrain']:
            for x in range(math.floor(t['x']),math.ceil(t['x']+t['w'])+1):
                for y in range(math.floor(t['y']),math.ceil(t['y']+t['h'])+1):
                    self.tiles.setdefault((x,y),[]).append(t)
        # Floor corridors, end ramps and both sides of the base body. No node
        # lies on the road humps or under a tunnel roof.
        red = [(1.1,7.5),(1.1,10.0),(2.9,10.0),(3.0,5.5),(3.0,10.4),(3.8,8.15),
            (4.4,10.0),(4.5,11.5),(4.5,13.5),(5.0,5.4),(7.9,5.9),(7.95,9.25),
            (8.0,7.5),(8.3,10.0),(8.3,11.5),(8.3,13.55),(10.8,13.55),(12.0,13.5),
            (12.0,12.2),(11.8,10.0),(11.4,10.55),(10.8,9.25),(11.5,9.7),(11.5,7.5),
            (11.8,5.3),(12.0,5.0),(16.2,3.0),(16.2,1.0),(19.7,1.0),(19.7,3.4),
            (20.0,4.85),(23.7,4.85),(26.9,4.4),(27.0,7.5)]
        self.nodes = list(dict.fromkeys(red+[(28-x,15-y) for x,y in red]))
        self.edges = [[] for _ in self.nodes]
        for i,a in enumerate(self.nodes):
            for j,b in enumerate(self.nodes):
                length=math.dist(a,b)
                if i!=j and length<7 and self.clear(a,b):
                    self.edges[i].append((j,length))
        self.special={}
        for a,b,kind in [((8.,7.5),(11.5,7.5),'highland'),
                         ((11.5,7.5),(8.,7.5),'highland'),
                         ((8.3,11.5),(8.3,13.55),'road'),
                         ((8.3,13.55),(8.3,11.5),'road')]:
            for start,end in ((a,b),((28-a[0],15-a[1]),(28-b[0],15-b[1]))):
                for point in (start,end):
                    if point in self.nodes:continue
                    n=len(self.nodes);self.nodes.append(point);self.edges.append([])
                    for old,other in enumerate(self.nodes[:-1]):
                        length=math.dist(point,other)
                        if length>=7:continue
                        if self.clear(point,other):self.edges[n].append((old,length))
                        if self.clear(other,point):self.edges[old].append((n,length))
                i,j=self.nodes.index(start),self.nodes.index(end)
                self.edges[i].append((j,math.dist(start,end)+1.8));self.special[i,j]=kind
        self.reverse=[[] for _ in self.nodes]
        for i,edges in enumerate(self.edges):
            for j,d in edges:self.reverse[j].append((i,d))
        self.costs = {}

    def height(self, x, y):
        h=0.
        for t in self.tiles.get((math.floor(x),math.floor(y)),[]):
            if t['x']<=x<=t['x']+t['w'] and t['y']<=y<=t['y']+t['h'] and point_in_polygon(x,y,t['polygon']):
                h=max(h,_terrain_surface(t,x,y))
        return h+min(y,15-y)*math.tan(math.radians(self.arena.get('floor_slope_deg',0)))

    def clear(self, a, b, escape=False):
        dx,dy=b[0]-a[0],b[1]-a[1]
        length2=dx*dx+dy*dy
        for x,y,radius in self.circles:
            if escape and math.dist(a,(x,y))<radius and (a[0]-x)*dx+(a[1]-y)*dy>=0:continue
            u=max(0.,min(1.,((x-a[0])*dx+(y-a[1])*dy)/max(1e-9,length2)))
            if math.hypot(a[0]+dx*u-x,a[1]+dy*u-y)<radius:return False
        for cx,cy,hw,hh,c,s in self.boxes:
            ax,ay=(a[0]-cx)*c+(a[1]-cy)*s,-(a[0]-cx)*s+(a[1]-cy)*c
            vx,vy=dx*c+dy*s,-dx*s+dy*c
            if escape and abs(ax)<hw and abs(ay)<hh:
                horizontal=abs(ax)-hw>=abs(ay)-hh
                outward=ax*vx>=0 if horizontal else ay*vy>=0
                if outward and max(abs(ax+vx)-hw,abs(ay+vy)-hh)>max(abs(ax)-hw,abs(ay)-hh)+.03:
                    continue
            lo,hi=0.,1.
            for p,v,half in ((ax,vx,hw),(ay,vy,hh)):
                if abs(v)<1e-9:
                    if not -half<p<half:lo=2.;break
                else:
                    low,high=sorted(((-half-p)/v,(half-p)/v));lo,hi=max(lo,low),min(hi,high)
            if lo<hi and hi>0 and lo<1:return False
        count=max(1,math.ceil(math.hypot(dx,dy)/.08))
        length=math.hypot(dx,dy)
        side=(-dy/max(1e-9,length)*.25,dx/max(1e-9,length)*.25)
        offsets=((0.,0.),side,(-side[0],-side[1]))
        previous=[self.height(a[0]+ox,a[1]+oy) for ox,oy in offsets]
        for i in range(1,count+1):
            h=[self.height(a[0]+dx*i/count+ox,a[1]+dy*i/count+oy) for ox,oy in offsets]
            spread_limit=.45 if escape and i<=4 else .17
            if any(n-p>.075 or p-n>(.45 if escape else .15) for n,p in zip(h,previous)) or max(h)-min(h)>spread_limit:return False
            previous=h
        return True

    def waypoint(self, start, goal, banned=()):
        if self.clear(start,goal,True):return goal
        blocked=set(banned)
        key=(tuple(round(v,3) for v in goal),tuple(sorted(blocked)))
        if key not in self.costs:
            costs={i:math.dist(p,goal) for i,p in enumerate(self.nodes) if self.clear(p,goal,True)}
            queue=[(d,i) for i,d in costs.items()];heapq.heapify(queue)
            while queue:
                d,i=heapq.heappop(queue)
                if d!=costs[i]:continue
                for j,edge in self.reverse[i]:
                    if (j,i) in self.special and f'{self.nodes[j]}:{self.nodes[i]}' in blocked:continue
                    if d+edge<costs.get(j,float('inf')):
                        costs[j]=d+edge;heapq.heappush(queue,(d+edge,j))
            if len(self.costs)>64:self.costs.clear()
            self.costs[key]=costs
        distances=self.costs[key]
        for (i,j),kind in self.special.items():
            if f'{self.nodes[i]}:{self.nodes[j]}' in blocked:continue
            if i in distances and j in distances and math.dist(start,self.nodes[i])<1.:
                edge=next(v for k,v in self.edges[i] if k==j)
                if distances[j]+edge<=distances[i]+.02:
                    return ('jump',self.nodes[i],self.nodes[j],kind)
        choices=sorted((math.dist(start,self.nodes[i])+v,i) for i,v in distances.items()
            if math.dist(start,self.nodes[i])>.32)
        for _,i in choices:
            if self.clear(start,self.nodes[i],True):return self.nodes[i]
        return None


_SERIAL_ROADMAPS = {team:SerialRoadmap(ARENAS_BY_SEASON['2027'],team) for team in ('red','blue')}
_original_serial_drive = drive
_opening_entry = highland_entry
_proven_homeward = max_homeward


def highland_entry(robot,ctx):
    if ctx.time<25:return _opening_entry(robot,ctx)
    memory=leg_memory(robot,ctx.obs,ctx.memory)
    x,_=local_point(ctx.team,(robot['x'],robot['y']))
    anchor=next((r for r in ctx.obs['robots'] if r['slot']==1),None)
    covering=robot['slot']==4 and (ctx.state.get('base_cover') or not ctx.controls(f'{ctx.team}_base')
        or anchor is None or not anchor['alive'] or anchor.get('weak') or anchor['hp']<anchor['max_hp']*.5 or ctx.state.get('guard_recover'))
    if robot.get('weak') or memory.get('entry_done') or covering:
        memory.pop('entry_wait',None)
        return None
    if not memory.get('entry') and x>=8.4:return None
    queue=ctx.state.setdefault('sortie_queue',{'pending':{},'since':ctx.time})
    queue['pending'][str(robot['slot'])]=ctx.time
    eligible=[r for r in ctx.obs['robots'] if r['alive'] and not r.get('weak') and r['role'] in ('infantry','sentry')
        and ctx.time-queue['pending'].get(str(r['slot']),-99)<.4]
    owner=next((r for r in eligible if r['slot']==queue.get('owner')),None)
    if owner is None and ctx.time-queue['since']>=.15:
        owner=min(eligible,key=lambda r:distance(r,max_local(ctx,(7.95,9.15))),default=None)
        if owner is not None:queue.update(owner=owner['slot'],owner_since=ctx.time)
    memory['entry_wait']=True
    if owner is None or owner['slot']!=robot['slot']:
        return {'move':(0,0),'leg_height':.245,'brake':True}
    if ctx.time-queue.get('owner_since',ctx.time)>40.:
        memory['entry_done']=True;memory.pop('entry_wait',None)
        queue['pending'].pop(str(robot['slot']),None);queue.pop('owner',None)
        return None
    if memory.get('sortie_ticket')!=queue.get('owner_since'):
        sx,sy=local_point(ctx.team,(robot['x'],robot['y']))
        memory.update(sortie_ticket=queue.get('owner_since'),sortie_from_supply=sx<4.2 and sy>10.5)
    if not memory.get('entry') and not memory.get('sortie_from_supply'):
        staging=max_local(ctx,(7.95,9.15))
        if distance(robot,staging)>.22:return drive(robot,staging,ctx.obs,ctx.memory,tolerance=.15)
        memory['entry']={'phase':1,'since':ctx.time,'began':ctx.time,'row':9.15}
    fields=_opening_entry(robot,ctx)
    if fields is None:
        queue['pending'].pop(str(robot['slot']),None);queue.pop('owner',None)
        memory.pop('entry_wait',None)
    return fields


def max_homeward(robot,goal,ctx):
    return max_hold(robot,goal,ctx)


def serial_escape(robot, obs, memory):
    """Latch an axial escape until the complete chassis has cleared a hump band."""
    m=leg_memory(robot,obs,memory)
    active=m.get('road_escape')
    if active:
        t=active['band'];x,y=robot['x'],robot['y']
        if not(t[0]-.55<x<t[2]+.55 and t[1]-.55<y<t[3]+.55) or obs['time']-active['began']>6.:
            m.pop('road_escape',None)
        else:
            return {'move':active['move'],'heading':active['heading'],'leg_height':.245,'brake':True,'power':200}
    escape=road_exit(robot,obs)
    if escape is None:return None
    band=next(t for t in obs['arena']['terrain'] if t['kind']=='bumps'
        and t['x']-.3<robot['x']<t['x']+t['w']+.3 and t['y']-.3<robot['y']<t['y']+t['h']+.3)
    m['road_escape']={'band':[band['x'],band['y'],band['x']+band['w'],band['y']+band['h']],
        'began':obs['time'],'move':escape['move'],'heading':escape['heading']}
    return escape


def drive(robot, goal, obs, memory, tolerance=.25):
    if not serial_leg(robot,obs):return _original_serial_drive(robot,goal,obs,memory,tolerance)
    if goal is None or distance(robot,goal)<tolerance:return {'move':(0,0),'brake':True,'leg_height':.245}
    escape=serial_escape(robot,obs,memory)
    if escape is not None:return escape
    start=(robot['x'],robot['y']);graph=_SERIAL_ROADMAPS[robot['team']]
    m=leg_memory(robot,obs,memory)
    locks=memory.setdefault('nav_locks',{})
    if m.get('nav_jump'):
        jump=m['nav_jump']
        end=jump['end']
        dx,dy=end[0]-jump['start'][0],end[1]-jump['start'][1]
        progress=((start[0]-jump['start'][0])*dx+(start[1]-jump['start'][1])*dy)/(dx*dx+dy*dy)
        rising=graph.height(*end)>graph.height(*jump['start'])+.1
        complete=(.82 if rising else .72) if jump['kind']=='highland' else .92
        if jump['kind']=='road' and progress>.83 and obs['time']-jump['began']<12.:
            jump.setdefault('landing',obs['time'])
            if obs['time']-jump['landing']<.7 or not robot.get('grounded') or math.hypot(robot['vx'],robot['vy'])>.2:
                return {'move':(0,0),'heading':jump.get('heading',robot['heading']),'leg_height':.245,'brake':True}
            progress=complete+1.
        if progress>complete or obs['time']-jump['began']>12.:
            if progress<=complete:m.setdefault('banned_jumps',{})[jump['lock']]=obs['time']+30.
            locks.pop(jump['lock'],None)
            m.pop('nav_jump',None)
        else:
            locks[jump['lock']]={'slot':robot['slot'],'until':obs['time']+3.}
            course=math.atan2(dy,dx)
            heading=jump.setdefault('heading',min((course,wrap(course+math.pi)),key=lambda h:abs(wrap(h-robot['heading']))))
            if jump['phase']==-1:
                fields=pointed_move(robot,jump['prep'],1.6)
                fields.update(leg_height=.245,brake=True)
                if distance(robot,jump['prep'])<.18:
                    jump.update(phase=0,settled=obs['time'])
                return fields
            if jump['phase']==0:
                if abs(wrap(heading-robot['heading']))<.12 and obs['time']-jump.get('settled',jump['began'])>.7:
                    jump['phase']=1
                return {'move':(0,0),'heading':heading,'leg_height':.12,'brake':True}
            fields=pointed_move(robot,end,2.2)
            fields.update(heading=heading,leg_height=.12,brake=True,power=180)
            rising=graph.height(*end)>graph.height(*jump['start'])+.1
            takeoff=(.13 if rising else .23) if jump['kind']=='highland' else (.35 if rising else .15)
            if progress>takeoff and robot.get('grounded') and obs['time']-m['last_jump']>1.1 and (jump['kind']!='road' or not jump.get('launched')):
                fields['jump']=1.;m['last_jump']=obs['time'];jump['launched']=True
            return fields
    banned=m.setdefault('banned_jumps',{})
    for key in list(banned):
        if banned[key]<=obs['time']:del banned[key]
    blocked=set(banned)
    local_goal=local_point(robot['team'],goal)
    if obs['time']>=25 or local_goal[0]<9.2:
        # The fast opening is a controlled jump from a known pose. Later
        # sorties use end ramps instead of repeatedly attacking the tall rim.
        blocked.update(f'{graph.nodes[i]}:{graph.nodes[j]}' for (i,j),kind in graph.special.items() if kind=='highland')
    waypoint=graph.waypoint(start,goal,blocked)
    if waypoint is not None and waypoint[0]=='jump':
        _,a,b,kind=waypoint
        lock=f'{a}:{b}'
        held=locks.get(lock,{})
        if held.get('slot') not in (None,robot['slot']) and held.get('until',0)>obs['time']:
            return {'move':(0,0),'leg_height':.245,'brake':True}
        owner='red' if (a[0] if a[0]<9. else b[0])<14 else 'blue'
        offset={3:-.6,4:.6,7:0.}.get(robot['slot'],0.)*(1 if owner=='red' else -1)
        if kind=='highland':a=(a[0],a[1]+offset);b=(b[0],b[1]+offset)
        descending=graph.height(*a)>graph.height(*b)+.1
        length=math.dist(a,b)
        prep=(a[0]-(b[0]-a[0])/length*.65,a[1]-(b[1]-a[1])/length*.65) if descending and kind=='highland' else a
        locks[lock]={'slot':robot['slot'],'until':obs['time']+3.}
        m['nav_jump']={'start':a,'end':b,'prep':prep,'kind':kind,'phase':-1,'began':obs['time'],'lock':lock}
        fields=pointed_move(robot,prep,1.6);fields.update(leg_height=.245,brake=True);return fields
    if waypoint is None:
        # A step up to the road has no continuous ramp from this side. The
        # controller uses the same bounded crouch/run-up as the highland entry.
        return _original_serial_drive(robot,goal,obs,memory,tolerance)
    fields=pointed_move(robot,waypoint,2.5)
    fields.update(leg_height=.245,brake=True)
    if math.hypot(robot['vx'],robot['vy'])<.4 and math.hypot(*fields['move'])>.2:fields['power']=180
    return fields


_route_drive=drive


def drive(robot,goal,obs,memory,tolerance=.25):
    """A bounded axial backoff also recovers a chassis already touching a rim."""
    if not serial_leg(robot,obs):
        fields=_route_drive(robot,goal,obs,memory,tolerance)
        design=obs['robot_models'].get(str(robot.get('model_slot')), {})
        if design.get('chassis_type')=='swerve':fields.setdefault('heading',robot['heading'])
        return fields
    m=memory.setdefault('nav_stall',{}).setdefault(str(robot['slot']),{'trail':[]})
    if obs['time']<m.get('until',-1):
        return {'move':m['move'],'heading':m['heading'],'leg_height':.245,'brake':True,'power':200}
    fields=_route_drive(robot,goal,obs,memory,tolerance)
    if goal is None or distance(robot,goal)<.6:
        m['trail']=[];return fields
    trail=m['trail'];trail.append((obs['time'],robot['x'],robot['y'],robot['heading']))
    while trail and obs['time']-trail[0][0]>2.5:trail.pop(0)
    if trail and obs['time']-trail[0][0]>2.3 and distance(robot,trail[0][1:3])<.10 and abs(wrap(robot['heading']-trail[0][3]))<.12:
        h=robot['heading'];graph=_SERIAL_ROADMAPS[robot['team']];start=(robot['x'],robot['y'])
        move=fields.get('move',(0,0));dot=move[0]*math.cos(h)+move[1]*math.sin(h)
        preferred=-1 if dot>=0 else 1
        def escape_score(sign):
            end=(start[0]+sign*.9*math.cos(h),start[1]+sign*.9*math.sin(h))
            bounded=.3<end[0]<27.7 and .3<end[1]<14.7
            reverse_bonus=.5*(sign==preferred) if abs(dot)>.12 else 0.
            return 4.*(bounded and graph.clear(start,end,True))+reverse_bonus+.2*(math.dist(start,goal)-math.dist(end,goal))
        sign=max((-1,1),key=escape_score);pace=1.4/robot['speed_reference_mps']
        m.update(move=(sign*pace*math.cos(h),sign*pace*math.sin(h)),heading=h,until=obs['time']+.65,trail=[])
        jump=leg_memory(robot,obs,memory).pop('nav_jump',None)
        if jump:
            memory.get('nav_locks',{}).pop(jump['lock'],None)
            leg_memory(robot,obs,memory).setdefault('banned_jumps',{})[jump['lock']]=obs['time']+20.
        return {'move':m['move'],'heading':h,'leg_height':.245,'brake':True,'power':200}
    return fields


# A bounded crouch and hop frees a healthy chassis straddling a tall rim.
_unwedge_parent=drive

def drive(robot,goal,obs,memory,tolerance=.25):
    if not serial_leg(robot,obs) or robot.get('weak') or goal is None:return _unwedge_parent(robot,goal,obs,memory,tolerance)
    m=leg_memory(robot,obs,memory);now=obs['time'];jump=m.get('rim_hop')
    g=_SERIAL_ROADMAPS[robot['team']]
    if jump and now-jump['since']>2.7:m.pop('rim_hop',None);jump=None
    if not jump:
        fields=_unwedge_parent(robot,goal,obs,memory,tolerance)
        stall=memory.get('nav_stall',{}).get(str(robot['slot']),{})
        heights=[g.height(robot['x']+dx,robot['y']+dy) for dx,dy in ((0,0),(.3,0),(-.3,0),(0,.3),(0,-.3))]
        # Road ramps have their own jump state. This escape is only for a
        # chassis touching a central-highland kerb, including its diagonal
        # end sections, where an axial backoff may not clear the edge.
        near_side=False
        for wall in obs['arena']['obstacles']:
            if not wall['id'].startswith('central_') or 'kerb' not in wall['id']:continue
            angle=wall.get('rotation',0);c,q=math.cos(angle),math.sin(angle)
            dx,dy=robot['x']-wall['x']-wall['w']/2,robot['y']-wall['y']-wall['h']/2
            ax,ay=dx*c+dy*q,-dx*q+dy*c
            if math.hypot(max(0.,abs(ax)-wall['w']/2),max(0.,abs(ay)-wall['h']/2))<.45:
                near_side=True;break
        # A hull resting on an end ramp can be grounded while both wheel probes carry
        # no load. Axial backoffs then have no traction; crouch and hop to put the wheels
        # back down, using the same bounded recovery as a kerb.
        unloaded = (robot.get('grounded') and not robot.get('tipped')
            and sum(robot.get('wheel_loads_n',(1.,))) < 1.)
        if stall.get('until',0)>now and now-m.get('rim_hop_last',-99)>20 and (unloaded or near_side and max(heights)-min(heights)>.18):
            m['rim_hop']=jump={'since':now,'goal':goal};m['rim_hop_last']=now
        else:return fields
    fields=pointed_move(robot,jump['goal'],2.2)
    fields.update(leg_height=.12,brake=True,power=200)
    if now-jump['since']<.7:fields['move']=(0,0)
    elif robot.get('grounded') and now-m['last_jump']>1.1:
        fields['jump']=1.;m['last_jump']=now
    return fields


"""Keep the base anchor on its card while using the base body as cover."""
_previous_base_guard = max_guard


def base_body_blocks(a, b, body):
    lo,hi=0.,1.
    for p,d,low,high in ((a[0],b[0]-a[0],body['x'],body['x']+body['w']),
                          (a[1],b[1]-a[1],body['y'],body['y']+body['h'])):
        if abs(d)<1e-9:
            if not low<p<high:return False
        else:
            left,right=sorted(((low-p)/d,(high-p)/d));lo,hi=max(lo,left),min(hi,right)
    return lo<hi and hi>0 and lo<1


def max_guard(robot, ctx):
    fields=_previous_base_guard(robot,ctx)
    ctx.state['guard_secure']=False
    if ctx.time<25 or robot.get('weak'):return fields
    memory=ctx.state.setdefault('guard_cover',{})
    base=ctx.obs['bases'][ctx.team]
    on_card=robot['id'] in ctx.obs['zones'].get(f'{ctx.team}_base',{}).get('occupants',[])
    relief=any(r['slot']!=robot['slot'] and r['alive'] and not r.get('weak')
        and r['id'] in ctx.obs['zones'].get(f'{ctx.team}_base',{}).get('occupants',[])
        for r in ctx.obs['robots'])
    if ctx.state.get('guard_recover') and relief:return fields
    if not on_card and (not memory or distance(robot,(base['x'],base['y']))>4.):return fields
    threats=[e for e in ctx.obs['enemies'] if e['alive'] and not e.get('invulnerable')
        and e.get('role')!='aerial' and distance(e,(base['x'],base['y']))<9.]
    points=[max_local(ctx,p) for p in ((1.05,7.5),(1.05,8.8),(2.4,8.8),(3.85,8.8),
                                      (3.85,7.5),(3.85,6.2),(2.4,6.2),(1.05,6.2))]
    body=min((w for w in ctx.arena['forbidden'] if w['kind']=='base'),
        key=lambda w:math.hypot(w['x']+w['w']/2-base['x'],w['y']+w['h']/2-base['y']))
    def risk(point):
        return sum((.015 if base_body_blocks((e['x'],e['y']),point,body) else 1.)/
                   max(.6,distance(e,point)) for e in threats)
    closest=min(range(len(points)),key=lambda i:distance(robot,points[i]))
    recent=ctx.time-robot.get('last_damage_time',-99)<2.5
    ctx.state['guard_secure']=on_card and not ctx.state.get('guard_recover') and not recent and ctx.time-robot.get('last_damage_time',-99)>6.2 and risk((robot['x'],robot['y']))<.08
    exposed=risk((robot['x'],robot['y']))>min(risk(p) for p in points)+.08
    if 'target' not in memory and not (exposed or recent and robot['hp']<robot['max_hp']*.85):
        return fields
    if threats:
        desired=min((0,2,4,6),key=lambda i:risk(points[i])+.006*distance(robot,points[i]))
        old=memory.get('target',desired)
        if 'target' not in memory or risk(points[old])>risk(points[desired])+.08:
            memory.update(target=desired,since=ctx.time,until=ctx.time+8.)
    elif recent and robot['hp']<robot['max_hp']*.9:
        # A close attacker can be outside every camera. React to our own
        # damage telemetry without assuming a hidden opponent position.
        if 'target' not in memory or ctx.time>memory.get('until',0):
            memory.update(target=max((0,2,4,6),key=lambda i:distance(robot,points[i])),
                since=ctx.time,until=ctx.time+8.)
    if 'target' not in memory:return fields
    desired=memory['target']
    if memory.get('route_target')!=desired:
        clockwise=(desired-closest)%len(points);counter=(closest-desired)%len(points)
        direction=1 if clockwise<=counter else -1
        route=[];index=closest
        if distance(robot,points[index])>.25:route.append(index)
        while index!=desired:
            index=(index+direction)%len(points);route.append(index)
        memory.update(route_target=desired,route=route,heading=robot['heading'])
    route=memory['route']
    while route and distance(robot,points[route[0]])<.18:route.pop(0)
    goal=points[route[0]] if route else points[desired]
    dx,dy=goal[0]-robot['x'],goal[1]-robot['y'];gap=math.hypot(dx,dy)
    if gap<.15:fields.update(move=(0,0),brake=True)
    else:
        speed=min(1.8,gap*3.)/robot['speed_reference_mps']
        fields.update(move=(dx/gap*speed,dy/gap*speed),heading=memory['heading'],brake=True,power=200)

    return fields


ROLES['heavy']=max_guard


"""Keep useful firing lanes and maintain distance from armor targets."""
_formation_hold=max_hold


def max_hold(robot,goal,ctx,tolerance=.18):
    if robot['role'] not in ('infantry','sentry') or robot.get('weak') or goal is None:
        return _formation_hold(robot,goal,ctx,tolerance)
    contacts=set(robot.get('last_raw_zones',[]))
    card=next((z for z in ctx.arena['zones'] if z['kind']=='central' and z['id'] in contacts
        and point_in_polygon(goal[0],goal[1],z['polygon'])),None)
    enemies=[e for e in ctx.obs['enemies'] if e['alive'] and not e.get('invulnerable')
        and distance(e,(robot['x'],robot['y']))<5.]
    close=any(distance(e,(robot['x'],robot['y']))<1.35 for e in enemies)
    spacing=ctx.state.setdefault('spacing',{})
    memory=spacing.setdefault(str(robot['slot']),{})
    if card and close and (ctx.time>=memory.get('until',0) or memory.get('card')!=card['id']):
        owner=card['owner']
        points=[local_point(owner,(x,y)) for x in (10.6,11.0) for y in (6.,7.7,9.25)]
        friends=[]
        for r in ctx.obs['robots']:
            if r['id']==robot['id'] or not r['alive'] or r['role']=='aerial':continue
            intent=spacing.get(str(r['slot']),{})
            friends.append(intent['goal'] if intent.get('card')==card['id'] else (r['x'],r['y']))
        def shadow(p,e,f):
            dx,dy=e['x']-p[0],e['y']-p[1];square=dx*dx+dy*dy
            u=((f[0]-p[0])*dx+(f[1]-p[1])*dy)/max(.01,square)
            return .03<u<.97 and math.hypot(p[0]+u*dx-f[0],p[1]+u*dy-f[1])<.27
        def score(p):
            return sum(1/max(.5,distance(e,p)) for e in enemies) \
                +sum(max(0.,1.-math.dist(f,p))*2 for f in friends) \
                +sum(1.5*shadow(p,e,f) for f in friends for e in enemies)+.025*distance(robot,p)
        memory.update(goal=min(points,key=score),until=ctx.time+3.,card=card['id'])
    if card and memory.get('card')==card['id'] and (enemies or ctx.time<memory.get('until',0)):
        goal=memory['goal']
    if card and robot['slot']==4 and (enemies or ctx.time-robot.get('last_damage_time',-99)<2.):
        # Move along the card rather than offering a stationary armor plate.
        # Two frequencies change acceleration without reading the match seed.
        candidate=(goal[0],goal[1]+.35*math.sin(ctx.time*3.7)+.15*math.sin(ctx.time*7.1))
        if point_in_polygon(candidate[0],candidate[1]+.21,card['polygon']):goal=candidate
    fields=_formation_hold(robot,goal,ctx,tolerance)
    if card and distance(robot,goal)<.25 and not leg_memory(robot,ctx.obs,ctx.memory).get('nav_jump'):
        # The receiver stays inside the narrow card while the gimbal remains
        # free to aim in world coordinates.
        fields['heading']=math.pi/2
    return fields


"""Use the free infantry to intercept base divers before the anchor is depleted."""
_support_parent=ROLES['infantry']


def support_goal(robot,ctx,threats):
    points=[max_local(ctx,p) for p in ((3.8,8.15),(3.85,6.95),(2.4,9.),(2.4,6.),(1.05,6.4),(1.05,8.6))]
    previous=ctx.state.setdefault('base_support_goal',{})
    if ctx.time<previous.get('until',-1):return previous['point']
    def score(p):
        proxy=dict(robot,x=p[0],y=p[1],z=robot.get('z',0)+terrain_height(ctx.arena,*p)-terrain_height(ctx.arena,robot['x'],robot['y']))
        shots=sum(max_shot_clear(proxy,e,ctx) and distance(e,p)>1.3 for e in threats)
        crowd=sum(max(0.,.9-distance(r,p)) for r in ctx.obs['robots'] if r['id']!=robot['id'] and r['alive'] and r['role']!='aerial')
        close=sum(max(0.,1.3-distance(e,p)) for e in threats)
        return -3*shots+close*2+crowd+distance(robot,p)*.04
    point=min(points,key=score) if threats else points[0]
    previous.update(point=point,until=ctx.time+2.)
    return point


def support_fighter(robot,ctx):
    if robot['slot']!=3:return _support_parent(robot,ctx)
    base=ctx.obs['bases'][ctx.team]
    threats=[e for e in ctx.obs['enemies'] if e['alive'] and not e.get('invulnerable')
        and e.get('role')!='aerial' and distance(e,(base['x'],base['y']))<7.]
    heavy_robot=next((r for r in ctx.obs['robots'] if r['role']=='heavy'),None)
    active=ctx.enemy in ctx.positions.get(f'{ctx.team}_base',{}).get('active',[])
    hurt=heavy_robot is not None and heavy_robot['hp']<heavy_robot['max_hp']*.8 \
        and ctx.time-heavy_robot.get('last_damage_time',-99)<3.
    # A protected, healthy anchor already denies the base clock. Do not pull
    # the mobile infantry off the outpost solely because a diver is nearby.
    unsafe=heavy_robot is None or not heavy_robot['alive'] or heavy_robot.get('weak') \
        or heavy_robot['hp']<heavy_robot['max_hp']*.7 or not ctx.controls(f'{ctx.team}_base')
    if hurt or unsafe and (threats or active):ctx.state['base_threat_until']=ctx.time+15.
    wanted=ctx.time<ctx.state.get('base_threat_until',-1)
    front=front_threats(ctx)
    lost_home=not ctx.controls(f'{ctx.team}_outpost')
    if lost_home or len(front)>=2 and any(e['role']=='sentry' for e in front):
        ctx.state['front_reinforce_until']=ctx.time+6.
    reinforce=ctx.time<ctx.state.get('front_reinforce_until',-1)
    if ctx.controls(f'{ctx.enemy}_base') and robot['id'] in ctx.obs['zones'].get(f'{ctx.enemy}_base',{}).get('occupants',[]):
        reinforce=False
    base_critical=not ctx.controls(f'{ctx.team}_base') or heavy_robot is not None and heavy_robot['hp']<heavy_robot['max_hp']*.6
    if not (wanted or reinforce) or robot.get('weak') or robot['hp']<robot['max_hp']*.24 \
            or ctx.state.get('max_recovery',{}).get(str(robot['slot'])):
        return _support_parent(robot,ctx)
    fields=max_logistics(robot,ctx)
    if ctx.obs['tick']==0:fields['profile']={'chassis':'hp','weapon':'cooling'}
    goal=outpost_card_spot(ctx,ctx.team) if reinforce and not base_critical else support_goal(robot,ctx,threats)
    fields.update(max_hold(robot,goal,ctx))
    fields.update(weapon(robot,ctx,reach=9.,structures=False,drones_too=False))
    ctx.state.get('max_routes',{}).pop(str(robot['slot']),None)
    return fields


ROLES['infantry']=support_fighter


_front_parent=ROLES['sentry']


def front_threats(ctx):
    center=ctx.zone(ctx.team,'central')
    return [e for e in ctx.obs['enemies'] if e['alive'] and e.get('role')!='aerial'
        and e['hp']>e['max_hp']*.25 and local_point(ctx.team,(e['x'],e['y']))[0]>8.5
        and distance(e,center)<4.]


def front_response(robot,ctx):
    threats=front_threats(ctx)
    pressure=len(threats)>=2 and any(e['role']=='sentry' for e in threats)
    if pressure or not ctx.controls(f'{ctx.team}_outpost'):
        ctx.state['front_guard_until']=ctx.time+6.;ctx.state['home_sentry']=True
    guardian=next((r for r in ctx.obs['robots'] if r['slot']==4),None)
    relieved=guardian is not None and guardian['alive'] and not guardian.get('weak') \
        and guardian['hp']>guardian['max_hp']*.6 \
        and not ctx.state.get('base_cover') and not ctx.state.get('max_recovery',{}).get('4') \
        and on_outpost_card(guardian,ctx.team,ctx)
    if ctx.time>=ctx.state.get('front_guard_until',-1) and relieved:
        ctx.state['home_sentry']=False
    ration_due=int(ctx.time//60)>robot.get('supply_grants_taken',0)
    needs_recovery=robot['hp']<robot['max_hp']*.24 or robot['ammo']<20 and ration_due and relieved
    if not ctx.state.get('home_sentry') or robot.get('weak') or needs_recovery \
            or ctx.state.get('max_recovery',{}).get(str(robot['slot'])):
        return _front_parent(robot,ctx)
    if ctx.time<25 and not leg_memory(robot,ctx.obs,ctx.memory).get('entry_done'):
        return _front_parent(robot,ctx)
    fields=max_logistics(robot,ctx)
    fields.update(max_hold(robot,max_local(ctx,(10.8,6.)),ctx))
    fields.update(weapon(robot,ctx,reach=10.,structures=False,drones_too=False))
    fighting=any(e['alive'] and not e.get('invulnerable') and distance(e,(robot['x'],robot['y']))<9 for e in ctx.obs['enemies'])
    wanted='attack' if fighting and robot['hp']>robot['max_hp']*.45 else 'defense'
    if ctx.time>=(robot.get('posture_ready_at') or 0):
        fields.update(posture=wanted,posture_enhanced=wanted=='defense' and robot['hp']<robot['max_hp']*.45
            and ctx.time-robot.get('last_damage_time',-99)<2.)
    return fields


ROLES['sentry']=front_response


"""Track public target motion and account for the first gimbal update before firing."""
_motion_context=Context
_motion_solution=firing_solution
_motion_weapon=weapon


class Context(_motion_context):
    def zone(self,team,kind):
        # The card is large; its nominal center is beside the workbench.
        # This interior point clears both fixtures and the receiver margin.
        if kind=='supply':return local_point(team,(2.5,12.4))
        return super().zone(team,kind)

    def __init__(self,obs,state):
        history=state.setdefault('motion_history',{})
        enemies=[];now=obs['time']
        for enemy in obs['enemies']:
            e=dict(enemy);old=history.get(e['id']);accel=(0.,0.)
            if old and 0.<now-old['time']<.4 and e['alive'] and old['alive']:
                dt=now-old['time']
                raw=((e['vx']-old['vx'])/dt,(e['vy']-old['vy'])/dt)
                length=math.hypot(*raw);scale=min(1.,6./max(.01,length))
                accel=tuple(.65*value*scale+.35*previous for value,previous in zip(raw,old['accel']))
            e['_accel']=accel
            history[e['id']]={'time':now,'vx':e['vx'],'vy':e['vy'],'alive':e['alive'],'accel':accel}
            enemies.append(e)
        for key in list(history):
            if now-history[key]['time']>3.:del history[key]
        super().__init__(dict(obs,enemies=enemies),state)


def firing_solution(robot,target):
    if '_accel' not in target:return _motion_solution(robot,target)
    lead=distance(robot,(target['x'],target['y']))/(muzzle_speed(robot)*.88)+.025
    proxy=dict(target)
    q=target.get('quaternion')
    omega=target.get('angular_velocity',(0.,0.,0.))[2]
    if q:
        angle=max(-.7,min(.7,omega*lead))/2;c,s=math.cos(angle),math.sin(angle)
        x,y,z,w=q
        proxy['quaternion']=(c*x-s*y,s*x+c*y,c*z+s*w,c*w-s*z)
    point=_aim_target(robot,proxy)
    ax,ay=target['_accel']
    proxy.update(x=point[0]+.5*ax*lead*lead,y=point[1]+.5*ay*lead*lead,aim_z=point[2])
    return _motion_solution(robot,proxy)


def weapon(robot,ctx,reach=9.,structures=False,drones_too=False):
    fields=_motion_weapon(robot,ctx,reach,structures,drones_too)
    if fields.get('fire') or 'aim' not in fields or 'pitch' not in fields:return fields
    if not can_fire(robot) or math.sqrt(sum(v*v for v in robot.get('angular_velocity',(0.,0.,0.))))>.4:
        return fields
    design=ctx.obs['robot_models'].get(str(robot.get('model_slot')), {})
    yaw_step=design.get('turret_yaw_rate_rad_s',6.5)/120
    pitch_step=design.get('turret_pitch_rate_rad_s',2.5)/120
    yaw,pitch=barrel_angles(robot)
    margin=100 if robot['role']=='heavy' else 20
    fields['fire']=abs(wrap(fields['aim']-yaw))<yaw_step+.004 \
        and abs(fields['pitch']-pitch)<pitch_step+.004 and robot['heat']+margin<=robot['max_heat']
    return fields


"""Spend the public, per-posture enhanced budget on useful close engagements."""
_sentry_decide=decide


def decide(robot,ctx):
    fields=_sentry_decide(robot,ctx)
    if robot['role']!='sentry' or not robot['alive'] or robot.get('weak') or robot.get('tipped'):
        return fields
    if ctx.time<(robot.get('posture_ready_at') or 0):return fields
    spent=robot.get('posture_enhanced_time',(0.,0.,0.))[0]
    enemies=[e for e in ctx.obs['enemies'] if e['alive'] and not e.get('invulnerable')
        and e.get('targetable',True) and distance(e,(robot['x'],robot['y']))<6.]
    friends=sum(r['alive'] and not r.get('weak') and r['role']!='aerial'
        and distance(r,(robot['x'],robot['y']))<5. for r in ctx.obs['robots'])
    continuing=robot.get('posture')=='attack' and robot.get('posture_enhanced') and robot['hp']>robot['max_hp']*.4
    start=robot['hp']>robot['max_hp']*.5 and robot['ammo']>=80 and len(enemies)<=max(1,friends+1)
    if ('aim' in fields and 'pitch' in fields) and robot['ammo']>0 and enemies and spent<14.5 and (start or continuing):
        fields.update(posture='attack',posture_enhanced=True)
    return fields


"""Give serial turns a bounded settling window instead of waiting at an edge."""
_turn_context=Context
_road_pointed=pointed_move
_turn_time=0.
_turn_memory={}
_turn_models={}


class Context(_turn_context):
    def __init__(self,obs,state):
        global _turn_time,_turn_memory,_turn_models
        super().__init__(obs,state)
        _turn_time=obs['time']
        _turn_memory=state.setdefault('turn_settle',{})
        _turn_models=obs['robot_models']


def pointed_move(robot,goal,speed):
    fields=_road_pointed(robot,goal,speed)
    model=_turn_models.get(str(robot.get('model_slot')), {})
    if model.get('leg_type')!='serial' or 'heading' not in fields:
        return fields
    key=robot['id'];heading=fields['heading'];turn=_turn_memory.get(key)
    if turn is None or abs(wrap(heading-turn['heading']))>.3:
        turn={'heading':heading,'since':_turn_time}
        _turn_memory[key]=turn
    if abs(wrap(heading-robot['heading']))>.18 and _turn_time-turn['since']<.7:
        fields['move']=(0,0)
    return fields


"""Acquire hidden approaches through staggered, legal gimbal searches."""
_search_weapon=weapon
_search_decide=decide

def search_bearing(robot,ctx):
    phase={1:1.,3:0.,4:2.1,7:4.2}.get(robot['slot'],0.)
    return wrap(ctx.time*2.2+phase+(math.pi if ctx.team=='blue' else 0.))

def weapon(robot,ctx,reach=9.,structures=False,drones_too=False):
    fields=_search_weapon(robot,ctx,reach,structures,drones_too)
    if 'aim' not in fields:fields['aim']=search_bearing(robot,ctx)
    return fields

def decide(robot,ctx):
    fields=_search_decide(robot,ctx)
    if robot['alive'] and robot['role']!='aerial' and not robot.get('tipped'):
        fields.setdefault('aim',search_bearing(robot,ctx))
    return fields

_transit_decide=decide

def decide(robot,ctx):
    fields=_transit_decide(robot,ctx)
    if robot['role']!='sentry' or not robot['alive'] or robot.get('weak') or robot.get('tipped'):
        return fields
    memory=leg_memory(robot,ctx.obs,ctx.memory)
    entry=(ctx.time<25. or memory.get('entry') or memory.get('entry_wait')) and not memory.get('entry_done')
    jumping=bool(memory.get('nav_jump') or memory.get('rim_hop') or memory.get('road_escape'))
    transit=entry or jumping or not robot.get('grounded',True)
    if transit and ctx.time >= (robot.get('posture_ready_at') or 0):
        fields.update(posture='move',posture_enhanced=False)
    return fields

def max_supply_point(robot,ctx):
    return max_local(ctx,(2.7,{3:12.45,4:13.25,7:14.05}[robot['slot']]))

# Preserve the forward sentry and the independent mobile infantry assignment.
ROLES.update(infantry=max_fighter,sentry=max_fighter)

_guarded_decide=decide

def decide(robot,ctx):
    fields=_guarded_decide(robot,ctx)
    if robot['role']!='sentry' or not robot['alive'] or robot.get('weak') or robot.get('tipped') or not robot.get('grounded',True):return fields
    if ctx.time<(robot.get('posture_ready_at') or 0):return fields
    memory=leg_memory(robot,ctx.obs,ctx.memory)
    transit=(ctx.time<25. or memory.get('entry') or memory.get('entry_wait')) and not memory.get('entry_done')
    if transit or memory.get('nav_jump') or memory.get('rim_hop') or memory.get('road_escape'):return fields
    spent=robot.get('posture_enhanced_time',(0.,0.,0.))[1]
    threats=[e for e in ctx.obs['enemies'] if e['alive'] and not e.get('weak') and not e.get('invulnerable')
        and (e['role'] in ('infantry','sentry') or e['role']=='heavy' and ctx.time-robot.get('last_damage_time',-99)<1.)
        and distance(e,(robot['x'],robot['y']))<5.]
    if spent<14.5 and threats and ('pitch' in fields or ctx.time-robot.get('last_damage_time',-99)<1.):
        fields.update(posture='defense',posture_enhanced=True)
    return fields

_alarm_context=Context
_alarm_hold=max_hold
_alarm_entry=highland_entry

class Context(_alarm_context):
    def __init__(self,obs,state):
        super().__init__(obs,state)
        base=self.obs['bases'][self.team]
        divers=[e for e in self.obs['enemies'] if e['alive'] and not e.get('invulnerable') and e['role'] in ('infantry','sentry','heavy')
            and local_point(self.team,(e['x'],e['y']))[0]<9.7 and distance(e,(base['x'],base['y']))<8.5]
        alarm=self.state.setdefault('base_alarm',{'until':-1.})
        trigger=len(divers)>=2 or any(e['role']=='sentry' for e in divers)
        if trigger or divers and self.time<alarm['until']:
            if self.time>=alarm['until']:alarm['began']=self.time
            alarm['until']=self.time+18.
        heavy=next((r for r in self.obs['robots'] if r['slot']==1),None)
        helper=next((r for r in self.obs['robots'] if r['slot']==alarm.get('slot')),None)
        reached=helper is not None and helper['id'] in self.obs['zones'].get(f'{self.team}_base',{}).get('occupants',[])
        safe=heavy is not None and heavy['alive'] and not heavy.get('weak') and heavy['hp']>=heavy['max_hp']*.8 and self.time-heavy.get('last_damage_time',-99)>6.2
        if len(divers)<=1 and reached and safe and self.time-alarm.get('began',self.time)>20.:
            alarm.update(until=self.time-1.,released_at=self.time)
        if len(divers)<=1 and 'released_at' in alarm and heavy is not None and heavy['alive'] and not heavy.get('weak') and heavy.get('last_damage_time',-99)<=alarm['released_at'] and self.controls(f'{self.team}_base'):
            alarm['until']=self.time-1.
        if self.time>=alarm['until']:alarm.pop('slot',None);return
        eligible=[r for r in self.obs['robots'] if r['alive'] and not r.get('weak') and r['slot'] in (3,4,7)
            and r['hp']>r['max_hp']*.4 and r['ammo']>0 and not self.state.get('max_recovery',{}).get(str(r['slot']))]
        old=next((r for r in eligible if r['slot']==alarm.get('slot')),None)
        if old is None and eligible:
            alarm['slot']=min(eligible,key=lambda r:{4:0,3:5,7:10}[r['slot']]+.2*distance(r,(base['x'],base['y'])))['slot']
        if alarm.get('slot')==4:self.state['base_cover']=True

def highland_entry(robot,ctx):
    alarm=ctx.state.get('base_alarm',{})
    if ctx.time>=25. and ctx.time<alarm.get('until',-1.) and robot['slot']==alarm.get('slot'):return None
    return _alarm_entry(robot,ctx)

def max_hold(robot,goal,ctx,tolerance=.18):
    alarm=ctx.state.get('base_alarm',{})
    if ctx.time>=25. and ctx.time<alarm.get('until',-1.) and robot['slot']==alarm.get('slot') and not robot.get('weak') and not ctx.state.get('max_recovery',{}).get(str(robot['slot'])):
        goal=max_local(ctx,(3.8,8.15))
        if robot['slot']==4:ctx.state['base_cover']=True
    return _alarm_hold(robot,goal,ctx,tolerance)

_escort_context=Context
_escort_hold=max_hold

class Context(_escort_context):
    def __init__(self,obs,state):
        previous=state.get('base_alarm',{}).get('slot')
        super().__init__(obs,state)
        alarm=self.state.get('base_alarm',{})
        base=self.obs['bases'][self.team]
        divers=[e for e in self.obs['enemies'] if e['alive'] and not e.get('invulnerable') and e['role'] in ('infantry','sentry','heavy')
            and local_point(self.team,(e['x'],e['y']))[0]<9.7 and distance(e,(base['x'],base['y']))<8.5]
        sentry=next((r for r in self.obs['robots'] if r['slot']==7),None)
        if len(divers)>=2:alarm['multi_until']=self.time+15.
        multiple=self.time<alarm.get('multi_until',-1.)
        if multiple:
            alarm['until']=max(alarm.get('until',-1.),alarm['multi_until'])
            guardian=next((r for r in self.obs['robots'] if r['slot']==4),None)
            if guardian is not None and guardian['alive'] and not guardian.get('weak') and guardian['hp']>guardian['max_hp']*.4 and guardian['ammo']>0 and not self.state.get('max_recovery',{}).get('4'):
                alarm['slot']=4;self.state['base_cover']=True
        if not multiple and self.time<alarm.get('until',-1.) and len(divers)==1 and divers[0]['role']=='sentry' and sentry is not None and sentry['alive'] and not sentry.get('weak') and sentry['hp']>sentry['max_hp']*.4 and sentry['ammo']>0 and not self.state.get('max_recovery',{}).get('7'):
            alarm['slot']=7
        if previous is not None and previous!=alarm.get('slot'):
            relieved=next((r for r in self.obs['robots'] if r['slot']==previous),None)
            if relieved is not None and relieved.get('grounded') and local_point(self.team,(relieved['x'],relieved['y']))[0]<8.4:
                memory=leg_memory(relieved,self.obs,self.memory)
                jump=memory.pop('nav_jump',None)
                if jump:self.memory.get('nav_locks',{}).pop(jump['lock'],None)
                for key in ('entry_done','entry','entry_wait','road_escape','rim_hop'):memory.pop(key,None)

def max_hold(robot,goal,ctx,tolerance=.18):
    alarm=ctx.state.get('base_alarm',{})
    if robot['slot']==7 and alarm.get('slot')==7 and ctx.time<alarm.get('until',-1.) and not robot.get('weak') and not ctx.state.get('max_recovery',{}).get('7'):
        base=ctx.obs['bases'][ctx.team]
        threats=[e for e in ctx.obs['enemies'] if e['alive'] and not e.get('invulnerable') and e['role']!='aerial' and distance(e,(base['x'],base['y']))<9.]
        goal=support_goal(robot,ctx,threats)
        # Call the pre-alarm hold once so the selected firing lane is retained.
        return _alarm_hold(robot,goal,ctx,tolerance)
    return _escort_hold(robot,goal,ctx,tolerance)
