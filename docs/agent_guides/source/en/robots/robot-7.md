## Your Robot: Slot 7 Infantry (Steady)

### Role

You are the toughest of the three infantry robots: the HP chassis by default (200 HP at level 1), a low center of mass, stronger tire grip and brakes, and armor centered only 0.175 m above the ground. You are also the only robot that can **lower its turret**. The price is lower power (45 W at level 1) and a 3.8 m/s reference speed.

{{own_hardware}}

- Launcher: 17mm, 25 m/s muzzle speed, minimum firing interval 0.05 s, 10 heat per shot.
- Preselected profile: **HP chassis + cooling launcher** — level 1 has 200 HP, 45 W, heat cap 40 and 12/s cooling.

### Lowering the Turret

- Add `crouch=True` to an action to lower the turret: the muzzle drops from 0.45 m to 0.185 m and movement speed is halved. The `crouched` field shows the current state.
- **Send `crouch=True` in every action to stay lowered**; when it is omitted the robot tries to stand up. Without enough room above, it stays lowered until there is room.
- A lower muzzle changes both trajectories and sight lines; `sdk.aim_pitch` uses the current muzzle height.

{{> robots/infantry}}

### Tips

- High HP and strong grip suit holding ground: your fortress, the central highland, the area around the outpost, and the 10 s stay needed to rebuild the outpost.
- Low power means slow acceleration; plan routes ahead and avoid long exposure in open ground.
- Lowering the turret makes the body shorter, so you can pass under lower clearances, but your speed is halved — use it when it pays off.
- The cooling launcher suits sustained pressure; keep `heat + 20 <= cap` while firing continuously.
