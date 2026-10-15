## Information and Control

### What You Control

Your program controls only your slot {{slot}}. `observation["controlled_ids"]` is always `["{{slot}}"]`, and your `actions` may contain only the key `"{{slot}}"`; any other slot disables your program.

### What You Can See

There are two kinds of information.

**Vision (from your own robot only)**

- `observation["enemies"]` contains only enemy robots **your robot can currently see** (wrecks included), with everything their exterior shows: position, velocity, orientation, turret direction, HP, whether they are tipped, arm and leg state and more (see "Interface Reference"). Enemies seen by your teammates do not appear here.
- You look from your camera toward a target's body center, turret top and four armor plates; you see it if any of those sight lines is not blocked by walls, terrain, structures or other robots (arms and wrecks included). `observation["vision"]` also lists the teammates you see.
- Your vision range is {{vision}} m. You see nothing while dead.
{{#hero}}
- Once deployed you lose your first-person view: `enemies` stays empty until you cancel the deployment.
{{/hero}}
{{#aerial}}
- You can see only while air support is on; with support off, `enemies` is empty.
{{/aerial}}
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

Ground cameras have a {{ground_fov_horizontal}}° horizontal and {{ground_fov_vertical}}° vertical field of view following the actual muzzle direction, with existing range and occlusion limits. Aerial coverage is unchanged. All own positions and referee information remain readable.
