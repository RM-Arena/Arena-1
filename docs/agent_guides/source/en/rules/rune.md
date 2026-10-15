## Power Rune

The power rune stands at the center of the field (14, 7.5), its hub about 3.0 m high, on a gantry above the assembly pedestal. It has **a red face and a blue face** on one shaft that turn together: the red face looks toward the red half and the blue face toward the blue half, each 0.35 m from the shaft center (shaft direction: `arena["rune"]["axis_yaw"]`). When the red face turns clockwise seen from red, the blue face turns counter-clockwise seen from blue. Each face has 5 arms, each ending in a round target of radius 0.15 m that rotates around the hub at a radius of 0.7 m. Each team activates its own face independently and can only hit the face turned toward it.

- Both small and large runes turn at smoothly varying, irregular speeds while idle, during activation and while buffs are active. Both faces stay synchronized on the same shaft; activation does not reset its speed. Current `angular_velocity` (rad/s) and `angular_acceleration` (rad/s²) are visible under the same range restriction as target positions. Aim must account for speed changes during projectile flight.

- **Only infantry can start an activation**: send `rune_start=True` (alive and not weakened; position does not matter).
- **Only 17mm counts**, from infantry or the aerial robot. 42mm hits are ignored and earn nothing.
- A projectile's horizontal speed along the rune's axis must exceed 12 m/s.
- Targets are in `observation["runes"][your team]["targets"]`; each has `arm, x, y, z, radius, lit`, and `lit=True` marks the target to hit now. Target positions are provided only while one of your observers is within vision range.
- The activation state is `runes[your team]["status"]`: `idle`, `activating` or `active`. You cannot start again while the buff is `active`.
- When aiming, pass `dict(target, kind="rune_target")` to `sdk.aim_pitch` so it treats the target as an exact point instead of adding an armor height.

### Small Rune (0–180 s)

- Chances: one at kickoff and another at 90 s. Unused chances do not carry over to the large-rune phase.
- After starting, one target lights up and must be hit within 2.5 s; then another arm that has not yet been hit lights up. Hitting **5 different arms** in turn activates the rune.
- A wrong target, or 2.5 s without a hit, resets progress to the beginning. The whole attempt is limited to 20 s; after that the chance is lost.
- Effect: your robots, base and outpost get **25% defense** for 45 s, and XP earned during that time is doubled (at most 1200 extra XP for the team).

### Large Rune (from 180 s)

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
