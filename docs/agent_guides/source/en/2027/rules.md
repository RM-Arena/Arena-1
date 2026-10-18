## Rules

### Shooting and damage

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

### Coins, ammo, healing and respawn

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

### Control Positions and Control Degree

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

### Structures and the fortress

- Bases have 10000 HP; outposts 1000 HP (500 after a rebuild). The outpost's three middle plates rotate with its rotor until 180 s; its top armor deals no damage in 2027.
- The base's three upper plates can always be hit by 17 mm, 42 mm and aerial impacts; its three large plates are exposed only once "opened". **A base's armor opens after enemy robots spend a total of 10 s on its fortress card** (the timer resets after more than 3 s away).
- **Own fortress**: active while your team does not control its own outpost position (the enemy holds it temporarily or fully). One own robot holds the card: 50% defense, a cooling bonus of min(75, ⌊max base HP lost/80⌋), and a reserve of min(500, 100 + ⌊max base HP lost/15⌋) rounds that is spent first when firing from the card (10 reserve units per 42 mm shot).
- **Enemy fortress**: after 180 s, a team that controls the enemy outpost position may activate the enemy fortress card (taking 100% vulnerability). 10 s there opens the enemy base armor, and standing there also advances temporary control of the enemy base position.

### Buff cards and terrain crossings

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

### Tech-Core Assembly

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

### Power Rune

- The rune stands on the gantry at the field center (14, 7.5). Its red and blue faces share one axis and turn together, each with 5 arms (target radius 0.15 m on a 0.7 m arm). Teams activate independently and may only hit the face turned toward them (axis direction in `arena["rune"]["axis_yaw"]`).
- **Infantry or the sentry** start an activation: `rune_start=True` (alive and not weak, anywhere). Only 17 mm counts, with normal speed above 12 m/s; 42 mm has no effect.
- Targets are in `observation["runes"][own]["targets"]` (`arm, x, y, z, radius, lit`); `lit=True` marks the target to hit now. Positions are reported only while an own observer is within vision range. Aim with `dict(target, kind="rune_target")` in `sdk.aim_pitch`.
- Small rune (0–180 s, one chance at 0 s and one at 90 s): hit 5 different lit arms, each within 2.5 s; a wrong hit or timeout resets the progress, and the whole attempt has 20 s. Effect: 25% defense for the team and structures for 45 s, and infantry XP doubles (at most 1200 extra per team).
- Large rune (one chance each at 180, 255 and 330 s): each round lights 2 targets; hit the first within 2.5 s and optionally the second within 1 s more; 5 rounds give 5–10 valid hits. The average ring decides an attack multiplier of 1.5–3, 25–50% defense and cooling ×1–×5 for 30–60 s; living infantry share 750 XP.
- Motion: small runes and large runes outside activation rotate at π/3 rad/s. During a large activation the shared shaft follows a·sin(ωt)+2.090−a; each new large activation resets t, a and ω.
- **2027 shrinking rule**: after your team's first large activation only hits on ring 4 or better (closer to the center) count; after the second, only ring 7 or better (one ring per 1.5 cm from the center, 10 at the center).

### Levels, experience and performance

- **Only infantry gain experience**: 1 per 17 mm shot fired, 4 per HP of robot damage, 2 per HP of outpost damage, 1 per 2 HP of base damage, rounded up for odd damage; a kill gives 50 × victim level × (1 + 0.2 × level gap); first terrain crossings give 300.
- When a damage or kill source cannot gain XP, eligible living infantry below their cap share it according to projectile caliber; non-projectile XP is shared among all eligible infantry. Shares are rounded to one decimal place.
- The infantry level cap starts at 5, becomes 7 after a level-2 assembly and 10 after a level-3 assembly.

{{xp_table}}

- Infantry chassis and launcher profiles can only be chosen with `profile` at `tick == 0` and lock afterwards. Without an explicit selection, all infantry use the HP chassis and cooling launcher. Model recommendations apply only when selected explicitly.

Chassis (HP / power):

{{infantry_chassis_levels}}

Launcher (heat cap / cooling per second):

{{infantry_weapon_levels}}

- The heavy robot uses no experience; its performance rises with assemblies (see "Heavy Robot"). The sentry keeps fixed automatic parameters (400 HP, heat cap 260, cooling 30/s, 100 W) and counts as level 1 when killed.

### Power

- Chassis power caps are listed above. Drawing more first consumes a 60 J buffer; when the buffer is empty the chassis loses power for 5 s. The absolute cap is 200 W.
- 2027 has no 2026 chassis energy pool and no wireless charging.

### Penalties

- The referee only penalizes objectively decidable behavior (for example excess muzzle speed or leaving the field) and never randomly judges intent. A yellow card removes 15% HP from the offender (5% from teammates); three yellow cards send the robot off. A yellow card also cuts the sentry's chassis power for 2 s. An aerial robot leaving the field receives a red card.
