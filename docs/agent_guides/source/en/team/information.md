## Information and Control

### What You Control

Your program controls all six robots on your side. `observation["controlled_ids"]` lists the slots you may control, as strings such as `"1"` and `"7"`. The keys of your `actions` must come from this list. Do not assume the slots are contiguous, and do not loop over 1–7 to guess them.

### What You Can See

There are two kinds of information.

**Vision (limited by line of sight)**

- `observation["enemies"]` contains only enemy robots **currently seen by at least one of your observers** (wrecks included), with everything their exterior shows: position, velocity, orientation, turret direction, HP, whether they are tipped, arm and leg state and more (see "Interface Reference").
- Observers are your living robots that are not deployed. Vision range: hero 18 m, engineer 15 m, infantry 18 m, aerial robot 24 m. An observer looks from its camera toward the target's body center, turret top and four armor plates; it sees the target if any of those sight lines is not blocked by walls, terrain, structures or other robots (arms and wrecks included).
- `observation["vision"]` lists the robots each observer sees, and each entry of `enemies` has `seen_by` with the slots that see it.
- A deployed hero loses its first-person view and stops being an observer; the aerial robot is an observer only while air support is on.
- Enemy projectiles are visible only within vision; your own projectiles are always visible.
- Power-rune target positions are provided only when one of your observers is within its vision range of the rune center.

**Public information (not limited by vision)**

- Slot, role, HP, max HP and alive state of every robot on both teams (the referee snapshot `referee`);
- HP, armor, shield, ever-destroyed flag and armor rotation of both bases and outposts;
- both teams' attack damage, both teams' tech-core assembly state, and who holds each buff zone;
- full state of all your robots and your team's economy;
- the map, rule parameters and robot designs.

**Hidden**: the opponent's coins, ammo, heat, experience, code and private state; anything about the position of enemy robots you cannot see.

Knowing an enemy's HP is not knowing where it is. The robot list in `referee` has no coordinates — never build aiming targets from it; aim only at entries in `enemies`.

Ground cameras have a {{ground_fov_horizontal}}° horizontal and {{ground_fov_vertical}}° vertical field of view following the actual muzzle direction, with existing range and occlusion limits. Aerial coverage is unchanged. All own positions and referee information remain readable.
