"""RMUC 2027 rulebook baseline: every role, in team, squad, distributed or deck play.

The heavy robot carries energy units, climbs the tech-core levels, fits its modular 42 mm
launcher at the workbench and then shells structures from the central deck. Infantry take
the enemy outpost position (control degree, and the enemy base loses its invulnerability)
and later the enemy fortress. The sentry holds the own central-highland card in the
posture the fight calls for. Aerial robots ram the rotating outpost armor with timed
dashes, then the enemy base once it can be damaged.

TACTIC selects the behaviour: balanced (the rulebook baseline), assault or guard.
"""
import math
from sdk import (DESIGNS, action, aim_at, aim_pitch, assembly_work_point, ballistic_reachable, can_fire,
                 drones, instant_revive_cost, intercept, message, navigate, rescue_point, resource_pickup_point,
                 terrain_height, tipped_teammates, workbench_point, zone_center)

TACTIC = "balanced"

STEP_ORDER = ("positioning", "inserting", "lifting", "flipping", "rotating", "verifying", "complete")

# A chassis spins at a fraction of its turret's slew rate: the gun has to keep pointing at the
# target while the hull turns, and a spin faster than the turret can follow would trade every
# shot for the armour rotation it buys.
SPIN_TURRET_FRACTION = .55
# 小陀螺 holds for this long after the last hit, and while an enemy is this close even without
# new damage, so incoming fire keeps landing on a different plate.
SPIN_HOLD_S = 1.6
SPIN_RANGE_M = 8.0
# Enemy inside this radius gets a retreat first and a shot second (per role).
EVADE_RANGE = {'heavy': 3.2, 'infantry': 2.6, 'sentry': 2.2}
# A retreat keeps a share of the current route: backing straight off lets a chaser pin the robot
# in place, and the robot that never reaches its own plinth loses the whole economy of a match.
EVADE_KEEP = .5
# One dodge burst lasts this long, then the robot holds its line for `EVADE_REST_S`: a chaser
# cannot freeze the task by staying close, and the gun keeps working either way.
EVADE_HOLD_S = 2.5
EVADE_REST_S = 1.5
# Chassis types that can translate while the hull turns; a legged chassis drives along its own
# heading, so it only spins while standing.
STRAFE_CHASSIS = ('mecanum', 'omni', 'swerve')
# Supercap reserve kept for the next climb: the store is 1800 J and a climb burns ~170 J/s.
SUPERCAP_RESERVE_J = 250.0
CLIMB_DELTA_M = .06


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


def design(robot):
    """The hardware record the engine plays: turret slew, chassis type, supercap."""
    return DESIGNS.get(str(robot.get('model_slot') or robot['slot']), {})


def turret_rate(robot):
    return float(design(robot).get('turret_yaw_rate_rad_s') or 5.0)


def can_strafe(robot):
    return design(robot).get('chassis_type') in STRAFE_CHASSIS


def supercap(robot):
    return robot.get('supercap_energy_j', 0.0)


def climb_ahead(robot, move, arena, lookahead=.55):
    """Metres the ground rises over the next `lookahead` along `move`."""
    pace = math.hypot(*move)
    if pace < .05:
        return 0.0
    x = robot['x'] + move[0] / pace * lookahead
    y = robot['y'] + move[1] / pace * lookahead
    return terrain_height(arena, x, y) - terrain_height(arena, robot['x'], robot['y'])


def give_way(robot, move, obs):
    """Step around a teammate standing in the way instead of pushing into it.

    Two robots driving into each other used to lock both on the same line: neither could pass
    and the pair spun on the spot. The lower slot keeps the route and the other one sidesteps,
    which is deterministic, so the two never mirror each other's dodge.
    """
    pace = math.hypot(*move)
    if pace < .2:
        return move
    ux, uy = move[0] / pace, move[1] / pace
    for mate in obs['robots']:
        if mate['id'] == robot['id'] or not mate['alive']:
            continue
        rx, ry = mate['x'] - robot['x'], mate['y'] - robot['y']
        gap = math.hypot(rx, ry)
        if gap > 1.6 or gap < 1e-6 or (rx * ux + ry * uy) / gap < .45:
            continue
        if robot['slot'] < mate['slot']:
            continue
        side = 1.0 if (rx * uy - ry * ux) > 0 else -1.0
        return (ux * .5 - uy * side * .86, uy * .5 + ux * side * .86)
    return move


def drive(robot, goal, obs, memory, tolerance=.35):
    """Navigate to `goal`. The chassis draws on its supercap (`power`) on a climb and while it
    is slow under a move order: the 2027 heavy robot has only 50 W for slopes and steps."""
    if goal is None or distance(robot, goal) <= tolerance:
        return {'move': (0, 0)}
    fields = unstick(robot, navigate(robot, goal, obs['arena']), memory, obs['time'])
    fields['move'] = give_way(robot, fields['move'], obs)
    # Spend the supercap *before* the chassis stalls: waiting for the stall meant the heavy
    # robot burned its approach against the resource-island slope and then lost the momentum it
    # needed to crest it. The cap is 1800 J and the boost is ~170 W, so a reserve is kept for
    # the next climb instead of emptying it on the flat.
    climbing = climb_ahead(robot, fields['move'], obs['arena']) > CLIMB_DELTA_M
    stalled = math.hypot(robot['vx'], robot['vy']) < .3 and math.hypot(*fields['move']) > .2
    if (climbing or stalled) and supercap(robot) > SUPERCAP_RESERVE_J:
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
        self.positions = obs.get('positions', {})
        self.memory = state.setdefault('stuck', {})

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
    if outpost and ballistic_reachable(robot, outpost):
        return outpost
    if ctx.enemy_base_vulnerable():
        base = dict(ctx.obs['bases'][ctx.enemy], kind='base')
        if ballistic_reachable(robot, base):
            return base
    return None


def enemy_target(robot, ctx, reach):
    """Nearest visible, damageable enemy robot within `reach` metres and ballistic range."""
    best = None
    for e in ctx.obs['enemies']:
        if not e['alive'] or not e.get('targetable', True) or e.get('invulnerable'):
            continue
        d = distance(robot, (e['x'], e['y']))
        if d <= reach and (best is None or (d, e['hp']) < best[0]) and ballistic_reachable(robot, e):
            best = ((d, e['hp']), e)
    return intercept(robot, best[1]) if best else None


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
        target = drone_target(robot, ctx)
    if target is None and structures:
        target = structure_target(robot, ctx)
    if target is None:
        return {}
    aim = aim_at(robot, target)
    heavy = robot['role'] == 'heavy'
    aligned = abs(wrap(aim - robot['aim'])) < (.08 if heavy else .14)
    # 17 mm keeps a 20-heat margin: one decision can fire two rounds.
    fire = aligned and can_fire(robot) and (heavy or robot['heat'] + 20 <= robot['max_heat'])
    return {'aim': aim, 'pitch': aim_pitch(robot, target), 'fire': fire}


def nearest_foe(robot, ctx):
    """Closest visible ground enemy as (distance, enemy); aerial bodies are not a threat."""
    best = None
    for e in ctx.obs['enemies']:
        if not e['alive'] or not e.get('targetable', True) or e.get('invulnerable'):
            continue
        d = distance(robot, (e['x'], e['y']))
        if best is None or d < best[0]:
            best = (d, e)
    return best


def evade(robot, ctx, fields, foe, reach=None):
    """贴近就脱离再输出: back out of an enemy's reach, then keep shooting from there.

    A rowing chassis can only drive along its heading, so it turns away and accepts the turret
    swing; a strafing one keeps the gun on the target and slides sideways out of reach. The
    retreat is a burst, not a state: after `EVADE_HOLD_S` the robot takes its route back for
    `EVADE_REST_S`, which is what stops an enemy that merely stands nearby from pinning it.
    """
    reach = EVADE_RANGE.get(robot['role'], 2.6) if reach is None else reach
    memory = ctx.memory.setdefault('evade-' + str(robot['slot']), {})
    if foe is None or foe[0] > reach:
        memory['since'] = None
        return fields
    if ctx.time < memory.get('rest_until', -1):
        return fields
    since = memory.get('since')
    if since is None or ctx.time < since:
        since = memory['since'] = ctx.time
    if ctx.time - since >= EVADE_HOLD_S:
        memory['since'], memory['rest_until'] = None, ctx.time + EVADE_REST_S
        return fields
    ax, ay = robot['x'] - foe[1]['x'], robot['y'] - foe[1]['y']
    gap = math.hypot(ax, ay) or 1.0
    away = (ax / gap, ay / gap)
    task = fields.get('move') or (0, 0)
    pace = math.hypot(*task)
    if pace > .05:
        away = (away[0] + task[0] / pace * EVADE_KEEP, away[1] + task[1] / pace * EVADE_KEEP)
        length = math.hypot(*away) or 1.0
        away = (away[0] / length, away[1] / length)
    fields.pop('heading', None)
    if can_strafe(robot):
        fields['move'] = away          # the hull keeps its bearing, the turret keeps the target
    else:
        fields['move'] = (away[0] * .7, away[1] * .7)
        fields['heading'] = math.atan2(away[1], away[0])
    if supercap(robot) > SUPERCAP_RESERVE_J:
        fields['power'] = 200          # leaving is worth the capacitor
    return fields


def spin(robot, ctx, fields, foe):
    """小陀螺: turn the hull under fire so successive hits land on different armour plates.

    A hit makes the robot stop and spin: that is the whole point of the move, and a chassis
    that keeps driving cannot turn its hull. Merely having an enemy inside `SPIN_RANGE_M` is
    not enough to stop it, so a robot on a task only spins when it is already standing.
    """
    if foe is None or robot.get('weak'):
        return fields
    hit = ctx.time - robot.get('last_damage_time', -99) <= SPIN_HOLD_S
    pressed = foe[0] <= SPIN_RANGE_M
    if not (hit or pressed):
        return fields
    if not can_strafe(robot):
        if hit:
            fields['move'] = (0, 0)
            fields['brake'] = True
        elif math.hypot(*fields.get('move', (0, 0))) > .2:
            return fields
    fields.pop('heading', None)
    fields['yaw_rate'] = round(turret_rate(robot) * SPIN_TURRET_FRACTION, 2)
    return fields


def can_buy_here(robot, ctx):
    """Local exchange: own base, supply zone or high point (contact lasts 2 s)."""
    for kind in ('base', 'supply', 'high_point'):
        if distance(robot, ctx.zone(ctx.team, kind)) < (1.6 if kind == 'base' else 1.0):
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
    # attempt gets 15 s (a robot wedged where the arm cannot reach is left for a minute),
    # so a failed rescue never stalls the assemblies.
    attempts = memory.setdefault('rescue', {})
    for key, started in list(attempts.items()):
        if ctx.time - started > 75:
            del attempts[key]
    tipped = [t for t in tipped_teammates(obs) if t['role'] != 'aerial' and t['slot'] != robot['slot']
              and distance(robot, (t['x'], t['y'])) < 7 and ctx.time - attempts.get(t['id'], ctx.time) < 15]
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
    level_four = armed and 4 not in done and TACTIC != 'assault' and not memory.get('l4_tried') and ctx.time < 285
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
    """Take an energy unit at the own resource hub.

    A two-arm heavy parks square to the dispenser: its arms sit at ±0.21 m off the centreline,
    so a chassis that arrives at an angle leaves the second arm outside the unit's reach and
    the grab stalls until the engine times it out. The heading is squared up during the
    approach (not only at the station), and the grabbing arm is named explicitly so the two
    arms take turns instead of both reaching for the same unit.

    The grab request must stay asserted for the whole sequence: releasing `pick_unit` reads as
    an abandoned grab and cancels it mid-way. Recovery therefore keys off the engine dropping
    the pickup itself (its own stall timeout), never off a frozen progress number.
    """
    goal = resource_pickup_point(robot, ctx.arena)
    station = next(f for f in ctx.arena['field_geometry']['fixtures'] if f['kind'] == 'resource' and f['team'] == ctx.team)
    facing = math.atan2(station['pick_dir'][1], station['pick_dir'][0])
    arms = int(design(robot).get('arm_count', 1))
    arm = robot['carried_units'] % 2 if arms >= 2 else 0
    gap = distance(robot, goal)
    # A private memory slot: `unstick` owns the plain slot key and expects its own fields there.
    memory = ctx.memory.setdefault('grab-' + str(robot['slot']), {})
    state = robot.get('unit_pickup') or {}
    # A grab the engine cancelled (unreachable, wrong side, chassis drifted out of the zone)
    # needs a new pose: back off the dispenser lane once, then drive in again.
    if memory.get('grab_stage') and not state and robot['carried_units'] <= memory.get('grab_carry', 0) \
            and ctx.time >= memory.get('retry_until', -1):
        memory['retry_until'] = ctx.time + .8
    memory['grab_stage'] = state.get('stage')
    memory['grab_carry'] = robot['carried_units']
    if ctx.time < memory.get('retry_until', -1):
        back = (goal[0] + station['pick_dir'][0] * -.4, goal[1] + station['pick_dir'][1] * -.4)
        fields = drive(robot, back, ctx.obs, ctx.memory, .1)
        fields['heading'] = facing
        return fields
    # Drift across the dispenser lane: the two arms stand ±0.21 m off the centreline, so a
    # chassis that parks a few centimetres to the side leaves the far arm short of the unit and
    # the grab can only time out. Request the grab from the lane, and keep closing until there.
    lateral = abs((robot['x'] - goal[0]) * math.sin(facing) - (robot['y'] - goal[1]) * math.cos(facing))
    on_lane = lateral <= .05
    if gap <= .12 and on_lane:
        return {'move': (0, 0), 'brake': True, 'pick_unit': True, 'pickup_arm': arm, 'heading': facing}
    fields = drive(robot, goal, ctx.obs, ctx.memory, .03)
    # Square up while still approaching: a chassis that only aligns once it has stopped needs a
    # second pass, and a two-arm heavy cannot reach across its own deck.
    fields['heading'] = facing
    fields['pickup_arm'] = arm
    fields['pick_unit'] = gap <= .3 and on_lane
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
            fields['assembly_rotate2'] = cores[1]['target_rotation']
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
    x, y = (14.9, 5.0) if TACTIC != 'guard' else (12.0, 9.6)
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
    foe = nearest_foe(robot, ctx)
    fields.update(weapon(robot, ctx, reach=12.0))
    evade(robot, ctx, fields, foe)
    spin(robot, ctx, fields, foe)
    return fields


# ---- Infantry ------------------------------------------------------------------------------

def infantry_job(robot, ctx):
    """striker: take the enemy outpost position; flex: shoot structures and escort; guard."""
    if TACTIC == 'guard':
        return 'guard'
    mates = sorted(r['slot'] for r in ctx.obs['robots'] if r['role'] == 'infantry')
    if TACTIC == 'assault':
        return 'striker' if mates.index(robot['slot']) % 2 == 0 else 'flex'
    return 'striker' if mates and robot['slot'] == mates[0] else 'flex'


def outpost_card_spot(ctx, owner, side=0):
    """A standing point on an outpost buff card, on the deck side away from the kerb."""
    x, y = ctx.obs['outposts'][owner]['x'], ctx.obs['outposts'][owner]['y']
    toward = (14 - x, 7.5 - y)
    length = math.hypot(*toward) or 1
    ux, uy = toward[0] / length, toward[1] / length
    return (x + ux * .62 - uy * side * .3, y + uy * .62 + ux * side * .3)


def infantry(robot, ctx):
    obs, team, enemy = ctx.obs, ctx.team, ctx.enemy
    fields = {}
    if obs['tick'] == 0:
        fields['profile'] = {'chassis': robot['chassis_profile'], 'weapon': robot['weapon_profile']}
    fields.update(ammo_fields(robot, ctx, 30, 150, 100, 200))
    if robot['weak'] or robot['hp'] < robot['max_hp'] * (.45 if TACTIC == 'guard' else .3):
        fields.update(drive(robot, ctx.zone(team, 'supply'), obs, ctx.memory))
        fields.update(weapon(robot, ctx, reach=6, structures=False))
        return fields
    if ctx.time < 1.2:
        return fields
    job = infantry_job(robot, ctx)
    side = 1 if robot['slot'] % 2 else -1
    if job == 'guard':
        goal = ctx.zone(team, 'central') if robot['slot'] % 2 else outpost_card_spot(ctx, team, side)
    elif job == 'striker':
        holds_outpost = ctx.controls(f'{enemy}_outpost')
        if holds_outpost and ctx.time >= 180 and obs['bases'][enemy]['hp'] > 0:
            goal = ctx.zone(enemy, 'fortress')       # open the enemy base and take its position
        else:
            goal = ctx.zone(enemy, 'central')        # take the enemy outpost position
    elif TACTIC != 'assault' and not ctx.controls(f'{team}_outpost', full=True) and not sentry_holds(ctx):
        goal = ctx.zone(team, 'central')             # our outpost position is only held by presence
    else:
        outpost = ctx.hostile_outpost()
        if outpost and outpost['site'] == enemy:
            goal = outpost_card_spot(ctx, enemy, side)
        elif not ctx.controls(f'{team}_outpost'):
            goal = ctx.zone(team, 'central')         # win back our own outpost position
        else:
            goal = ctx.zone(enemy, 'central') if TACTIC != 'assault' else outpost_card_spot(ctx, enemy, side)
    fields.update(drive(robot, goal, obs, ctx.memory, .3))
    fields.update(weapon(robot, ctx, reach=7 if job == 'guard' else 9))
    foe = nearest_foe(robot, ctx)
    evade(robot, ctx, fields, foe)
    spin(robot, ctx, fields, foe)
    return fields


def sentry_holds(ctx):
    """An own sentry is alive on (or close to) the own central-highland card."""
    spot = ctx.zone(ctx.team, 'central')
    return any(r['role'] == 'sentry' and r['alive'] and not r['weak'] and distance(r, spot) < 1.5 for r in ctx.obs['robots'])


# ---- Sentry --------------------------------------------------------------------------------

def sentry(robot, ctx):
    obs, team = ctx.obs, ctx.team
    memory = ctx.state.setdefault('sentry', {})
    fields = {}
    # Holding the card matters more than rations: while our outpost position is held only
    # by our presence, leaving it for 5 s hands it to the enemy. Ammo is bought remotely;
    # the rations are collected when the sentry has to heal at the supply zone anyway.
    covered = any(r['alive'] and not r['weak'] and r['slot'] != robot['slot'] and r['role'] != 'aerial'
                  and distance(r, ctx.zone(team, 'central')) < .6 for r in obs['robots'])
    if robot['weak'] or (robot['hp'] < robot['max_hp'] * .25 and (covered or ctx.controls(f'{team}_outpost', full=True))):
        goal = ctx.zone(team, 'supply')
    elif TACTIC == 'assault' and ctx.controls(f'{ctx.enemy}_outpost'):
        goal = ctx.zone(ctx.enemy, 'central')
    else:
        goal = ctx.zone(team, 'central')             # hold our outpost position (exclusive card)
    moving = distance(robot, goal) > .6
    fields.update(drive(robot, goal, obs, ctx.memory, .3))
    shot = weapon(robot, ctx, reach=10)
    fields.update(shot)
    threatened = ctx.time - robot.get('last_damage_time', -99) < 2.0
    if robot['hp'] < robot['max_hp'] * .5 and threatened:
        wanted = 'defense'
    elif shot and not moving:
        wanted = 'attack'
    elif moving and distance(robot, goal) > 4:
        wanted = 'move'
    else:
        wanted = 'defense' if TACTIC == 'guard' else robot.get('posture', 'move')
    if wanted != robot.get('posture') and ctx.time >= (robot.get('posture_ready_at') or 0):
        fields['posture'] = wanted
    enhanced = wanted == 'defense' and robot['hp'] < robot['max_hp'] * .3 and threatened
    if bool(robot.get('posture_enhanced')) != enhanced and ctx.time >= (robot.get('posture_ready_at') or 0):
        fields['posture_enhanced'] = enhanced
    memory['last'] = wanted
    # The sentry holds the card without ammo too, so it rebuys remotely with a small reserve.
    fields.update(ammo_fields(robot, ctx, 40, 100, 100, 50))
    foe = nearest_foe(robot, ctx)
    # A sentry does not abandon its card, but it still slides out of a body check and spins
    # under fire; the hull has enough yaw authority that the gun keeps the target.
    evade(robot, ctx, fields, foe, EVADE_RANGE['sentry'] * .8)
    spin(robot, ctx, fields, foe)
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
    outpost = ctx.hostile_outpost()
    if outpost:
        track_spin(memory, outpost['site'], outpost, ctx.time)
        return dict(outpost, spin=memory.get('spin', {}).get(outpost['site'], 0.0))
    if TACTIC != 'guard' or ctx.time >= 300:
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


def act(obs, state):
    state = dict(state or {})
    ctx = Context(obs, state)
    commands = {}
    for robot in obs['robots']:
        slot = str(robot['slot'])
        if slot not in obs['controlled_ids']:
            continue
        try:
            commands[slot] = action(**decide(robot, ctx))
        except Exception:
            commands[slot] = action()       # hold still rather than lose the program
    state['ticks'] = state.get('ticks', 0) + 1
    return commands, state


# One author provides five self-contained strategies; each process owns one slot and
# reports what it sees to its teammates every second.
_team_act = act


def act(obs, state):
    slot = "1"
    assert obs["controlled_ids"] == [slot]
    commands, new_state = _team_act(obs, state)
    new_state["reports"] = obs["messages"][-4:]
    if obs["tick"] % 20 == 0:
        commands.setdefault(slot, action())["messages"] = [message({
            "intent": "report", "slot": slot,
            "seen": [enemy["id"] for enemy in obs["enemies"][:3]],
        })]
    return commands, new_state
