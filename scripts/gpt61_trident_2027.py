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
