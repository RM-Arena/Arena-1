## Your Robot: Slot 1 Hero

### Role

You are the team's only robot that fires 42mm. A 42mm round deals 200 damage — ten times a 17mm round — and while the opponent's base armor is closed, **only 42mm can damage the base**. The price is heat and ammo cost: at level 1 the ranged profile has a heat cap of only 100 with 20/s cooling, so you can sustain about one shot every 5 s; local ammo costs 10 coins per round, and the team may buy at most 100 rounds per match.

{{own_hardware}}

- Launcher: 42mm, 12 m/s muzzle speed (16.5 m/s when deployed), minimum firing interval 0.2 s, 100 heat per shot.
- A 42mm hit needs more than 10 m/s of normal speed relative to the armor, while your muzzle speed is only 12 m/s: long shots, oblique hits or targets moving away from you easily fall below the threshold.
- You cannot hit power-rune targets and cannot start a rune activation.

### Profile

You start with the ranged profile. Only at `tick == 0` can you switch with `action(profile="melee")` or `action(profile="ranged")`; it is locked afterwards.

| Profile | Level 1 | Character |
| --- | --- | --- |
| Ranged `"ranged"` | 150 HP, 50 W, heat cap 100, cooling 20/s | Can deploy; cools fast |
| Melee `"melee"` | 200 HP, 70 W, heat cap 140, cooling 12/s | Tougher and stronger; cannot deploy; cools slowly |

Per-level values (the level cap depends on the engineer's assembly progress; see "Profiles, Levels and Experience"):

{{hero_levels}}

{{> mechanics/hero}}

### Tips

- Coins arrive at 1 s. Buy 42mm locally in your base or supply zone, e.g. `buy_ammo={"amount": 5, "remote": False}` (50 coins); away from home, buy 10 rounds remotely once disengaged (150 coins, delivered after 6 s).
- Remember that 42mm rounds in flight stop dealing damage once you have not fired for 4 s. With long lobs, keep the gap between shots under 4 s; 3 s after you die, rounds already in the air stop counting too.
- Once deployed you cannot see enemies and `enemies` is empty. Aim at the public structure coordinates, and fire only when `sdk.ballistic_reachable` is true.
- While the opponent's outpost stands, their base is invulnerable, so take the outpost down first.
- Remote healing (disengaged + coins) and the supply zone keep you alive, but coins belong to the whole team.
