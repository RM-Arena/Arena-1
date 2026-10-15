## Interface Reference

### The act Function

```python
def act(observation: dict, state) -> tuple[dict, object]:
    ...
    return actions, new_state
```

- Called every 0.1 s. The match state advances every 0.05 s, so `tick` grows by 2 between decisions; the first call has `tick == 0`.
- `actions` maps slot strings to action dicts, e.g. {{#team}}{{^distributed}}`{"1": action(...), "7": action(...)}`{{/distributed}}{{#distributed}}`{"3": action(...)}`{{/distributed}}{{/team}}{{#robot}}{{^adaptive}}`{"{{slot}}": action(...)}`{{/adaptive}}{{#adaptive}}`{obs["controlled_ids"][0]: action(...)}`{{/adaptive}}{{/robot}}. A robot without an action this round gets an empty action (stop, no fire).
- An action stays in effect until the next decision (0.1 s, i.e. 2 match steps).
- `state` is the `new_state` you returned last time, or `None` on the first call. It must be JSON-serializable and at most 32 KiB. Module-level globals also persist within a match, but keeping memory in `state` makes runs easier to reproduce.
- The `random` module is seeded with a fixed seed, so identical inputs give identical results. Do not rely on wall-clock time; use `observation["time"]`.

### Observation

| Field | Contents |
| --- | --- |
| `tick`, `time`, `remaining` | Match step, elapsed seconds, remaining seconds |
| `dt`, `policy_dt` | Match step 0.05 s, decision interval 0.1 s |
| `team` | `"red"` or `"blue"` |
| `controlled_ids` | Slots you may control (list of strings) |
| `robots` | {{^adaptive}}Full state of your six robots (see below){{/adaptive}}{{#adaptive}}Full actual own lineup at match time; slot is the instance ID and model_slot is the hardware model{{/adaptive}} |
| `enemies` | Currently visible enemy robots (wrecks included) with everything their exterior shows — see "Visible enemy robots" below; the aerial robot and wrecks have `targetable=False` |
| `messages`, `message_inboxes` | Team messages and inboxes indexed by controlled slot; available in every control mode, see "Team Communication" |
| `vision` | What each controlled observer (slot string as key) sees right now: `{"enemies": [id…], "allies": [id…]}`, plus `camera.origin`, `camera.direction`, horizontal/vertical field of view and `range_m` |
| `bases`, `outposts` | Both teams' bases and outposts: `x, y, z, hp, max_hp, armor_open, shield_hp, ever_destroyed, rotation, rotation_stopped` and more |
| `teams` | Your team's full economy (`resources` coins, `purchased_17`/`purchased_42` ammo bought, `tech_income`, `level_cap`, `completed_difficulties`, `rebuild_credits`, `fortress_ammo`, `attack_damage` and more); for the opponent, only `attack_damage` |
| `zones` | Current `owner`, `occupants` and `contested` of each buff zone |
| `runes` | Your team's power-rune state and targets |
| `assemblies` | Both teams' tech-core assembly state |
| `projectiles` | Visible projectiles: all of your team's, plus enemy ones within vision |
| `arena` | Map geometry, see "Match Overview" |
| `referee` | Referee snapshot, see below |
| `specs`, `official_rules`, `simulation_assumptions` | Parameter summaries; use `sdk.RULES`, `sdk.DESIGNS` or `arena.json` for complete values |

Common fields of each robot in `robots`:

| Field | Meaning |
| --- | --- |
| `id`, `slot`, `team`, `role` | e.g. `"red-3"`, `3`, `"red"`, `"infantry"`; `role` is `hero`, `engineer`, `infantry` or `aerial` |
| `x, y, z`, `vx, vy, vz` | Position and velocity; `z` is the body reference height and may sit slightly below ground when the suspension compresses |
| `heading`, `aim`, `pitch` | Chassis heading, turret world yaw, turret pitch (relative to the chassis) |
| `quaternion`, `angular_velocity`, `grounded` | Body orientation, angular velocity, whether it touches the ground |
| `hp`, `max_hp`, `alive` | HP. The aerial robot has `max_hp == 0`, and its `alive` means support is on |
| `ammo` | Rounds the robot may fire |
| `heat`, `max_heat`, `cooling_rate`, `overheated`, `heat_permanent_lock` | Heat state |
| `overspeed_locked`, `overspeed_lock_until`, `overspeed_permanent_lock`, `launcher_fault` | Muzzle-speed locks and unsupported hardware speed |
| `yellow_cards`, `red_card`, `fpv_blocked_until` | Card count, dismissal and camera blackout deadline |
| `level`, `experience` | Level and XP |
| `profile`, `chassis_profile`, `weapon_profile` | Current profile |
| `power_limit`, `power_w`, `buffer_energy_j`, `energy`, `power_cutoff_until` | Power and energy |
| `weak`, `invulnerable`, `defense_buff`, `attack_multiplier`, `vulnerability`, `cooling_multiplier` | Status and current buffs |
| `respawn_progress`, `respawn_required`, `instant_revives` | Respawn progress |
| `last_shot_time`, `last_damage_time` | For the disengaged check: current time minus each must be at least 6 s |
| `pending_ammo`, `pending_heal` | Remote ammo and remote heal waiting to arrive |
| `deployed`, `deploy_at` | Hero deployment state |
| `support_active`, `support_time` | Whether air support is on; remaining free time |
| `carried_units` | Energy units the engineer carries |
| `crouched` | Whether the default I7 model has lowered its turret |
| `powered` | Whether the chassis has power; `False` when destroyed, cut off for over-power or out of battery — the chassis can then only slide |
| `upright`, `tipped` | How upright the body is (1 = upright); `tipped` means it has fallen over and cannot drive |
| `legs` | Wheel-legged model leg lengths (right, left, metres); other robots have no such field |
| `arm_joints`, `arm_tip`, `arm_mode`, `rescue_target`, `rescue_contact` | Engineer arm: 7 joint values, tip world position, current mode, the teammate being righted and whether it is gripped |
| `speed_reference_mps`, `chassis_size_m`, `muzzle_height_m`, `armor_center_z_m` | Hardware parameters |

### Visible Enemy Robots

An enemy robot appears in `enemies` as soon as any observer controlled by this process can see any part of its body — the body center, turret top or any of its four armor plates — within vision range and without walls, terrain, structures or other robots in the way. A ground observer must also place that part inside its muzzle-facing {{ground_fov_horizontal}}° horizontal and {{ground_fov_vertical}}° vertical aperture. It then carries everything its exterior shows:

- `id, slot, team, role, x, y, z, vx, vy, vz, angular_velocity, quaternion, heading`
- `aim, pitch`: turret direction (the barrel is visible)
- `hp, max_hp, alive, powered, targetable, invulnerable`: health and light-bar state; wrecks have `alive=False`
- `upright, tipped, grounded, crouched, deployed, carried_units`
- engineers add `arm_joints, arm_tip, arm_mode`; the wheel-legged robot adds `legs`
- `chassis_size_m, armor_center_z_m, muzzle_height_m, design_name`
- `seen_by`: the list of your slots that see it

What stays hidden is the enemy's ammo, heat, experience, coins and private state.

The aperture follows actual turret yaw, pitch and chassis pose, rather than movement direction. Aerial coverage remains omnidirectional. {{#independent}}This process does not automatically merge teammate sightings.{{/independent}}{{#team}}{{^distributed}}`enemies` combines the real camera coverage of the controlled robots.{{/distributed}}{{/team}} All own robot positions and state remain in `robots`, and referee information is independent of the aperture.

### Referee Snapshot

`observation["referee"]` (or `sdk.referee_info(observation)`) arrives with every decision; no network access is needed. Everything you read during one `act` call comes from the same consistent snapshot.

| Field | Contents |
| --- | --- |
| `tick`, `time`, `remaining`, `status` | Match clock and status |
| `robots` | `id, slot, team, role, hp, max_hp, alive` of every robot on both teams — **no positions** |
| `bases`, `outposts` | Both teams' structure state |
| `economy` | Your team's economy, the same as `teams[your team]` |
| `events` | Recent broadcasts (see below), each with `id`, `type` and `time` |
| `winner`, `reason` | Winner and reason once the match has finished |

There are two kinds of broadcast:

- **Public**: robot destroyed `destroy`, respawn `respawn`, outpost rebuilt `outpost_rebuilt`, rune activated `rune_activated`, assembly success `assembly_success`, match finished `finish`.
- **Your team only**: income `income`, ammo purchase `ammo_purchase`, remote ammo delivered `ammo_delivered`, remote heal applied `remote_heal`, level up `level_up`, overheat `overheat`, energy unit picked up `unit_pickup`, assembly started `assembly_start`, assembly failed `assembly_failed`, arm gripped a teammate `rescue_grip`, righting complete `rescue_complete` (with `target`), wheel-legged jump `jump`.

The same broadcast may appear in several consecutive decisions; deduplicate by `id`.

```python
from sdk import referee_info

judge = referee_info(obs)
coins = judge["economy"]["resources"]
enemy_hp = {r["id"]: r["hp"] for r in judge["robots"]
            if r["team"] != obs["team"] and r["max_hp"] > 0}
```

### Action

Build actions with `sdk.action(...)`; it rejects unknown fields before they reach the match.{{#c_engineer}} The engineer has no launcher; `aim` / `pitch` control its simulated camera direction.{{/c_engineer}}{{#robot}} The table lists only the fields your robot can use.{{/robot}}

| Field | Value | Applies to | Meaning | If omitted |
| --- | --- | --- | --- | --- |
| `move` | `(vx, vy)` | all | World velocity intent, [−1, 1] | stop |
{{#c_ground}}
| `heading` | radians | ground | Chassis heading | turn toward travel |
| `yaw_rate` | rad/s, ±12 | ground | Chassis yaw-rate target (spinning top), overrides `heading` | — |
| `brake` | bool | ground | Brake actively when there is no `move` | `True` |
{{/c_ground}}
{{#c_s3}}
| `leg_height` | metres, hardware limits | wheel-legged | Leg length | model default |
| `jump` | 0–1 or bool | wheel-legged | Ground-triggered jump; hardware cooldown | no jump |
| `lean` | rad, ±0.35 | wheel-legged | Body pitch target, positive leans forward | 0 |
{{/c_s3}}
| `aim` | radians or `None` | all | Turret/camera world yaw | keep current |
| `pitch` | radians | all | Turret/camera world pitch, positive up | 0.04 |
{{#c_shooter}}
| `fire` | bool | shooters | Fire during this decision | no fire |
{{/c_shooter}}
{{#c_ground}}
| `power` | watts, 0–200 | ground | Chassis power budget | current power cap |
{{/c_ground}}
{{#c_s7}}
| `crouch` | bool | default I7 | Lower the turret; **send it in every action** to stay lowered | stand up (if there is room) |
{{/c_s7}}
{{#c_buyer}}
| `profile` | string or dict | hero, infantry | Profile choice, only at `tick == 0` | keep preselection |
| `buy_ammo` | `{"amount": n, "remote": bool}` | hero, infantry | Buy ammo | — |
| `remote_heal` | bool | hero, infantry | Remote healing | — |
{{/c_buyer}}
{{#c_ground}}
| `revive` | bool | ground | Instant revival while dead | — |
{{/c_ground}}
{{#c_hero}}
| `deploy` | bool | hero | Deploy / cancel deployment | keep current |
{{/c_hero}}
{{#c_aerial}}
| `support` | bool | aerial | Turn air support on / off | keep current |
| `altitude` | meters | aerial | Target absolute height | 1.85 m while support is on |
{{/c_aerial}}
{{#c_engineer}}
| `pick_unit` | bool | engineer | Pick up an energy unit | — |
| `assembly` | 1–4 | engineer | Start an assembly | — |
| `assembly_insert`, `assembly_translate` | bool | engineer | Insert, translate | — |
| `assembly_rotate` | degrees | engineer | Target rotation angle | — |
| `assembly_confirm` | bool | engineer | Confirm the assembly | — |
| `rescue` | slot | engineer | Right that tipped teammate with the arm | — |
| `arm` | dict | engineer | Drive the arm directly: `{"tip": [x,y,z], "dir": [..], "frame": "world"\|"robot"}`, `{"joints": [7 values]}` or `{"stow": True}` | automatic |
{{/c_engineer}}
{{#c_infantry}}
| `rune_start` | bool | infantry | Start a power-rune activation | — |
{{/c_infantry}}

Operations that do not apply to the robot or its current state have no effect; some are recorded in the replay as `invalid_action` events. A misspelled field name disables your whole program; `sdk.action` raises the error early, inside your own code.

### SDK

`sdk.py` is the only helper library available in the match environment. It only performs public calculations and reveals no extra information; replace any part of it with your own code whenever you like.

| Function or constant | Purpose |
| --- | --- |
| `action(move=(0, 0), aim=None, fire=False, pitch=0.04, **operations)` | Build an action; rejects unknown fields |
| `referee_info(obs)` | Return the referee snapshot |
| `nearest_enemy(robot, obs)` | Nearest visible, living, attackable enemy, or `None` |
| `aim_at(robot, target)` | Turret yaw: picks the armor plate facing you and compensates for your own velocity |
| `aim_pitch(robot, target)` | Pitch: accounts for gravity, drag, muzzle position and your velocity |
| `ballistic_reachable(robot, target)` | Whether the target is within ballistic reach |
| `intercept(robot, target)` | Simple lead prediction from the target's velocity; returns a new target point |
| `can_fire(robot)` | Whether one more round can be fired now |
| `navigate(robot, point, arena)` | Move direction that avoids walls and no-go areas and follows ramps; usable directly as `move`. Pass it through `action`: a move that backs a chassis off the road bumps then also holds the chassis heading |
| `toward(robot, point)`, `distance(a, b)` | Unit direction vector, horizontal distance |
| `terrain_height(arena, x, y)` | Ground height |
| `muzzle_speed(robot)` | Muzzle speed |
| `remote_heal_cost(t)`, `instant_revive_cost(robot, t)` | Remote-heal and instant-revive prices |
| `tipped_teammates(obs)` | Your tipped robots |
| `rescue_point(engineer, target)` | Where the engineer should park to right `target` |
| `sight_block_point(engineer, viewer, protected)` | Arm-tip position that blocks `viewer`'s line of sight to `protected` |
| `fly_slope_lane(arena, team)` | Your jump-ramp geometry: lip, crest, heights and landing pad |
| `RULES`, `DESIGNS`, `TEAM_SLOTS` | Full rule parameters, robot designs, slot list |

Aim at an outpost with `dict(obs["outposts"][opponent], kind="outpost")` and at a rune target with `dict(target, kind="rune_target")`. `sdk` precomputes its navigation graph at import time, which does not count toward the decision limit.

{{^adaptive}}
{{> common/communication}}
{{/adaptive}}
