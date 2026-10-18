# Robot Strategy Battle · Single-Robot Competition Guide (Slot 2 Engineer)

This guide contains the complete rules and interface for the Single-Robot Competition. You write one Python program that **controls only your team's slot 2 engineer**. Each of the other five robots on your side runs an independent program written by another participant: you share coins and the result, and can communicate through team messages. No language model is called during a match; code makes every decision in real time.

## At a Glance

| Item | Details |
| --- | --- |
| Deliverable | `strategy.py`, defining `act(observation, state)` |
| You control | Your slot 2 engineer (`controlled_ids == ["2"]`) |
| Teammates | Your other five robots, each run by another participant's program; team messaging supported |
| Decision rate | `act` is called every 0.1 s and must return within 200 ms |
| Match length | 420 s; ends early only when a base is destroyed |
| Development time | 90 minutes by default, started by the organizer; reading, coding, practice and submitting all count |
| Entry | Your last successful submission before the deadline |

**Getting started**

1. Run `python3 -B arena.py status` to confirm the development clock has started and note how much time is left.
2. Read this guide. On a first pass, "Task and Constraints", "Match Overview", "Your Robot", "Your Team", and "Information and Control" are enough; look up the other chapters as you need them.
3. Read `strategy.py`. It is a runnable template that already buys ammo, revives, assembles tech cores, flies air support and attacks structures, and it works for any slot.
4. Run one short practice game to check your setup: `python3 -B arena.py test --duration 30`.
5. **Submit early**: `python3 -B arena.py submit`. Whatever happens later, you then have a valid entry.
6. Then iterate: change → practice → read results and replays → submit.

## 1. Task and Constraints

### 1.1 Deliverable

You deliver only `strategy.py`. It must define `act(observation, state)` and return `(actions, new_state)`. See "Interface Reference" for how it is called and what the data looks like.

### 1.2 Development Time

- The default development time is **90 minutes**, started by the organizer. Reading, planning, coding, practice, waiting for results and submitting all share one continuous window.
- `python3 -B arena.py status` shows the remaining time as recorded by the host. Before the clock starts, the tool tells you to wait for the organizer; you cannot practice or submit yet.
- Until the deadline you may edit, practice and submit as often as you like. **Your last successful submission before the deadline is your entry**; with no successful submission you have no entry.
- After the deadline, new practice runs and submissions are refused and running practice is stopped. Editing files after the deadline does not change what you submitted.
- The 90-minute development clock and the 420 s match clock are unrelated.

### 1.3 Files and Permissions

**Edit only `strategy.py`.** Every other file in the workspace is a protected reference or tool; changing or deleting one, or adding new files, makes practice and submission fail. The one exception is the `practice/` directory: keep practice scripts, notes, logs and replays there. Those files never reach the match environment, so `strategy.py` must not depend on them.

| File | Purpose |
| --- | --- |
| `strategy.py` | Your strategy — the only editable file |
| `AGENT_GUIDE.md`, `AGENT_GUIDE.en.md` | This guide in Chinese and in English, with identical content |
| `AGENT_TASK.md` | Task summary |
| `sdk.py` | Helper library you can `import` during a match |
| `arena.json` | Full map, rule parameters and robot designs |
| `agent.json` | Your entry details and practice credentials |
| `arena.py` | Practice and submission tool |
| `practice/` | Free-to-write directory for practice output |

Do not read, or try to obtain, other participants' code, private state, submissions or logs.

### 1.4 Runtime Environment and Limits

During a match your program runs in its own container, which holds only your `strategy.py`:

- Python 3.12, with the standard library and `sdk.py` only;
- no network, read-only root file system, non-root user; a single process that may not start threads or subprocesses;
- 1 GiB of memory and 1 CPU core;
- source code of at most 512 KiB;
- **200 ms** per decision; importing the module and global initialization do not count toward that limit but must finish within 60 s;
- at most 16 KiB of actions per decision and 1 KiB per robot;
- `new_state` must be JSON-serializable and at most 256 KiB.

A single decision timeout skips that round's actions while retaining the program and its private state. Late actions are discarded; subsequent decisions use fresh observations. Each round still has a 200 ms wall-clock budget, including any wait for the previous response. A successful fresh decision resets the consecutive-timeout count. All policy errors, including recovered timeouts, remain in the replay and exclude the match from Elo rating.

Any of the following **disables your program for the rest of the match** — the match goes on, but the robots controlled by that process receive no further commands:

- three consecutive decision rounds time out, or `act` raises an exception;
- the return value is malformed, or an action contains an unsupported field or a non-finite number (NaN, Infinity);
- you try to control a robot that is not yours;
- you exceed one of the size limits above.

So catch exceptions inside `act` and check your worst-case decision time in practice. Practice games use the same container and limits as real matches. Output from `print` goes to the error log and is returned with practice results only when your program fails.

## 2. Match Overview

### 2.1 Lineup

Each team has six robots. Robots with the same slot number have identical hardware, starting state and rules on both teams. Slot numbers are labels and are not contiguous (there is no slot 5).

| Slot | Role | Selected model and focus | Projectile | Initial HP | Initial ammo |
| --- | --- | --- | --- | ---: | ---: |
| 1 | hero | H42 Heavy Hero · heavy platform, 42mm long-range support | 42mm | 150 | 0 |
| 2 | engineer | E35 Carrier Engineer · payload, lift-and-boom manipulator arm, righting tipped robots | none | 250 | 0 |
| 3 | infantry | W3 Wheel-Legged Infantry · self-balancing, adjustable legs, jumps steps and fly-slopes, cannot strafe | 17mm | 150 | 0 |
| 4 | infantry | I4 Assault Infantry · large magazine, short bursts of fire | 17mm | 150 | 0 |
| 6 | aerial robot | A13 Guarded Quadrotor · electric flight, 17mm air support | 17mm | — | 750 |
| 7 | infantry | I7 Steady Infantry · low center of mass, low armor, strong grip, lowerable turret | 17mm | 200 | 0 |

- "Ammo" means the number of projectiles a robot is allowed to fire. Ground robots start with 0 and must buy ammo with coins before they can shoot (see "Coins, Ammo, Healing and Revival").
- The three infantry robots follow exactly the same rules; only their hardware and default profiles differ (see "Profiles, Levels and Experience").
- Starting HP assumes the default profile, which you may change at the start.

Hardware of each robot (full data in `sdk.DESIGNS`):

| Slot | Design | Mass kg | Chassis m | Ref. speed m/s | Vision m | Turret yaw rad/s | Armor center height m | Muzzle height m |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | H42 Heavy Hero | 34.01 | 0.64 × 0.6 | 3.6 | 18 | 5 | 0.32 | 0.6 |
| 2 | E35 Carrier Engineer | 34.64 | 0.55 × 0.55 | 3.1 | 15 | — | 0.275 | — |
| 3 | W3 Wheel-Legged Infantry | 21.65 | 0.42 × 0.36 | 4.6 | 18 | 6.5 | 0.28 | 0.47 |
| 4 | I4 Assault Infantry | 26.65 | 0.54 × 0.54 | 4.2 | 18 | 5.5 | 0.285 | 0.48 |
| 6 | A13 Guarded Quadrotor | 11.46 | 0.38 × 0.3 | 3 | 24 | 5.5 | — | 0.14 |
| 7 | I7 Steady Infantry | 27.35 | 0.55 × 0.55 | 3.8 | 18 | 5.5 | 0.175 | 0.45 |

The reference speed is the drive controller's target; the speed you actually reach depends on power, slope, load and grip. Armor center height and muzzle height are measured from the ground.

### 2.2 Field and Coordinates

- The field is 28 m × 15 m, enclosed by a 2.4 m wall. x runs along the long side from 0 to 28, y along the short side from 0 to 15, and z points up. All units are meters.
- **Red is on the low-x side and blue on the high-x side.** The field is point-symmetric about the center (14, 7.5): red's point (x, y) corresponds to blue's (28 − x, 15 − y).
- Angles are in radians. Horizontal angle 0 points along +x and angles increase counterclockwise (π/2 points along +y).

Key locations (red coordinates; mirror them through the center for blue):

| Location | Red coordinates | Notes |
| --- | --- | --- |
| Base | (2.41, 7.50) | Lose it and you lose the match |
| Fortress | (6.60, 7.50) | Buff zone enabled after your outpost is first destroyed |
| Outpost | (10.99, 11.36) | Makes your base invulnerable while it stands |
| Supply zone | the rectangle x 0–2.56, y 11.35–15 (buff card at (1.35, 12.28)) | Healing, faster respawn, local ammo purchase, charging |
| Resource zone | (0.98, 13.08), inside the supply zone | Engineer picks up energy units |
| Assembly zone | (13.34, 6.84) | Engineer assembles tech cores |
| Trapezoid highland | (4.32, 3.70) | Your defensive buff zone |
| Charging dock | transmitter center (0.94, 12.10), facing +x | Hero and infantry dock to recharge |
| Landing pad | (1.40, 1.85) | Aerial robot takeoff and landing, 0.9 m high |
| Central highland buff points | (10.95, 6.55) and (17.05, 8.45) | Contested by both teams; the highland is 0.4 m high |
| Power rune | (14.00, 7.50), center about 3.0 m high | Center of the field; red and blue faces on one shaft, each facing its own half |

- The field also has a road, a bumpy section, tunnels, a jump ramp (with a 0.65 m gap in the middle), the fortress platform (0.15 m high) and more. Wheeled robots cannot climb vertical steps and must use ramps to reach high ground. The central highland (0.4 m) faces each fortress with two 0.2 m steps, not a ramp, so ordinary wheeled robots cannot climb there; they take the 10° slope west of the road notch up to the 0.2 m road (the notch's south edge is a 0.2 m road-crossing step), round the kerb onto the road, drive straight over the bumpy section that fills the road south of the kerb (see "Chassis Physics and Fine Control"), and then the 10.5° slope at either end of the highland; the wheel-legged model can jump up (see "Chassis Physics and Fine Control"). The floor rises slightly (1.5°) from both long sides toward the center line.
- At the center of the central highland stand the assembly pedestal (1.9 m long, 0.6 m wide, 0.3 m high) and the rune gantry (two posts on end blocks). They are solid and split the assembly platform into a red and a blue half; the gantry crossbeam at about 2.8 m only stops shots.
- Both bases and the opponent's supply zone, assembly zone and landing pad are no-go areas. Past each jump ramp's crest, the gap, the landing block and the jump-ramp card behind it form a highway no-go area for both teams: you may enter it only by flying in after running the whole 17° slope from its low end, and may then stay or drive out.
- Full geometry is in `observation["arena"]` (the same as `map` in `arena.json`): `terrain` holds terrain pieces — each piece's `polygon` is its real shape, while `x, y, w, h` is only its bounding box, and ramps give their direction with `ramp_start`/`ramp_end`; `obstacles` are walls, possibly with `rotation` and `bottom` (height above ground, e.g. a tunnel roof); `zones` are buff zones; `forbidden` lists no-go areas; `navigation` holds public route nodes; `flight_lanes`, `pads`, `charging_docks` and `rune` describe the flight lanes, landing pads, charging docks and power rune.
- `sdk.terrain_height(arena, x, y)` returns the ground height, and `sdk.navigate(robot, point, arena)` returns a move direction that steers around walls and follows ramps. You may write your own navigation instead.

### 2.3 Match Timeline

| Match time | What happens |
| --- | --- |
| 0 s | First decision — the only moment you can choose a profile (`profile`); one small-rune chance; 30 s of free air support; the engineer may start level-1 assembly |
| 1 s | Each team receives 400 coins |
| 60, 120, 180, 240, 300, 360 s | +20 s of free air support each time |
| 60 / 120 / 180 s | Engineer may start level 2 / 3 / 4 assembly |
| 61, 121, 181, 241, 301 s | +50 coins each time |
| 90 s | A second small-rune chance |
| 180 s | Small-rune phase ends and the first large-rune chance arrives (more at 255 and 330 s); outpost armor stops rotating; the opponent's fortress can be captured while their outpost is down |
| 240 s | Faster supply-zone healing (25% per second when disengaged) |
| 300 s | Outposts can no longer be rebuilt, and a destroyed enemy outpost's buff zone can no longer be used |
| 361 s | +150 coins |
| 420 s | Match ends and the tiebreakers decide the winner |

### 2.4 Winning the Match

- **A match ends early in exactly one case: a base is destroyed.** Losing all ground robots does not end the match — dead robots can respawn.
- When 420 s run out, compare the following in order; the first difference decides the winner:
  1. remaining base HP (virtual shield excluded);
  2. whether the outpost was **never destroyed** — if only one team's outpost was ever destroyed, the other team wins;
  3. if neither outpost was ever destroyed, remaining outpost HP;
  4. team attack damage (total effective damage dealt to robots, outposts and bases);
  5. total remaining HP of living ground robots;
  6. if still equal, the match is a draw.
- "Ever destroyed" is permanent; rebuilding the outpost does not erase it. If both outposts were ever destroyed, comparison jumps straight to item 4.

## 3. Your Robot: Slot 2 Engineer

### 3.1 Role

You cannot shoot and earn no XP, so you stay at level 1. Your value is economy and technology: every successful tech-core assembly gives the whole team a lasting coin income and unlocks higher level caps and defense buffs — the foundation for the other five robots to get stronger.

| Item | Value |
| --- | --- |
| Design | E35 Carrier Engineer |
| Role | payload, lift-and-boom manipulator arm, righting tipped robots |
| Mass kg | 34.64 |
| Chassis m | 0.55 × 0.55 |
| Ref. speed m/s | 3.1 |
| Vision m | 15 |
| Launcher | none |
| Armor center height m | 0.275 |

- 250 HP and 120 W chassis power, independent of level; no profile choice.
- Protection: 50% defense throughout the first 180 s; invulnerable in your resource zone; invulnerable in your assembly zone (at most 180 s per match in total).
- You cannot buy ammo or heal remotely, but you can heal in the supply zone. After death you respawn naturally, or revive instantly for coins (`revive=True`; the level term of the price uses level 1).
- You rebuild the outpost after only **5 s** in a row in your outpost zone (hero and infantry need 10 s); see "Base and Outpost".

### 3.2 Engineer: Energy Units and Tech-Core Assembly

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

### 3.3 Tips

- The resource zone (0.98, 13.08) and the assembly zone (13.34, 6.84) are about 14 m apart in a straight line (red coordinates); the round trip is your main cost. Carry 2 units at a time to save trips.
- Difficulty 1 is available from 0 s, and the sooner it succeeds, the sooner the income starts: +50 team coins every 10 s after the first success.
- Difficulties 2 and 3 unlock at 60 and 120 s. Completing them on time raises the team level cap to 7 and 10, and difficulty 3 also gives the team 25% defense.
- Difficulty 4 needs 2 units, two cores within 45 s, and no more than 3 s between the two confirms. The reward is large (50% defense, +2000 base HP), but a failure locks it for 90 s, and failing an interrupting attempt costs even more.
- Repeating a difficulty still pays (+5/+10/+15 every 10 s for repeats of levels 1/2/3), so keep assembling after the main line is done.
- The assembly zone is near the field center, where enemies pass by; its invulnerability lasts only 180 s per match. The technology-core pedestal and the rune gantry posts in the middle are solid and split the assembly platform into a red and a blue half.
- A tipped teammate cannot drive, and respawning does not right it: righting it with `rescue` is often worth more than waiting for its respawn (see "Righting a tipped teammate" under the engineer).
- The arm blocks sight and shots: when escorting a deploying hero or covering a teammate at the supply area, hold it toward the threat (`arm={"tip": ...}`).

## 4. Your Team

Each of the other five robots on your side runs an independent program written by another participant. You share coins, the base, the outpost, the level cap and team buffs, and can use **messages for team communication**, while code and private state stay isolated and vision is not automatically shared.

### 4.1 What Your Teammates Do

- **Hero (slot 1)**: the team's only 42mm shooter, 200 damage per hit; while the opponent's base armor is closed, only 42mm can damage the base. A ranged-profile hero can "deploy" in its own half as a fixed gun: it cannot move and loses its view, but gains muzzle speed, deals ×1.5 damage to the base and gets 25% defense. The hero's 42mm ammo is also paid from team coins (10 coins per round when bought locally).
- **Infantry (slots 3, 4 and 7)**: the main 17mm firepower; they buy ammo, start the power rune and hold fortresses and the central highland. All three follow the same rules. Drive, mass, default profiles and folding capabilities depend on the selected model; see the hardware table. The three share the team's 1000-round 17mm purchase allowance.
- **Aerial robot (slot 6)**: cannot be attacked and acts only while air support is on, flying along a lane at the side of your half with 24 m vision and 750 non-refillable 17mm rounds. Once its free support time is used up, it costs 1 team coin per second.

### 4.2 Working Together

- **Read teammate state**: `observation["robots"]` holds each teammate's full public state, such as position, HP, ammo, heat, level, whether it is alive, `carried_units` (energy units the engineer carries), `deployed` (whether the hero is deployed) and `support_active` (whether air support is on).
- **Read economy events**: your team's events in `referee["events"]` carry a `robot` field, so you can see who bought ammo and who leveled up.
- **Coins are shared**: teammates also buy ammo, heal remotely and revive instantly, and air support costs coins every second once its free time runs out. Do not assume the balance is yours; think about what teammates may need before spending.
- **Settlement order**: when several robots spend at the same moment, requests settle in slot order 1→2→3→4→6→7. A request the balance cannot cover simply fails — no charge, no error.
- **Vision is not shared**: enemies your teammates see do not automatically appear in your `enemies`; teammates can report observed positions and intentions through messages. Changes in enemy HP in the referee snapshot, destruction broadcasts and teammates losing HP still hint at where the fighting is.
- **Do not bet everything on one teammate**: a teammate's program may behave erratically or even be disabled by an error. Your strategy should work on its own.

## 5. Information and Control

### 5.1 What You Control

Your program controls only your slot 2. `observation["controlled_ids"]` is always `["2"]`, and your `actions` may contain only the key `"2"`; any other slot disables your program.

### 5.2 What You Can See

There are two kinds of information.

**Vision (from your own robot only)**

- `observation["enemies"]` contains only enemy robots **your robot can currently see** (wrecks included), with everything their exterior shows: position, velocity, orientation, turret direction, HP, whether they are tipped, arm and leg state and more (see "Interface Reference"). Enemies seen by your teammates do not appear here.
- You look from your camera toward a target's body center, turret top and four armor plates; you see it if any of those sight lines is not blocked by walls, terrain, structures or other robots (arms and wrecks included). `observation["vision"]` also lists the teammates you see.
- Your vision range is 15 m. You see nothing while dead.
- Enemy projectiles are visible only within your vision; your team's projectiles (teammates' included) are always visible.
- Power-rune target positions are provided only when you are within vision range of the rune center.

**Public information (not limited by vision)**

- Full state of all six robots on your side, including your teammates' positions, HP, ammo, heat and levels;
- slot, role, HP, max HP and alive state of every robot on both teams (the referee snapshot `referee`);
- HP, armor, shield, ever-destroyed flag and armor rotation of both bases and outposts;
- both teams' attack damage, both teams' tech-core assembly state, and who holds each buff zone;
- your team's economy; the map, rule parameters and robot designs.

**Hidden**: the opponent's coins, ammo, heat and experience; anything about the position of enemy robots you cannot see; any other participant's code, private `state` and logs — your teammates' included.

Knowing an enemy's HP is not knowing where it is. The robot list in `referee` has no coordinates — never build aiming targets from it; aim at entries in `enemies` or positions explicitly reported by teammates, accounting for report age and reliability.

Ground cameras have a 100° horizontal and 70° vertical field of view following the actual muzzle direction, with existing range and occlusion limits. Aerial coverage is unchanged. All own positions and referee information remain readable.

## 6. Shooting and Damage

### 6.1 Launchers

| Parameter | 17mm (infantry, aerial) | 42mm (hero) |
| --- | ---: | ---: |
| Damage per armor hit | 20 | 200 |
| Heat per shot | 10 | 100 |
| Muzzle speed | 25 m/s | 12 m/s (16.5 m/s when deployed) |
| Minimum firing interval | 0.05 s | 0.2 s |
| Normal relative speed needed to register on armor | > 12 m/s | > 10 m/s |
| Minimum interval between two valid hits on the same armor plate | 0.05 s | 0.2 s |

- Muzzle speed is fixed; actions cannot change it. Projectiles feel gravity and air drag and inherit the shooter's velocity at the moment of firing; firing also produces recoil.
- Each shot has independent angular spread around the muzzle axis: up to 1.8° for 17mm and 1.6° for 42mm (public simulation calibration, not rulebook limits). The cone widens with distance, so lateral spread increases at longer ranges. The same seed and action trace reproduce the spread. All projectiles are green for both teams.
- `fire=True` stays in effect for the 0.1 s after the decision: 17mm may fire **2 rounds**, 42mm at most 1.
- The engineer has no launcher. The aerial robot cannot be attacked and is not a valid target.

### 6.2 What Counts as a Hit

Every ground robot has 4 armor plates facing the front, back, left and right of its chassis, tilted upward (75° from straight up). HP is lost only when all of the following hold:

1. the projectile strikes an armor plate — hits elsewhere on the body do no damage and are simply blocked;
2. the projectile's normal speed relative to the plate exceeds the threshold above — long shots, glancing hits or shots chasing a fleeing target may fall short;
3. the minimum interval since that plate's previous valid hit has passed;
4. the target is alive and not invulnerable.

42mm also depends on the hero's state: **once the hero has not fired for 4 s in a row, or has been dead for 3 s, your 42mm rounds still in flight no longer deal damage**.

### 6.3 Damage Formula

```text
damage = round( base damage × attack buff × (1 − defense buff + vulnerability) )
```

- Base damage is 20 for 17mm and 200 for 42mm. The attack buff defaults to 1 and comes from sources such as the power rune.
- Buffs of the same kind do not stack; **the largest applies**. With both a 25% and a 50% defense buff, 50% is used.
- A single hit never deals more than the target's remaining HP.
- Hitting the 10 mm × 10 mm weak spot at the center of a base or outpost armor plate gives an attack buff of at least 1.5.

### 6.4 Heat

While overheating remains above zero, this robot’s vision range is 35% of normal. It recovers at zero; public referee health remains available. This disclosed sensor proxy represents reduced FPV visibility. `vision[slot]` reports `range_m` and `fpv_dimmed`.

- Each shot adds heat (17mm +10, 42mm +100). Every 0.1 s heat drops by "cooling × 0.1", where cooling is per second.
- **Heat above the cap locks the launcher**; it unlocks only after cooling all the way to 0.
- Reaching "cap + 100" (17mm) or "cap + 200" (42mm) locks the launcher **for the rest of the match**.
- Heat cap and cooling depend on level and profile; see "Your Robot".
- `sdk.can_fire(robot)` checks alive, weakened, lock, ammo, and whether one more shot would exceed the cap. Because 17mm may fire 2 rounds per decision, infantry and the aerial robot should fire only when `heat + 20 <= cap`.

## 7. Referee Penalties and Launcher Locks

Referee decisions use a separate interface from robot actions. Contestants cannot issue cards or change penalty state. The organizer judges subjective fouls; ordinary collisions do not randomly generate yellow cards. Invalid action input is rejected without becoming a yellow card.

### 7.1 Yellow Cards

- A single-team yellow deducts 15% of the offender's maximum HP and 5% from each other living ground teammate. Damage is rounded to an integer, stops at 1 HP, and bypasses defence and invulnerability.
- Another individual yellow less than 30 s after the previous one doubles that robot's deduction ratio. At 30 s or later it returns to 15%; teammates still lose 5% each.
- The offender's camera is obscured for 5 s and teammates' cameras for 2 s. Consecutive durations stack. An obscured camera provides no enemy positions, vision lists or rune target positions; public referee telemetry remains available, and movement and firing remain possible.
- An engineer's second yellow, or any other robot's third yellow, immediately also issues a red card.
- A simultaneous yellow deducts 5% from every living ground robot on both teams and obscures every camera for 2 s. It changes neither individual card counts nor individual repeated-penalty ratios.

### 7.2 Red Cards and Forfeits

- A ground robot receiving red has 0 HP, loses chassis power and cannot revive naturally or buy a revival for the remainder of the match. Its wreck stays on the field.
- An aerial robot receiving red stops support and firing, returns automatically to its pad and cannot restart support.
- Penalty HP loss counts toward the opposing team's attack damage without granting robot XP or kill rewards. A referee forfeit sets the losing team's base HP to 0 and immediately ends the match.
- Own status is in `yellow_cards`, `red_card` and `fpv_blocked_until`; public `referee.robots` also shows both teams' card counts and red-card states.

### 7.3 Excess Muzzle Speed

Fixed hardware determines muzzle speed; contestants cannot request a different speed. The sensor measures speed relative to the launcher, excluding inherited chassis motion.

- 17mm: exceeding 25 m/s by less than 5 m/s locks firing for 15 s; an excess from 5 to less than 10 m/s locks it for 20 s; an excess of at least 10 m/s permanently locks it for this match.
- 42mm: exceeding the current limit (12 m/s; 16.5 m/s when deployed) by up to 1.1 times the limit locks for 15 s; above 1.1 and up to 1.2 times the limit locks for 20 s. Actual speed above 18 m/s permanently locks firing; this absolute boundary takes priority.
- Unsupported undeployed 42mm hardware speeds strictly above 14.4 and up to 18 m/s are rejected before firing; the undefined sanction band is not invented.
- Muzzle-speed and heat locks are independent. Clearing one does not clear the other; revival cannot remove a permanent lock.
- Status is in `overspeed_locked`, `overspeed_lock_until`, `overspeed_permanent_lock`, `heat_permanent_lock` and `launcher_fault`; `sdk.can_fire` checks these locks.

## 8. Coins, Ammo, Healing and Revival

### 8.1 Coins

Coins belong to the whole team. `observation["teams"][your team]["resources"]` is the current balance; the opponent's balance is hidden. Your teammates spend from the same balance.

- **Scheduled income**: 400 at 1 s; 50 each at 61, 121, 181, 241 and 301 s; 150 at 361 s — 800 in total.
- **Tech income**: every successful tech-core assembly by the engineer adds a payment to the team every 10 s, and these add up (see "Engineer: Energy Units and Tech-Core Assembly").
- **Spending**: buying ammo, remote healing, instant revival, and air support beyond its free time.

### 8.2 Buying Ammo

Ground robots start with 0 ammo and **must buy ammo before they can shoot**. Only the hero (42mm) and infantry (17mm) can buy; the aerial robot's 750 rounds cannot be refilled, and the engineer uses no ammo.

| Method | 17mm | 42mm | Condition | Delivery |
| --- | --- | --- | --- | --- |
| Local | 10 coins per 10 rounds | 10 coins per round | In (or left within the last 2 s) your base, your supply zone, or an outpost buff zone you may hold; not weakened | Immediate |
| Remote | 150 coins per 100 rounds | 150 coins per 10 rounds | Disengaged | After 6 s |

- The amount must be a whole multiple of the method's batch, e.g. 10, 20 or 50 rounds of local 17mm, or 100 or 200 rounds of remote 17mm; anything else is ignored.
- Each team has a total purchase cap for the match: **1000 rounds** of 17mm (shared by all three infantry) and **100 rounds** of 42mm.
- A failed request costs nothing and reports no error; check your ammo and balance to see whether it worked.

```python
action(buy_ammo={"amount": 50, "remote": False})   # infantry buys 50 rounds locally for 50 coins
action(buy_ammo={"amount": 10, "remote": True})    # hero buys 10 rounds remotely for 150 coins, delivered after 6 s
```

**Disengaged**: the robot is alive and has gone **6 s in a row without firing and without taking damage**. Merely standing still does not make a robot disengaged.

### 8.3 Healing

- **Supply zone**: your ground robots in your supply zone recover 10% of max HP per second; after 240 s, a robot that is also disengaged recovers 25% per second.
- **Remote healing** (hero and infantry only): while disengaged, send `remote_heal=True`. It costs `50 + ceil(elapsed_seconds / 60 × 20)` coins and, 6 s later, restores 60% of the max HP at that moment. The price rises continuously, not once per minute. Dying while waiting cancels it without refund; only one remote heal can be pending at a time.
- **Leveling up**: any increase in max HP is added to current HP immediately.
- The engineer cannot heal teammates.

### 8.4 Death and Revival

A ground robot dies when its HP reaches 0: heat and the power buffer reset to zero, and it loses all zone buffs and any pending remote heal. The aerial robot never dies.

**Natural respawn**

- Required progress = `round(10 + elapsed_seconds_at_death / 10 + 20 × instant revives this robot has used)`, in seconds.
- Progress grows by 1 per second, or by 4 per second if the robot died inside your supply zone or your base HP is **below** 2000. See `respawn_progress` / `respawn_required`.
- The robot respawns where it died, keeps its level and experience, has 10% HP, becomes **weakened**, and is invulnerable for up to 30 s.
- A weakened robot cannot shoot, receive zone buffs, buy ammo locally, rebuild the outpost or start the power rune, and a weakened engineer cannot assemble. Returning to your base, your supply zone or an outpost buff zone you may hold clears the weakened state, and the invulnerability ends with it.

**Instant revival**: a dead ground robot sends `revive=True`

- Costs `ceil(elapsed_seconds / 60) × 80 + level × 20` coins;
- full HP, level and experience kept, not weakened, 3 s of invulnerability; for the next 4 s the chassis power cap is doubled (at most 200 W);
- each use adds 20 s to that robot's future natural-respawn progress requirement.

`sdk.remote_heal_cost(seconds)` and `sdk.instant_revive_cost(robot, seconds)` compute these prices.

## 9. Profiles, Levels and Experience

### 9.1 Choosing a Profile

The hero and the infantry each start with a preselected profile. It can be changed **only on the first decision (`tick == 0`)** and is locked afterwards.

| Role | Options | Preselected |
| --- | --- | --- |
| Hero | `"ranged"` / `"melee"` | Selected model’s `hero_profile` |
| Infantry chassis | `"hp"` (HP first) / `"power"` (power first) | Selected model’s `chassis_profile` |
| Infantry launcher | `"cooling"` (cooling first) / `"burst"` (burst first) | Selected model’s `weapon_profile` |

```python
action(profile="melee")                               # hero
action(profile={"chassis": "hp", "weapon": "burst"})  # infantry; either key may be given alone
```

- The engineer and the aerial robot have no profile choice.
- Only a ranged hero with deployment hardware can deploy. A melee hero has more HP, power and heat cap, but cools more slowly.
- Per-level numbers are in "Your Robot"; full data is in `sdk.RULES["profiles"]`. The steps are not always even — for example, the cooling-first infantry launcher has a heat cap of 114 at level 9.

### 9.2 Levels and Experience

Robots start at level 1 and level up when their total experience (XP) reaches:

| Level | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Total XP | 0 | 550 | 1100 | 1650 | 2200 | 2750 | 3300 | 3850 | 4400 | 5000 |

- The level cap starts at **5**. It rises to **7** when the engineer first completes a level-2 assembly and to **10** when it first completes a level-3 assembly. XP stops accumulating at the current cap.
- Leveling up raises max HP, chassis power, heat cap and cooling (depending on role and profile); the increase in max HP is added to current HP at once. The aerial robot's levels only raise its heat cap and cooling.
- The engineer earns no XP and stays at level 1.

XP sources (earned only while alive):

| Action | XP |
| --- | --- |
| Firing one 17mm / 42mm round | 1 / 10 |
| Each point of damage to a robot | 4 |
| Each point of damage to an outpost | 2 |
| Each point of damage to a base | 0.5 |
| Destroying a robot | `50 × victim level × (1 + 0.2 × max(victim level − your level, 0))` |
| First trigger of each terrain-crossing type | 300 |
| Each damaging hit by a deployed hero | 100 extra |
| Power rune | see "Power Rune" |

## 10. Movement, Chassis Power and Energy

### 10.1 Movement and Turret

- `move=(vx, vy)` is a velocity intent in **world coordinates**, each component in [−1, 1]; vectors longer than 1 are scaled down to 1. Target velocity = intent × the robot's reference speed (`speed_reference_mps`).
- Robots are rigid bodies with mass, inertia, suspension and tire friction: accelerating and braking take time, sharp turns slide, slopes slow you down, and robots can get airborne or tip over. **Brake early**; never assume an instant stop, and do not try to drive straight over a step.
- `heading` sets the chassis heading in radians; when omitted, the chassis turns toward its direction of travel. The heading determines which way the four armor plates face.
- `aim` is the turret's horizontal angle in world coordinates and `pitch` its world elevation (positive up). The turret turns at a limited rate, its pitch is limited to −15° … +45° relative to the chassis, and it compensates for chassis tilt automatically. `aim=None` keeps the current direction.

### 10.2 Chassis Power

- Each ground robot has a chassis power cap, `power_limit`, that depends on role, level and profile.
- The `power` action field (watts, 0–200) is this decision's power budget and defaults to the current cap. Any budget above the cap is drawn from a **buffer**: the buffer holds 60 J and is settled every 0.1 s as `buffer −= (actual power − cap) × 0.1`.
- If the buffer is empty and power is still over the cap, the **chassis is cut off for 5 s** and cannot move.
- For 4 s after an instant revival the power cap is doubled (at most 200 W).

### 10.3 Chassis Energy (Hero and Infantry)

- Chassis energy `energy` starts at 20 000 J with a cap of 40 000 J. Each joule the chassis outputs costs one joule; driving at a steady 60 W drains it in about 330 s.
- When energy runs out, the power cap drops to 35 W; at 25 000 J or more, the power cap rises to 125% (at most 200 W).
- Recharging: park still (below 0.08 m/s) at your charging dock. It supplies 100 W, credited to chassis energy at 8 × the net input, i.e. about `8 × (100 − chassis power)` J/s. The dock stands inside your supply zone; `arena["charging_docks"]` gives its `transmitter` center and the `normal` it faces. The receiver at the center of your chassis front must face the transmitter (your heading opposite to `normal`, within about 11°) and lie within 3 cm of the point `transmitter + 0.24 × normal`, so your chassis center sits half a chassis length (`chassis_size_m[0] / 2`) further along `normal`. Red's transmitter is at (0.94, 12.10) facing +x: face −x with your center near x = 1.18 + half the chassis length, y = 12.10.
- The engineer and the aerial robot do not use chassis energy.

The physical battery `battery_remaining_wh` and the supercapacitor `supercap_energy_j` are hardware state, settled separately from the chassis energy above.

## 11. Base and Outpost

| Structure | HP | Key points |
| --- | ---: | --- |
| Base | 5000 | Lose it and you lose. Invulnerable while your outpost stands (HP > 0) |
| Outpost | 1500 | Three rotating armor plates; once destroyed, your base loses its protection |

Only the armor of either structure takes damage, under the same conditions as robot armor (normal-speed threshold, minimum interval per plate). Both also receive your team's defense buffs (tech cores, power rune).

### 11.1 Base Armor

- The base armor starts closed. **While it is closed, only 42mm can damage the base** (by hitting the raised target area).
- When base HP falls to **2000 or less**, the armor opens and 17mm can damage the base too (another way to open it is described under "Fortress"). Once open, it never closes again.
- The base's virtual shield (from the level-4 tech core) absorbs damage before HP.

### 11.2 Outpost Armor Rotation

- The armor starts rotating at kickoff and reaches 0.8π rad/s within 5 s.
- It stops when any of these happens, turns back to its initial orientation within 10 s, and never rotates again: this outpost is destroyed for the first time; the opponent's base armor opens; the match reaches 180 s.

### 11.3 Rebuilding the Outpost

- Every 1000 HP of cumulative damage to your base grants one rebuild credit (`teams[your team]["rebuild_credits"]`).
- Before 300 s, while your outpost is destroyed, a hero or infantry robot that stays in your outpost zone for 10 s **in a row** (an engineer needs only 5 s) spends one credit and rebuilds the outpost to 750 HP. Leaving the zone resets the timer; a weakened robot cannot rebuild.
- While rebuilding, `outposts[your team]["rebuild"]` contains the robot ID, `elapsed`, `required` seconds and `progress` (0–1); otherwise it is `None`. With several builders, the display shows the highest completion fraction without combining their progress. Progress bars appear above the outpost and in the data panel. Leaving the zone, dying or becoming weakened resets that robot's timer.
- A rebuilt outpost protects the base again, but the "ever destroyed" record stays (it matters for tiebreaker 2).

### 11.4 Aiming at Structures

`sdk.aim_at` and `sdk.aim_pitch` accept structures directly as targets and choose the target height from the armor state:

```python
enemy = "blue" if obs["team"] == "red" else "red"
outpost = dict(obs["outposts"][enemy], kind="outpost")   # outposts need kind="outpost"
base = obs["bases"][enemy]
```

Without `kind="outpost"`, `aim_pitch` computes an outpost target at the wrong height.

Closed, the base's three corner shells form a pyramid that meets at a narrow slit in the middle of each face. Opening swings the half-shell on each side of the slit about 66° outward on its corner hinge, exposing that face's lower large panel, centred 0.287 m above the pedestal and tilted 15° upward (figure 4-11). Both calibres can attack these panels from outside the forbidden pedestal; opening takes about 1.5 s (`armor_open_progress`) and the shells block shots at every intermediate angle. The outpost's three rotating panels sit at different heights, 1.116 / 1.216 / 1.316 m above its base (figure 4-32), and each keeps its height while turning; its top 42mm module is at 1.5 m. Covers, supports and foundations stop shots. Only finite `armor_plates` register damage; each publishes `center`, `normal`, width, height and calibre restrictions. These unlabelled centers and motion timings are public reconstructed simulation parameters. The SDK aims at a panel facing the shooter. Top small base and outpost modules accept 42mm even after opening, without a center weak-spot bonus.

## 12. Zone Buffs and Terrain Crossings

Buff zone positions, shapes, kinds and owners are in `arena["zones"]`; who currently holds each zone is in `observation["zones"][zone id]` (`owner`, `occupants`, `contested`).

General rules:

- Only living, non-weakened ground robots receive zone buffs; the aerial robot never does.
- A buff lasts 2 s after leaving the zone; it ends immediately on death.
- Buffs of the same kind take the maximum and do not stack.

| Zone | Who benefits | Effect |
| --- | --- | --- |
| Your base | Your ground robots | 50% defense; local ammo purchase; clears weakened state |
| Central highland (two points) | Hero and infantry; one team at a time | 25% defense. Once one team holds it, the other cannot gain it until every holder has left |
| Your trapezoid highland | Your ground robots | 50% defense |
| Outpost | Your robots in your outpost zone while your outpost stands; or, before 300 s and with the enemy outpost destroyed, your robots in the enemy outpost zone | 25% defense; local ammo purchase; clears weakened state |
| Your supply zone | Your ground robots | Healing; faster respawn when dead; local ammo purchase; clears weakened state |
| Your resource zone | Your engineer | Invulnerable; pick up energy units |
| Your assembly zone | Your engineer | Invulnerable (at most 180 s per match in total); assemble tech cores |
| Your fortress | Enabled after your outpost is first destroyed; works for one of your infantry at a time | See below |
| Enemy fortress | Your infantry, after 180 s while the enemy outpost is down | See below |

In addition, the engineer always has 50% defense during the first 180 s.

### 12.1 Fortress

**Your fortress** (enabled once your outpost has been destroyed; if several infantry are inside, only the lowest slot benefits)

- 50% defense;
- cooling bonus: cooling is at least `base cooling + min(75, floor(base HP lost / 40))`;
- reserve ammo: an extra team pool with capacity `min(500, 100 + 2 × floor(base HP lost / 15))`, topped up as your base loses HP. The infantry holding the fortress fires from the reserve first, so it can shoot even with 0 ammo of its own (`sdk.can_fire` only looks at the robot's own ammo and ignores the reserve). Base healing reduces capacity and clips excess reserve; leaving and re-entering does not create a fresh reserve. The remaining reserve is `teams[your team]["fortress_ammo"]`.

**Enemy fortress** (capturable after 180 s while the enemy outpost is down; infantry only)

- The holder takes **100% vulnerability** — double damage;
- after 20 s of valid occupation, the enemy base armor opens. Loss of occupation or death pauses the timer for up to 3 s; re-entry after that cannot restore old progress.

### 12.2 Terrain Crossings

The field has four kinds of crossing routes, each made of two detection cards: zones whose `kind` is `road`, `highland`, `fly` or `tunnel`, where both cards of one route share a `group` and have `order` 0 and 1. Passing both cards of a group within the time window triggers a buff:

| Kind | Direction | Window | Effect |
| --- | --- | ---: | --- |
| Road `road` | low (order 0) → high (order 1) | 3 s | 25% defense for 5 s; cannot trigger again for 15 s |
| Highland `highland` | low → high | 5 s | 50% defense for 30 s |
| Jump ramp `fly` | either | 10 s | 25% defense for 30 s |
| Tunnel `tunnel` | either | 3 s | cooling ×2 for 120 s |

- The road cards sit at the road notch: the low card on the notch floor, the high card on the road above the 0.2 m step. Each side has two tunnels: tunnel A in the road's north strip east of the notch (`*_tunnel`, a road-level passage with 0.25 m clearance whose north mouth drops 0.2 m to the floor, so it is entered from the road) and tunnel B beside the centre line north of the jump ramp (`*_tunnel_b`, floor level, beam 0.25 m above the floor).
- If a crossing defense buff is still active when you trigger another defensive crossing, the new one is 50%.
- The first trigger of each kind gives 300 XP.
- Weakened robots cannot trigger crossings.

## 13. Power Rune

The power rune stands at the center of the field (14, 7.5), its hub about 3.0 m high, on a gantry above the assembly pedestal. It has **a red face and a blue face** on one shaft that turn together: the red face looks toward the red half and the blue face toward the blue half, each 0.35 m from the shaft center (shaft direction: `arena["rune"]["axis_yaw"]`). When the red face turns clockwise seen from red, the blue face turns counter-clockwise seen from blue. Each face has 5 arms, each ending in a round target of radius 0.15 m that rotates around the hub at a radius of 0.7 m. Each team activates its own face independently and can only hit the face turned toward it.

- Both small and large runes turn at smoothly varying, irregular speeds while idle, during activation and while buffs are active. Both faces stay synchronized on the same shaft; activation does not reset its speed. Current `angular_velocity` (rad/s) and `angular_acceleration` (rad/s²) are visible under the same range restriction as target positions. Aim must account for speed changes during projectile flight.

- **Only infantry can start an activation**: send `rune_start=True` (alive and not weakened; position does not matter).
- **Only 17mm counts**, from infantry or the aerial robot. 42mm hits are ignored and earn nothing.
- A projectile's horizontal speed along the rune's axis must exceed 12 m/s.
- Targets are in `observation["runes"][your team]["targets"]`; each has `arm, x, y, z, radius, lit`, and `lit=True` marks the target to hit now. Target positions are provided only while one of your observers is within vision range.
- The activation state is `runes[your team]["status"]`: `idle`, `activating` or `active`. You cannot start again while the buff is `active`.
- When aiming, pass `dict(target, kind="rune_target")` to `sdk.aim_pitch` so it treats the target as an exact point instead of adding an armor height.

### 13.1 Small Rune (0–180 s)

- Chances: one at kickoff and another at 90 s. Unused chances do not carry over to the large-rune phase.
- After starting, one target lights up and must be hit within 2.5 s; then another arm that has not yet been hit lights up. Hitting **5 different arms** in turn activates the rune.
- A wrong target, or 2.5 s without a hit, resets progress to the beginning. The whole attempt is limited to 20 s; after that the chance is lost.
- Effect: your robots, base and outpost get **25% defense** for 45 s, and XP earned during that time is doubled (at most 1200 extra XP for the team).

### 13.2 Large Rune (from 180 s)

- Chances: one each at 180, 255 and 330 s.
- The large rune has stronger speed variation. Each round lights **2** targets: the first must be hit within 2.5 s, and the second may then be hit within 1 s (optional). After 5 rounds you have 5–10 valid hits.
- A wrong target, or no first hit within 2.5 s in a round, resets progress. The whole attempt is again limited to 20 s.
- Rings: each 1.5 cm between the hit point and the target center costs one ring; dead center is 10, the minimum is 1.
- Duration depends on the number of hits: 5, 6, 7, 8, 9 or 10 hits give 30, 35, 40, 45, 50 or 60 s. The buff depends on the average ring:

| Average ring | Attack buff | Defense buff | Cooling multiplier |
| --- | ---: | ---: | ---: |
| ≤ 3 | 1.5 | 25% | ×1 |
| ≤ 7 | 1.5 | 25% | ×2 |
| ≤ 8 | 2 | 25% | ×2 |
| ≤ 9 | 2 | 25% | ×3 |
| ≤ 10 | 3 | 50% | ×5 |

- The defense buff also covers your base and outpost.
- Activation also grants 750 XP, split evenly among your robots that are alive and can earn XP at that moment (the engineer excluded).

## 14. Chassis Physics and Fine Control

Every ground robot is a 120 Hz rigid-body simulation with mass, inertia, suspension, tyre grip and collisions. `move` is only a velocity intent; the actual motion comes from motor force, power and friction. These physical details matter tactically.

### 14.1 Power Cuts and Momentum

The referee cuts chassis power when a robot is destroyed, during an over-power cut-off (see "Power and Energy") and when the battery is empty. Then `powered == False`:

- The motors neither drive nor brake. The robot **keeps sliding on its momentum**, slowed only by back-driven gearboxes, rolling resistance and whatever it hits. A mecanum chassis decelerates at about 2.2 m/s² (about 2 m from 3 m/s); on slopes steeper than about 12° (such as the 17° jump ramp) an unpowered mecanum robot rolls downhill.
- A destroyed robot stays on the field as a **wreck**: it is still solid, blocks paths, shots and sight lines, and can be pushed. Respawning happens in place and restores power; a tipped robot is still tipped after it respawns.
- A powered robot without `move` brakes actively and holds its position and heading (up to tyre friction). Send `brake=False` to let a powered chassis coast.

### 14.2 Tipping Over and Righting

- `upright` is the cosine between the body's vertical axis and world vertical (1 is upright); below 0.5, `tipped == True`. A tipped robot's wheels are off the ground and it cannot drive.
- Typical causes: running off the side of a ramp at speed, dropping off a step, a bad jump-ramp landing, collisions.
- The engineer can right a tipped teammate with its arm (the engineer's `rescue` action).

### 14.3 Fine-Control Fields

| Field | Effect |
| --- | --- |
| `move` | World-frame velocity intent in [−1, 1], scaled by the reference speed |
| `heading` | Chassis heading target; when omitted, a mecanum chassis turns toward its motion |
| `yaw_rate` | Chassis yaw-rate target (rad/s, up to ±12), overriding `heading`. A mecanum robot can translate while spinning (a "spinning top") so enemies cannot keep hitting the same armor plate |
| `power` | Chassis power budget for this decision (0–200 W). Power above the limit is drawn from the supercapacitor; once it is empty the buffer energy starts to drain |
| `brake` | `True` by default; with `False` the chassis does not brake when there is no `move` |

Spinning costs power: torque times angular velocity counts toward chassis power, so watch the limit when spinning for long.

### 14.4 Road Bumps

- The road south of the kerb (red x 5.25–7.65, blue mirrored) is covered by ten smooth 70 mm humps 240 mm apart. Wheeled robots that climb the 10° slope west of the notch must cross them to reach the east road, the jump ramp and the highland end slopes.
- Wheeled chassis ride 100 mm clear on soft suspension, so the wheels follow the humps while the body stays nearly level: drive straight at full speed and you are over in about 3–5 s. Crawling (especially the heavier dual-arm engineer) can stall between two humps; back off a little and accelerate again.
- Without a `power` field, heroes and infantry with a supercapacitor draw on it automatically while on the humps; an explicit `power` budget takes precedence.
- A wheel-legged chassis lifts both wheels at once, so enter at full speed and keep to the middle of the section; brushing the side kerbs can catch it.

## 15. Interface Reference

### 15.1 The act Function

```python
def act(observation: dict, state) -> tuple[dict, object]:
    ...
    return actions, new_state
```

- Called every 0.1 s. The match state advances every 0.05 s, so `tick` grows by 2 between decisions; the first call has `tick == 0`.
- `actions` maps slot strings to action dicts, e.g. `{"2": action(...)}`. A robot without an action this round gets an empty action (stop, no fire).
- An action stays in effect until the next decision (0.1 s, i.e. 2 match steps).
- `state` is the `new_state` you returned last time, or `None` on the first call. It must be JSON-serializable and at most 32 KiB. Module-level globals also persist within a match, but keeping memory in `state` makes runs easier to reproduce.
- The `random` module is seeded with a fixed seed, so identical inputs give identical results. Do not rely on wall-clock time; use `observation["time"]`.

### 15.2 Observation

| Field | Contents |
| --- | --- |
| `tick`, `time`, `remaining` | Match step, elapsed seconds, remaining seconds |
| `dt`, `policy_dt` | Match step 0.05 s, decision interval 0.1 s |
| `team` | `"red"` or `"blue"` |
| `controlled_ids` | Slots you may control (list of strings) |
| `robots` | Full state of your six robots (see below) |
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
| `specs`, `rulebook_rules`, `simulation_assumptions` | Parameter summaries; use `sdk.RULES`, `sdk.DESIGNS` or `arena.json` for complete values |

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

### 15.3 Visible Enemy Robots

An enemy robot appears in `enemies` as soon as any observer controlled by this process can see any part of its body — the body center, turret top or any of its four armor plates — within vision range and without walls, terrain, structures or other robots in the way. A ground observer must also place that part inside its muzzle-facing 100° horizontal and 70° vertical aperture. It then carries everything its exterior shows:

- `id, slot, team, role, x, y, z, vx, vy, vz, angular_velocity, quaternion, heading`
- `aim, pitch`: turret direction (the barrel is visible)
- `hp, max_hp, alive, powered, targetable, invulnerable`: health and light-bar state; wrecks have `alive=False`
- `upright, tipped, grounded, crouched, deployed, carried_units`
- engineers add `arm_joints, arm_tip, arm_mode`; the wheel-legged robot adds `legs`
- `chassis_size_m, armor_center_z_m, muzzle_height_m, design_name`
- `seen_by`: the list of your slots that see it

What stays hidden is the enemy's ammo, heat, experience, coins and private state.

The aperture follows actual turret yaw, pitch and chassis pose, rather than movement direction. Aerial coverage remains omnidirectional. This process does not automatically merge teammate sightings. All own robot positions and state remain in `robots`, and referee information is independent of the aperture.

### 15.4 Referee Snapshot

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

### 15.5 Action

Build actions with `sdk.action(...)`; it rejects unknown fields before they reach the match. The engineer has no launcher; `aim` / `pitch` control its simulated camera direction. The table lists only the fields your robot can use.

| Field | Value | Applies to | Meaning | If omitted |
| --- | --- | --- | --- | --- |
| `move` | `(vx, vy)` | all | World velocity intent, [−1, 1] | stop |
| `heading` | radians | ground | Chassis heading | turn toward travel |
| `yaw_rate` | rad/s, ±12 | ground | Chassis yaw-rate target (spinning top), overrides `heading` | — |
| `brake` | bool | ground | Brake actively when there is no `move` | `True` |
| `aim` | radians or `None` | all | Turret/camera world yaw | keep current |
| `pitch` | radians | all | Turret/camera world pitch, positive up | 0.04 |
| `power` | watts, 0–200 | ground | Chassis power budget | current power cap |
| `revive` | bool | ground | Instant revival while dead | — |
| `pick_unit` | bool | engineer | Pick up an energy unit | — |
| `assembly` | 1–4 | engineer | Start an assembly | — |
| `assembly_insert`, `assembly_translate` | bool | engineer | Insert, translate | — |
| `assembly_rotate` | degrees | engineer | Target rotation angle | — |
| `assembly_confirm` | bool | engineer | Confirm the assembly | — |
| `rescue` | slot | engineer | Right that tipped teammate with the arm | — |
| `arm` | dict | engineer | Drive the arm directly: `{"tip": [x,y,z], "dir": [..], "frame": "world"\|"robot"}`, `{"joints": [7 values]}` or `{"stow": True}` | automatic |

Operations that do not apply to the robot or its current state have no effect; some are recorded in the replay as `invalid_action` events. A misspelled field name disables your whole program; `sdk.action` raises the error early, inside your own code.

### 15.6 SDK

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

### 15.7 Team Communication

Every control mode supports robot-addressed communication. Each robot may set `messages` in its own action, sending at most four per decision. Delivery happens at the next decision, 0.1 s later, independently of distance, camera visibility or whether the robot is alive.

An independent process continues to receive its addressed messages in `obs["messages"]`. `obs["message_inboxes"][obs["controlled_ids"][0]]` exposes the same inbox.

```python
from sdk import action, message

def act(obs, state):
    slot = obs["controlled_ids"][0]
    received = obs["messages"]
    return {slot: action(messages=[message({"intent": "advance"})])}, {"received": received}
```

- `message(data)` broadcasts to the other robots in your actual lineup. `message(data, to="2")` addresses an own deployment slot: 1,2,3,4,6,7 in fixed lineups, or the actual instance IDs in free battle. Never address yourself or opponents. The host authenticates the sender from the action's robot slot.
- The raw format is `{"to": "all" or a teammate slot string, "data": JSON value}`. Encoded data is at most 512 bytes. Messages and physical operations must together fit each robot's 1 KiB action budget. The four-message limit is per robot, including whole-team mode.
- Received envelopes are `{"from": "red-1", "to": "red-2", "tick": 0, "delivery_tick": 2, "data": ...}`. Inboxes start empty; each envelope appears once at the next decision. Keep useful reports in `state`.
- Ordering follows sender instance number and message-list order, regardless of action-dictionary or process completion order. Missing free-battle recipients receive nothing. Disabled programs no longer send or process messages.
- Messages do not modify visual `enemies` or automatically share private independent-process state. Report sightings, targets and intentions explicitly, with timestamps and appropriate handling of stale reports.
- Replay decision steps store sends in `actions[i]["communication"]`, with sender, recipient list, send/delivery ticks and data. Messages never enter physics or resend during the held-action simulation step.

## 16. Practice and Submission

Run every command from your workspace:

```bash
python3 -B arena.py status                  # remaining time, submitted versions, practice jobs
python3 -B arena.py test [options]          # start a batch of practice games with the current strategy.py
python3 -B arena.py results JOB_ID           # practice progress and results
python3 -B arena.py replay JOB_ID --game 0   # save the full replay of game 0 into practice/
python3 -B arena.py submit                   # submit the current strategy.py
```

### 16.1 Practice Games

| Option | Default | Meaning |
| --- | --- | --- |
| `--opponent` | `baseline` | `baseline`: the public baseline strategy (defensive); `self`: your current code against itself; or one of your own submitted versions listed by `status` |
| `--duration` | 30 | Seconds per game, 1–420; real matches last 420 |
| `--games` | 1 | Number of games; seeds count up from `--seed` |
| `--seed` | 42 | Seed of the first game |
| `--swap-sides` | off | Play each seed once as red and once as blue, doubling the games |

```bash
python3 -B arena.py test --opponent baseline --duration 30
python3 -B arena.py test --opponent self --duration 420 --games 4 --swap-sides
python3 -B arena.py test --opponent VERSION --duration 420 --games 2 --seed 200
```

- Starting a batch snapshots the current `strategy.py`; later edits do not affect that batch.
- Only one batch can run at a time, and the service may queue it when busy. Queueing and running both count against your development time; a 420 s game takes several minutes of real time, so plan for it.
- Practice uses the same container and limits as real matches. It is unranked and does not use up any real matches.
- In practice your program controls only slot 2, and **the other five robots run public example strategies**; with `self`, slot 2 on both sides runs your code and the rest are still examples. The example teammates are only sparring partners and do not represent how your real teammates will play.

### 16.2 Results and Replays

- `results` returns, for each game, the winner, the reason, the end time, which side you played (`candidate_team`), both teams' data (attack damage, kills, coins and more) and how many times your program failed (`policy_errors`). When your program fails, `diagnostics` includes the error and its latest log lines (including `print` output).
- `replay` saves the full replay into `practice/`: the whole-field state at every step, both sides' actions and all events, ready for your own analysis scripts. A 420 s replay is about 300 MB, so download only what you need.

### 16.3 Submitting

- `submit` saves the current `strategy.py` as an immutable version and returns its version id.
- You may submit many times; **your last successful submission before the deadline is your entry**. Earlier versions can be practice opponents (`--opponent VERSION`).
- Before submitting, check that practice showed no errors or timeouts, that nothing depends on files in `practice/`, and that the worst-case decision time is well under 200 ms.
- Do not leave your last submission to the final moment, and never treat practiced-but-unsubmitted code as your entry. After the deadline you can still read existing results and replays, but you can no longer practice or submit.

## 17. Starter Code

The `strategy.py` in your workspace is a complete, runnable template (it drives any slot and includes full level 1–4 assembly logic) that you can improve directly. Below is a minimal engineer-only skeleton that illustrates the interface; it is not a strong strategy. It picks up energy units in the resource zone and completes levels 1–3 in the assembly zone in unlock order.

```python
from sdk import action, distance, navigate, assembly_work_point

def act(obs, state):
    slot = obs["controlled_ids"][0]
    me = next(r for r in obs["robots"] if str(r["slot"]) == slot)
    try:
        command = decide(me, obs)
    except Exception:
        command = action()                     # on error, hold still instead of disabling the program
    return {slot: command}, state

def decide(me, obs):
    if not me["alive"]:
        return action()                        # wait for natural respawn; send revive=True if coins allow
    team = obs["team"]
    zones = {z["id"]: z for z in obs["arena"]["zones"]}
    resource, assembly = zones[team + "_resource"], zones[team + "_assembly"]
    core = obs["assemblies"][team]
    done = obs["teams"][team]["completed_difficulties"]
    busy = core["stage"] in ("moving", "inserting", "buffered")
    in_resource = distance(me, resource) <= resource["radius"]
    if not busy and (me["carried_units"] == 0 or (in_resource and me["carried_units"] < 2)):
        return action(move=go(me, resource, obs), pick_unit=True)
    # highest difficulty available now (this skeleton skips level 4)
    level = max(d for d in (1, 2, 3) if obs["time"] >= (d - 1) * 60 and (d == 1 or d - 1 in done))
    x, y = assembly_work_point(me, obs["arena"])
    work = {"x": x, "y": y}
    settled = distance(me, work) <= 0.06
    return action(move=(0, 0) if settled else navigate(me, (x, y), obs["arena"]),
                  brake=settled, assembly=level, assembly_insert=True,
                  assembly_translate=True, assembly_rotate=core["target_rotation"],
                  assembly_confirm=True)

def go(me, zone, obs):
    if distance(me, zone) <= 0.3:
        return (0.0, 0.0)
    return navigate(me, (zone["x"], zone["y"]), obs["arena"])
```

Ideas for improvement: plan the round trips, carry 2 units at a time, attempt level 4 at the right moment, rebuild the outpost when it falls (only 5 s for you), and stay out of enemy fire.

## Appendix: Common Mistakes

- Putting any slot other than `"2"` into `actions`, which disables your program.
- `act` raising an exception or timing out, which disables your program for the whole match. Catch exceptions inside `act` and check your worst-case decision time.
- Requesting more than the power cap for too long; once the buffer is empty the chassis is cut off for 5 s.
- Assuming that losing every ground robot loses the match: only a destroyed base ends a match early.
- Expecting a destroyed or unpowered robot to stop at once: it slides on its momentum, and its wreck blocks paths and sight lines.
- Sending `move` to a tipped robot: its wheels are off the ground; wait for the engineer to right it, or (wheel-legged models) stand up from the front or back.
- Sending `move` during `rescue`: moving after the grip drags the teammate away or loses the grip.
- Letting `strategy.py` depend on files in `practice/`, the network or wall-clock time.
- Submitting for the first time right before the deadline.
