"""Adaptive single-robot policy; materialized into self-contained submissions."""
import math
from sdk import (action, aim_at, aim_pitch, ballistic_reachable, can_fire,
                 intercept, navigate, nearest_enemy, instant_revive_cost,
                 rescue_point, tipped_teammates, resource_pickup_point, assembly_work_point, message)

TACTIC = "guard"


def distance(robot, point):
    return math.hypot(robot['x'] - point[0], robot['y'] - point[1])


def move_to(robot, goal, arena, tolerance=.4):
    return navigate(robot, goal, arena) if distance(robot, goal) > tolerance else (0, 0)


def unstick(robot, move, memory, now):
    """Action fields for `move`; once a robot pushing on has neither moved nor turned for
    1.5 s, it backs off at an angle for 0.7 s so teammates that meet head-on in a narrow
    lane get past each other. It keeps its heading then: a chassis cannot turn on bumps."""
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
    turned = abs((robot['heading'] - trail[0][3] + math.pi) % math.tau - math.pi)
    if now - trail[0][0] < 1.4 or distance(robot, trail[0][1:3]) > .1 or turned > .15:
        return {'move': move}
    m['tries'] += 1
    angle = math.atan2(move[1], move[0]) + math.pi + (.9 if (robot['slot'] + m['tries']) % 2 else -.9)
    m.update(escape=[.7 * math.cos(angle), .7 * math.sin(angle)], until=now + .7, heading=robot['heading'])
    trail.clear()
    return {'move': m['escape'], 'heading': m['heading']}


def rescue(robot, observation, target, memory):
    return action(rescue=target['slot'],
                  **unstick(robot, move_to(robot, rescue_point(robot, target), observation['arena'], .12),
                            memory, observation['time']))


def engineer(robot, obs, memory):
    core = obs['assemblies'][obs['team']]
    active = core['stage'] in ('moving', 'inserting', 'buffered')
    tipped = [r for r in tipped_teammates(obs) if r['role'] != 'aerial']
    target = min(tipped, key=lambda r: (distance(robot, (r['x'], r['y'])), r['slot']), default=None)
    if TACTIC == 'guard':
        if target and not robot['weak']:
            return rescue(robot, obs, target, memory)
        front = [r for r in obs['robots'] if r['alive'] and r['role'] in ('hero', 'infantry')]
        sign = 1 if obs['team'] == 'red' else -1
        ally = max(front, key=lambda r: (sign * r['x'], -r['slot']), default=None)
        base = obs['bases'][obs['team']]
        goal = (ally['x'] - sign * 1.5, ally['y']) if ally else (base['x'] + sign * 3, base['y'])
        return action(**unstick(robot, move_to(robot, goal, obs['arena']), memory, obs['time']))
    completed = obs['teams'][obs['team']]['completed_difficulties']
    possible = [d for d in range(1, 5) if obs['time'] >= (d - 1) * 60
                and (d == 1 or d - 1 in completed)
                and not (d == 4 and (4 in completed or core['permanent_lock'] or obs['time'] < core['retry_at']))]
    if not active and not possible:
        if target and not robot['weak']:
            return rescue(robot, obs, target, memory)
        return action()
    difficulty = core['difficulty'] if active else max(possible)
    needed = 1 if difficulty < 4 or core['inserted_units'] == 1 else 2
    if not active and robot['carried_units'] < needed:
        goal = resource_pickup_point(robot, obs['arena'])
        drive = unstick(robot, move_to(robot, goal, obs['arena'], .08), memory, obs['time'])
        # Face the station there: the arm cannot slew round to a unit behind the chassis.
        if distance(robot, goal) <= .08:
            station = next(f for f in obs['arena']['field_geometry']['fixtures']
                           if f['kind'] == 'resource' and f['team'] == obs['team'])
            drive['heading'] = math.atan2(station['pick_dir'][1], station['pick_dir'][0])
        return action(pick_unit=True, **drive)
    goal = assembly_work_point(robot, obs['arena'])
    gap = distance(robot, goal)
    docked = gap <= .1
    move = move_to(robot, goal, obs['arena'], .1)
    pace = math.hypot(*move)
    # The work point lies past the plinth's bevelled edge: a slowing approach stalls
    # on that slope, tilted too far for the exact grades. Dock level, facing the core.
    if gap < 1 and 0 < pace < .2:
        move = (move[0] / pace * .2, move[1] / pace * .2)
    drive = unstick(robot, move, memory, obs['time']) if gap > .6 else {'move': move}
    if docked:
        origin = obs['arena']['assembly_frames'][obs['team']]['origin']
        plinth = next(z for z in obs['arena']['zones'] if z['id'] == obs['team'] + '_assembly')
        drive['heading'] = math.atan2(origin[1] - plinth['y'], origin[0] - plinth['x'])
    return action(brake=docked, assembly=difficulty, assembly_insert=True, assembly_translate=True,
                  assembly_rotate=core['target_rotation'], assembly_confirm=True, **drive)


def act(obs, state):
    slot = obs['controlled_ids'][0]
    robot = next(r for r in obs['robots'] if str(r['slot']) == slot)
    team = obs['team']
    sign = 1 if team == 'red' else -1
    enemy = 'blue' if team == 'red' else 'red'
    base, outpost = obs['bases'][team], obs['outposts'][enemy]
    memory = (state or {}).get('stuck', {})
    structure = dict(outpost if outpost['hp'] > 0 else obs['bases'][enemy],
                     kind='outpost' if outpost['hp'] > 0 else 'base')
    # Aerial robots start on the pad: support requests launch them from standby.
    if not robot['alive'] and robot['role'] != 'aerial':
        command = action(revive=obs['teams'][team]['resources'] >= instant_revive_cost(robot, obs['time']) and obs['time'] < 300)
    elif robot['role'] == 'engineer':
        command = engineer(robot, obs, memory)
    else:
        aerial = robot['role'] == 'aerial'
        defending = TACTIC == 'guard'
        retreating = not aerial and (robot['weak'] or robot['hp'] < robot['max_hp'] * (.5 if defending else .22) or robot['ammo'] == 0)
        target = nearest_enemy(robot, obs)
        if defending and target and distance(robot, (target['x'], target['y'])) > 8:
            target = None
        if TACTIC == 'assault' and (robot['role'] in ('hero', 'aerial') or target is None):
            target = structure
        if target and ballistic_reachable(robot, target):
            target = intercept(robot, target) if 'vx' in target else target
        else:
            target = None
        if aerial:
            lane = obs['arena']['flight_lanes'][team]
            forward = lane['max_x'] - .8 if team == 'red' else lane['min_x'] + .8
            rear = lane['min_x'] + 1 if team == 'red' else lane['max_x'] - 1
            goal = (rear if defending else forward, lane['center_y'])
        elif retreating:
            supply = next(z for z in obs['arena']['zones'] if z['id'] == team + '_supply')
            goal = (supply['x'], supply['y'])
        elif defending:
            own_outpost = obs['outposts'][team]
            anchor = own_outpost if own_outpost['hp'] > 0 else base
            goal = (anchor['x'] - sign * 1.5, anchor['y'] + (robot['slot'] % 3 - 1) * .8)
        else:
            goal = (structure['x'] - sign * (4.5 if robot['role'] == 'hero' else 2.6),
                    structure['y'] + (robot['slot'] % 3 - 1) * .8)
        aim = aim_at(robot, target) if target else None
        aligned = aim is not None and abs((aim - robot['aim'] + math.pi) % math.tau - math.pi) < .15
        operations = {}
        if aerial:
            operations.update(support=True, altitude=1.9)
        if not aerial and robot['ammo'] < (2 if robot['role'] == 'hero' else 20):
            operations['buy_ammo'] = {'amount': 5 if robot['role'] == 'hero' else 50, 'remote': False}
        move = move_to(robot, goal, obs['arena'])
        # Preserve each model's selected chassis/weapon profiles from its hardware.
        command = action(aim=aim, fire=aligned and target is not None and can_fire(robot),
                         pitch=aim_pitch(robot, target) if target else .04, **operations,
                         **({'move': move} if aerial else unstick(robot, move, memory, obs['time'])))
    if obs['tick'] % 20 == 0:
        command['messages'] = [message({'intent': TACTIC, 'model': robot['model_slot']})]
    return {slot: command}, {'ticks': (state or {}).get('ticks', 0) + 1, 'tactic': TACTIC, 'stuck': memory}
