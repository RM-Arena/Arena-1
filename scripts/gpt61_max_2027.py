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
