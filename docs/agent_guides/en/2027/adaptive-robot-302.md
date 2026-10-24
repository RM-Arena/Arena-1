# Mode D · Adaptive Single-Robot Strategy (RMUC 2027 · model 302 · I-S Swerve Assault Infantry)

You develop the Python strategy for one **302 · I-S Swerve Assault Infantry** robot under the RMUC 2027 rules. **The final lineup, team size and teammate models are not disclosed during development**; users freely pick deployed robots in the web deck builder, and the same model and strategy may be deployed more than once (at most one aerial robot system per team). Every deployment has its own process, random seed and private `state`; strategy files cannot share memory.

Once the match starts, `observation["robots"]` lists the complete current own lineup, so you can read it and adapt to your teammates, but you may only return an action for your own instance in `controlled_ids`. Never treat a hardware model as a deployment slot, and never assume a fixed number of teammates.

## At a Glance

| Item | Details |
| --- | --- |
| Deliverable | `strategy.py`, defining `act(observation, state)` |
| Controls | One deployed 302 · I-S Swerve Assault Infantry instance; its slot is `controlled_ids[0]` in the match |
| Teammates | Not disclosed during development; the full own lineup is readable in the match |
| Decisions | Every 0.1 s, at most 200 ms each; control only yourself |
| Team messages | Broadcast or address a deployed instance; delivered next decision |
| Match | 420 s; ends early when a base is destroyed; deck battles are stored separately and do not affect the rulebook Elo |

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

Each team fields five robots: the slot 1 heavy robot, slot 3 and 4 infantry, the slot 6 aerial robot system (a hangar plus fully automatic aerial robots) and the slot 7 fully automatic sentry. Robots with the same slot have identical hardware, initial state and rules on both sides. This arena **uses no darts, radar or electronic countermeasures**; none of their rules apply.

| Slot | Role | Selected model and focus | Projectile | Initial HP | Initial ammo |
| --- | --- | --- | --- | ---: | ---: |
| 1 | heavy robot | HV-A Single-arm Heavy · One arm for energy units; modular 42 mm launcher from the workbench | 42mm (modular; unlock and install first) | 400 | 0 |
| 3 | infantry | I27-W Stair-climbing Wheel-legged Infantry · Strong legs climb the high-point steps and hop tunnel roofs | 17mm | 200 | 0 |
| 4 | infantry | I27-T Folding Mecanum Infantry · Folds under the 250 mm tunnel roofs for the tunnel cooling buff | 17mm | 200 | 0 |
| 6 | aerial robot system | AS-4 Four-drone Hangar · Four light 141 mm drones; fast but fragile | none (impact) | — | 0 |
| 7 | sentry | S27-O Omni Automatic Sentry · Omni chassis, fast gimbal and a large magazine for autonomous patrol | 17mm | 400 | 300 |

- "Ammo" is the number of projectiles a robot may fire. The heavy robot and infantry start with 0 and must buy ammo with coins; the sentry starts with 300 rounds and collects 100 more per minute at its supply zone.
- The heavy robot **starts without a launcher**: it can fire only after its modular 42 mm launcher is unlocked (level-3 assembly or the time rule) and fitted at the workbench (fitting may come first; the launcher powers up at the unlock).
- Aerial robots cannot be destroyed and can only attack structure armor by ramming it; they have no HP and cannot shoot.

Ground robot hardware (full data in `sdk.DESIGNS`):

| Slot | Design | Mass kg | Chassis m | Ref. speed m/s | Vision m | Turret yaw rad/s | Armor center height m | Muzzle height m |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | HV-A Single-arm Heavy | 31.8 | 0.55 × 0.55 | 3.2 | 18 | 4.5 | 0.275 | 0.64 |
| 3 | I27-W Stair-climbing Wheel-legged Infantry | 23.85 | 0.42 × 0.36 | 4.3 | 18 | 6.5 | 0.28 | 0.435 |
| 4 | I27-T Folding Mecanum Infantry | 24.35 | 0.46 × 0.44 | 3.9 | 18 | 5.5 | 0.15 | 0.4 |
| 7 | S27-O Omni Automatic Sentry | 27.15 | 0.55 × 0.55 | 3.9 | 20 | 8 | 0.175 | 0.45 |

| Slot | Design | Count | Each kg | Size m | Ref. speed m/s | Battery Wh | Guard strikes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 6 | AS-4 Four-drone Hangar | 4 | 0.145 | 0.141 | 6 | 3.8 | 3 |

The reference speed is the drive controller's target; actual speed depends on power, slope, payload and grip. Armor center and muzzle heights are above the ground.

### 2.2 Field and Coordinates

- The field is 28 m × 15 m with a 2.4 m fence. x runs along the long side from 0 to 28, y along the short side from 0 to 15, z points up; all in meters.
- **Red is on the low-x side, blue on the high-x side.** The field is point-symmetric about (14, 7.5): red's (x, y) corresponds to blue's (28 − x, 15 − y).
- Angles are radians. Heading 0 points along +x, counterclockwise positive (π/2 points along +y).

Key places (red coordinates; mirror for blue):

| Place | Red coordinates | Notes |
| --- | --- | --- |
| Base | (2.41, 7.50) | destroyed = defeat; invulnerable while you fully control your outpost position |
| Fortress card | (6.57, 7.50) | part of the base position |
| Outpost | (10.98, 11.40) | three rotating middle plates; part of the outpost position |
| Central highland card | (10.80, 7.50) | on the 0.3 m central highland, own side; the other card of the outpost position |
| Supply zone | (1.40, 13.00) | healing, respawn, local exchange; closed to the enemy |
| Resource hub | (1.20, 13.85) | the heavy robot picks energy units (6 in stock) |
| Workbench | (1.22, 12.82) | the heavy robot docks here to fit its 42 mm launcher |
| Assembly zone | (13.34, 6.84) | on the central assembly plinth; closed to the enemy |
| Hangar | (13.01, 8.49) | aerial robots launch and dock, 1.77 m high |
| High point | (1.42, 2.82) | 0.8 m high, three steps on the east and four on the south; defense buff and local exchange |
| Power rune | (14.00, 7.50) | centre about 2.9 m high; coaxial red and blue faces |

- The central highland is a 0.3 m deck that runs from your outpost side to the field center, with 12° end slopes. On the fortress side a 0.2 m step band and a 0.4 m rim stop ordinary wheeled robots. The 0.4 m assembly plinth and the rune gantry stand in the middle of the deck; the hangar platforms sit above the gantry.
- The trapezoid highland is 0.2 m high (23° slope); the high point is 0.8 m high and reachable only by steps (about 0.2 m each): three from the trapezoid highland on its east side, four from the field on its south side, so only step-climbing wheel-legged robots get up; the fortress platform is 0.15 m high (20° slope).
- Roads are 0.2 m high with 11° and 15° entry ramps. The road tunnels have about 0.25 m of clearance: only robots that fold their turret **pass through**; robots that jump or climb steps can **cross over** the roofs. Some road sections carry 0.07 m bumps.
- Forbidden areas: both base bodies, the enemy's supply zone and assembly zone, and the dart stations (no darts are used, but the stations remain solid no-go areas).
- Full geometry is in `observation["arena"]` (the same as `map` in `arena.json`): `terrain` (each `polygon` is the real shape), `obstacles` (walls, possibly with `rotation` and `bottom` for tunnel roofs), `zones` (buff cards), `forbidden`, `navigation` (public road-map nodes), `hangars`, `positions` (control positions), `field_geometry.fixtures` (workbench, resource hub, hangar platforms) and `rune`.
- `sdk.terrain_height(arena, x, y)` returns the ground height; `sdk.navigate(robot, point, arena)` returns a move direction around walls and along ramps. You may also write your own navigation.

### 2.3 Match Timeline

| Match time | What happens |
| --- | --- |
| 0 s | First decision and the only moment to choose infantry performance (`profile`); first small-rune chance; the heavy robot may start a level-1 assembly |
| 1 s | Each team receives 800 coins |
| 60 / 120 / 180 s | Level 2 / 3 / 4 assemblies may start |
| 61, 121, 181, 241, 301 s | +100 coins each |
| 90 s | Second small-rune chance |
| 180 s | First large-rune chance (then 255 and 330 s); outpost armor stops rotating; the heavy robot's opening 50% defense ends; the enemy fortress becomes capturable (requires controlling the enemy outpost position) |
| 240 s | Faster disengaged healing at the supply zone |
| 300 − M/50 − 2N/3 s | The heavy launcher unlocks by time (M and N in "Heavy Robot"; the further behind, the earlier) |
| 361 s | +300 coins |
| 420 s | Match ends and the criteria decide the winner |

### 2.4 Winning the Match

- **Only one thing ends a match early: a destroyed base** (the higher remaining base HP wins). Losing all ground robots does not end the match; dead robots can respawn.
- At 420 s the following are compared in order; the first difference decides:
  1. **Control degree** (see "Control Positions and Control Degree");
  2. Team attack damage (effective damage dealt to robots, outposts and bases);
  3. Total remaining HP of living ground robots;
  4. Otherwise a draw.
- Unlike 2026, base HP is not the first timeout criterion; control degree is.

## 3. Your Robot

| Item | Value |
| --- | --- |
| Design | I-S Swerve Assault Infantry |
| Role | High-traction swerve drive and burst launcher |
| Launcher | 17mm |
| Mass kg | 27.55 |
| Chassis m | 0.54 × 0.54 |
| Ref. speed m/s | 4.4 |
| Vision m | 18 |
| Turret yaw rad/s | 5.5 |
| Pitch range (relative to chassis) | -15° ~ +45° |
| Muzzle height m | 0.48 |
| Armor center height m | 0.285 |

## 4. Rules

### 4.1 Shooting and damage

| Source | Damage | Valid when |
| --- | --- | --- |
| 17 mm projectile | 20 | hits an armor plate with normal speed > 12 m/s; one hit per plate per 0.05 s |
| 42 mm projectile | 200 | normal speed > 8 m/s; one hit per plate per 0.2 s |
| Aerial robot impact | 200 | only on base armor and the outpost's middle armor; see "Aerial Robot System" |

- Damage = base damage × attack multiplier × (1 − defense + vulnerability), rounded. Buffs of the same kind take the maximum and do not stack.
- **42 mm projectiles count only while your heavy robot is "online"**: it fired within the last 4 s and is alive (or died less than 3 s ago). The heavy robot's first 42 mm shot completes the launcher installation and deals no damage, heat or speed check.
- Heat: +10 per 17 mm shot, +100 per 42 mm shot, cooled every 0.1 s. Above the cap the launcher locks until heat returns to 0; exceeding the cap by 100 (17 mm) / 200 (42 mm) or more locks it **permanently**.
- Muzzle speed: 17 mm limit 25 m/s, excess of 0–5 / 5–10 m/s locks for 15 / 20 s, more than 10 m/s locks permanently; 42 mm limit 16.5 m/s, up to 18 m/s locks for 15 s, faster locks permanently. Every default model fires below its limit.
- Dead robots leave wrecks that block paths and sight; their heat resets at death.

### 4.2 Coins, ammo, healing and respawn

- Each team receives 800 coins at 1 s, +100 at 61, 121, 181, 241 and 301 s, and +300 at 361 s. Tech-core assemblies add income (see "Tech-Core Assembly").
- Buying ammo (`buy_ammo={"amount": n, "remote": bool}`):

| Caliber | Local exchange | Remote exchange | Team cap |
| --- | --- | --- | --- |
| 17 mm (infantry, sentry) | 10 rounds / 10 coins, multiples of 10 | 100 rounds / 150 coins, delivered after 6 s | 1000 |
| 42 mm (heavy) | 1 round / 10 coins | 10 rounds / 150 coins, delivered after 6 s | 100 |

  Local exchange requires your **own base, own supply zone or own high point**, or an outpost card of an outpost **your team fully controls** (contact counts for 2 s after leaving). Remote exchange requires being "disengaged" (no shot fired and no damage taken for 6 s). Weak robots cannot exchange.
- Remote healing `remote_heal=True`: while disengaged, costs 50 + ⌈t/60 × 20⌉ coins and restores 60% × λ of max HP after 6 s.
- Supply-zone healing: 10% × λ of max HP per second; 25% × λ while disengaged after 240 s. Healing on the card of an outpost your team fully controls runs at half that rate.
- **Logistics factor λ = 1 − base HP lost / 20000** (`referee["logistics"]`). The more your base has lost, the slower you heal and respawn.
- Respawn: a dead robot's progress rises by 1 per second (by 4 in your supply zone or while your base is below 4000 HP); it needs (10 + t/10 + 20 × instant respawns so far) / λ. A normal respawn returns 10% HP and 30 s of invulnerability, and the robot stays "weak" (cannot fire or receive buffs) until it touches your base or supply zone (or the card of a fully controlled outpost).
- Instant respawn `revive=True`: costs ⌈t/60⌉ × 80 + level × 20 coins (the sentry counts as level 1); full HP, weakness and invulnerability that both end after 3 s, and double power for 4 s.
- Coins are shared by the team. Simultaneous purchases settle in slot order, and a request the balance cannot cover simply fails.

### 4.3 Control Positions and Control Degree

The core of the 2027 rules is four **control positions** (`observation["positions"]`):

| Position | Cards | Notes |
| --- | --- | --- |
| `red_outpost` / `blue_outpost` | that team's outpost card + that team's central-highland card | fully controlled by its owner at the start |
| `red_base` / `blue_base` | that team's base card + that team's fortress card | only the original owner can hold it fully |

- Each position has a `controller` and a `control` level (`full` or `temporary`).
- **Capture**: on a position the other team fully controls, when only your robots activate any of its cards and none of theirs do, after 5 s it becomes your **temporary control**. Progress falls back at the same rate when you leave and pauses while both teams are on the cards.
- **Becoming full**: when the temporary holder has had no robot on the cards for 5 s, an outpost position passes to the other team's full control; a base position always returns to its original owner.
- **Outpost destroyed**: full → the same team's temporary control; temporary → the same team's full control. Whenever an outpost position becomes some team's full control while its outpost lies destroyed, the outpost is **rebuilt at 500 HP for the new controller** and is from then on that team's outpost (its own shots no longer damage it).
- **Control degree**: +1 per second while controlling (fully or temporarily) both outpost positions; +3 per second while controlling both base positions. Control degree never decreases and is the first timeout criterion.
- **Base invulnerability**: while a team fully controls its own outpost position, its base takes no damage at all. To damage a base you must first take full control of its outpost position away (capture it, or destroy the outpost).
- Central-highland cards are exclusive: the team already on a card keeps it and the other team's robots cannot activate it.

### 4.4 Structures and the fortress

- Bases have 10000 HP; outposts 1000 HP (500 after a rebuild). The outpost's three middle plates rotate with its rotor until 180 s; its top armor deals no damage in 2027.
- The base's three upper plates can always be hit by 17 mm, 42 mm and aerial impacts; its three large plates are exposed only once "opened". **A base's armor opens after enemy robots spend a total of 10 s on its fortress card** (the timer resets after more than 3 s away).
- **Own fortress**: active while your team does not control its own outpost position (the enemy holds it temporarily or fully). One own robot holds the card: 50% defense, a cooling bonus of min(75, ⌊max base HP lost/80⌋), and a reserve of min(500, 100 + ⌊max base HP lost/15⌋) rounds that is spent first when firing from the card (10 reserve units per 42 mm shot).
- **Enemy fortress**: after 180 s, a team that controls the enemy outpost position may activate the enemy fortress card (taking 100% vulnerability). 10 s there opens the enemy base armor, and standing there also advances temporary control of the enemy base position.

### 4.5 Buff cards and terrain crossings

| Buff | Condition | Effect |
| --- | --- | --- |
| Base | own base card | 50% defense |
| High point | own high-point card | 50% defense, local exchange |
| Central highland | central card (exclusive) | 25% defense |
| Supply zone | own supply zone | healing, faster respawn, local exchange; the heavy robot is invulnerable inside |
| Assembly | own assembly zone during an assembly | up to 45 s of heavy-robot invulnerability (reset by each new best assembly level) |
| Road crossing | low road card then high road card within 3 s | 25% defense for 5 s, 15 s cooldown |
| Highland crossing | low highland card then central card within 5 s | 25% defense for 30 s |
| Tunnel over | both tunnel end cards within 3 s (over the roof) | 25% defense for 30 s |
| Tunnel through | end card, middle card under the roof, end card within 3 s | cooling ×1.5 for 120 s |

- A buff card keeps working for 2 s after leaving it. Weak robots cannot activate cards.
- Holding two different crossing buffs raises the defense to 50%.
- Infantry earn 300 XP for their first road, highland and tunnel crossing and for first reaching the high point.

### 4.6 Tech-Core Assembly

The **heavy robot** assembles (2027 has no engineer): it picks energy units at your resource hub (6 per team, at most 2 carried), drives to your assembly zone and uses its arm to install a unit into the tech core.

- Start times: level 1 at 0 s, level 2 at 60 s, level 3 at 120 s, level 4 at 180 s, each after completing the previous level.
- Steps (commands settle every 0.1 s): level 1 insert → confirm; level 2 insert → lift → confirm; levels 3 and 4 insert → lift → flip 90° → rotate to the target angle (±5°) → confirm. Every step checks actual tool position, direction and wrist roll. Levels 3 and 4 require 0.4 s at the target rotation before confirmation; an incorrect confirmation locks retries for 1 s.
- Level 4 needs **two** cores (your own and one borrowed from the opponent), can be completed once per team, and has 45 s; insertion, lifting, rotation and confirmation must each finish on both cores within 5 s (the flip step is exempt). Dual-arm models use `assembly_core=2` to work both cores at once; single-arm models alternate `assembly_core=0/1`.
- First-completion rewards:

| Level | Reward | Repeat completions |
| --- | --- | --- |
| 1 | heavy robot to level 5; tech income +40 per 10 s | +4 per 10 s |
| 2 | heavy level 7; infantry level cap 7; income +20 | +8 per 10 s |
| 3 | heavy level 10; infantry level cap 10; 25% team defense; **unlocks the heavy launcher**; income +20 | +12 per 10 s |
| 4 | 50% team defense; income +40 | cannot repeat |

- Levels 1–3 have no extra attempt timeout, and successful assemblies have no repeat cooldown. Level 4 has 45 s after the cores arrive. Failed retries retain the pose and target rotation; only success generates a new set. The heavy robot cannot fire during assembly; death or 15 s without detecting its assembly card fails the attempt.

### 4.7 Power Rune

- The rune stands on the gantry at the field center (14, 7.5). Its red and blue faces share one axis and turn together, each with 5 arms (target radius 0.15 m on a 0.7 m arm). Teams activate independently and may only hit the face turned toward them (axis direction in `arena["rune"]["axis_yaw"]`).
- **Infantry or the sentry** start an activation: `rune_start=True` (alive and not weak, anywhere). Only 17 mm counts, with normal speed above 12 m/s; 42 mm has no effect.
- Targets are in `observation["runes"][own]["targets"]` (`arm, x, y, z, radius, lit`); `lit=True` marks the target to hit now. Positions are reported only while an own observer is within vision range. Aim with `dict(target, kind="rune_target")` in `sdk.aim_pitch`.
- Small rune (0–180 s, one chance at 0 s and one at 90 s): hit 5 different lit arms, each within 2.5 s; a wrong hit or timeout resets the progress, and the whole attempt has 20 s. Effect: 25% defense for the team and structures for 45 s, and infantry XP doubles (at most 1200 extra per team).
- Large rune (one chance each at 180, 255 and 330 s): each round lights 2 targets; hit the first within 2.5 s and optionally the second within 1 s more; 5 rounds give 5–10 valid hits. The average ring decides an attack multiplier of 1.5–3, 25–50% defense and cooling ×1–×5 for 30–60 s; living infantry share 750 XP.
- Motion: small runes and large runes outside activation rotate at π/3 rad/s. During a large activation the shared shaft follows a·sin(ωt)+2.090−a; each new large activation resets t, a and ω.
- **2027 shrinking rule**: after your team's first large activation only hits on ring 4 or better (closer to the center) count; after the second, only ring 7 or better (one ring per 1.5 cm from the center, 10 at the center).

### 4.8 Levels, experience and performance

- **Only infantry gain experience**: 1 per 17 mm shot fired, 4 per HP of robot damage, 2 per HP of outpost damage, 1 per 2 HP of base damage, rounded up for odd damage; a kill gives 50 × victim level × (1 + 0.2 × level gap); first terrain crossings give 300.
- When a damage or kill source cannot gain XP, eligible living infantry below their cap share it according to projectile caliber; non-projectile XP is shared among all eligible infantry. Shares are rounded to one decimal place.
- The infantry level cap starts at 5, becomes 7 after a level-2 assembly and 10 after a level-3 assembly.

| Level | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Total XP | 0 | 550 | 1100 | 1650 | 2200 | 2750 | 3300 | 3850 | 4400 | 5000 |

- Infantry chassis and launcher profiles can only be chosen with `profile` at `tick == 0` and lock afterwards. Without an explicit selection, all infantry use the HP chassis and cooling launcher. Model recommendations apply only when selected explicitly.

Chassis (HP / power):

| Level | HP chassis HP | Power W | Power chassis HP | Power W |
| --- | ---: | ---: | ---: | ---: |
| 1 | 200 | 45 | 150 | 60 |
| 2 | 225 | 50 | 175 | 65 |
| 3 | 250 | 55 | 200 | 70 |
| 4 | 275 | 60 | 225 | 75 |
| 5 | 300 | 65 | 250 | 80 |
| 6 | 325 | 70 | 275 | 85 |
| 7 | 350 | 75 | 300 | 90 |
| 8 | 375 | 80 | 325 | 95 |
| 9 | 400 | 90 | 350 | 100 |
| 10 | 400 | 100 | 400 | 100 |

Launcher (heat cap / cooling per second):

| Level | Cooling launcher Heat cap | Cooling /s | Burst launcher Heat cap | Cooling /s |
| --- | ---: | ---: | ---: | ---: |
| 1 | 40 | 12 | 170 | 5 |
| 2 | 48 | 14 | 180 | 7 |
| 3 | 56 | 16 | 190 | 9 |
| 4 | 64 | 18 | 200 | 11 |
| 5 | 72 | 20 | 210 | 12 |
| 6 | 80 | 22 | 220 | 13 |
| 7 | 88 | 24 | 230 | 14 |
| 8 | 96 | 26 | 240 | 16 |
| 9 | 104 | 28 | 250 | 18 |
| 10 | 120 | 30 | 260 | 20 |

- The heavy robot uses no experience; its performance rises with assemblies (see "Heavy Robot"). The sentry keeps fixed automatic parameters (400 HP, heat cap 260, cooling 30/s, 100 W) and counts as level 1 when killed.

### 4.9 Power

- Chassis power caps are listed above. Drawing more first consumes a 60 J buffer; when the buffer is empty the chassis loses power for 5 s. The absolute cap is 200 W.
- 2027 has no 2026 chassis energy pool and no wireless charging.

### 4.10 Penalties

- The referee only penalizes objectively decidable behavior (for example excess muzzle speed or leaving the field) and never randomly judges intent. A yellow card removes 15% HP from the offender (5% from teammates); three yellow cards send the robot off. A yellow card also cuts the sentry's chassis power for 2 s. An aerial robot leaving the field receives a red card.

## 5. Robot Mechanics

### 5.1 Infantry

- The only role that gains experience; its level cap follows assembly progress (5 / 7 / 10).
- Starts rune activations; earns +300 XP each for its first road, highland and tunnel crossing and for first reaching the high point.
- Best suited to holding control positions: 5 s on the enemy outpost or central-highland card captures the enemy outpost position, which starts your control degree and is required before the enemy base can be damaged.

## 6. Interface Reference

### 6.1 The act function

```python
def act(observation: dict, state) -> tuple[dict, object]:
    ...
    return actions, new_state
```

- Called every 0.1 s. The match advances every 0.05 s, so `tick` grows by 2 per decision; `tick == 0` on the first call.
- `actions` maps slot strings to action dicts, for example `{obs["controlled_ids"][0]: action(...)}`. A robot without an action this decision gets an empty action (stop, no fire).
- An action stays in effect until the next decision (0.1 s, two match steps).
- `state` is the `new_state` you returned last time, `None` on the first call. It must be JSON-serializable and at most 32 KiB.
- `random` is seeded deterministically. Do not rely on wall-clock time; use `observation["time"]`.

### 6.2 Observation

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

### 6.3 Action

Build actions with `sdk.action(...)`, which rejects unknown fields early. The table lists only the fields your robot uses.

| Field | Value | Applies to | Meaning |
| --- | --- | --- | --- |
| `move` | `(vx, vy)` | ground | world-frame velocity intent in [−1, 1] |
| `heading` | radians | ground | chassis heading |
| `yaw_rate` | rad/s, ±12 | ground | chassis spin target (overrides `heading`) |
| `aim`, `pitch` | radians | ground | turret world yaw and pitch |
| `fire` | bool | ground shooters | fire during this decision |
| `power` | watts | ground | chassis power budget |
| `buy_ammo` | `{"amount": n, "remote": bool}` | heavy, infantry, sentry | buy ammo |
| `remote_heal` | bool | ground | remote healing |
| `revive` | bool | ground | instant respawn while dead |
| `profile` | string or dict | infantry | performance choice, only at `tick == 0` |
| `rune_start` | bool | infantry, sentry | start a rune activation |
| `messages` | list | all | team messages, see "Team Messages" |

Operations that do not apply to the robot or its current state have no effect; some are recorded as `invalid_action` events in the replay. A misspelled field disables the whole program; `sdk.action` reports it in your own code first.

### 6.4 SDK

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

### 6.5 Slots and messages in mode D

`robot["model_slot"]` is the hardware model and `robot["slot"]` the deployment slot of this match; duplicated models have different slots. `TEAM_SLOTS_2027` describes fixed lineups and must not be used to infer this match's team size. Read the actual lineup from the observation.

```python
from sdk import action, message

def act(obs, state):
    slot = obs["controlled_ids"][0]
    own = next(r for r in obs["robots"] if str(r["slot"]) == slot)
    teammates = [r for r in obs["robots"] if str(r["slot"]) != slot]
    outgoing = [message({"intent": "cover", "model": own["model_slot"]})]
    return {slot: action(messages=outgoing)}, {"teammates": [r["id"] for r in teammates]}
```

Send at most 4 messages per decision; each `data` is a JSON value of at most 512 bytes and counts toward your 1 KiB action limit. `to="all"` broadcasts to your current teammates; otherwise give a teammate's deployment slot string (not a model). A message sent now arrives once in `obs["messages"]` at the next decision (0.1 s later).

## 7. Practice and Submission

Practice uses varying teammate counts and models; they are only samples, so do not assume the real lineup matches them.

## 8. Practice and Submission

Run every command from your workspace:

```bash
python3 -B arena.py status                  # remaining time, submitted versions, practice jobs
python3 -B arena.py test [options]          # start a batch of practice games with the current strategy.py
python3 -B arena.py results JOB_ID           # practice progress and results
python3 -B arena.py replay JOB_ID --game 0   # save the full replay of game 0 into practice/
python3 -B arena.py submit                   # submit the current strategy.py
```

### 8.1 Practice Games

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
- Practice varies the decks: your code controls one instance of the selected model, identified by `controlled_ids[0]`. Teammate counts and models vary and use public examples. Self-play gives each side one instance of your policy with example teammates.

### 8.2 Results and Replays

- `results` returns, for each game, the winner, the reason, the end time, which side you played (`candidate_team`), both teams' data (attack damage, kills, coins and more) and how many times your program failed (`policy_errors`). When your program fails, `diagnostics` includes the error and its latest log lines (including `print` output).
- `replay` saves the full replay into `practice/`: the whole-field state at every step, both sides' actions and all events, ready for your own analysis scripts. A 420 s replay is about 300 MB, so download only what you need.

### 8.3 Submitting

- `submit` saves the current `strategy.py` as an immutable version and returns its version id.
- You may submit many times; **your last successful submission before the deadline is your entry**. Earlier versions can be practice opponents (`--opponent VERSION`).
- Before submitting, check that practice showed no errors or timeouts, that nothing depends on files in `practice/`, and that the worst-case decision time is well under 200 ms.
- Do not leave your last submission to the final moment, and never treat practiced-but-unsubmitted code as your entry. After the deadline you can still read existing results and replays, but you can no longer practice or submit.

### Model capabilities

Drive: `swerve`; arms: 0.
