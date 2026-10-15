### What Infantry Can Do

The three infantry robots (slots 3, 4 and 7) follow exactly the same rules; only their hardware and default profiles differ. Infantry provide most of the 17mm firepower, and two things are infantry-only:

- **Starting the power rune**: send `rune_start=True`, then hit the lit targets in turn with 17mm (see "Power Rune").
- **Holding a fortress**: after your outpost is first destroyed, holding your own fortress gives 50% defense, a cooling bonus and reserve ammo; after 180 s, while the enemy outpost is down, holding the enemy fortress opens the enemy base armor (see "Fortress").

Like the hero, you can also buy ammo, heal remotely, hold the central highland, and rebuild the outpost by staying in your outpost zone for 10 s in a row. The 17mm purchase allowance (1000 rounds per match) is shared by all three infantry.

### Profile

You can switch only at `tick == 0`; it is locked afterwards:

```python
action(profile={"chassis": "hp", "weapon": "burst"})   # either key may be given alone
```

| Option | Level 1 | Character |
| --- | --- | --- |
| Chassis `"hp"` (HP first) | 200 HP, 45 W | Tougher, less power |
| Chassis `"power"` (power first) | 150 HP, 60 W | Better acceleration and sustained mobility |
| Launcher `"cooling"` (cooling first) | heat cap 40, cooling 12/s | Sustained fire (about 1.2 rounds per second) |
| Launcher `"burst"` (burst first) | heat cap 170, cooling 5/s | About 17 rounds in one burst, then a very slow recovery |

Per-level values (the level cap depends on the engineer's assembly progress; see "Profiles, Levels and Experience"):

{{infantry_chassis_levels}}

{{infantry_weapon_levels}}
