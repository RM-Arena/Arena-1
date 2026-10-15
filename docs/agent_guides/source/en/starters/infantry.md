## Starter Code

The `strategy.py` in your workspace is a complete, runnable template (it drives any slot) that you can improve directly. Below is a minimal infantry-only skeleton that illustrates the interface; it is not a strong strategy. It returns to the base to buy ammo when low, then closes in on the enemy outpost (the base once the outpost is down), preferring visible enemies as targets.

```python
from sdk import (action, aim_at, aim_pitch, ballistic_reachable, can_fire, distance,
                 intercept, navigate, nearest_enemy)

PROFILE = {{profile_code}}   # slot {{slot}}'s preselected profile; only applies at tick == 0


def act(obs, state):
    slot = obs["controlled_ids"][0]
    me = next(r for r in obs["robots"] if str(r["slot"]) == slot)
    try:
        command = decide(me, obs)
    except Exception:
        command = action()                     # on error, hold still instead of disabling the program
    return {slot: command}, state


def decide(me, obs):
    if obs["tick"] == 0:
        return action(profile=PROFILE)
    if not me["alive"]:
        return action()                        # wait for natural respawn; send revive=True if coins allow
    team = obs["team"]
    enemy_team = "blue" if team == "red" else "red"
    side = 1 if team == "red" else -1
    if me["ammo"] < 20:                        # buy locally at the base: 50 rounds = 50 coins
        base = obs["bases"][team]
        home = (base["x"] + 1.5 * side, base["y"])
        return action(move=navigate(me, home, obs["arena"]),
                      buy_ammo={"amount": 50, "remote": False})
    outpost = obs["outposts"][enemy_team]
    structure = dict(outpost, kind="outpost") if outpost["hp"] > 0 else obs["bases"][enemy_team]
    goal = (structure["x"] - 3 * side, structure["y"])
    move = navigate(me, goal, obs["arena"]) if distance(me, structure) > 3.5 else (0.0, 0.0)
    enemy = nearest_enemy(me, obs)
    target = intercept(me, enemy) if enemy and ballistic_reachable(me, enemy) else structure
    fire = (can_fire(me) and me["heat"] + 20 <= me["max_heat"]
            and ballistic_reachable(me, target))
    return action(move=move, aim=aim_at(me, target), pitch=aim_pitch(me, target), fire=fire)
```

Ideas for improvement: when to start and hit the power rune (`rune_start=True` and `runes[your team]["targets"]`), using buff zones and terrain crossings, when to go to the supply zone or heal remotely, holding a fortress, and picking fights based on your teammates' positions and HP.
