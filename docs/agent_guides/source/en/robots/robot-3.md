## Your Robot: Slot 3 Infantry (Wheel-Legged)

### Role

You are a self-balancing wheel-legged infantry: the body rides on two five-bar legs with hub-motor wheels and stays upright by active balancing. You can change your leg length, jump onto 0.4 m steps and run the jump ramp — even in reverse — so you cross terrain better than any teammate. The price: you cannot strafe, and you fall over when you are destroyed and lose power. Default HP is 150.

{{own_hardware}}

- Launcher: 17mm, 25 m/s muzzle speed, minimum firing interval 0.05 s, 10 heat per shot.
- Preselected profile: **power chassis + cooling launcher** — level 1 has 150 HP, 60 W, heat cap 40 and 12/s cooling.
- Legs 0.12–0.34 m (default 0.20 m); armor center height follows them: 0.28 m + (leg length − 0.20 m). Full parameters in `sdk.DESIGNS["3"]`.

{{> robots/infantry}}

### Tips

- You steer like a differential drive: turning takes time, so slow down before sharp turns. When following a lane, also send `heading` and correct small lateral offsets with small heading changes rather than a sideways `move`.
- Jumping lets you reach high ground and cross gaps along routes nobody else can use; calibrate take-off point, speed and strength in practice (see "Chassis Physics and Fine Control").
- Shorter legs lower your armor and prepare a jump; longer legs let you look and shoot over low cover.
- 150 HP is not made for long head-on duels. Use the defense of buff zones and terrain crossings, and hit and retreat.
- You fall when destroyed; if you land on your side, the engineer must right you with `rescue`, or you still cannot drive after respawning.
