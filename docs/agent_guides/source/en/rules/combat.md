## Shooting and Damage

### Launchers

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

### What Counts as a Hit

Every ground robot has 4 armor plates facing the front, back, left and right of its chassis, tilted upward (75° from straight up). HP is lost only when all of the following hold:

1. the projectile strikes an armor plate — hits elsewhere on the body do no damage and are simply blocked;
2. the projectile's normal speed relative to the plate exceeds the threshold above — long shots, glancing hits or shots chasing a fleeing target may fall short;
3. the minimum interval since that plate's previous valid hit has passed;
4. the target is alive and not invulnerable.

42mm also depends on the hero's state: **once the hero has not fired for 4 s in a row, or has been dead for 3 s, your 42mm rounds still in flight no longer deal damage**.

### Damage Formula

```text
damage = round( base damage × attack buff × (1 − defense buff + vulnerability) )
```

- Base damage is 20 for 17mm and 200 for 42mm. The attack buff defaults to 1 and comes from sources such as the power rune.
- Buffs of the same kind do not stack; **the largest applies**. With both a 25% and a 50% defense buff, 50% is used.
- A single hit never deals more than the target's remaining HP.
- Hitting the 10 mm × 10 mm weak spot at the center of a base or outpost armor plate gives an attack buff of at least 1.5.

### Heat

While overheating remains above zero, this robot’s vision range is 35% of normal. It recovers at zero; public referee health remains available. This disclosed sensor proxy represents reduced FPV visibility. `vision[slot]` reports `range_m` and `fpv_dimmed`.

- Each shot adds heat (17mm +10, 42mm +100). Every 0.1 s heat drops by "cooling × 0.1", where cooling is per second.
- **Heat above the cap locks the launcher**; it unlocks only after cooling all the way to 0.
- Reaching "cap + 100" (17mm) or "cap + 200" (42mm) locks the launcher **for the rest of the match**.
- Heat cap and cooling depend on level and profile; see {{#team}}"Appendix: Level Tables"{{/team}}{{#robot}}"Your Robot"{{/robot}}.
- `sdk.can_fire(robot)` checks alive, weakened, lock, ammo, and whether one more shot would exceed the cap. Because 17mm may fire 2 rounds per decision, infantry and the aerial robot should fire only when `heat + 20 <= cap`.
