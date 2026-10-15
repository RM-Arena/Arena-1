## Match Overview

### Lineup

Each team fields five robots: the slot 1 heavy robot, slot 3 and 4 infantry, the slot 6 aerial robot system (a hangar plus fully automatic aerial robots) and the slot 7 fully automatic sentry. Robots with the same slot have identical hardware, initial state and rules on both sides. This arena **uses no darts, radar or electronic countermeasures**; none of their rules apply.

{{roster_table}}

- "Ammo" is the number of projectiles a robot may fire. The heavy robot and infantry start with 0 and must buy ammo with coins; the sentry starts with 300 rounds and collects 100 more per minute at its supply zone.
- The heavy robot **starts without a launcher**: it can fire only after its modular 42 mm launcher is unlocked (level-3 assembly or the time rule) and fitted at the workbench.
- Aerial robots cannot be destroyed and can only attack structure armor by ramming it; they have no HP and cannot shoot.

Ground robot hardware (full data in `sdk.DESIGNS`):

{{hardware_table}}

{{aerial_table}}

The reference speed is the drive controller's target; actual speed depends on power, slope, payload and grip. Armor center and muzzle heights are above the ground.

### Field and Coordinates

- The field is 28 m × 15 m with a 2.4 m fence. x runs along the long side from 0 to 28, y along the short side from 0 to 15, z points up; all in meters.
- **Red is on the low-x side, blue on the high-x side.** The field is point-symmetric about (14, 7.5): red's (x, y) corresponds to blue's (28 − x, 15 − y).
- Angles are radians. Heading 0 points along +x, counterclockwise positive (π/2 points along +y).

Key places (red coordinates; mirror for blue):

{{location_table}}

- The central highland is a 0.3 m deck that runs from your outpost side to the field center, with 12° end slopes. On the fortress side a 0.2 m step band and a 0.4 m rim stop ordinary wheeled robots. The 0.4 m assembly plinth and the rune gantry stand in the middle of the deck; the hangar platforms sit above the gantry.
- The trapezoid highland is 0.2 m high (23° slope); the high point is 0.8 m high and reachable only by its three steps (about 0.2 m each), so only step-climbing wheel-legged robots get up; the fortress platform is 0.15 m high (20° slope).
- Roads are 0.2 m high with 11° and 15° entry ramps. The road tunnels have about 0.25 m of clearance: only robots that fold their turret **pass through**; robots that jump or climb steps can **cross over** the roofs. Some road sections carry 0.07 m bumps.
- Forbidden areas: both base bodies, the enemy's supply zone and assembly zone, and the dart stations (no darts are used, but the stations remain solid no-go areas).
- Full geometry is in `observation["arena"]` (the same as `map` in `arena.json`): `terrain` (each `polygon` is the real shape), `obstacles` (walls, possibly with `rotation` and `bottom` for tunnel roofs), `zones` (buff cards), `forbidden`, `navigation` (public road-map nodes), `hangars`, `positions` (control positions), `field_geometry.fixtures` (workbench, resource hub, hangar platforms) and `rune`.
- `sdk.terrain_height(arena, x, y)` returns the ground height; `sdk.navigate(robot, point, arena)` returns a move direction around walls and along ramps. You may also write your own navigation.

### Match Timeline

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

### Winning the Match

- **Only one thing ends a match early: a destroyed base** (the higher remaining base HP wins). Losing all ground robots does not end the match; dead robots can respawn.
- At 420 s the following are compared in order; the first difference decides:
  1. **Control degree** (see "Control Positions and Control Degree");
  2. Team attack damage (effective damage dealt to robots, outposts and bases);
  3. Total remaining HP of living ground robots;
  4. Otherwise a draw.
- Unlike 2026, base HP is not the first timeout criterion; control degree is.
