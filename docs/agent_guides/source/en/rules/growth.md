## Profiles, Levels and Experience

### Choosing a Profile

The hero and the infantry each start with a preselected profile. It can be changed **only on the first decision (`tick == 0`)** and is locked afterwards.

| Role | Options | Preselected |
| --- | --- | --- |
| Hero | `"ranged"` / `"melee"` | Selected model’s `hero_profile` |
| Infantry chassis | `"hp"` (HP first) / `"power"` (power first) | Selected model’s `chassis_profile` |
| Infantry launcher | `"cooling"` (cooling first) / `"burst"` (burst first) | Selected model’s `weapon_profile` |

```python
action(profile="melee")                               # hero
action(profile={"chassis": "hp", "weapon": "burst"})  # infantry; either key may be given alone
```

- The engineer and the aerial robot have no profile choice.
- Only a ranged hero with deployment hardware can deploy. A melee hero has more HP, power and heat cap, but cools more slowly.
- Per-level numbers are in {{#team}}"Appendix: Level Tables"{{/team}}{{#robot}}"Your Robot"{{/robot}}; full data is in `sdk.RULES["profiles"]`. The steps are not always even — for example, the cooling-first infantry launcher has a heat cap of 114 at level 9.

### Levels and Experience

Robots start at level 1 and level up when their total experience (XP) reaches:

{{xp_table}}

- The level cap starts at **5**. It rises to **7** when the engineer first completes a level-2 assembly and to **10** when it first completes a level-3 assembly. XP stops accumulating at the current cap.
- Leveling up raises max HP, chassis power, heat cap and cooling (depending on role and profile); the increase in max HP is added to current HP at once. The aerial robot's levels only raise its heat cap and cooling.
- The engineer earns no XP and stays at level 1.

XP sources (earned only while alive):

| Action | XP |
| --- | --- |
| Firing one 17mm / 42mm round | 1 / 10 |
| Each point of damage to a robot | 4 |
| Each point of damage to an outpost | 2 |
| Each point of damage to a base | 0.5 |
| Destroying a robot | `50 × victim level × (1 + 0.2 × max(victim level − your level, 0))` |
| First trigger of each terrain-crossing type | 300 |
| Each damaging hit by a deployed hero | 100 extra |
| Power rune | see "Power Rune" |
