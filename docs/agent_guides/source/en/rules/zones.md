## Zone Buffs and Terrain Crossings

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

### Fortress

**Your fortress** (enabled once your outpost has been destroyed; if several infantry are inside, only the lowest slot benefits)

- 50% defense;
- cooling bonus: cooling is at least `base cooling + min(75, floor(base HP lost / 40))`;
- reserve ammo: an extra team pool with capacity `min(500, 100 + 2 × floor(base HP lost / 15))`, topped up as your base loses HP. The infantry holding the fortress fires from the reserve first, so it can shoot even with 0 ammo of its own (`sdk.can_fire` only looks at the robot's own ammo and ignores the reserve). Base healing reduces capacity and clips excess reserve; leaving and re-entering does not create a fresh reserve. The remaining reserve is `teams[your team]["fortress_ammo"]`.

**Enemy fortress** (capturable after 180 s while the enemy outpost is down; infantry only)

- The holder takes **100% vulnerability** — double damage;
- after 20 s of valid occupation, the enemy base armor opens. Loss of occupation or death pauses the timer for up to 3 s; re-entry after that cannot restore old progress.

### Terrain Crossings

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
