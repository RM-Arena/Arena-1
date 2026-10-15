## Base and Outpost

| Structure | HP | Key points |
| --- | ---: | --- |
| Base | 5000 | Lose it and you lose. Invulnerable while your outpost stands (HP > 0) |
| Outpost | 1500 | Three rotating armor plates; once destroyed, your base loses its protection |

Only the armor of either structure takes damage, under the same conditions as robot armor (normal-speed threshold, minimum interval per plate). Both also receive your team's defense buffs (tech cores, power rune).

### Base Armor

- The base armor starts closed. **While it is closed, only 42mm can damage the base** (by hitting the raised target area).
- When base HP falls to **2000 or less**, the armor opens and 17mm can damage the base too (another way to open it is described under "Fortress"). Once open, it never closes again.
- The base's virtual shield (from the level-4 tech core) absorbs damage before HP.

### Outpost Armor Rotation

- The armor starts rotating at kickoff and reaches 0.8π rad/s within 5 s.
- It stops when any of these happens, turns back to its initial orientation within 10 s, and never rotates again: this outpost is destroyed for the first time; the opponent's base armor opens; the match reaches 180 s.

### Rebuilding the Outpost

- Every 1000 HP of cumulative damage to your base grants one rebuild credit (`teams[your team]["rebuild_credits"]`).
- Before 300 s, while your outpost is destroyed, a hero or infantry robot that stays in your outpost zone for 10 s **in a row** (an engineer needs only 5 s) spends one credit and rebuilds the outpost to 750 HP. Leaving the zone resets the timer; a weakened robot cannot rebuild.
- While rebuilding, `outposts[your team]["rebuild"]` contains the robot ID, `elapsed`, `required` seconds and `progress` (0–1); otherwise it is `None`. With several builders, the display shows the highest completion fraction without combining their progress. Progress bars appear above the outpost and in the data panel. Leaving the zone, dying or becoming weakened resets that robot's timer.
- A rebuilt outpost protects the base again, but the "ever destroyed" record stays (it matters for tiebreaker 2).

### Aiming at Structures

`sdk.aim_at` and `sdk.aim_pitch` accept structures directly as targets and choose the target height from the armor state:

```python
enemy = "blue" if obs["team"] == "red" else "red"
outpost = dict(obs["outposts"][enemy], kind="outpost")   # outposts need kind="outpost"
base = obs["bases"][enemy]
```

Without `kind="outpost"`, `aim_pitch` computes an outpost target at the wrong height.

Closed, the base's three corner shells form a pyramid that meets at a narrow slit in the middle of each face. Opening swings the half-shell on each side of the slit about 66° outward on its corner hinge, exposing that face's lower large panel, centred 0.287 m above the pedestal and tilted 15° upward (figure 4-11). Both calibres can attack these panels from outside the forbidden pedestal; opening takes about 1.5 s (`armor_open_progress`) and the shells block shots at every intermediate angle. The outpost's three rotating panels sit at different heights, 1.116 / 1.216 / 1.316 m above its base (figure 4-32), and each keeps its height while turning; its top 42mm module is at 1.5 m. Covers, supports and foundations stop shots. Only finite `armor_plates` register damage; each publishes `center`, `normal`, width, height and calibre restrictions. These unlabelled centers and motion timings are public reconstructed simulation parameters. The SDK aims at a panel facing the shooter. Top small base and outpost modules accept 42mm even after opening, without a center weak-spot bonus.
