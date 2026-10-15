## Match Overview

### Lineup

Each team has six robots. Robots with the same slot number have identical hardware, starting state and rules on both teams. Slot numbers are labels and are not contiguous (there is no slot 5).

{{roster_table}}

- "Ammo" means the number of projectiles a robot is allowed to fire. Ground robots start with 0 and must buy ammo with coins before they can shoot (see "Coins, Ammo, Healing and Revival").
- The three infantry robots follow exactly the same rules; only their hardware and default profiles differ (see "Profiles, Levels and Experience").
- Starting HP assumes the default profile, which you may change at the start.

Hardware of each robot (full data in `sdk.DESIGNS`):

{{hardware_table}}

The reference speed is the drive controller's target; the speed you actually reach depends on power, slope, load and grip. Armor center height and muzzle height are measured from the ground.

### Field and Coordinates

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

### Match Timeline

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

### Winning the Match

- **A match ends early in exactly one case: a base is destroyed.** Losing all ground robots does not end the match — dead robots can respawn.
- When 420 s run out, compare the following in order; the first difference decides the winner:
  1. remaining base HP (virtual shield excluded);
  2. whether the outpost was **never destroyed** — if only one team's outpost was ever destroyed, the other team wins;
  3. if neither outpost was ever destroyed, remaining outpost HP;
  4. team attack damage (total effective damage dealt to robots, outposts and bases);
  5. total remaining HP of living ground robots;
  6. if still equal, the match is a draw.
- "Ever destroyed" is permanent; rebuilding the outpost does not erase it. If both outposts were ever destroyed, comparison jumps straight to item 4.
