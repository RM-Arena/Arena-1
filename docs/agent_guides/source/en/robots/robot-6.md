## Your Robot: Slot 6 Aerial Robot

### Role

You cannot be attacked and you never die. You have the longest vision on the field (24 m) and 750 rounds of 17mm on board, but you can only fly inside a lane along one side of your half, and only while air support is on; once the free support time is used up, you cost the team 1 coin per second.

{{own_hardware}}

- Launcher: 17mm, 25 m/s muzzle speed, minimum firing interval 0.05 s, 10 heat per shot.
- Level 1 has a heat cap of 100 and 20/s cooling, both rising with level; you earn XP too (while support is on).

Per-level values (the level cap depends on the engineer's assembly progress; see "Profiles, Levels and Experience"):

{{aerial_levels}}

{{> mechanics/aerial}}

### Tips

- Free support time totals 150 s per match (30 s at kickoff, then 20 s more every 60 s). After that each second costs 1 coin from the same balance your teammates use for ammo and revivals; decide when to fly from `support_time` and the coin balance.
- Your vision serves only you: teammates do not get the enemies you spot.
- Once the 750 rounds are gone there are no more. Heat is your main limit; keep `heat + 20 <= cap` while firing continuously.
- The lane runs along the edge of your half up to the center line; from there you can reach enemies near the center line, targets around the enemy outpost, and the power rune. Check `sdk.ballistic_reachable` before firing.
- You cannot fire near the landing pad; take off before engaging.
