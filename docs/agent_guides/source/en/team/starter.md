## Starter Code and Strategy Tips

The `strategy.py` in your workspace is already a complete, runnable template that buys ammo, revives, assembles tech cores, flies air support and attacks structures; you can improve it directly. The minimal skeleton below only illustrates the interface and is not a strong strategy:

```python
from sdk import action, aim_at, aim_pitch, can_fire, nearest_enemy


def act(obs, state):
    actions = {}
    for robot in obs["robots"]:
        slot = str(robot["slot"])
        if slot not in obs["controlled_ids"]:
            continue
        try:
            actions[slot] = decide(robot, obs)
        except Exception:
            actions[slot] = action()        # on error, hold still instead of disabling the program
    return actions, state


def decide(robot, obs):
    if robot["role"] == "aerial":
        return action(support=True, altitude=1.9)
    if not robot["alive"]:
        return action(revive=True)          # does nothing without enough coins
    if robot["role"] == "engineer":
        return action()                     # replace with the template's pickup and assembly logic
    enemy = nearest_enemy(robot, obs)
    if enemy is None:
        return action()
    spare_heat = robot["role"] == "hero" or robot["heat"] + 20 <= robot["max_heat"]
    return action(aim=aim_at(robot, enemy), pitch=aim_pitch(robot, enemy),
                  fire=can_fire(robot) and spare_heat)
```

**Strategy tips**

- Get the economy going first: buy ammo right after coins arrive at 1 s, and have the engineer finish level 1 early and climb the levels. Tech income is the largest source of coins, and the level cap depends on it as well.
- The base decides the match first, the outpost second. Do not chase unrelated kills at the cost of protecting your outpost or attacking the opponent's structures.
- While the opponent's base armor is closed only 42mm hurts it, so the hero — especially when deployed — is your main base attacker.
- Free air-support time is limited and costs coins per second afterwards; save it for the moments that matter.
- Watch heat and ammo to avoid a permanent lock, and watch the power buffer to avoid a cutoff.
- Practice on several seeds with `--swap-sides`, so your strategy does not only work on one side or one seed.
