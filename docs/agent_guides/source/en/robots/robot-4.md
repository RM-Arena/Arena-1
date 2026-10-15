## Your Robot: Slot 4 Infantry (Burst)

### Role

Your default launcher is burst-first: at level 1 its heat cap is 170, enough for about 17 rounds in a row, but cooling is only 5/s, so recovering after a full burst takes a long time. Your body is of medium weight, with a 4.2 m/s reference speed.

{{own_hardware}}

- Launcher: 17mm, 25 m/s muzzle speed, minimum firing interval 0.05 s, 10 heat per shot.
- Preselected profile: **power chassis + burst launcher** — level 1 has 150 HP, 60 W, heat cap 170 and 5/s cooling.

{{> robots/infantry}}

### Tips

- Save your heat for the windows that matter: enemies at close range, exposed outpost or base armor, an active rune buff. Do not spend it on targets you cannot hurt.
- Recovery after a burst is slow (half a round per second at level 1). Tunnel crossings (cooling ×2 for 120 s), the large rune's cooling multiplier and your fortress's cooling bonus all help a lot.
- Going over the cap means cooling all the way to 0, and reaching "cap + 100" locks you permanently; with a big heat pool, take extra care not to overshoot.
- If you prefer sustained fire, switch to the cooling launcher at `tick == 0`.
