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
        if robot.get('grounded') and 8.45 < x < 10.65 and ctx.time - m['last_jump'] > 1.1:
            fields['jump'] = 1.
            m['last_jump'] = ctx.time
    return fields


def max_logistics(robot, ctx):
    """Reserve shared coins immediately so simultaneous orders cannot overspend."""
    fields = {}
    cost = 50 + math.ceil(ctx.time / 60 * 20)
    if robot['hp'] < robot['max_hp'] * .70 and disengaged(robot, ctx.time) \
            and not robot.get('pending_heal') and ctx.budget >= cost + 100:
        fields['remote_heal'] = True
        ctx.budget -= cost
    if robot['role'] == 'heavy':
        return fields
    if robot['ammo'] < 25 and not robot.get('pending_ammo') and ctx.time >= 1.05:
        local = can_buy_here(robot, ctx)
        amount = min(100, ctx.ammo_remaining // 10 * 10) if local else 100
        price = amount if local else 150
        if (local or disengaged(robot, ctx.time)) and ctx.budget >= price + 50 \
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
        margin = 100 if robot['role'] == 'heavy' else 10 if robot['cooling_rate'] >= 20 else 20
        fire = aligned and can_fire(robot) and robot['heat'] + margin <= robot['max_heat']
        return {'aim': aim, 'pitch': pitch, 'fire': fire}
    return {'fire': False}


def max_guard(robot, ctx):
    fields = max_logistics(robot, ctx)
    launcher = robot.get('launcher', 'locked')
    if ctx.time < 25 and launcher in ('locked', 'unlocked', 'installing'):
        bench = workbench_point(robot, ctx.arena)
        fields.update(drive(robot, bench, ctx.obs, ctx.memory, .16))
        if distance(robot, bench) < .24:
            fields.update(move=(0, 0), brake=True, install_launcher=True)
            if robot['ammo'] < 5 and ctx.budget >= 150 and ctx.time > 1.05:
                fields['buy_ammo'] = {'amount': 10, 'remote': False}
                ctx.budget -= 100
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
    front_quiet = not any(e['alive'] and not e.get('invulnerable') and
        distance(e, max_local(ctx, (17.1, 7.5))) < 5. for e in ctx.obs['enemies'])
    if robot['role'] == 'sentry' and robot['ammo'] < 20 and due_grants > 0 and covered and front_quiet:
        recovering = True
    supply = ctx.zone(ctx.team, 'supply')
    if recovering and robot['hp'] >= robot['max_hp'] * .85 and not robot.get('weak') \
            and (robot['role'] != 'sentry' or robot['ammo'] >= 100 or due_grants <= 0) \
            and distance(robot, supply) < 1.:
        recovering = False
        leg_memory(robot, ctx.obs, ctx.memory).clear()
        leg_memory(robot, ctx.obs, ctx.memory)['last_jump'] = -10.
        ctx.state.get('max_routes', {}).pop(key, None)
    recovery[key] = recovering
    if recovering:
        fields.update(max_homeward(robot, supply, ctx))
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
                    and heavy_robot['hp'] >= heavy_robot['max_hp'] * .8 \
                    and f'{ctx.team}_base' in heavy_robot.get('last_raw_zones', []):
                cover = False
            ctx.state['base_cover'] = cover
            if was_covering and not cover:
                m = leg_memory(robot, ctx.obs, ctx.memory)
                m.pop('entry_done', None)
                m.pop('entry', None)
            goal = max_local(ctx, (3.8, 8.15)) if cover else outpost_card_spot(ctx, ctx.team)
            fields.update(max_homeward(robot, goal, ctx) if cover else max_hold(robot, goal, ctx))
        elif robot['slot'] == 7:
            fields.update(max_hold(robot, max_local(ctx, (17.15, 8.1)), ctx))
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
                fields.update(max_hold(robot, max_local(ctx, (17.15, 9.15)), ctx))
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
