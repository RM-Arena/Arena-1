## Interface Reference

### The act function

```python
def act(observation: dict, state) -> tuple[dict, object]:
    ...
    return actions, new_state
```

- Called every 0.1 s. The match advances every 0.05 s, so `tick` grows by 2 per decision; `tick == 0` on the first call.
- `actions` maps slot strings to action dicts, for example {{#team}}{{^distributed}}`{"1": action(...), "7": action(...)}`{{/distributed}}{{#distributed}}`{"3": action(...)}`{{/distributed}}{{/team}}{{#robot}}{{^adaptive}}`{"{{slot}}": action(...)}`{{/adaptive}}{{#adaptive}}`{obs["controlled_ids"][0]: action(...)}`{{/adaptive}}{{/robot}}. A robot without an action this decision gets an empty action (stop, no fire).
- An action stays in effect until the next decision (0.1 s, two match steps).
- `state` is the `new_state` you returned last time, `None` on the first call. It must be JSON-serializable and at most 32 KiB.
- `random` is seeded deterministically. Do not rely on wall-clock time; use `observation["time"]`.

### Observation

| Field | Content |
| --- | --- |
| `season` | `"2027"`; one program can tell 2026 and 2027 rules apart with it |
| `tick`, `time`, `remaining` | match steps, elapsed and remaining seconds |
| `team`, `controlled_ids` | `"red"` or `"blue"`; slots you control (strings) |
| `robots` | full state of all your robots (table below) |
| `enemies`, `enemy_drones` | visible enemy robots (wrecks included) and visible enemy aerial robots |
| `messages`, `message_inboxes` | team messages |
| `vision` | what each controlled observer sees, with camera parameters |
| `positions` | the four control positions: `owner, kind, zones, controller, control (full/temporary), progress, active` |
| `bases`, `outposts` | `x, y, z, hp, max_hp, owner, armor_open, ever_destroyed, rotation, rotation_stopped, armor_plates` |
| `teams` | your economy: `resources` (coins), `purchased_17/42`, `tech_income`, `level_cap`, `completed_difficulties`, `control` (control degree), `energy_units_left`, `launcher_unlock_s`, `fortress_ammo`, `attack_damage` and more; for the enemy only `attack_damage` and `control` |
| `zones` | each buff card's `owner`, `occupants`, `contested` |
| `runes`, `assemblies` | your rune; both teams' assembly states (with `cores`, `operation`, `blocked_reason`) |
| `projectiles` | visible projectiles |
| `arena` | map geometry |
| `referee` | referee snapshot: `robots` (no positions), `bases`, `outposts`, `positions`, `control` (both teams), `logistics` (your λ), `economy`, `events` |

Common fields of each robot in `robots`:

| Field | Meaning |
| --- | --- |
| `id`, `slot`, `model_slot`, `team`, `role` | `role` is `heavy`, `infantry`, `aerial` or `sentry` |
| `x, y, z`, `vx, vy, vz`, `heading`, `aim`, `pitch` | position, velocity, chassis heading, turret yaw and pitch |
| `hp`, `max_hp`, `alive`, `weak`, `invulnerable` | health and status |
| `ammo`, `heat`, `max_heat`, `cooling_rate`, `overheated` | ammo and heat |
| `level`, `experience` | level and experience (infantry; the heavy level comes from assemblies) |
| `defense_buff`, `attack_multiplier`, `vulnerability`, `cooling_multiplier` | current buffs |
| `power_limit`, `buffer_energy_j`, `powered` | power |
| `respawn_progress`, `respawn_required` | respawn progress |
| `last_shot_time`, `last_damage_time` | disengaged when the current time is at least 6 s past both |
| `pending_ammo`, `pending_heal` | remote purchases and healing on the way |
| `launcher`, `launcher_progress` | heavy launcher state and fitting progress |
| `carried_units`, `arm_joints`, `arm_tip`, `arm_mode` | the heavy robot's energy units and arm |
| `posture`, `posture_enhanced`, `posture_time`, `posture_enhanced_time`, `posture_ready_at` | sentry posture |
| `drones` | each aerial robot of an aerial system |
| `legs`, `transform_progress`, `upright`, `tipped` | leg lengths, folding progress, tipping |

### Action

Build actions with `sdk.action(...)`, which rejects unknown fields early.{{#robot}} The table lists only the fields your robot uses.{{/robot}}

| Field | Value | Applies to | Meaning |
| --- | --- | --- | --- |
{{#c_ground}}
| `move` | `(vx, vy)` | ground | world-frame velocity intent in [−1, 1] |
| `heading` | radians | ground | chassis heading |
| `yaw_rate` | rad/s, ±12 | ground | chassis spin target (overrides `heading`) |
| `aim`, `pitch` | radians | ground | turret world yaw and pitch |
| `fire` | bool | ground shooters | fire during this decision |
| `power` | watts | ground | chassis power budget |
| `buy_ammo` | `{"amount": n, "remote": bool}` | heavy, infantry, sentry | buy ammo |
| `remote_heal` | bool | ground | remote healing |
| `revive` | bool | ground | instant respawn while dead |
{{/c_ground}}
{{#c_s3}}
| `leg_height`, `jump`, `lean` | m / 0–1 / rad | wheel-legged | leg length, jump, body pitch |
{{/c_s3}}
{{#c_fold}}
| `transform` | bool | folding models | fold / unfold the turret |
{{/c_fold}}
{{#c_infantry}}
| `profile` | string or dict | infantry | performance choice, only at `tick == 0` |
| `rune_start` | bool | infantry, sentry | start a rune activation |
{{/c_infantry}}
{{#c_heavy}}
| `pick_unit` | bool | heavy | pick an energy unit at your resource hub |
| `assembly` | 1–4 | heavy | start an assembly |
| `assembly_insert`, `assembly_lift`, `assembly_flip` | bool | heavy | insert, lift, flip |
| `assembly_rotate` | degrees | heavy | target rotation angle |
| `assembly_confirm` | bool | heavy | confirm the assembly |
| `assembly_core` | 0 / 1 / 2 | heavy | which level-4 core to work (2 = both, dual arm) |
| `install_launcher` | bool | heavy | fit the launcher at the workbench; keep sending |
| `rescue` | slot | heavy | right that tipped teammate with the arm |
| `arm`, `arm2` | dict | heavy | direct arm control (`{"tip": [...], "dir": [...]}`, `{"joints": [...]}` or `{"stow": True}`); omit for automatic |
{{/c_heavy}}
{{#c_sentry}}
| `posture` | `"attack"`, `"defense"`, `"move"` | sentry | switch posture (5 s cooldown) |
| `posture_enhanced` | bool | sentry | enhance the current posture or stop |
| `rune_start` | bool | sentry | start a rune activation |
{{/c_sentry}}
{{#c_aerial}}
| `drones` | `{"1": command, ...}` | aerial system | one command per aerial robot, see "Aerial Robot System" |
{{/c_aerial}}
| `messages` | list | all | team messages, see "Team Messages" |

Operations that do not apply to the robot or its current state have no effect; some are recorded as `invalid_action` events in the replay. A misspelled field disables the whole program; `sdk.action` reports it in your own code first.

### SDK

`sdk.py` is the only helper library available in matches. It only performs public calculations and reveals nothing extra. The general 2026 helpers (`nearest_enemy`, `aim_at`, `aim_pitch`, `ballistic_reachable`, `intercept`, `can_fire`, `navigate`, `toward`, `distance`, `terrain_height`, `referee_info`, `message`) work in 2027 too and already handle 42 mm ballistics, heavy launcher states and forbidden areas per season. New in 2027:

| Function or constant | Purpose |
| --- | --- |
| `rules(obs)`, `RULES_2027`, `season_of(obs)` | full rule parameters of the current season |
| `TEAM_SLOTS_2027`, `DESIGNS` | 2027 slots and robot designs |
| `position(obs, name)`, `controls(obs, name, team=None)`, `control_degree(obs, team=None)` | control positions and control degree |
| `zone_center(arena, zone_id)` | a buff card's center, e.g. `"blue_central"`, `"red_supply"` |
| `workbench_point(robot, arena)`, `launcher_ready(robot)` | workbench parking point; launcher unlocked and waiting to be fitted (fitting before the unlock is also allowed, see "Heavy Robot") |
| `resource_pickup_point(robot, arena)`, `assembly_work_point(robot, arena)` | resource-hub pickup point and assembly parking point |
| `drones(robot)`, `strike_plan(drone, plate)`, `hostile_plates(obs, kind)` | aerial robots, ramming plan and rammable plates |

Aim at an outpost with `dict(obs["outposts"][enemy], kind="outpost")` and at a rune target with `dict(target, kind="rune_target")`. `sdk` precomputes both seasons' navigation graphs at import time, outside the decision time limit.

{{^adaptive}}
{{> common/communication}}
{{/adaptive}}
