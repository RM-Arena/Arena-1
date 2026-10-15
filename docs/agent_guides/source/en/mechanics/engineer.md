### Engineer: Energy Units and Tech-Core Assembly

{{#team}}
The engineer cannot shoot, yet it drives the team's economy and growth: every successful tech-core assembly gives the team a lasting coin income and unlocks higher level caps and defense buffs.
{{/team}}

**Simulation difficulty ladder**: physical tool position, direction and roll, chassis stability, and a continuous confirmation hold are checked independently for each grade. Releasing confirmation or losing alignment resets its progress. A 20 s reset applies to repeating completed grades; a first challenge at a newly unlocked grade can start immediately. `requirements` publishes the actual grade parameters and `attempt_remaining_s` reports time left.

| Grade | Challenge | Tip tolerance | Tool direction / roll | Max chassis speed | Max angular speed | Confirm hold | Operation limit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Basic: horizontal entry, reliable execution | 9 cm | 12° | 0.20 m/s | 0.50 rad/s | 0.4 s | 30 s |
| 2 | Precise: modest pose variation | 4 cm | 6° | 0.12 m/s | 0.30 rad/s | 0.6 s | 35 s |
| 3 | Expert: substantial tilt and rotation, precise docking | 1.5 cm | 2.5° | 0.05 m/s | 0.12 rad/s | 0.8 s | 40 s |
| 4 | Extreme: full pose envelope and two units under tight timing; usually fails | 4 mm | 0.75° | 0.01 m/s | 0.025 rad/s | 1.2 s | 45 s |

Grade 1 keeps a horizontal entry. Grade 2 has a narrow pose range; grade 3 broadens height, tilt, heading and roll. Grade 4 uses the manual's full advanced envelope: height 0.70–0.90 m, heading ±90°, tilt 0–90°, roll ±45°. Terrain and arm capabilities are preserved. Millimetre positioning, very low chassis motion, and the 3 s second-unit deadline make completion possible only for rare favourable pose/control combinations. There is no independent random success/failure lottery.

Profiles are public in `simulation_assumptions.assembly_difficulties`. A timeout fails the current attempt; grades 1–3 can restart, while grade 4 retains its 90 s retry lock and interruption penalties. A unit already consumed at first-core confirmation is not refunded on failure. `blocked_reason` distinguishes `chassis_unstable`, `arm_out_of_reach`, `arm_misaligned` and `engineer_absent`. Read each pose and adjust docking and tool alignment rather than issuing commands from an arbitrary point in the zone.

`alignment` reports current tip-position, tool-direction and roll errors for precise closed-loop control.

**Procedure**

1. **Pick up**: keep sending `pick_unit=True` in your resource zone. The actual arm must reach the unit, close its gripper, lift it and stow it before `carried_units` increases by one (maximum 2). The engineer’s `unit_pickup` reports `stage`, `elapsed`, `progress` and `held`; the viewer shows the carried object and progress. Releasing the command, leaving, destruction, weakness, manual arm control or rescue cancels the unfinished pickup. The simulated dispenser supplies unlimited units, and the engineer is invulnerable in the zone.
2. **Start**: in your assembly zone, send `assembly=difficulty` (1–4). If the difficulty is unlocked and you carry enough units, the core first moves into place; about 2 s later the operation phase begins and `assemblies[your team]["stage"]` changes from `"moving"` to `"inserting"`.
3. **Operate** (inside your assembly zone; steps advance with elapsed simulation time, one actuator phase at a time):
   - `assembly_insert=True`: insert 0.01 m per 0.1 s, 0.1 m in total (about 1 s);
   - `assembly_translate=True`: after insertion, translate 0.1 m at 0.15 m/s (about 0.7 s); not needed at difficulty 1;
   - `assembly_rotate=angle`: after translation, rotate to `assemblies[your team]["target_rotation"]` (0–90°, 120° per second) within `requirements.rotation_tolerance_deg`; needed only at difficulties 3 and 4.
4. **Confirm**: `assembly_confirm=True`. After all mechanical steps finish, hold this command for `requirements.confirm_hold_s` before one energy unit is consumed and rewards are settled. Releasing confirmation, leaving the zone, dying or becoming weakened resets confirmation progress. Early confirmation does not count as a failure. Difficulty 1 takes about 3.4 s including core positioning; higher grades also require translation, rotation and a longer hold.

Keep these fields in the same action to execute them in sequence; a combined action cannot skip the process or settle rewards instantly. In `assemblies`, `operation`, `operation_progress` and `progress` report the current step, its progress and overall exchange progress (0–1); `confirm_progress_s` reports confirmation time. The spectator view and data panel show the same process:

```python
core = obs["assemblies"][obs["team"]]
action(pick_unit=True)                                   # in the resource zone
action(assembly=2, assembly_insert=True, assembly_translate=True,
       assembly_rotate=core["target_rotation"], assembly_confirm=True)   # in the assembly zone
```

**Manipulator arm**

The engineer carries a solid arm: a slewing base, a two-stage lift mast, a telescoping boom and a three-axis wrist ending in a gripper with a suction cup. It collides like the chassis: it stops shots and blocks sight lines, and it pushes whatever it touches.

| Joint (`arm_joints` order) | Range | Max speed |
| --- | --- | --- |
| slew | ±170° | 2.4 rad/s |
| lift (shoulder height = 0.30 m + lift) | 0–0.50 m | 0.6 m/s |
| reach (mast center to wrist) | 0.22–0.70 m | 0.7 m/s |
| wrist yaw / pitch (positive = down) / roll | ±100° / −95°~+100° / ±180° | 3 / 3 / 4 rad/s |
| grip opening | 0–1 | 4 /s |

The tool tip is 0.15 m ahead of the wrist; it reaches at most about 0.85 m horizontally from the body center, at heights of about 0.15–0.95 m. Observations carry `arm_joints`, `arm_tip` (tip world position) and `arm_mode` (`stow`, `pick`, `assembly`, `rescue`, `manual`).

- By default the arm works automatically: it reaches for the energy unit at the resource station during `pick_unit`, carries the unit into the core entry during assembly, and stows otherwise.
- The `arm` field drives the arm directly (overriding the automatic poses, but not `rescue`):
  - `arm={"tip": [x, y, z], "dir": [dx, dy, dz]}`: put the tip at a world point with the tool pointing along `dir` (default: horizontal along the chassis heading); add `"frame": "robot"` for body coordinates (x forward, y left, z up, origin at the chassis bottom center); optional `"roll"` (rad) and `"grip"` (0–1).
  - `arm={"joints": [7 values]}`: joint targets, clamped to their ranges.
  - `arm={"stow": True}`: fold it away.
- Joints move at their maximum speeds; an unreachable target leaves the arm at the nearest reachable pose. You can raise the arm between an enemy hero and its target to block its view; `sdk.sight_block_point(engineer, viewer, protected)` returns the point on that sight line closest to you, ready to use as `tip`.

**Righting a tipped teammate**

`rescue=slot` (one of your ground robots, not yourself) makes the arm grip an edge of that tipped teammate (`tipped == True`) facing you and push it back upright (up to 320 N); the reaction pushes you as well.

- You must be alive and not weakened, and the teammate must be within reach — about 0.6–0.8 m between body centers works best; `sdk.rescue_point(engineer, target)` gives a parking point. Do not send `move` while gripping.
- A `rescue_grip` event marks the grip and `rescue_complete` marks the teammate upright and settled. A robot on its side usually takes 1–2 s; one on its roof first rolls onto its side, and if it rolls away you must approach again. The heavier hero may need several grips.
- The arm does nothing if the teammate is not tipped; `rescue` works only on your own team.

**Difficulties and rewards**

| Difficulty | Unlocks | Units | First success | Each repeat |
| ---: | --- | ---: | --- | --- |
| 1 | from 0 s | 1 | +50 team coins every 10 s | another +5 every 10 s |
| 2 | from 60 s, after a level-1 success | 1 | another +25 every 10 s; level cap 7 | another +10 every 10 s |
| 3 | from 120 s, after a level-2 success | 1 | another +25 every 10 s; level cap 10; 25% defense for your robots, base and outpost | another +15 every 10 s |
| 4 | from 180 s, after a level-3 success | 2 | another +50 every 10 s; defense rises to 50%; base restores 2000 HP, any excess becoming a virtual shield | succeeds only once |

- Income adds up. After one success at each of levels 1, 2 and 3, the team earns 50 + 25 + 25 = 100 coins every 10 s. Payments start 10 s after the first success.
- While an assembly is in progress (`stage` is `moving`, `inserting` or `buffered`) a new one cannot start; it can when the stage is `idle`, `complete` or `failed`.
- A weakened engineer cannot assemble.
- The engineer is invulnerable in the assembly zone, but for at most 180 s per match in total.

**Special rules for difficulty 4**

- You need 2 energy units. Once the operation phase begins, you have **45 s** to complete **two** cores, and the second must be confirmed within **3 s** of the first; the second core needs a fresh insert, translate and rotate.
- After a failure you cannot try difficulty 4 again for 90 s.
- Starting difficulty 4 while the opponent is running a difficulty 1–3 assembly interrupts them: they have a 15 s buffer (`buffered`) to continue and confirm their assembly; unfinished attempts exit at `buffer_until`. Your start is also delayed by 15 s. If such an interrupting difficulty-4 attempt fails, you can never try difficulty 4 again this match and the team's income drops by 25 every 10 s.
- You cannot start difficulty 4 while the opponent is running difficulty 4.
