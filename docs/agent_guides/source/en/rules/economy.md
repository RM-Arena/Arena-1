## Coins, Ammo, Healing and Revival

### Coins

Coins belong to the whole team. `observation["teams"][your team]["resources"]` is the current balance; the opponent's balance is hidden.{{#robot}} Your teammates spend from the same balance.{{/robot}}

- **Scheduled income**: 400 at 1 s; 50 each at 61, 121, 181, 241 and 301 s; 150 at 361 s — 800 in total.
- **Tech income**: every successful tech-core assembly by the engineer adds a payment to the team every 10 s, and these add up (see {{#c_engineer}}"Engineer: Energy Units and Tech-Core Assembly"{{/c_engineer}}{{^c_engineer}}"Your Team"{{/c_engineer}}).
- **Spending**: buying ammo, remote healing, instant revival, and air support beyond its free time.

### Buying Ammo

Ground robots start with 0 ammo and **must buy ammo before they can shoot**. Only the hero (42mm) and infantry (17mm) can buy; the aerial robot's 750 rounds cannot be refilled, and the engineer uses no ammo.

| Method | 17mm | 42mm | Condition | Delivery |
| --- | --- | --- | --- | --- |
| Local | 10 coins per 10 rounds | 10 coins per round | In (or left within the last 2 s) your base, your supply zone, or an outpost buff zone you may hold; not weakened | Immediate |
| Remote | 150 coins per 100 rounds | 150 coins per 10 rounds | Disengaged | After 6 s |

- The amount must be a whole multiple of the method's batch, e.g. 10, 20 or 50 rounds of local 17mm, or 100 or 200 rounds of remote 17mm; anything else is ignored.
- Each team has a total purchase cap for the match: **1000 rounds** of 17mm (shared by all three infantry) and **100 rounds** of 42mm.
- A failed request costs nothing and reports no error; check your ammo and balance to see whether it worked.

```python
action(buy_ammo={"amount": 50, "remote": False})   # infantry buys 50 rounds locally for 50 coins
action(buy_ammo={"amount": 10, "remote": True})    # hero buys 10 rounds remotely for 150 coins, delivered after 6 s
```

**Disengaged**: the robot is alive and has gone **6 s in a row without firing and without taking damage**. Merely standing still does not make a robot disengaged.

### Healing

- **Supply zone**: your ground robots in your supply zone recover 10% of max HP per second; after 240 s, a robot that is also disengaged recovers 25% per second.
- **Remote healing** (hero and infantry only): while disengaged, send `remote_heal=True`. It costs `50 + ceil(elapsed_seconds / 60 × 20)` coins and, 6 s later, restores 60% of the max HP at that moment. The price rises continuously, not once per minute. Dying while waiting cancels it without refund; only one remote heal can be pending at a time.
- **Leveling up**: any increase in max HP is added to current HP immediately.
- The engineer cannot heal teammates.

### Death and Revival

A ground robot dies when its HP reaches 0: heat and the power buffer reset to zero, and it loses all zone buffs and any pending remote heal. The aerial robot never dies.

**Natural respawn**

- Required progress = `round(10 + elapsed_seconds_at_death / 10 + 20 × instant revives this robot has used)`, in seconds.
- Progress grows by 1 per second, or by 4 per second if the robot died inside your supply zone or your base HP is **below** 2000. See `respawn_progress` / `respawn_required`.
- The robot respawns where it died, keeps its level and experience, has 10% HP, becomes **weakened**, and is invulnerable for up to 30 s.
- A weakened robot cannot shoot, receive zone buffs, buy ammo locally, rebuild the outpost or start the power rune, and a weakened engineer cannot assemble. Returning to your base, your supply zone or an outpost buff zone you may hold clears the weakened state, and the invulnerability ends with it.

**Instant revival**: a dead ground robot sends `revive=True`

- Costs `ceil(elapsed_seconds / 60) × 80 + level × 20` coins;
- full HP, level and experience kept, not weakened, 3 s of invulnerability; for the next 4 s the chassis power cap is doubled (at most 200 W);
- each use adds 20 s to that robot's future natural-respawn progress requirement.

`sdk.remote_heal_cost(seconds)` and `sdk.instant_revive_cost(robot, seconds)` compute these prices.
