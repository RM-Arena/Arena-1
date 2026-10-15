## Movement, Chassis Power and Energy

### Movement and Turret

- `move=(vx, vy)` is a velocity intent in **world coordinates**, each component in [−1, 1]; vectors longer than 1 are scaled down to 1. Target velocity = intent × the robot's reference speed (`speed_reference_mps`).
- Robots are rigid bodies with mass, inertia, suspension and tire friction: accelerating and braking take time, sharp turns slide, slopes slow you down, and robots can get airborne or tip over. **Brake early**; never assume an instant stop, and do not try to drive straight over a step.
- `heading` sets the chassis heading in radians; when omitted, the chassis turns toward its direction of travel. The heading determines which way the four armor plates face.
- `aim` is the turret's horizontal angle in world coordinates and `pitch` its world elevation (positive up). The turret turns at a limited rate, its pitch is limited to −15° … +45° relative to the chassis, and it compensates for chassis tilt automatically. `aim=None` keeps the current direction.

### Chassis Power

- Each ground robot has a chassis power cap, `power_limit`, that depends on role, level and profile.
- The `power` action field (watts, 0–200) is this decision's power budget and defaults to the current cap. Any budget above the cap is drawn from a **buffer**: the buffer holds 60 J and is settled every 0.1 s as `buffer −= (actual power − cap) × 0.1`.
- If the buffer is empty and power is still over the cap, the **chassis is cut off for 5 s** and cannot move.
- For 4 s after an instant revival the power cap is doubled (at most 200 W).

### Chassis Energy (Hero and Infantry)

- Chassis energy `energy` starts at 20 000 J with a cap of 40 000 J. Each joule the chassis outputs costs one joule; driving at a steady 60 W drains it in about 330 s.
- When energy runs out, the power cap drops to 35 W; at 25 000 J or more, the power cap rises to 125% (at most 200 W).
- Recharging: park still (below 0.08 m/s) at your charging dock. It supplies 100 W, credited to chassis energy at 8 × the net input, i.e. about `8 × (100 − chassis power)` J/s. The dock stands inside your supply zone; `arena["charging_docks"]` gives its `transmitter` center and the `normal` it faces. The receiver at the center of your chassis front must face the transmitter (your heading opposite to `normal`, within about 11°) and lie within 3 cm of the point `transmitter + 0.24 × normal`, so your chassis center sits half a chassis length (`chassis_size_m[0] / 2`) further along `normal`. Red's transmitter is at (0.94, 12.10) facing +x: face −x with your center near x = 1.18 + half the chassis length, y = 12.10.
- The engineer and the aerial robot do not use chassis energy.

The physical battery `battery_remaining_wh` and the supercapacitor `supercap_energy_j` are hardware state, settled separately from the chassis energy above.
