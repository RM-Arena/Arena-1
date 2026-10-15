## Starter Code

The `strategy.py` in your workspace is a complete, runnable template (it drives any slot) that you can improve directly. Below is a minimal aerial-only skeleton that illustrates the interface; it is not a strong strategy. It flies while free support time remains or coins are plentiful, heads to the end of the lane nearest the center line, and attacks visible enemies.

```python
from sdk import (action, aim_at, aim_pitch, ballistic_reachable, can_fire, intercept,
                 navigate, nearest_enemy)

RESERVE = 200   # coins left for teammates once free time is used up


def act(obs, state):
    slot = obs["controlled_ids"][0]
    me = next(r for r in obs["robots"] if str(r["slot"]) == slot)
    try:
        command = decide(me, obs)
    except Exception:
        command = action()                     # on error, keep the current state instead of disabling the program
    return {slot: command}, state


def decide(me, obs):
    team = obs["team"]
    coins = obs["teams"][team]["resources"]
    if me["support_time"] <= 0 and coins < RESERVE:
        return action(support=False)           # return to the pad and stop spending
    lane = obs["arena"]["flight_lanes"][team]
    end = lane["max_x"] - 1 if team == "red" else lane["min_x"] + 1
    move = navigate(me, (end, lane["center_y"]), obs["arena"])
    enemy = nearest_enemy(me, obs)
    if enemy is None:
        return action(move=move, support=True, altitude=1.9)
    target = intercept(me, enemy)
    fire = (can_fire(me) and me["heat"] + 20 <= me["max_heat"]
            and ballistic_reachable(me, target))
    return action(move=move, aim=aim_at(me, target), pitch=aim_pitch(me, target),
                  fire=fire, support=True, altitude=1.9)
```

Ideas for improvement: budget support time across the match, help the infantry hit the power rune, pick spots that reveal more enemies, and trade off heat against ammo.
