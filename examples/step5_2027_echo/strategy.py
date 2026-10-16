"""Step 5 Preview · RMUC 2027 全队策略 · 读阵应变（echo）

机械层：项目公开 2027 机制基线（导航/脱困/装配/无人机撞击/弹道），
与 examples/official_2027_team、examples/gpt61_2027_* 同源；
战术层：Step 5 Preview 设计。
"""
import math
from sdk import (action, aim_at, aim_pitch, assembly_work_point, ballistic_reachable, can_fire,
                 drones, instant_revive_cost, navigate, rescue_point, resource_pickup_point,
                 tipped_teammates, workbench_point, zone_center, muzzle_speed, point_in_polygon,
                 _aim_target, _rotate)

STYLE = "echo"          # lock | rush | echo —— 由构建脚本替换

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
    """Per-decision facts every role reads, plus Step 5's control bookkeeping."""

    def __init__(self, obs, state):
        self.obs, self.state = obs, state
        self.team = obs['team']
        self.enemy = other(self.team)
        self.arena = obs['arena']
        self.time = obs['time']
        self.economy = obs['teams'][self.team]
        self.coins = self.economy['resources']
        self.positions = obs.get('positions', {})
        self.zones = obs.get('zones', {})
        self.gap = self.economy.get('control', 0) - obs['teams'][self.enemy].get('control', 0)
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

    def occupants(self, zone_id, team=None):
        """Robots standing on a card; zone occupancy is public, not vision-limited."""
        ids = self.zones.get(zone_id, {}).get('occupants', [])
        if team is None:
            return list(ids)
        return [i for i in ids if i.startswith(f'{team}-')]

    def enemy_on(self, *zone_ids):
        return sum(len(self.occupants(z, self.enemy)) for z in zone_ids)

    def ours_on(self, *zone_ids):
        return sum(len(self.occupants(z, self.team)) for z in zone_ids)

    # ---- Step 5 tactical facts -------------------------------------------------------------

    @property
    def our_outpost(self):
        return self.controls(f'{self.team}_outpost')

    @property
    def our_outpost_full(self):
        return self.controls(f'{self.team}_outpost', full=True)

    @property
    def their_outpost(self):
        return self.controls(f'{self.enemy}_outpost')

    @property
    def their_outpost_full(self):
        return self.controls(f'{self.enemy}_outpost', full=True)

    @property
    def our_base(self):
        return self.controls(f'{self.team}_base')

    @property
    def their_base(self):
        return self.controls(f'{self.enemy}_base')

    def enemy_base_vulnerable(self):
        """A base takes no damage while its owner fully controls its own outpost position."""
        return not self.their_outpost_full and self.obs['bases'][self.enemy]['hp'] > 0

    def hostile_outpost(self):
        """The outpost to attack: the enemy's, or ours if the enemy rebuilt it as theirs."""
        for site in (self.enemy, self.team):
            o = self.obs['outposts'][site]
            if o['hp'] > 0 and o.get('owner', site) != self.team:
                return dict(o, kind='outpost', site=site)
        return None

    @property
    def fortress_open(self):
        """Enemy fortress card is enterable after 180 s while we hold their outpost position."""
        return self.time >= 180 and self.their_outpost and not self.obs['bases'][self.enemy].get('armor_open')

    def fortress_danger(self):
        """Enemy ground robots near their fortress card; the occupant takes double damage."""
        card = self.zone(self.enemy, 'fortress')
        return sum(1 for e in self.obs['enemies']
                   if e['alive'] and e.get('targetable', True) and distance(e, card) < 7)


# ---- Targeting and ballistics (public mechanism layer) --------------------------------------

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
    """Solve flight time and lead together, including drag and inherited chassis velocity."""
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


# ---- Economy (public mechanism layer) --------------------------------------------------------

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


# ---- Heavy robot (public mechanism layer) ----------------------------------------------------

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
    # 2027 has no engineer: the heavy robot's arm rights a tipped teammate close by.
    attempts = memory.setdefault('rescue', {})
    for key, started in list(attempts.items()):
        if ctx.time - started > 75:
            del attempts[key]
    tipped = [t for t in tipped_teammates(obs) if (1 in done or ctx.time > 60) and t['role'] != 'aerial'
              and t['slot'] != robot['slot'] and distance(robot, (t['x'], t['y'])) < 12
              and ctx.time - attempts.get(t['id'], ctx.time) < 25]
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
    level_four = armed and 4 not in done and attempt_fourth_core(ctx) and not memory.get('l4_tried')
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


# ---- Infantry / sentry (public mechanism layer) ----------------------------------------------

def infantry_job(robot, ctx):
    """striker: take the enemy outpost position; flex: shoot structures and escort."""
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
    goal = infantry_goal(robot, ctx, job, side)
    fields.update(drive(robot, goal, obs, ctx.memory, .20))
    fields.update(weapon(robot, ctx, reach=9))
    if robot.get('ammo', 0) == 0 and not robot.get('pending_ammo') and not fields.get('buy_ammo'):
        fields['fire'] = False
    # A quiet capture point is a safe place to receive a remote heal, without giving up control.
    if robot['hp'] < robot['max_hp'] * .72 and disengaged(robot, ctx.time) and not robot.get('pending_heal') \
            and ctx.coins >= 180 and distance(robot, goal) < .7:
        fields['remote_heal'] = True
    return fields


def sentry_holds(ctx):
    """An eligible own sentry is standing on either card of the home outpost position."""
    return any(r['role'] == 'sentry' and r['alive'] and not r.get('weak') and on_outpost_card(r, ctx.team, ctx) for r in ctx.obs['robots'])


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


# ---- Aerial robot system (public mechanism layer) --------------------------------------------

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
    """The rotating outpost first; the enemy base once it can be damaged."""
    obs = ctx.obs
    own = obs['outposts'][ctx.team]
    outpost = dict(own, kind='outpost', site=ctx.team) if ctx.hold_lead and own['hp'] > 0 and own.get('owner', ctx.team) != ctx.team else ctx.hostile_outpost()
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


# ---- Sentry driver (public mechanism layer) ---------------------------------------------------

def sentry(robot, ctx):
    obs, team = ctx.obs, ctx.team
    memory = ctx.state.setdefault('sentry', {})
    fields = {}
    # Holding the card matters more than rations: while our outpost position is held only
    # by our presence, leaving it for 5 s hands it to the enemy. Ammo is bought remotely.
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
    else:
        goal = sentry_goal(robot, ctx)
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
    if bool(robot.get('posture_enhanced')) != enhanced and ctx.time >= (robot.get('posture_ready_at') or 0):
        fields['posture_enhanced'] = enhanced
    memory['last'] = wanted
    # The sentry holds the card without ammo too, so it rebuys remotely with a small reserve.
    fields.update(ammo_fields(robot, ctx, 40, 100, 100, 50))
    if robot['hp'] < robot['max_hp'] * .7 and disengaged(robot, ctx.time) and not robot.get('pending_heal') and ctx.coins >= 180:
        fields['remote_heal'] = True
    return fields


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
        try:
            commands[slot] = action(**pause_tipped(robot, decide(robot, ctx)))
        except Exception:
            commands[slot] = action()       # hold still rather than lose the program
    state['ticks'] = state.get('ticks', 0) + 1
    return commands, state


# ---- Step 5 Preview tactical layer -----------------------------------------------------------
# 三种打法共用一套机械层；STYLE 决定战术层。
#   lock —— 双点锁链：以控制度为主线，己方两点不失、持续争夺敌方前哨卡，
#            180 s 后以堡垒卡把 +3/s 基地点收入囊中。
#   rush —— 破哨速攻：双步兵早期压上敌方前哨卡，重型跳过 4 级抢先装炮，
#            以基地血量决胜负的前期对攻。
#   echo —— 读阵应变：每 tick 用公开占卡信息给地面单位打分分配卡片，
#            根据敌方分布与控制度差动态调整攻防。

Context.hold_lead = property(lambda self: self.gap > 0.15)


def _near(robot, point, radius):
    return distance(robot, point) < radius


def _enemy_threat_near(ctx, point, radius=5.0):
    """Enemy ground robots close to a card (vision-limited, but own robots usually see them)."""
    count = 0
    for e in ctx.obs['enemies']:
        if e['alive'] and e.get('targetable', True) and distance(e, point) < radius:
            count += 1
    return count


# ---- lock -------------------------------------------------------------------------------------

def lock_attempt_fourth_core(ctx):
    """4 级（全队 50% 防御）值得一试，但控制度落后时火力优先。"""
    return ctx.time < 250 and ctx.gap > -3


def lock_heavy_post(ctx):
    """中央高地南肩：同时够得到敌方前哨与基地。"""
    x, y = (14.9, 5.0)
    return (x, y) if ctx.team == 'red' else (28 - x, 15 - y)


def lock_sentry_goal(robot, ctx):
    """中央高地块是己方前哨控制点的锚，哨兵不离开。"""
    return ctx.zone(ctx.team, 'central')


def lock_infantry_goal(robot, ctx, job, side):
    team, enemy = ctx.team, ctx.enemy
    their_card = outpost_card_spot(ctx, enemy, side)
    our_card = outpost_card_spot(ctx, team, side)
    our_threat = ctx.enemy_on(f'{team}_outpost') + _enemy_threat_near(ctx, our_card, 4.5)
    if job == 'flex':
        # 1. 己方前哨卡受压：回家补位，丢点等于基地失去无敌
        if our_threat > 0 and not ctx.our_outpost_full:
            return our_card
        # 2. 堡垒卡：+3/s 控制度并展开对方大装甲，确认安全才站
        if ctx.fortress_open and ctx.fortress_danger() == 0 and enemy_point_covered(ctx, robot['slot']):
            return ctx.zone(enemy, 'fortress')
        # 3. 敌方前哨卡被争夺或尚未易主：上去打第二持卡位
        if not ctx.their_outpost or ctx.enemy_on(f'{enemy}_outpost') > 0:
            return their_card
        # 4. 已双持：守住己方卡，顺便掩护 striker
        return our_card if our_threat > 0 else (their_card[0], their_card[1] + (1.5 if team == 'red' else -1.5))
    # striker：拿稳敌方前哨卡；对方全力压我们时才镜像回防
    if our_threat >= 2 and not ctx.their_outpost:
        return our_card
    return their_card


# ---- rush -------------------------------------------------------------------------------------

def rush_attempt_fourth_core(ctx):
    """速攻不碰 4 级：两枚单元和 45 秒都花在装炮上。"""
    return False


def rush_heavy_post(ctx):
    """对方点一开就前压到更近的射击位。"""
    forward = ctx.enemy_base_vulnerable() and ctx.obs['outposts'][ctx.enemy]['hp'] <= 0
    x, y = (16.6, 5.2) if forward else (14.9, 5.0)
    return (x, y) if ctx.team == 'red' else (28 - x, 15 - y)


def rush_sentry_goal(robot, ctx):
    return ctx.zone(ctx.team, 'central')


def rush_infantry_goal(robot, ctx, job, side):
    team, enemy = ctx.team, ctx.enemy
    their_card = outpost_card_spot(ctx, enemy, side)
    our_card = outpost_card_spot(ctx, team, side)
    our_threat = ctx.enemy_on(f'{team}_outpost') + _enemy_threat_near(ctx, our_card, 4.5)
    if job == 'flex':
        # 1. 家里快丢了还是得回
        if our_threat >= 2 and not ctx.our_outpost_full:
            return our_card
        # 2. 对方点已易主且前哨已毁：堡垒卡 +3/s
        if ctx.fortress_open and ctx.fortress_danger() == 0 and enemy_point_covered(ctx, robot['slot']):
            return ctx.zone(enemy, 'fortress')
        # 3. 双压敌方前哨卡，先把对面 striker 打掉
        return their_card
    # striker：全程钉在敌方前哨卡上
    if our_threat >= 3 and not ctx.their_outpost:
        return our_card
    return their_card


# ---- echo -------------------------------------------------------------------------------------

def echo_attempt_fourth_core(ctx):
    """控制度领先且时间充裕时补 4 级防御。"""
    return ctx.time < 260 and ctx.gap > -1


def echo_heavy_post(ctx):
    x, y = (14.9, 5.0)
    return (x, y) if ctx.team == 'red' else (28 - x, 15 - y)


def _echo_cards(ctx, robot, job):
    """候选卡片及分值；返回 [(score, point, tag)]。"""
    team, enemy = ctx.team, ctx.enemy
    their_card = outpost_card_spot(ctx, enemy, 1 if robot['slot'] % 2 else -1)
    our_card = outpost_card_spot(ctx, team, 1 if robot['slot'] % 2 else -1)
    our_threat = ctx.enemy_on(f'{team}_outpost') + _enemy_threat_near(ctx, our_card, 4.5)
    late = ctx.time > 300
    cards = []
    # 己方前哨卡：受压且未稳守时价值最高
    cards.append((90 if our_threat > 0 and not ctx.our_outpost_full else 25, our_card, 'our_outpost'))
    # 敌方前哨卡：未易主时全力争夺，已易主则维持
    contest = ctx.enemy_on(f'{enemy}_outpost') > 0
    cards.append((100 if not ctx.their_outpost else (60 if contest else 35), their_card, 'their_outpost'))
    # 敌方堡垒卡：+3/s，但吃双倍伤害
    if ctx.fortress_open:
        danger = ctx.fortress_danger()
        score = 0 if danger >= 2 else (170 if danger == 0 and late else 140 if danger == 0 else 70)
        cards.append((score if enemy_point_covered(ctx, robot['slot']) else 0, ctx.zone(enemy, 'fortress'), 'fortress'))
    else:
        cards.append((0, ctx.zone(enemy, 'fortress'), 'fortress'))
    # 己方中央卡：哨兵的锚；步兵只在哨兵失位且被抢时补
    if job == 'sentry':
        cards.append((200, ctx.zone(team, 'central'), 'our_central'))
    else:
        sentry_home = any(r['role'] == 'sentry' and r['alive'] and not r.get('weak')
                          and on_outpost_card(r, team, ctx) for r in ctx.obs['robots'])
        cards.append((80 if ctx.enemy_on(f'{team}_central') > 0 and not sentry_home else 0,
                      ctx.zone(team, 'central'), 'our_central'))
    # 落后且临近结束时：全部前压
    if ctx.gap < -10 and late:
        cards = [(score + (60 if tag in ('their_outpost', 'fortress') else -40 if tag in ('our_outpost', 'our_central') else 0), point, tag)
                 for score, point, tag in cards]
    # 领先且临近结束时：收缩保点
    if ctx.gap > 10 and late:
        cards = [(score + (50 if tag in ('our_outpost', 'our_central') else -50 if tag == 'fortress' else 0), point, tag)
                 for score, point, tag in cards]
    return cards


def echo_sentry_goal(robot, ctx):
    return ctx.zone(ctx.team, 'central')


def echo_infantry_goal(robot, ctx, job, side):
    """贪心分配：两台步兵各自选最高分且未被队友占用的卡片。"""
    team, enemy = ctx.team, ctx.enemy
    mine = _echo_cards(ctx, robot, 'infantry')
    mate = next((r for r in ctx.obs['robots'] if r['role'] == 'infantry' and r['slot'] != robot['slot']), None)
    if mate is not None:
        theirs = _echo_cards(ctx, mate, 'infantry')
        best_mate = max(theirs, key=lambda c: c[0]) if theirs else None
        if best_mate is not None and best_mate[0] >= 80:
            # 队友会去高价值卡：避开同卡，改选次高
            mine = [c for c in mine if c[2] != best_mate[2]] or mine
    best = max(mine, key=lambda c: c[0])
    if best[0] <= 0:
        return outpost_card_spot(ctx, enemy, side)
    return best[1]


# ---- anchor -----------------------------------------------------------------------------------
# 读对局教训：echo/rush 双压时，若对手双人反压我方前哨卡，5 秒内无人回防即丢点，
# 丢点 = 基地失去无敌 + 对手控制度 +1/s。anchor 用一台步兵常驻我方前哨卡、
# 哨兵常驻中央卡，两张卡同时有人即永久锁死己方前哨控制点；另一台步兵专职夺取
# 对方前哨卡。180 s 后确认安全才派锚位步兵去对方堡垒卡拿 +3/s。

def anchor_attempt_fourth_core(ctx):
    """控制度不落后就补 4 级（全队 50% 防御），锁点体系更依赖站得住。"""
    return ctx.time < 265 and ctx.gap > -3


def anchor_heavy_post(ctx):
    """中央高地南肩：同时够得到敌方前哨与基地。"""
    x, y = (14.9, 5.0)
    return (x, y) if ctx.team == 'red' else (28 - x, 15 - y)


def anchor_sentry_goal(robot, ctx):
    """中央高地块是己方前哨控制点的第二张卡，哨兵不离开。"""
    return ctx.zone(ctx.team, 'central')


def anchor_infantry_goal(robot, ctx, job, side):
    team, enemy = ctx.team, ctx.enemy
    their_card = outpost_card_spot(ctx, enemy, side)
    our_card = outpost_card_spot(ctx, team, side)
    behind = ctx.gap < -5
    if job == 'flex':
        # 1. 堡垒卡：已锁死对方前哨控制点且确认安全，+3/s 值得冒险
        if ctx.fortress_open and ctx.fortress_danger() == 0 and enemy_point_covered(ctx, robot['slot']):
            return ctx.zone(enemy, 'fortress')
        # 2. 大比分落后且临近收官：放弃锚位全员前压
        if behind and ctx.time > 300:
            return their_card
        # 3. 锚位：钉在我方前哨卡上，对方永远无法夺取
        return our_card
    # striker：专职夺取对方前哨卡；家里三人以上压上来才镜像回防
    if ctx.enemy_on(f'{team}_outpost') >= 3 and not ctx.their_outpost:
        return our_card
    return their_card


# ---- echo2（读阵应变 + 开局锚防）--------------------------------------------------------------
# echo 的唯一系统性败因：开局双压时，若对手反压我方前哨卡，flex 回防路上（5 s 窗口）
# 已经丢点。echo2 让 flex 在开局锚住我方前哨卡：对方 20 s 内没碰我方两张卡才去参压；
# 一旦对方露卡（公开占卡信息，不受视野限制）就钉住duels。

def echo2_infantry_goal(robot, ctx, job, side):
    team = ctx.team
    if job == 'flex' and not ctx.our_outpost_full:
        contested = ctx.enemy_on(f'{team}_outpost') + ctx.enemy_on(f'{team}_central')
        if ctx.time < 20 or contested > 0:
            return outpost_card_spot(ctx, team, side)
    return echo_infantry_goal(robot, ctx, job, side)


def echo2_attempt_fourth_core(ctx):
    return echo_attempt_fourth_core(ctx)


def echo2_heavy_post(ctx):
    return echo_heavy_post(ctx)


def echo2_sentry_goal(robot, ctx):
    return echo_sentry_goal(robot, ctx)


# ---- dispatch ---------------------------------------------------------------------------------

_LAYER = {
    'lock': {'fourth': lock_attempt_fourth_core, 'post': lock_heavy_post,
             'sentry': lock_sentry_goal, 'infantry': lock_infantry_goal},
    'rush': {'fourth': rush_attempt_fourth_core, 'post': rush_heavy_post,
             'sentry': rush_sentry_goal, 'infantry': rush_infantry_goal},
    'echo': {'fourth': echo_attempt_fourth_core, 'post': echo_heavy_post,
             'sentry': echo_sentry_goal, 'infantry': echo_infantry_goal},
    'anchor': {'fourth': anchor_attempt_fourth_core, 'post': anchor_heavy_post,
               'sentry': anchor_sentry_goal, 'infantry': anchor_infantry_goal},
    'echo2': {'fourth': echo2_attempt_fourth_core, 'post': echo2_heavy_post,
              'sentry': echo2_sentry_goal, 'infantry': echo2_infantry_goal},
}


def attempt_fourth_core(ctx):
    return _LAYER[STYLE]['fourth'](ctx)


def heavy_post(ctx):
    return _LAYER[STYLE]['post'](ctx)


def sentry_goal(robot, ctx):
    return _LAYER[STYLE]['sentry'](robot, ctx)


def infantry_goal(robot, ctx, job, side):
    return _LAYER[STYLE]['infantry'](robot, ctx, job, side)
