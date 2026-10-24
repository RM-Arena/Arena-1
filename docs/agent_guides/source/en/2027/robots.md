## Robot Mechanics

{{#c_heavy}}
### Heavy Robot

The heavy robot combines the 2026 hero and engineer: it starts without a launcher, first carries energy units with its arm to complete tech-core assemblies, then fits its modular 42 mm launcher at the workbench and becomes the team's only 42 mm firepower.

**Performance stages** (no experience):

{{heavy_stages}}

- 50% defense from the start until 180 s (or until the launcher is installed). Invulnerable inside your supply zone; up to 45 s of invulnerability in the assembly zone during an assembly.
- **Energy units**: near your resource hub (`zone_center(arena, "red_resource")`, mirrored for blue) send `pick_unit=True`; the arm reaches for the nearest unit. It carries at most 2 (`carried_units`). Each team has 6 units in total (`teams[own]["energy_units_left"]`) that are never replenished.
- **Assembly**: drive into your assembly zone carrying a unit and send `assembly=level`. Once the core is in place, include the current step's command in every action: `assembly_insert=True` → `assembly_lift=True` → `assembly_flip=True` → `assembly_rotate=target angle (degrees)` → `assembly_confirm=True` (level 1 is insert and confirm only; level 2 adds the lift). An arm in automatic mode aligns itself with the core; the chassis must be still to confirm. `observation["assemblies"][own]` shows `operation`, `cores[k]["operation"]`, `target_rotation` and `blocked_reason`.
- Level 4 needs 2 carried units. `assembly_core=0` works your own core, `1` the borrowed core, and dual-arm models may send `2` to work both. The cores have independent rotation targets: use `assembly_rotate` for the first arm and `assembly_rotate2` for the second when working simultaneously; a single arm uses `assembly_rotate` for its selected core. Paired steps must finish on both cores within 5 s (the flip is exempt).
- **Launcher** (`launcher`): `locked` → `unlocked` → `installing` → `fitted` → `installed`; it may also be fitted before the unlock: `locked` → `installing` → `fitted_locked`, which becomes `fitted` once the usage right arrives.
  - Unlock: your team completes a level-3 assembly, or match time reaches 300 − M/50 − 2N/3 s (M is the opponent's largest base-HP lead over you this match, N its largest control-degree lead; the current value is `teams[own]["launcher_unlock_s"]`).
  - Fitting: park at your workbench (`sdk.workbench_point(robot, arena)`, within 0.45 m), stay still (< 0.05 m/s) and send `install_launcher=True` in **every action**; `launcher_progress` rises to 1 and the state becomes `fitted`. Moving or stopping the command returns it to `unlocked` (`locked` before the unlock).
  - Early fitting (rules Q&A clarification): you may fit the module at the workbench before your team has the usage right; it then reads `fitted_locked`. The launcher stays unpowered, `fire` does nothing and enemy armor keeps shielding 42 mm damage; once the right is unlocked it becomes `fitted`. The module's mass counts from the moment it is fitted, and the 50% defense still lasts until `installed` or 180 s.
  - The first 42 mm shot after fitting is the referee check (state becomes `installed`) and deals no damage. Real firepower starts after it.
- 42 mm ammo can only be bought (local 1 round / 10 coins, remote 10 rounds / 150 coins); the team cap is 100 rounds.
- **Righting teammates**: 2027 has no engineer, so the heavy robot's arm rights tipped teammates: park at `sdk.rescue_point(robot, target)` and send `rescue=teammate slot` (serial-leg models right themselves).

{{/c_heavy}}
{{#c_sentry}}
### Sentry

The sentry is fully automatic and has no experience or levels: 400 HP, heat cap 260, cooling 30/s, 100 W chassis power and 300 rounds of 17 mm at the start.

- **Supply**: every 60 s it accrues a ration of 100 rounds; entering your supply zone collects all pending rations at once (an `ammo_delivered` event). It can also buy ammo with coins.
- **Postures** (`posture="attack"|"defense"|"move"`, default `move`): after a switch no further switch for 5 s. A posture weakens after 180 s of total use. Each posture has a 15 s enhancement budget (`posture_enhanced=True`) and leaves enhancement when it runs out.

{{sentry_postures}}

- `posture_time` holds the seconds spent in attack, defense and move. A yellow card cuts the sentry's chassis power for 2 s.
- The sentry may start rune activations but gains no experience, and counts as level 1 when killed.

{{/c_sentry}}
{{#c_aerial}}
### Aerial Robot System

Slot 6 is a hangar fixed on your hangar platform carrying 2–4 fully automatic aerial robots (count per model). Aerial robots **cannot shoot**; they can only ram **base armor** and the **outpost's middle armor** (never the rune, hangars or robots). They have no HP and cannot be destroyed, but:

- Each valid impact deals 200 damage (reduced by the target's defense) and wears the guard once; when the guard's strikes are used up the robot is disabled (`state="disabled"`). Each 17 mm hit wears 0.25 strikes and pushes it by the projectile's momentum; a 42 mm hit disables it outright. A landed or fallen aerial robot (`state="down"`) can take off again.
- A valid impact needs a normal speed of at least 1.5 m/s and enough impulse (simulation thresholds in `simulation_assumptions["drone_impact"]`); each plate counts once per 0.2 s.
- Batteries drain with the real hover power and **do not recharge in the hangar**; an empty battery makes it fall.
- Flight is capped at 2.35 m (the fence is 2.4 m); leaving the field is a red card.
- While a team fully controls its own outpost position its base is invulnerable, so ramming the base usually waits until the enemy outpost position is taken; ramming the enemy outpost is valid at any time (except an outpost rebuilt for your own team).

Command them by setting `drones={"1": command, "2": command, ...}` in slot 6's action (keys are robot numbers from 1):

| Command | Meaning |
| --- | --- |
| `{"launch": True}` | take off from the hangar (climbs vertically for about 0.6 s first) |
| `{"goto": [x, y, z]}` | fly toward a point (proportional; slower when close) |
| `{"move": [vx, vy, vz]}` | velocity intent, each in [−1, 1], scaled by the robot's reference / climb speed |
| `{"dock": True}` | return to the hangar and dock |
| `{"land": True}` | land where it is |

`robot["drones"]` reports each robot's `state` (`docked`/`flying`/`down`/`disabled`), `x, y, z`, velocity, `battery_wh`, `integrity`, `strikes` and `dock`. `sdk.strike_plan(drone, plate)` returns a command that first flies in front of a plate and then rams it at full speed once lined up; `sdk.hostile_plates(obs, "outpost"|"base")` lists plates you may ram.

{{/c_aerial}}
{{#c_infantry}}
### Infantry

- The only role that gains experience; its level cap follows assembly progress (5 / 7 / 10).
- Starts rune activations; earns +300 XP each for its first road, highland and tunnel crossing and for first reaching the high point.
- Best suited to holding control positions: 5 s on the enemy outpost or central-highland card captures the enemy outpost position, which starts your control degree and is required before the enemy base can be damaged.
{{#c_s3}}
- Wheel-legged models support `leg_height`, `jump` and `lean` and cannot strafe; step-climbing models (`step_climb_m` > 0) climb the high-point steps and hop onto tunnel roofs.
{{/c_s3}}
{{#c_fold}}
- Folding models send `transform=True` to fold the turret; once `transform_progress` reaches 1 they pass through 0.25 m tunnels for the 120 s cooling ×1.5 buff. Firing is disabled while transforming.
{{/c_fold}}

{{/c_infantry}}
