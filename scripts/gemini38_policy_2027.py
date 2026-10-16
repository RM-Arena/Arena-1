"""Gemini 3.8 Flash RMUC 2027 Multi-Style Strategy Controller.

Developed by Gemini 3.8 Flash for RMUC 2027.
Features:
- Dynamic supercap burst acceleration for opening card seizure and tactical disengagement.
- Coordinated multi-robot polygon inset card locking and standoff.
- Dual-iteration aerodynamic ballistic aiming with actual barrel angle verification.
- Intelligent sentry posture engine (defense/attack/move with adaptive enhancement).
- High-efficiency heavy robot assembly pipeline and 42mm high-ground artillery turret.
- Predictive rotating armor interception for hangar aerial drones.
- Dynamic control degree lead protection and tactical mode switching.
"""
import math
from sdk import (action, aim_at, aim_pitch, assembly_work_point, ballistic_reachable, can_fire,
                 drones, instant_revive_cost, navigate, rescue_point, resource_pickup_point,
                 tipped_teammates, workbench_point, zone_center, muzzle_speed, point_in_polygon,
                 _aim_target, _rotate)

STYLE = "blitz"

STEP_ORDER = ("positioning", "inserting", "lifting", "flipping", "rotating", "verifying", "complete")
UNLOCK = {1: 0, 2: 60, 3: 120, 4: 180}

DASH_STANDOFF = 0.38
DASH_TIME = 0.28
DASH_TOLERANCE = 0.16


def wrap(angle):
    return (angle + math.pi) % math.tau - math.pi


def distance(robot, point):
    return math.hypot(robot['x'] - point[0], robot['y'] - point[1])


def other(team):
    return 'blue' if team == 'red' else 'red'


def unstick(robot, move, memory, now):
    """Anti-stall maneuvering when trapped on terrain bumps, barriers or ramp kerbs."""
    m = memory.setdefault(str(robot['slot']), {'trail': [], 'tries': 0})
    if now < m.get('until', -1):
        return {'move': m['escape'], 'heading': m['heading']}
    trail = m['trail']
    if math.hypot(*move) < 0.01:
        trail.clear()
        return {'move': move}
    trail.append([now, robot['x'], robot['y'], robot['heading']])
    while now - trail[0][0] > 1.3:
        trail.pop(0)
    turned = abs(wrap(robot['heading'] - trail[0][3]))
    if now - trail[0][0] < 1.2 or distance(robot, trail[0][1:3]) > 0.12 or turned > 0.15:
        return {'move': move}
    m['tries'] += 1
    angle = math.atan2(move[1], move[0]) + math.pi + (0.85 if (robot['slot'] + m['tries']) % 2 else -0.85)
    m.update(escape=[0.75 * math.cos(angle), 0.75 * math.sin(angle)], until=now + 0.65, heading=robot['heading'])
    trail.clear()
    return {'move': m['escape'], 'heading': m['heading']}


def smart_drive(robot, goal, obs, memory, tolerance=0.30, turbo=False):
    """Smart navigation with dynamic supercap power burst."""
    if goal is None or distance(robot, goal) <= tolerance:
        return {'move': (0, 0)}
    fields = unstick(robot, navigate(robot, goal, obs['arena']), memory, obs['time'])
    speed = math.hypot(robot['vx'], robot['vy'])
    move_mag = math.hypot(*fields['move'])
    
    # Supercap trigger conditions:
    # 1. Opening rush / turbo commanded: sprint on long stretches
    # 2. Climbing heavy on slopes or plinths (low speed under heavy demand)
    # 3. Emergency escape when low HP and under fire
    needs_burst = False
    if turbo and distance(robot, goal) > 2.0:
        needs_burst = True
    elif robot['role'] == 'heavy' and speed < 0.35 and move_mag > 0.2:
        needs_burst = True
    elif speed < 0.25 and move_mag > 0.3:
        needs_burst = True
    elif robot.get('hp', 1000) < robot.get('max_hp', 1000) * 0.35 and obs['time'] - robot.get('last_damage_time', -99) < 1.5:
        needs_burst = True

    if needs_burst and robot.get('capacitor_energy_j', 500) > 150:
        fields['power'] = 200
    return fields


class Context:
    def __init__(self, obs, state):
        self.obs = obs
        self.state = state
        self.team = obs['team']
        self.enemy = other(self.team)
        self.arena = obs['arena']
        self.time = obs['time']
        self.economy = obs['teams'][self.team]
        self.enemy_economy = obs['teams'][self.enemy]
        self.coins = self.economy['resources']
        self.control_gap = self.economy.get('control', 0.0) - self.enemy_economy.get('control', 0.0)
        
        self.remaining = obs.get('remaining', 420.0 - self.time)
        # Mathematical victory lock: enemy cannot overtake even if scoring every remaining second
        if self.control_gap > max(8.0, self.remaining + 3.0):
            self.hold_lead = True
        elif self.remaining < 65 and self.control_gap > 15.0:
            self.hold_lead = True
        else:
            self.hold_lead = False
        
        self.positions = obs.get('positions', {})
        self.memory = state.setdefault('stuck', {})
        self.rotation = state.setdefault('target_rotation', {})
        self.spin = {}
        for site, outpost in obs['outposts'].items():
            prev = self.rotation.get(site)
            self.spin[site] = 0.0 if outpost.get('rotation_stopped') or not prev else \
                wrap(outpost['rotation'] - prev[1]) / max(0.001, self.time - prev[0])
            self.rotation[site] = [self.time, outpost['rotation']]

    def zone(self, team, kind):
        return zone_center(self.arena, f'{team}_{kind}')

    def controls(self, name, team=None, full=False):
        p = self.positions.get(name)
        return bool(p) and p['controller'] == (team or self.team) and (not full or p['control'] == 'full')

    def enemy_base_vulnerable(self):
        return not self.controls(f'{self.enemy}_outpost', self.enemy, full=True) and self.obs['bases'][self.enemy]['hp'] > 0

    def hostile_outpost(self):
        for site in (self.enemy, self.team):
            o = self.obs['outposts'][site]
            if o['hp'] > 0 and o.get('owner', site) != self.team:
                return dict(o, kind='outpost', site=site)
        return None


def barrel_angles(robot):
    yaw = robot['aim'] - robot['heading']
    pitch = robot.get('pitch', 0)
    v = _rotate(robot.get('quaternion', (0, 0, 0, 1)),
                (math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), math.sin(pitch)))
    return math.atan2(v[1], v[0]), math.atan2(v[2], math.hypot(v[0], v[1]))


def firing_solution(robot, target):
    point = _aim_target(robot, target)
    speed = muzzle_speed(robot)
    mass, radius = (0.0445, 0.02125) if robot['role'] == 'heavy' else (0.0032, 0.0084)
    drag = 0.5 * 1.225 * 0.47 * math.pi * radius * radius / mass
    pivot = _rotate(robot.get('quaternion', (0, 0, 0, 1)), (0, 0, robot.get('muzzle_height_m', 0.45)))
    ox, oy, oz = robot['x'] + pivot[0], robot['y'] + pivot[1], robot.get('z', 0) + pivot[2]
    reach = robot.get('muzzle_reach_m', 0.22)
    flight = math.hypot(point[0] - ox, point[1] - oy) / speed
    lead = flight + 0.02
    tx, ty = point[0] + target.get('vx', 0) * lead, point[1] + target.get('vy', 0) * lead
    tz = point[2] + target.get('vz', 0) * lead
    dx, dy = tx - ox, ty - oy
    gap = max(0.05, math.hypot(dx, dy))
    ux, uy = dx / gap, dy / gap
    along = robot.get('vx', 0) * ux + robot.get('vy', 0) * uy
    across = -robot.get('vx', 0) * uy + robot.get('vy', 0) * ux

    def trajectory(angle):
        horizontal = speed * math.cos(angle)
        if horizontal <= abs(across):
            return -100.0
        vx = math.sqrt(horizontal * horizontal - across * across) + along
        vz = speed * math.sin(angle) + robot.get('vz', 0)
        x, z = reach * math.cos(angle), oz + reach * math.sin(angle)
        dt = 1 / 60
        for _ in range(50):
            velocity = math.hypot(vx, vz)
            ax, az = -drag * velocity * vx, -9.81 - drag * velocity * vz
            xn, zn = x + vx * dt + 0.5 * ax * dt * dt, z + vz * dt + 0.5 * az * dt * dt
            if xn >= gap:
                fraction = (gap - x) / max(1e-8, xn - x)
                return z + (zn - z) * fraction
            x, z = xn, zn
            vx, vz = vx + ax * dt, vz + az * dt
            if vx <= 0 or z < oz - 6:
                break
        return -100.0

    low, high = -math.pi / 12, math.pi / 4
    if trajectory(high) < tz:
        return None
    for _ in range(6):
        middle = (low + high) / 2
        if trajectory(middle) < tz:
            low = middle
        else:
            high = middle
    pitch = (low + high) / 2
    yaw = math.atan2(dy, dx) - math.asin(max(-0.99, min(0.99, across / (speed * math.cos(pitch)))))
    return yaw, pitch


def structure_target(robot, ctx):
    if not hasattr(ctx, '_structure_target'):
        ctx._structure_target = None
        outpost = ctx.hostile_outpost()
        if outpost:
            flight = max(0, distance(robot, (outpost['x'], outpost['y'])) - 0.3) / (muzzle_speed(robot) * 0.86)
            turn = ctx.spin.get(outpost['site'], 0.0) * flight
            c, s = math.cos(turn), math.sin(turn)
            plates = []
            for p in outpost.get('armor_plates', []):
                dx, dy = p['center'][0] - outpost['x'], p['center'][1] - outpost['y']
                nx, ny = p['normal'][:2]
                x, y = outpost['x'] + dx * c - dy * s, outpost['y'] + dx * s + dy * c
                normal = (nx * c - ny * s, nx * s + ny * c)
                score = ((robot['x'] - x) * normal[0] + (robot['y'] - y) * normal[1])
                plates.append((score, {'x': x, 'y': y, 'aim_z': p['center'][2]}))
            ctx._structure_target = max(plates, key=lambda p: p[0])[1] if plates else outpost
        elif ctx.enemy_base_vulnerable():
            ctx._structure_target = dict(ctx.obs['bases'][ctx.enemy], kind='base')
    target = ctx._structure_target
    if target and ballistic_reachable(robot, target):
        return target
    return None


def enemy_target(robot, ctx, reach):
    """Focus fire on vulnerable and high-threat enemies."""
    candidates = []
    for e in ctx.obs['enemies']:
        if not e['alive'] or not e.get('targetable', True) or e.get('invulnerable'):
            continue
        d = distance(robot, (e['x'], e['y']))
        if d <= reach:
            hp_ratio = e['hp'] / max(1, e.get('max_hp', 1000))
            # Primary priority: eliminate low health / weak enemies first!
            score = e['hp'] * (1.0 + e.get('defense_buff', 0.0)) + d * 20
            if e.get('weak'):
                score -= 180
            elif hp_ratio < 0.35:
                score -= 120
            if e['role'] == 'sentry':
                score -= 70
            if e['role'] == 'heavy' and e.get('launcher') not in ('fitted', 'installed'):
                score += 150
            candidates.append((score, e))
    for _, target in sorted(candidates, key=lambda p: p[0])[:4]:
        if ballistic_reachable(robot, target):
            return target
    return None


def drone_target(robot, ctx, reach=4.0):
    best = None
    for d in ctx.obs.get('enemy_drones', []):
        if d['state'] != 'flying' or math.hypot(d['vx'], d['vy']) > 2.5:
            continue
        gap = distance(robot, (d['x'], d['y']))
        if gap <= reach and (best is None or gap < best[0]):
            best = (gap, {'x': d['x'], 'y': d['y'], 'z': d['z'], 'aim_z': d['z']})
    return best[1] if best else None


def weapon(robot, ctx, reach=9.5, structures=True, drones_too=True):
    target = enemy_target(robot, ctx, reach)
    if target is None and drones_too and robot['role'] != 'heavy':
        target = drone_target(robot, ctx, reach=3.2)
    if target is None and structures:
        target = structure_target(robot, ctx)
    if target is None:
        front = ctx.zone(ctx.enemy, 'central')
        return {'aim': math.atan2(front[1] - robot['y'], front[0] - robot['x']) + 0.4 * math.sin(ctx.time * 0.8), 'fire': False}
    solution = firing_solution(robot, target)
    if solution is None:
        return {'aim': aim_at(robot, target), 'fire': False}
    aim, pitch = solution
    heavy = robot['role'] == 'heavy'
    cone = max(0.012, min(0.038, 0.065 / max(1.0, distance(robot, (target['x'], target['y'])))))
    actual_aim, actual_pitch = barrel_angles(robot)
    aligned = abs(wrap(aim - actual_aim)) < cone and abs(pitch - actual_pitch) < 0.026
    fire = aligned and can_fire(robot) and (heavy or robot['heat'] + 20 <= robot['max_heat'])
    return {'aim': aim, 'pitch': pitch, 'fire': fire}


def can_buy_here(robot, ctx):
    contacts = set(robot.get('last_raw_zones', []))
    contacts.update(zone for zone, last in robot.get('zone_contacts', {}).items() if ctx.time - last <= 2.0)
    if any(f'{ctx.team}_{kind}' in contacts for kind in ('base', 'supply', 'high_point')):
        return True
    if any(f'{owner}_outpost' in contacts and ctx.controls(f'{owner}_outpost', full=True) for owner in (ctx.team, ctx.enemy)):
        return True
    for kind in ('base', 'supply', 'high_point'):
        if distance(robot, ctx.zone(ctx.team, kind)) < (1.6 if kind == 'base' else 1.0):
            return True
    for owner in (ctx.team, ctx.enemy):
        if ctx.controls(f'{owner}_outpost', full=True) and distance(robot, ctx.zone(owner, 'outpost')) < 0.85:
            return True
    return False


def disengaged(robot, now):
    return now - max(robot.get('last_shot_time', -99), robot.get('last_damage_time', -99)) >= 6.0


def ammo_fields(robot, ctx, low, local_amount, remote_amount, reserve):
    if robot['ammo'] >= low or ctx.time < 1.05 or robot.get('pending_ammo'):
        return {}
    unit = 10 if robot['role'] == 'heavy' else 1
    if can_buy_here(robot, ctx) and ctx.coins >= local_amount * unit + reserve:
        return {'buy_ammo': {'amount': local_amount, 'remote': False}}
    if disengaged(robot, ctx.time) and ctx.coins >= 150 + reserve:
        return {'buy_ammo': {'amount': remote_amount, 'remote': True}}
    return {}


def revive_fields(robot, ctx, reserve=120):
    cost = instant_revive_cost(robot, ctx.time)
    return {'revive': ctx.time < 380 and ctx.coins >= cost + reserve}


_OUTPOST_CARD_SPOTS = {}


def outpost_card_spot(ctx, owner, side=0):
    cache_key = (owner, side)
    if cache_key in _OUTPOST_CARD_SPOTS:
        return _OUTPOST_CARD_SPOTS[cache_key]
    x, y = ctx.obs['outposts'][owner]['x'], ctx.obs['outposts'][owner]['y']
    toward = (14.0 - x, 7.5 - y)
    length = math.hypot(*toward) or 1.0
    ux, uy = toward[0] / length, toward[1] / length
    card = next(z for z in ctx.arena['zones'] if z['id'] == f'{owner}_outpost')
    polygon = card.get('polygon')
    if polygon:
        points = [(px * 0.76 + x * 0.24, py * 0.76 + y * 0.24) for px, py in polygon]
        points = [p for p in points if point_in_polygon(*p, polygon)]
        points.sort(key=lambda p: (p[0] - x) * ux + (p[1] - y) * uy, reverse=True)
        if points:
            idx = 2 if side > 0 else 0 if side < 0 else 1
            res = points[min(idx, len(points) - 1)]
            _OUTPOST_CARD_SPOTS[cache_key] = res
            return res
    res = (x + ux * 0.8, y + uy * 0.8)
    _OUTPOST_CARD_SPOTS[cache_key] = res
    return res


# ---- Heavy Robot -------------------------------------------------------------

def dock_heading(ctx):
    origin = ctx.arena['assembly_frames'][ctx.team]['origin']
    plinth = zone_center(ctx.arena, ctx.team + '_assembly')
    return math.atan2(origin[1] - plinth[1], origin[0] - plinth[0])


def pick(robot, ctx):
    goal = resource_pickup_point(robot, ctx.arena)
    if distance(robot, goal) <= 0.12:
        station = next(f for f in ctx.arena['field_geometry']['fixtures'] if f['kind'] == 'resource' and f['team'] == ctx.team)
        return {'move': (0, 0), 'brake': True, 'pick_unit': True,
                'heading': math.atan2(station['pick_dir'][1], station['pick_dir'][0])}
    fields = smart_drive(robot, goal, ctx.obs, ctx.memory, 0.10)
    fields['pick_unit'] = distance(robot, goal) < 0.6
    return fields


def start_assembly(robot, ctx, level, core, work, memory):
    gap = distance(robot, work)
    if gap > 0.16:
        fields = smart_drive(robot, work, ctx.obs, ctx.memory, 0.10)
        move = fields['move']
        pace = math.hypot(*move)
        if gap < 1.0 and 0 < pace < 0.25:
            fields['move'] = (move[0] / pace * 0.25, move[1] / pace * 0.25)
        return fields
    fields = {'move': (0, 0), 'brake': True, 'heading': dock_heading(ctx)}
    if ctx.time + 1e-6 >= UNLOCK[level] and core['stage'] not in ('moving', 'inserting'):
        fields['assembly'] = level
        if level == 4:
            memory['l4_tried'] = True
    return fields


def assemble(robot, ctx, core, work):
    fields = {'move': (0, 0) if distance(robot, work) < 0.16 else smart_drive(robot, work, ctx.obs, ctx.memory, 0.1)['move'],
              'brake': True, 'heading': dock_heading(ctx), 'assembly_insert': True, 'assembly_lift': True,
              'assembly_flip': True, 'assembly_confirm': True}
    cores = core.get('cores') or [{'core': 0, 'operation': core.get('operation'), 'target_rotation': core.get('target_rotation', 0)}]
    if core['difficulty'] == 4 and len(cores) == 2:
        if robot.get('arm_count', 1) >= 2:
            fields['assembly_core'] = 2
            fields['assembly_rotate'] = cores[0]['target_rotation']
            return fields
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
    team = ctx.team
    # Dominant central deck firing position overlooking enemy outpost and central crossing
    x, y = (14.8, 5.1) if not ctx.hold_lead else (13.6, 6.2)
    return (x, y) if team == 'red' else (28.0 - x, 15.0 - y)


def heavy_combat(robot, ctx):
    obs = ctx.obs
    fields = {}
    fields.update(ammo_fields(robot, ctx, 6, 20, 10, 50))
    if robot['ammo'] == 0 and not robot.get('pending_ammo') and not fields:
        return smart_drive(robot, ctx.zone(ctx.team, 'supply'), obs, ctx.memory)
    if robot['hp'] < robot['max_hp'] * 0.28:
        fields.update(smart_drive(robot, ctx.zone(ctx.team, 'supply'), obs, ctx.memory))
        return fields
    fields.update(smart_drive(robot, heavy_post(ctx), obs, ctx.memory, 0.40))
    fields.update(weapon(robot, ctx, reach=12.5))
    return fields


def heavy(robot, ctx):
    obs, team = ctx.obs, ctx.team
    memory = ctx.state.setdefault('heavy', {})
    done = ctx.economy.get('completed_difficulties', [])
    core = obs['assemblies'][team]
    stage = core['stage']
    active = stage in ('moving', 'inserting')
    work = assembly_work_point(robot, ctx.arena)
    if robot['weak']:
        return smart_drive(robot, ctx.zone(team, 'supply'), obs, ctx.memory)
    launcher = robot.get('launcher', 'locked')
    if active and distance(robot, work) < 1.2:
        return assemble(robot, ctx, core, work)

    # Teammate rescue
    attempts = memory.setdefault('rescue', {})
    for key, started in list(attempts.items()):
        if ctx.time - started > 70:
            del attempts[key]
    tipped = [t for t in tipped_teammates(obs) if (1 in done or ctx.time > 55) and t['role'] != 'aerial' and t['slot'] != robot['slot']
              and distance(robot, (t['x'], t['y'])) < 12 and ctx.time - attempts.get(t['id'], ctx.time) < 25]
    if tipped and launcher != 'installing':
        target = min(tipped, key=lambda t: distance(robot, (t['x'], t['y'])))
        attempts.setdefault(target['id'], ctx.time)
        far = distance(robot, (target['x'], target['y'])) > 0.8
        fields = smart_drive(robot, rescue_point(robot, target), obs, ctx.memory, 0.10) if far else {'move': (0, 0), 'brake': True}
        fields['rescue'] = target['slot']
        return fields

    if launcher in ('unlocked', 'installing'):
        bench = workbench_point(robot, ctx.arena)
        if distance(robot, bench) <= 0.25:
            fields = {'move': (0, 0), 'brake': True, 'install_launcher': True}
            fields.update(ammo_fields(robot, ctx, 8, 20, 10, 80))
            return fields
        return smart_drive(robot, bench, obs, ctx.memory, 0.20)

    armed = launcher in ('fitted', 'installed')
    if armed:
        return heavy_combat(robot, ctx)

    # Rapid tech assembly for levels 1, 2, 3 to unlock 42mm launcher ASAP
    wanted = next((d for d in (1, 2, 3) if d not in done), None)
    if wanted is None:
        return heavy_combat(robot, ctx)
    units_left = ctx.economy.get('energy_units_left', 0)
    if robot['carried_units'] == 0 or (robot['carried_units'] < 2 and units_left > 0 and distance(robot, resource_pickup_point(robot, ctx.arena)) < 1.0):
        if units_left <= 0 and robot['carried_units'] == 0:
            return heavy_combat(robot, ctx)
        return pick(robot, ctx)
    return start_assembly(robot, ctx, wanted, core, work, memory)


# ---- Infantry ----------------------------------------------------------------

def recovery_goal(robot, ctx):
    memory = ctx.state.setdefault('recovery', {})
    key = str(robot['slot'])
    empty = (robot['ammo'] == 0 and not can_buy_here(robot, ctx))
    if robot['weak'] or robot['hp'] < robot['max_hp'] * 0.28 or empty:
        memory[key] = True
    if robot['hp'] >= robot['max_hp'] * 0.82 and robot['ammo'] >= 40 and not robot['weak']:
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


def on_outpost_card(robot, owner, ctx=None):
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


def sentry_holds(ctx):
    return any(r['role'] == 'sentry' and r['alive'] and not r['weak'] and on_outpost_card(r, ctx.team, ctx) for r in ctx.obs['robots'])


def enemy_point_covered(ctx, excluded):
    return any(r['slot'] != excluded and r['alive'] and not r.get('weak') and r['role'] != 'aerial'
               and r['hp'] >= r['max_hp'] * 0.40
               and on_outpost_card(r, ctx.enemy, ctx) for r in ctx.obs['robots'])


def infantry(robot, ctx):
    obs, team, enemy = ctx.obs, ctx.team, ctx.enemy
    fields = {}
    if obs['tick'] == 0:
        fields['profile'] = {'chassis': robot['chassis_profile'], 'weapon': robot['weapon_profile']}
    fields.update(ammo_fields(robot, ctx, 25, 120, 100, 110))
    recovery = recovery_goal(robot, ctx)
    if recovery:
        fields.update(smart_drive(robot, recovery, obs, ctx.memory, 0.20))
        fields.update(weapon(robot, ctx, reach=7.0, structures=False))
        return fields
    if ctx.time < 1.05:
        return fields

    # Infantry role determination: slot 3 striker, slot 4 flex/support
    is_striker = (robot['slot'] == 3)
    side = 1 if is_striker else -1
    own = ctx.controls(f'{team}_outpost')
    theirs = ctx.controls(f'{enemy}_outpost')
    turbo = (ctx.time < 14.0)  # Opening supercap sprint!

    if ctx.hold_lead:
        # Defend own outpost position to protect control lead
        goal = outpost_card_spot(ctx, team, side) if is_striker else (ctx.zone(team, 'central')[0], ctx.zone(team, 'central')[1] + (-1.2 if team == 'red' else 1.2))
    elif not own:
        # Recover/take own outpost position first
        goal = outpost_card_spot(ctx, team, side) if is_striker else ctx.zone(team, 'central')
    elif not ctx.controls(f'{team}_outpost', full=True) and not sentry_holds(ctx) and not is_striker:
        # Help sentry secure own outpost until full control
        goal = ctx.zone(team, 'central')
    elif theirs:
        # Both controlled! Maintain capture and attack enemy fortress/base
        if not is_striker and ctx.time >= 160 and enemy_point_covered(ctx, robot['slot']):
            goal = ctx.zone(enemy, 'fortress')
        else:
            goal = outpost_card_spot(ctx, enemy, side) if is_striker else ctx.zone(enemy, 'central')
    elif STYLE == 'blitz':
        # Blitz rush: strike enemy outpost card
        goal = outpost_card_spot(ctx, enemy, side) if is_striker else ctx.zone(enemy, 'central')
    elif STYLE == 'tech_overload':
        goal = outpost_card_spot(ctx, enemy, side) if is_striker else ctx.zone(team, 'central')
    else: # hunter
        goal = outpost_card_spot(ctx, enemy, side)

    fields.update(smart_drive(robot, goal, obs, ctx.memory, 0.20, turbo=turbo))
    fields.update(weapon(robot, ctx, reach=9.5))
    if robot.get('ammo', 0) == 0 and not robot.get('pending_ammo') and not fields.get('buy_ammo'):
        fields['fire'] = False
    if robot['hp'] < robot['max_hp'] * 0.72 and disengaged(robot, ctx.time) and not robot.get('pending_heal') \
            and ctx.coins >= 180 and distance(robot, goal) < 0.7:
        fields['remote_heal'] = True
    return fields


# ---- Sentry ------------------------------------------------------------------

def sentry(robot, ctx):
    obs, team = ctx.obs, ctx.team
    memory = ctx.state.setdefault('sentry', {})
    fields = {}

    covered = any(r['alive'] and not r['weak'] and r['slot'] != robot['slot'] and r['role'] != 'aerial'
                  and r['hp'] >= r['max_hp'] * 0.40 and on_outpost_card(r, team, ctx) for r in obs['robots'])
    if robot['ammo'] < 30 and ctx.time > 20:
        memory['resupply'] = True
    if robot['ammo'] >= 80:
        memory.pop('resupply', None)
    recovery = recovery_goal(robot, ctx)

    # Holding the card matters more than anything: leaving for 5s hands outpost to enemy!
    if recovery and (covered or ctx.controls(f'{team}_outpost', full=True)):
        goal = recovery
    elif memory.get('resupply') and ctx.controls(f'{team}_outpost', full=True):
        goal = outpost_card_spot(ctx, team)
    elif memory.get('resupply') and robot['ammo'] == 0 and covered:
        goal = ctx.zone(team, 'supply')
    elif STYLE == 'hunter' and covered and ctx.controls(f'{team}_outpost', full=True) and not ctx.hold_lead:
        goal = ctx.zone(ctx.enemy, 'central')
    else:
        goal = ctx.zone(team, 'central')
        own_card = obs.get('zones', {}).get(f'{team}_central', {})
        opposite = obs.get('zones', {}).get(f'{ctx.enemy}_central', {})
        if own_card.get('owner') != team and opposite.get('owner') == ctx.enemy:
            goal = outpost_card_spot(ctx, team, 1)

    moving = distance(robot, goal) > 0.6
    fields.update(smart_drive(robot, goal, obs, ctx.memory, 0.30))
    fields.update(weapon(robot, ctx, reach=10.5))

    threatened = ctx.time - robot.get('last_damage_time', -99) < 2.0
    if robot['hp'] < robot['max_hp'] * 0.48 and threatened:
        wanted = 'defense'
    elif robot['ammo'] > 0 and any(e['alive'] and not e.get('invulnerable') and distance(robot, (e['x'], e['y'])) < 9.0 for e in obs['enemies']):
        wanted = 'attack'
    elif moving and distance(robot, goal) > 3.5:
        wanted = 'move'
    else:
        wanted = 'defense'

    if wanted != robot.get('posture') and ctx.time >= (robot.get('posture_ready_at') or 0):
        fields['posture'] = wanted

    enhanced = wanted == 'defense' and robot['hp'] < robot['max_hp'] * 0.32 and threatened
    if wanted == 'attack' and robot['ammo'] >= 110 and sum(e['alive'] and distance(robot, (e['x'], e['y'])) < 5.5 for e in obs['enemies']) >= 2:
        enhanced = True
    if bool(robot.get('posture_enhanced')) != enhanced and ctx.time >= (robot.get('posture_ready_at') or 0):
        fields['posture_enhanced'] = enhanced

    fields.update(ammo_fields(robot, ctx, 40, 100, 100, 20))
    if robot['hp'] < robot['max_hp'] * 0.70 and disengaged(robot, ctx.time) and not robot.get('pending_heal') and ctx.coins >= 180:
        fields['remote_heal'] = True
    return fields


# ---- Aerial Robot System -----------------------------------------------------

def track_spin(memory, owner, outpost, now):
    last = memory.setdefault('rotation', {}).get(owner)
    if last and now > last[0] and not outpost.get('rotation_stopped'):
        memory.setdefault('spin', {})[owner] = wrap(outpost['rotation'] - last[1]) / (now - last[0])
    elif outpost.get('rotation_stopped'):
        memory.setdefault('spin', {})[owner] = 0.0
    memory['rotation'][owner] = [now, outpost['rotation']]


def aerial_target(ctx, memory):
    obs = ctx.obs
    own = obs['outposts'][ctx.team]
    outpost = dict(own, kind='outpost', site=ctx.team) if (ctx.hold_lead or STYLE == 'tech_overload') and own['hp'] > 0 and own.get('owner', ctx.team) != ctx.team else ctx.hostile_outpost()
    if outpost:
        track_spin(memory, outpost['site'], outpost, ctx.time)
        return dict(outpost, spin=memory.get('spin', {}).get(outpost['site'], 0.0))
    if ctx.enemy_base_vulnerable():
        return dict(obs['bases'][ctx.enemy], kind='base', spin=0.0)
    return None


def gantry_exit(hangar, target, ctx):
    rune = ctx.arena['rune']
    axis = (hangar['x'] - rune['x'], hangar['y'] - rune['y'])
    length = math.hypot(*axis) or 1.0
    side = (-axis[1] / length, axis[0] / length)
    toward = (target['x'] - hangar['x'], target['y'] - hangar['y'])
    if side[0] * toward[0] + side[1] * toward[1] < 0:
        side = (-side[0], -side[1])
    return (hangar['x'] + side[0] * 0.6, hangar['y'] + side[1] * 0.6)


def ram(d, target, k, n, now, memory, hangar):
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
        bearing = math.atan2(hangar[1] - cy, hangar[0] - cx) + (k - (n - 1) / 2) * 0.88
        radius = math.hypot(plate['center'][0] - cx, plate['center'][1] - cy)
        anchor = (cx, cy)
    hold = (anchor[0] + math.cos(bearing) * (radius + DASH_STANDOFF), anchor[1] + math.sin(bearing) * (radius + DASH_STANDOFF),
            plate['center'][2])
    if m['mode'] == 'dash' and now < m['until']:
        return {'move': m['dir']}
    if m['mode'] == 'dash':
        m.update(mode='retreat', until=now + 0.38)
    if m['mode'] == 'retreat' and now < m['until']:
        return {'move': [math.cos(bearing), math.sin(bearing), 0]}
    m['mode'] = 'approach'
    if math.hypot(d['x'] - anchor[0], d['y'] - anchor[1]) < radius + 0.15:
        return {'move': [math.cos(bearing), math.sin(bearing), 0]}
    gap = math.dist((d['x'], d['y'], d['z']), hold)
    if gap > 0.07 or math.hypot(d['vx'], d['vy']) > 0.35:
        return {'goto': [round(v, 3) for v in hold]}
    facing = math.atan2(plate['normal'][1], plate['normal'][0]) + target['spin'] * DASH_TIME
    if abs(wrap(facing - bearing)) <= DASH_TOLERANCE:
        m.update(mode='dash', until=now + DASH_TIME + 0.14,
                 dir=[-math.cos(bearing), -math.sin(bearing), round((plate['center'][2] - d['z']) * 3, 3)])
        return {'move': m['dir']}
    return {'goto': [round(v, 3) for v in hold]}


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
        if target is None or d['battery_wh'] < 0.45:
            if d['state'] != 'docked':
                commands[key] = {'dock': True}
            continue
        if d['state'] == 'docked':
            commands[key] = {'launch': True}
            continue
        exit_point = gantry_exit(hangar, target, ctx)
        m = memory.setdefault(d['id'], {'mode': 'exit'})
        if m['mode'] == 'exit':
            if math.hypot(d['x'] - exit_point[0], d['y'] - exit_point[1]) > 0.2:
                commands[key] = {'goto': [exit_point[0], exit_point[1], 2.0]}
                continue
            m['mode'] = 'approach'
        commands[key] = ram(d, target, k, len(fleet), ctx.time, memory, (hangar['x'], hangar['y']))
    return {'drones': commands}


# ---- Main Dispatcher ---------------------------------------------------------

ROLES = {'heavy': heavy, 'infantry': infantry, 'sentry': sentry, 'aerial': aerial}


def decide(robot, ctx):
    if robot['role'] != 'aerial' and not robot['alive']:
        return revive_fields(robot, ctx, 100 if robot['role'] == 'heavy' else 200)
    return ROLES[robot['role']](robot, ctx)


def pause_tipped(robot, fields):
    if robot['role'] == 'aerial' or not robot['alive']:
        return fields
    if robot.get('tipped'):
        fields.update(move=(0, 0), brake=True, fire=False)
        fields.pop('power', None)
        return fields
    return fields


def act(obs, state):
    try:
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
    except Exception as exc:
        # Ultimate exception fallback to guarantee zero policy errors
        fallback_commands = {str(slot): action(move=(0, 0), fire=False) for slot in obs.get('controlled_ids', [])}
        return fallback_commands, state
