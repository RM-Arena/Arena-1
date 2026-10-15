## Chassis Physics and Fine Control

Every ground robot is a 120 Hz rigid-body simulation with mass, inertia, suspension, tyre grip and collisions. `move` is only a velocity intent; the actual motion comes from motor force, power and friction. These physical details matter tactically.

### Power Cuts and Momentum

The referee cuts chassis power when a robot is destroyed, during an over-power cut-off (see "Power and Energy") and when the battery is empty. Then `powered == False`:

- The motors neither drive nor brake. The robot **keeps sliding on its momentum**, slowed only by back-driven gearboxes, rolling resistance and whatever it hits. A mecanum chassis decelerates at about 2.2 m/s² (about 2 m from 3 m/s); on slopes steeper than about 12° (such as the 17° jump ramp) an unpowered mecanum robot rolls downhill.
- A destroyed robot stays on the field as a **wreck**: it is still solid, blocks paths, shots and sight lines, and can be pushed. Respawning happens in place and restores power; a tipped robot is still tipped after it respawns.
- A powered robot without `move` brakes actively and holds its position and heading (up to tyre friction). Send `brake=False` to let a powered chassis coast.

### Tipping Over and Righting

- `upright` is the cosine between the body's vertical axis and world vertical (1 is upright); below 0.5, `tipped == True`. A tipped robot's wheels are off the ground and it cannot drive.
- Typical causes: running off the side of a ramp at speed, dropping off a step, a bad jump-ramp landing, collisions.
- The engineer can right a tipped teammate with its arm (the engineer's `rescue` action).{{#c_s3}} A wheel-legged robot stands up by itself after falling on its front or back, but needs the engineer when it lies on its side.{{/c_s3}}

### Fine-Control Fields

| Field | Effect |
| --- | --- |
| `move` | World-frame velocity intent in [−1, 1], scaled by the reference speed |
| `heading` | Chassis heading target; when omitted, a mecanum chassis turns toward its motion |
| `yaw_rate` | Chassis yaw-rate target (rad/s, up to ±12), overriding `heading`. A mecanum robot can translate while spinning (a "spinning top") so enemies cannot keep hitting the same armor plate |
| `power` | Chassis power budget for this decision (0–200 W). Power above the limit is drawn from the supercapacitor; once it is empty the buffer energy starts to drain |
| `brake` | `True` by default; with `False` the chassis does not brake when there is no `move` |

Spinning costs power: torque times angular velocity counts toward chassis power, so watch the limit when spinning for long.

### Road Bumps

- The road south of the kerb (red x 5.25–7.65, blue mirrored) is covered by ten smooth 70 mm humps 240 mm apart. Wheeled robots that climb the 10° slope west of the notch must cross them to reach the east road, the jump ramp and the highland end slopes.
- Wheeled chassis ride 100 mm clear on soft suspension, so the wheels follow the humps while the body stays nearly level: drive straight at full speed and you are over in about 3–5 s. Crawling (especially the heavier dual-arm engineer) can stall between two humps; back off a little and accelerate again.
- Without a `power` field, heroes and infantry with a supercapacitor draw on it automatically while on the humps; an explicit `power` budget takes precedence.
- A wheel-legged chassis lifts both wheels at once, so enter at full speed and keep to the middle of the section; brushing the side kerbs can catch it.
{{#c_s3}}

### Wheel-Legged Chassis

A wheel-legged model is a self-balancing robot: the body rides on two five-bar legs with hub-motor wheels at the feet and balances actively. It differs fundamentally from a mecanum robot:

- **It cannot strafe.** The direction of `move` first turns the chassis onto that course (forward or reverse, whichever is closer), then it drives along its body axis. If you also give `heading`, only the component of `move` along the body axis is driven — the steadiest way to follow a straight lane.
- `leg_height`: Hip-to-axle length, bounded by the selected model’s `leg_min_m`, `leg_max_m`, `leg_nominal_m` and `leg_speed_mps`. It raises or lowers the body and armor.
- `jump`: jump strength 0–1 (`True` means 1). It triggers only with the wheels on the ground with cooldown `jump_cooldown_s`. The legs extend with a thrust of (1 + jump_thrust_gain×strength)×weight and tuck automatically in the air. For the default W3, a full-strength jump lifts the body about 0.4 m and, with the legs tucked, the wheels about 0.5 m — enough to land on the 0.4 m vertical edge of the central highland (take off about 0.5 m from the step at about 2 m/s).
- `lean`: body pitch target (rad, ±0.35, positive leans forward) for accelerating or setting the landing attitude. In the air only small wheel-reaction corrections are possible.
- The leg joint motors do not count toward the referee's chassis power but drain the battery (about 18 W).
- When power is cut (including when destroyed) the legs go limp, balancing stops and the body falls forward or backward while sliding on. After respawning it stands up again if it lies on its front or back.

**Jump ramp** (`sdk.fly_slope_lane(arena, team)` returns the geometry): your jump ramp sits at the end of your highway and is a 17° slope rising toward the centre line. The 0.2 m highway runs straight onto its low end (the lip, 0.203 m, with no kerb in front of it) and the crest is 0.553 m high; in front of the crest is a 0.65 m gap down to the floor, then a 0.2 m landing pad on the tip of the opponent's trapezoid highland. For red: lip at x = 12.55, crest at x = 13.695, landing edge at x = 14.345, lane center y = 14.4; the two jump-ramp buff cards are on the highway before the ramp (x ≈ 10.6) and past the landing pad (x ≈ 16.27). Rails 141 mm wide and 151 mm above the slope flank an 860 mm lane. From the crest to the second card is a highway no-go area: you may enter it only by flying in after running the slope from its low end, and may then stay or drive out; driving in from the floor or the opponent's trapezoid highland is blocked.

- Forward: accelerate along the highway (`power=200`) and drive straight up; no jump is needed. Leaving the crest at about 2.4 m/s or faster clears the gap.
- Reverse: drive from the landing pad toward the ramp at about 2.5 m/s and jump at full strength 0.3–0.4 m before the gap edge (red: about x = 14.65–14.75); you land on the crest and roll down the ramp onto the highway.
- Jump-ramp runs are timing-sensitive: a take-off point or speed that is off drops the robot into the gap or tips it over. Calibrate for your own controller in practice.
- The lip is flush with the highway, so mecanum and other ordinary chassis can drive onto the ramp too; slowly they stall before the crest, and at full speed they tend to tip over on landing, so calibrate the speed yourself.
{{/c_s3}}
