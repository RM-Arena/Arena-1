### Aerial Robot: Air Support

The aerial robot (slot 6) takes no damage, never dies, and does not take part in zone buffs, revival or outpost rebuilding. It counts as "alive" only while **air support is on** (`alive == support_active`): then it can fly, shoot, see and earn XP.

**Support time and cost**

- You get 30 s of free support at kickoff and 20 s more at 60, 120, 180, 240, 300 and 360 s; unused time accumulates (`support_time`). That is 150 s of free time per match.
- After the free time is used up, support costs 1 team coin per second; when coins run out, support switches off automatically.
- With support off, the aerial robot flies back to your landing pad and lands, spending neither time nor coins.

**Flight**

- `support=True` turns support on and takes off; `support=False` turns it off; omitting the field keeps the current state.
- `move=(vx, vy)` controls horizontal motion at a reference speed of 3 m/s. `altitude` is the target **absolute height** in meters, 1.85 m by default while support is on.
- The aerial robot hangs from a 2.4 m safety tether on a 3.9 m high rail along the field edge, so it can only move within **your flight lane**: red x ∈ [0.3, 14], blue x ∈ [14, 27.7], and no more than about 2 m sideways from the lane center line (red y = 1.85, blue y = 13.15); see `arena["flight_lanes"]`.
- Altitude is clamped between "1.5 m above the ground" and 2.08 m. Commands beyond these limits are clipped — do not keep pushing against a boundary.
- It cannot fire near the landing pad (within 0.6 m of the pad center and below 1.5 m).

**Firepower**

- Only **750 rounds** of 17mm for the whole match; they cannot be bought or refilled. Heat cap and cooling grow with level (see the level table).
- No profile choice.
- Its 17mm rounds can hit your team's power-rune targets (an infantry robot must start the activation).

```python
action(support=True, altitude=1.9, move=(1, 0), aim=yaw, pitch=pitch, fire=True)
action(support=False)   # return to the landing pad and pause support
```
