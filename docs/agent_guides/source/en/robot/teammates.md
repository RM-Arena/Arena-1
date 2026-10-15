## Your Team

Each of the other five robots on your side runs an independent program written by another participant. You share coins, the base, the outpost, the level cap and team buffs, and can use **messages for team communication**, while code and private state stay isolated and vision is not automatically shared.

### What Your Teammates Do

{{^hero}}
{{> summary/hero}}
{{/hero}}
{{^engineer}}
{{> summary/engineer}}
{{/engineer}}
{{> summary/infantry}}
{{^aerial}}
{{> summary/aerial}}
{{/aerial}}

### Working Together

- **Read teammate state**: `observation["robots"]` holds each teammate's full public state, such as position, HP, ammo, heat, level, whether it is alive, `carried_units` (energy units the engineer carries), `deployed` (whether the hero is deployed) and `support_active` (whether air support is on).
- **Read economy events**: your team's events in `referee["events"]` carry a `robot` field, so you can see who bought ammo and who leveled up.
- **Coins are shared**: teammates also buy ammo, heal remotely and revive instantly, and air support costs coins every second once its free time runs out. Do not assume the balance is yours; think about what teammates may need before spending.
- **Settlement order**: when several robots spend at the same moment, requests settle in slot order 1→2→3→4→6→7. A request the balance cannot cover simply fails — no charge, no error.
- **Vision is not shared**: enemies your teammates see do not automatically appear in your `enemies`; teammates can report observed positions and intentions through messages. Changes in enemy HP in the referee snapshot, destruction broadcasts and teammates losing HP still hint at where the fighting is.
- **Do not bet everything on one teammate**: a teammate's program may behave erratically or even be disabled by an error. Your strategy should work on its own.
