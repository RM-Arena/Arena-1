## Information and Control

### What you control

{{#team}}{{^distributed}}
Your program controls all five of your robots. `observation["controlled_ids"]` lists the slots you may control (strings such as `"1"` and `"7"`). Only those slots may appear as keys in `actions`. Do not assume consecutive slots.
{{/distributed}}{{/team}}
{{#distributed}}
You edit five strategies during development; in a match each process mounts only its own source (named `strategy.py` in the container). The five sources cannot import each other or share module variables or `state`. Each `act` has only its own slot in `controlled_ids`; returning another slot disables that process, and one failing process does not disable the other four.
{{/distributed}}
{{#robot}}
Your program controls only your slot {{slot}}. `observation["controlled_ids"]` is always `["{{slot}}"]`, and `actions` may only contain the key `"{{slot}}"`; any other slot disables your program. Other participants' independent programs control your four teammates: you share coins, base, control positions and team buffs and can talk through `messages`, but you cannot see each other's code or private state, and vision is not shared automatically.
{{/robot}}

### What you can see

**Visual observation (limited by sight)**

- `observation["enemies"]` contains only enemy robots (wrecks included) currently seen by at least one own observer{{#independent}} controlled by this process{{/independent}}, with everything their exterior shows.
- Observers are your living ground robots. Vision range: heavy 18 m, infantry 18 m, sentry 20 m. **The hangar has no camera and the aerial robots send no video**, so slot 6 provides no vision. An observer looks from its camera at the target's chassis center, turret top and four armor plates; the target is seen when any line of sight is clear of walls, terrain, structures and other robots and lies inside the camera frustum.
- Ground cameras cover {{ground_fov_horizontal}}° horizontally and {{ground_fov_vertical}}° vertically and turn with the real muzzle direction.
- `observation["enemy_drones"]` lists enemy aerial robots your observers see (position, velocity, state).
- Enemy projectiles are visible only in sight; your own are always visible. Rune targets are reported only while an own observer is within vision range of the rune center.

**Public information (not limited by sight)**

- Slot, role, HP, max HP and alive state of every robot on both teams (the `referee` snapshot, without positions);
- HP, owner, armor state and destruction history of both bases and outposts;
- Controller and progress of the four control positions (`positions`) and both teams' control degree (`referee["control"]`);
- Both teams' attack damage, both teams' assembly states and buff-card occupancy;
- The full state of all your robots (aerial robots included) and your economy (including the logistics factor `referee["logistics"]`);
- The map, rule parameters and robot designs.

**Hidden**: the enemy's coins, ammo, heat, experience, code and private state, and anything about the position of enemy robots you cannot see. Aim only with `enemies`{{#independent}} or intelligence your teammates send{{/independent}}.
