# Mode D · Adaptive Single-Robot Policy (Slot 3 Infantry · Wheel-Legged model)

Develop one Python policy for the **Slot 3 Infantry · Wheel-Legged model**. **The final lineup, teammate count and models are not disclosed during development.** The user chooses deployments through the Web deck builder and can deploy the same model or policy repeatedly. Each deployment has a separate process, random seed and private `state`.

During the match, `observation["robots"]` exposes the full actual own lineup so the policy can adapt. Return actions only for your own instance in `controlled_ids`. Never confuse hardware model numbers with deployment IDs or assume a fixed teammate count.

## At a Glance

| Item | Details |
| --- | --- |
| Deliverable | `strategy.py`, defining `act(observation, state)` |
| Controlled robot | One Slot 3 Infantry · Wheel-Legged model instance; use `controlled_ids[0]` at match time |
| Teammates | Unannounced during development; the actual own lineup is available during the match |
| Decisions | Every 0.1 s, at most 200 ms per call, control self only |
| Communication | Broadcast or address teammate instances; delivered next decision |
| Match | 420 s; ends early on base destruction; deck games are recorded separately and unranked |

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

## 2. Match and Own Hardware

The arena is 28 by 15 metres. Each side has a base, outpost, tech core and rune. Coins and team buffs are shared. Timeout compares base HP, outpost destruction history, outpost HP, attack damage and surviving ground HP in that order.

| Item | Value |
| --- | --- |
| Design | W3 Wheel-Legged Infantry |
| Role | self-balancing, adjustable legs, jumps steps and fly-slopes, cannot strafe |
| Mass kg | 21.65 |
| Chassis m | 0.42 × 0.36 |
| Ref. speed m/s | 4.6 |
| Vision m | 18 |
| Launcher | 17mm |
| Turret yaw rad/s | 6.5 |
| Pitch range (relative to chassis) | -15° ~ +45° |
| Muzzle height m | 0.47 |
| Armor center height m | 0.28 |

## 3. Shooting and Damage

### 3.1 Launchers

| Parameter | 17mm (infantry, aerial) | 42mm (hero) |
| --- | ---: | ---: |
| Damage per armor hit | 20 | 200 |
| Heat per shot | 10 | 100 |
| Muzzle speed | 25 m/s | 12 m/s (16.5 m/s when deployed) |
| Minimum firing interval | 0.05 s | 0.2 s |
| Normal relative speed needed to register on armor | > 12 m/s | > 10 m/s |
| Minimum interval between two valid hits on the same armor plate | 0.05 s | 0.2 s |

- Muzzle speed is fixed; actions cannot change it. Projectiles feel gravity and air drag and inherit the shooter's velocity at the moment of firing; firing also produces recoil.
- Each shot has independent angular spread around the muzzle axis: up to 1.8° for 17mm and 1.6° for 42mm (public simulation calibration, not official limits). The cone widens with distance, so lateral spread increases at longer ranges. The same seed and action trace reproduce the spread. All projectiles are green for both teams.
- `fire=True` stays in effect for the 0.1 s after the decision: 17mm may fire **2 rounds**, 42mm at most 1.
- The engineer has no launcher. The aerial robot cannot be attacked and is not a valid target.

### 3.2 What Counts as a Hit

Every ground robot has 4 armor plates facing the front, back, left and right of its chassis, tilted upward (75° from straight up). HP is lost only when all of the following hold:

1. the projectile strikes an armor plate — hits elsewhere on the body do no damage and are simply blocked;
2. the projectile's normal speed relative to the plate exceeds the threshold above — long shots, glancing hits or shots chasing a fleeing target may fall short;
3. the minimum interval since that plate's previous valid hit has passed;
4. the target is alive and not invulnerable.

42mm also depends on the hero's state: **once the hero has not fired for 4 s in a row, or has been dead for 3 s, your 42mm rounds still in flight no longer deal damage**.

### 3.3 Damage Formula

```text
damage = round( base damage × attack buff × (1 − defense buff + vulnerability) )
```

- Base damage is 20 for 17mm and 200 for 42mm. The attack buff defaults to 1 and comes from sources such as the power rune.
- Buffs of the same kind do not stack; **the largest applies**. With both a 25% and a 50% defense buff, 50% is used.
- A single hit never deals more than the target's remaining HP.
- Hitting the 10 mm × 10 mm weak spot at the center of a base or outpost armor plate gives an attack buff of at least 1.5.

### 3.4 Heat

While overheating remains above zero, this robot’s vision range is 35% of normal. It recovers at zero; public referee health remains available. This disclosed sensor proxy represents reduced FPV visibility. `vision[slot]` reports `range_m` and `fpv_dimmed`.

- Each shot adds heat (17mm +10, 42mm +100). Every 0.1 s heat drops by "cooling × 0.1", where cooling is per second.
- **Heat above the cap locks the launcher**; it unlocks only after cooling all the way to 0.
- Reaching "cap + 100" (17mm) or "cap + 200" (42mm) locks the launcher **for the rest of the match**.
- Heat cap and cooling depend on level and profile; see "Your Robot".
- `sdk.can_fire(robot)` checks alive, weakened, lock, ammo, and whether one more shot would exceed the cap. Because 17mm may fire 2 rounds per decision, infantry and the aerial robot should fire only when `heat + 20 <= cap`.
## 4. Referee Penalties and Launcher Locks

Referee decisions use a separate interface from robot actions. Contestants cannot issue cards or change penalty state. The organizer judges subjective fouls; ordinary collisions do not randomly generate yellow cards. Invalid action input is rejected without becoming a yellow card.

### 4.1 Yellow Cards

- A single-team yellow deducts 15% of the offender's maximum HP and 5% from each other living ground teammate. Damage is rounded to an integer, stops at 1 HP, and bypasses defence and invulnerability.
- Another individual yellow less than 30 s after the previous one doubles that robot's deduction ratio. At 30 s or later it returns to 15%; teammates still lose 5% each.
- The offender's camera is obscured for 5 s and teammates' cameras for 2 s. Consecutive durations stack. An obscured camera provides no enemy positions, vision lists or rune target positions; public referee telemetry remains available, and movement and firing remain possible.
- An engineer's second yellow, or any other robot's third yellow, immediately also issues a red card.
- A simultaneous yellow deducts 5% from every living ground robot on both teams and obscures every camera for 2 s. It changes neither individual card counts nor individual repeated-penalty ratios.

### 4.2 Red Cards and Forfeits

- A ground robot receiving red has 0 HP, loses chassis power and cannot revive naturally or buy a revival for the remainder of the match. Its wreck stays on the field.
- An aerial robot receiving red stops support and firing, returns automatically to its pad and cannot restart support.
- Penalty HP loss counts toward the opposing team's attack damage without granting robot XP or kill rewards. A referee forfeit sets the losing team's base HP to 0 and immediately ends the match.
- Own status is in `yellow_cards`, `red_card` and `fpv_blocked_until`; public `referee.robots` also shows both teams' card counts and red-card states.

### 4.3 Excess Muzzle Speed

Fixed hardware determines muzzle speed; contestants cannot request a different speed. The sensor measures speed relative to the launcher, excluding inherited chassis motion.

- 17mm: exceeding 25 m/s by less than 5 m/s locks firing for 15 s; an excess from 5 to less than 10 m/s locks it for 20 s; an excess of at least 10 m/s permanently locks it for this match.
- 42mm: exceeding the current limit (12 m/s; 16.5 m/s when deployed) by up to 1.1 times the limit locks for 15 s; above 1.1 and up to 1.2 times the limit locks for 20 s. Actual speed above 18 m/s permanently locks firing; this absolute boundary takes priority.
- Unsupported undeployed 42mm hardware speeds strictly above 14.4 and up to 18 m/s are rejected before firing; the undefined sanction band is not invented.
- Muzzle-speed and heat locks are independent. Clearing one does not clear the other; revival cannot remove a permanent lock.
- Status is in `overspeed_locked`, `overspeed_lock_until`, `overspeed_permanent_lock`, `heat_permanent_lock` and `launcher_fault`; `sdk.can_fire` checks these locks.
## 5. Coins, Ammo, Healing and Revival

### 5.1 Coins

Coins belong to the whole team. `observation["teams"][your team]["resources"]` is the current balance; the opponent's balance is hidden. Your teammates spend from the same balance.

- **Scheduled income**: 400 at 1 s; 50 each at 61, 121, 181, 241 and 301 s; 150 at 361 s — 800 in total.
- **Tech income**: every successful tech-core assembly by the engineer adds a payment to the team every 10 s, and these add up (see "Your Team").
- **Spending**: buying ammo, remote healing, instant revival, and air support beyond its free time.

### 5.2 Buying Ammo

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

### 5.3 Healing

- **Supply zone**: your ground robots in your supply zone recover 10% of max HP per second; after 240 s, a robot that is also disengaged recovers 25% per second.
- **Remote healing** (hero and infantry only): while disengaged, send `remote_heal=True`. It costs `50 + ceil(elapsed_seconds / 60 × 20)` coins and, 6 s later, restores 60% of the max HP at that moment. The price rises continuously, not once per minute. Dying while waiting cancels it without refund; only one remote heal can be pending at a time.
- **Leveling up**: any increase in max HP is added to current HP immediately.
- The engineer cannot heal teammates.

### 5.4 Death and Revival

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
## 6. Profiles, Levels and Experience

### 6.1 Choosing a Profile

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

### 6.2 Levels and Experience

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
## 7. Movement, Chassis Power and Energy

### 7.1 Movement and Turret

- `move=(vx, vy)` is a velocity intent in **world coordinates**, each component in [−1, 1]; vectors longer than 1 are scaled down to 1. Target velocity = intent × the robot's reference speed (`speed_reference_mps`).
- Robots are rigid bodies with mass, inertia, suspension and tire friction: accelerating and braking take time, sharp turns slide, slopes slow you down, and robots can get airborne or tip over. **Brake early**; never assume an instant stop, and do not try to drive straight over a step.
- `heading` sets the chassis heading in radians; when omitted, the chassis turns toward its direction of travel. The heading determines which way the four armor plates face.
- `aim` is the turret's horizontal angle in world coordinates and `pitch` its world elevation (positive up). The turret turns at a limited rate, its pitch is limited to −15° … +45° relative to the chassis, and it compensates for chassis tilt automatically. `aim=None` keeps the current direction.

### 7.2 Chassis Power

- Each ground robot has a chassis power cap, `power_limit`, that depends on role, level and profile.
- The `power` action field (watts, 0–200) is this decision's power budget and defaults to the current cap. Any budget above the cap is drawn from a **buffer**: the buffer holds 60 J and is settled every 0.1 s as `buffer −= (actual power − cap) × 0.1`.
- If the buffer is empty and power is still over the cap, the **chassis is cut off for 5 s** and cannot move.
- For 4 s after an instant revival the power cap is doubled (at most 200 W).

### 7.3 Chassis Energy (Hero and Infantry)

- Chassis energy `energy` starts at 20 000 J with a cap of 40 000 J. Each joule the chassis outputs costs one joule; driving at a steady 60 W drains it in about 330 s.
- When energy runs out, the power cap drops to 35 W; at 25 000 J or more, the power cap rises to 125% (at most 200 W).
- Recharging: park still (below 0.08 m/s) at your charging dock. It supplies 100 W, credited to chassis energy at 8 × the net input, i.e. about `8 × (100 − chassis power)` J/s. The dock stands inside your supply zone; `arena["charging_docks"]` gives its `transmitter` center and the `normal` it faces. The receiver at the center of your chassis front must face the transmitter (your heading opposite to `normal`, within about 11°) and lie within 3 cm of the point `transmitter + 0.24 × normal`, so your chassis center sits half a chassis length (`chassis_size_m[0] / 2`) further along `normal`. Red's transmitter is at (0.94, 12.10) facing +x: face −x with your center near x = 1.18 + half the chassis length, y = 12.10.
- The engineer and the aerial robot do not use chassis energy.

The physical battery `battery_remaining_wh` and the supercapacitor `supercap_energy_j` are hardware state, settled separately from the chassis energy above.
## 8. Base and Outpost

| Structure | HP | Key points |
| --- | ---: | --- |
| Base | 5000 | Lose it and you lose. Invulnerable while your outpost stands (HP > 0) |
| Outpost | 1500 | Three rotating armor plates; once destroyed, your base loses its protection |

Only the armor of either structure takes damage, under the same conditions as robot armor (normal-speed threshold, minimum interval per plate). Both also receive your team's defense buffs (tech cores, power rune).

### 8.1 Base Armor

- The base armor starts closed. **While it is closed, only 42mm can damage the base** (by hitting the raised target area).
- When base HP falls to **2000 or less**, the armor opens and 17mm can damage the base too (another way to open it is described under "Fortress"). Once open, it never closes again.
- The base's virtual shield (from the level-4 tech core) absorbs damage before HP.

### 8.2 Outpost Armor Rotation

- The armor starts rotating at kickoff and reaches 0.8π rad/s within 5 s.
- It stops when any of these happens, turns back to its initial orientation within 10 s, and never rotates again: this outpost is destroyed for the first time; the opponent's base armor opens; the match reaches 180 s.

### 8.3 Rebuilding the Outpost

- Every 1000 HP of cumulative damage to your base grants one rebuild credit (`teams[your team]["rebuild_credits"]`).
- Before 300 s, while your outpost is destroyed, a hero or infantry robot that stays in your outpost zone for 10 s **in a row** (an engineer needs only 5 s) spends one credit and rebuilds the outpost to 750 HP. Leaving the zone resets the timer; a weakened robot cannot rebuild.
- While rebuilding, `outposts[your team]["rebuild"]` contains the robot ID, `elapsed`, `required` seconds and `progress` (0–1); otherwise it is `None`. With several builders, the display shows the highest completion fraction without combining their progress. Progress bars appear above the outpost and in the data panel. Leaving the zone, dying or becoming weakened resets that robot's timer.
- A rebuilt outpost protects the base again, but the "ever destroyed" record stays (it matters for tiebreaker 2).

### 8.4 Aiming at Structures

`sdk.aim_at` and `sdk.aim_pitch` accept structures directly as targets and choose the target height from the armor state:

```python
enemy = "blue" if obs["team"] == "red" else "red"
outpost = dict(obs["outposts"][enemy], kind="outpost")   # outposts need kind="outpost"
base = obs["bases"][enemy]
```

Without `kind="outpost"`, `aim_pitch` computes an outpost target at the wrong height.

Closed, the base's three corner shells form a pyramid that meets at a narrow slit in the middle of each face. Opening swings the half-shell on each side of the slit about 66° outward on its corner hinge, exposing that face's lower large panel, centred 0.287 m above the pedestal and tilted 15° upward (figure 4-11). Both calibres can attack these panels from outside the forbidden pedestal; opening takes about 1.5 s (`armor_open_progress`) and the shells block shots at every intermediate angle. The outpost's three rotating panels sit at different heights, 1.116 / 1.216 / 1.316 m above its base (figure 4-32), and each keeps its height while turning; its top 42mm module is at 1.5 m. Covers, supports and foundations stop shots. Only finite `armor_plates` register damage; each publishes `center`, `normal`, width, height and calibre restrictions. These unlabelled centers and motion timings are public reconstructed simulation parameters. The SDK aims at a panel facing the shooter. Top small base and outpost modules accept 42mm even after opening, without a center weak-spot bonus.
## 9. Zone Buffs and Terrain Crossings

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

### 9.1 Fortress

**Your fortress** (enabled once your outpost has been destroyed; if several infantry are inside, only the lowest slot benefits)

- 50% defense;
- cooling bonus: cooling is at least `base cooling + min(75, floor(base HP lost / 40))`;
- reserve ammo: an extra team pool with capacity `min(500, 100 + 2 × floor(base HP lost / 15))`, topped up as your base loses HP. The infantry holding the fortress fires from the reserve first, so it can shoot even with 0 ammo of its own (`sdk.can_fire` only looks at the robot's own ammo and ignores the reserve). Base healing reduces capacity and clips excess reserve; leaving and re-entering does not create a fresh reserve. The remaining reserve is `teams[your team]["fortress_ammo"]`.

**Enemy fortress** (capturable after 180 s while the enemy outpost is down; infantry only)

- The holder takes **100% vulnerability** — double damage;
- after 20 s of valid occupation, the enemy base armor opens. Loss of occupation or death pauses the timer for up to 3 s; re-entry after that cannot restore old progress.

### 9.2 Terrain Crossings

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
## 10. Power Rune

The power rune stands at the center of the field (14, 7.5), its hub about 3.0 m high, on a gantry above the assembly pedestal. It has **a red face and a blue face** on one shaft that turn together: the red face looks toward the red half and the blue face toward the blue half, each 0.35 m from the shaft center (shaft direction: `arena["rune"]["axis_yaw"]`). When the red face turns clockwise seen from red, the blue face turns counter-clockwise seen from blue. Each face has 5 arms, each ending in a round target of radius 0.15 m that rotates around the hub at a radius of 0.7 m. Each team activates its own face independently and can only hit the face turned toward it.

- Both small and large runes turn at smoothly varying, irregular speeds while idle, during activation and while buffs are active. Both faces stay synchronized on the same shaft; activation does not reset its speed. Current `angular_velocity` (rad/s) and `angular_acceleration` (rad/s²) are visible under the same range restriction as target positions. Aim must account for speed changes during projectile flight.

- **Only infantry can start an activation**: send `rune_start=True` (alive and not weakened; position does not matter).
- **Only 17mm counts**, from infantry or the aerial robot. 42mm hits are ignored and earn nothing.
- A projectile's horizontal speed along the rune's axis must exceed 12 m/s.
- Targets are in `observation["runes"][your team]["targets"]`; each has `arm, x, y, z, radius, lit`, and `lit=True` marks the target to hit now. Target positions are provided only while one of your observers is within vision range.
- The activation state is `runes[your team]["status"]`: `idle`, `activating` or `active`. You cannot start again while the buff is `active`.
- When aiming, pass `dict(target, kind="rune_target")` to `sdk.aim_pitch` so it treats the target as an exact point instead of adding an armor height.

### 10.1 Small Rune (0–180 s)

- Chances: one at kickoff and another at 90 s. Unused chances do not carry over to the large-rune phase.
- After starting, one target lights up and must be hit within 2.5 s; then another arm that has not yet been hit lights up. Hitting **5 different arms** in turn activates the rune.
- A wrong target, or 2.5 s without a hit, resets progress to the beginning. The whole attempt is limited to 20 s; after that the chance is lost.
- Effect: your robots, base and outpost get **25% defense** for 45 s, and XP earned during that time is doubled (at most 1200 extra XP for the team).

### 10.2 Large Rune (from 180 s)

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
## 11. Chassis Physics and Fine Control

Every ground robot is a 120 Hz rigid-body simulation with mass, inertia, suspension, tyre grip and collisions. `move` is only a velocity intent; the actual motion comes from motor force, power and friction. These physical details matter tactically.

### 11.1 Power Cuts and Momentum

The referee cuts chassis power when a robot is destroyed, during an over-power cut-off (see "Power and Energy") and when the battery is empty. Then `powered == False`:

- The motors neither drive nor brake. The robot **keeps sliding on its momentum**, slowed only by back-driven gearboxes, rolling resistance and whatever it hits. A mecanum chassis decelerates at about 2.2 m/s² (about 2 m from 3 m/s); on slopes steeper than about 12° (such as the 17° jump ramp) an unpowered mecanum robot rolls downhill.
- A destroyed robot stays on the field as a **wreck**: it is still solid, blocks paths, shots and sight lines, and can be pushed. Respawning happens in place and restores power; a tipped robot is still tipped after it respawns.
- A powered robot without `move` brakes actively and holds its position and heading (up to tyre friction). Send `brake=False` to let a powered chassis coast.

### 11.2 Tipping Over and Righting

- `upright` is the cosine between the body's vertical axis and world vertical (1 is upright); below 0.5, `tipped == True`. A tipped robot's wheels are off the ground and it cannot drive.
- Typical causes: running off the side of a ramp at speed, dropping off a step, a bad jump-ramp landing, collisions.
- The engineer can right a tipped teammate with its arm (the engineer's `rescue` action). A wheel-legged robot stands up by itself after falling on its front or back, but needs the engineer when it lies on its side.

### 11.3 Fine-Control Fields

| Field | Effect |
| --- | --- |
| `move` | World-frame velocity intent in [−1, 1], scaled by the reference speed |
| `heading` | Chassis heading target; when omitted, a mecanum chassis turns toward its motion |
| `yaw_rate` | Chassis yaw-rate target (rad/s, up to ±12), overriding `heading`. A mecanum robot can translate while spinning (a "spinning top") so enemies cannot keep hitting the same armor plate |
| `power` | Chassis power budget for this decision (0–200 W). Power above the limit is drawn from the supercapacitor; once it is empty the buffer energy starts to drain |
| `brake` | `True` by default; with `False` the chassis does not brake when there is no `move` |

Spinning costs power: torque times angular velocity counts toward chassis power, so watch the limit when spinning for long.

### 11.4 Road Bumps

- The road south of the kerb (red x 5.25–7.65, blue mirrored) is covered by ten smooth 70 mm humps 240 mm apart. Wheeled robots that climb the 10° slope west of the notch must cross them to reach the east road, the jump ramp and the highland end slopes.
- Wheeled chassis ride 100 mm clear on soft suspension, so the wheels follow the humps while the body stays nearly level: drive straight at full speed and you are over in about 3–5 s. Crawling (especially the heavier dual-arm engineer) can stall between two humps; back off a little and accelerate again.
- Without a `power` field, heroes and infantry with a supercapacitor draw on it automatically while on the humps; an explicit `power` budget takes precedence.
- A wheel-legged chassis lifts both wheels at once, so enter at full speed and keep to the middle of the section; brushing the side kerbs can catch it.

### 11.5 Wheel-Legged Chassis

A wheel-legged model is a self-balancing robot: the body rides on two five-bar legs with hub-motor wheels at the feet and balances actively. It differs fundamentally from a mecanum robot:

- **It cannot strafe.** The direction of `move` first turns the chassis onto that course (forward or reverse, whichever is closer), then it drives along its body axis. If you also give `heading`, only the component of `move` along the body axis is driven — the steadiest way to follow a straight lane.
- `leg_height`: Hip-to-axle length, bounded by the selected model’s `leg_min_m`, `leg_max_m`, `leg_nominal_m` and `leg_speed_mps`. It raises or lowers the body and armor.
- `jump`: jump strength 0–1 (`True` means 1). It triggers only with the wheels on the ground with cooldown `jump_cooldown_s`. The legs extend with a thrust of (1 + jump_thrust_gain×strength)×weight and tuck automatically in the air. For the default W3, a full-strength jump lifts the body about 0.4 m and, with the legs tucked, the wheels about 0.5 m — enough to land on the 0.4 m vertical edge of the central highland (take off about 0.5 m from the step at about 2 m/s).
- `lean`: body pitch target (rad, ±0.35, positive leans forward) for accelerating or setting the landing attitude. In the air only small wheel-reaction corrections are possible.
- The leg joint motors do not count toward the referee's chassis power but drain the battery (about 18 W).
- When power is cut (including when destroyed) the legs go limp, balancing stops and the body falls forward or backward while sliding on. After respawning it stands up again if it lies on its front or back.

**Jump ramp** (`sdk.fly_slope_lane(arena, team)` returns the geometry): your jump ramp sits at the end of your highway and is a 17° slope rising toward the centre line. The 0.2 m highway runs straight onto its low end (the lip, 0.203 m, with no kerb in front of it) and the crest is 0.553 m high; in front of the crest is a 0.65 m gap down to the floor, then a 0.2 m landing pad on the tip of the opponent's trapezoid highland. For red: lip at x = 12.55, crest at x = 13.695, landing edge at x = 14.345, lane center y = 14.4; the two jump-ramp buff cards are on the highway before the ramp (x ≈ 10.6) and past the landing pad (x ≈ 16.27). Rails 141 mm wide and 151 mm above the slope flank an 860 mm lane. From the crest to the second card is a highway no-go area: you may enter it only by flying in after running the slope from its low end, and may then stay or drive out; driving in from the floor or the opponent's trapezoid highland is blocked.

- Forward: accelerate along the highway (`power=200`) and drive straight up; no jump is needed. Leaving the crest at about 2.4 m/s or faster clears the gap.
- Reverse: drive from the landing pad toward the ramp at about 2.5 m/s and jump at full strength 0.3–0.4 m before the gap edge (red: about x = 14.65–14.75); you land on the crest and roll down the ramp onto the highway.
- Jump-ramp runs are timing-sensitive: a take-off point or speed that is off drops the robot into the gap or tips it over. Calibrate for your own controller in practice.
- The lip is flush with the highway, so mecanum and other ordinary chassis can drive onto the ramp too; slowly they stall before the crest, and at full speed they tend to tip over on landing, so calibrate the speed yourself.

## 12. Interface Reference

### 12.1 The act Function

```python
def act(observation: dict, state) -> tuple[dict, object]:
    ...
    return actions, new_state
```

- Called every 0.1 s. The match state advances every 0.05 s, so `tick` grows by 2 between decisions; the first call has `tick == 0`.
- `actions` maps slot strings to action dicts, e.g. `{obs["controlled_ids"][0]: action(...)}`. A robot without an action this round gets an empty action (stop, no fire).
- An action stays in effect until the next decision (0.1 s, i.e. 2 match steps).
- `state` is the `new_state` you returned last time, or `None` on the first call. It must be JSON-serializable and at most 32 KiB. Module-level globals also persist within a match, but keeping memory in `state` makes runs easier to reproduce.
- The `random` module is seeded with a fixed seed, so identical inputs give identical results. Do not rely on wall-clock time; use `observation["time"]`.

### 12.2 Observation

| Field | Contents |
| --- | --- |
| `tick`, `time`, `remaining` | Match step, elapsed seconds, remaining seconds |
| `dt`, `policy_dt` | Match step 0.05 s, decision interval 0.1 s |
| `team` | `"red"` or `"blue"` |
| `controlled_ids` | Slots you may control (list of strings) |
| `robots` | Full actual own lineup at match time; slot is the instance ID and model_slot is the hardware model |
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

### 12.3 Visible Enemy Robots

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

### 12.4 Referee Snapshot

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

### 12.5 Action

Build actions with `sdk.action(...)`; it rejects unknown fields before they reach the match. The table lists only the fields your robot can use.

| Field | Value | Applies to | Meaning | If omitted |
| --- | --- | --- | --- | --- |
| `move` | `(vx, vy)` | all | World velocity intent, [−1, 1] | stop |
| `heading` | radians | ground | Chassis heading | turn toward travel |
| `yaw_rate` | rad/s, ±12 | ground | Chassis yaw-rate target (spinning top), overrides `heading` | — |
| `brake` | bool | ground | Brake actively when there is no `move` | `True` |
| `leg_height` | metres, hardware limits | wheel-legged | Leg length | model default |
| `jump` | 0–1 or bool | wheel-legged | Ground-triggered jump; hardware cooldown | no jump |
| `lean` | rad, ±0.35 | wheel-legged | Body pitch target, positive leans forward | 0 |
| `aim` | radians or `None` | all | Turret/camera world yaw | keep current |
| `pitch` | radians | all | Turret/camera world pitch, positive up | 0.04 |
| `fire` | bool | shooters | Fire during this decision | no fire |
| `power` | watts, 0–200 | ground | Chassis power budget | current power cap |
| `profile` | string or dict | hero, infantry | Profile choice, only at `tick == 0` | keep preselection |
| `buy_ammo` | `{"amount": n, "remote": bool}` | hero, infantry | Buy ammo | — |
| `remote_heal` | bool | hero, infantry | Remote healing | — |
| `revive` | bool | ground | Instant revival while dead | — |
| `rune_start` | bool | infantry | Start a power-rune activation | — |

Operations that do not apply to the robot or its current state have no effect; some are recorded in the replay as `invalid_action` events. A misspelled field name disables your whole program; `sdk.action` raises the error early, inside your own code.

### 12.6 SDK

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

### 12.7 Mode D Instance IDs and Messages

`robot["model_slot"]` identifies the hardware model; `robot["slot"]` is the deployment ID. Duplicates have different IDs. `TEAM_SIZE` and `TEAM_SLOTS` are legacy helpers for fixed lineups and do not determine this match's team size. Read the actual lineup from the observation.

```python
from sdk import action, message

def act(obs, state):
    slot = obs["controlled_ids"][0]
    own = next(r for r in obs["robots"] if str(r["slot"]) == slot)
    teammates = [r for r in obs["robots"] if str(r["slot"]) != slot]
    outgoing = [message({"intent": "cover", "model": own["model_slot"]})]
    # Address a teammate with message(data, to=str(teammates[0]["slot"]))
    return {slot: action(messages=outgoing)}, {"teammates": [r["id"] for r in teammates]}
```

Send at most four messages per decision. Each data payload is JSON of at most 512 bytes, and all messages plus physical operations must fit the robot action's total 1 KiB limit. `to="all"` broadcasts to current teammates; a slot string addresses an instance, not a model. Delivery is own-team only; nonexistent destinations receive nothing. Messages arrive once through `obs["messages"]` at the next decision, 0.1 s later, with `from`, `to`, `tick`, `delivery_tick` and `data`. Private state stays isolated and enemy vision is not automatically merged.

## 13. Practice and Submission

Practice varies the teammate count and models. These are practice examples and do not specify the final competition lineup. Adapt using the actual match observation.

## 14. Practice and Submission

Run every command from your workspace:

```bash
python3 -B arena.py status                  # remaining time, submitted versions, practice jobs
python3 -B arena.py test [options]          # start a batch of practice games with the current strategy.py
python3 -B arena.py results JOB_ID           # practice progress and results
python3 -B arena.py replay JOB_ID --game 0   # save the full replay of game 0 into practice/
python3 -B arena.py submit                   # submit the current strategy.py
```

### 14.1 Practice Games

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

### 14.2 Results and Replays

- `results` returns, for each game, the winner, the reason, the end time, which side you played (`candidate_team`), both teams' data (attack damage, kills, coins and more) and how many times your program failed (`policy_errors`). When your program fails, `diagnostics` includes the error and its latest log lines (including `print` output).
- `replay` saves the full replay into `practice/`: the whole-field state at every step, both sides' actions and all events, ready for your own analysis scripts. A 420 s replay is about 300 MB, so download only what you need.

### 14.3 Submitting

- `submit` saves the current `strategy.py` as an immutable version and returns its version id.
- You may submit many times; **your last successful submission before the deadline is your entry**. Earlier versions can be practice opponents (`--opponent VERSION`).
- Before submitting, check that practice showed no errors or timeouts, that nothing depends on files in `practice/`, and that the worst-case decision time is well under 200 ms.
- Do not leave your last submission to the final moment, and never treat practiced-but-unsubmitted code as your entry. After the deadline you can still read existing results and replays, but you can no longer practice or submit.

### Model capabilities

Drive: `wheel_legged`; arms: 0; deployment: unavailable.
Supports `leg_height`, `jump` and `lean`, without direct strafing. Heroes without deployment hardware cannot deploy even with the ranged performance profile.
