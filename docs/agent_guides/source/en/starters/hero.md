## Starter Code

The `strategy.py` in your workspace is a complete, runnable template (it drives any slot) that you can improve directly. Below is a minimal hero-only skeleton that illustrates the interface; it is not a strong strategy. It buys 42mm at the base, drives to a fixed spot at the foot of your side's ramp to the central highland, deploys and attacks the enemy outpost, then switches to the base once the outpost is down.

```python
from sdk import action, aim_at, aim_pitch, ballistic_reachable, can_fire, distance, navigate


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
        return action(profile="ranged")
    if not me["alive"]:
        return action()                        # wait for natural respawn; send revive=True if coins allow
    team = obs["team"]
    enemy = "blue" if team == "red" else "red"
    side = 1 if team == "red" else -1
    if me["ammo"] == 0:                        # buy locally at the base: 10 rounds = 100 coins
        base = obs["bases"][team]
        home = (base["x"] + 1.5 * side, base["y"])
        return action(move=navigate(me, home, obs["arena"]), deploy=False,
                      buy_ammo={"amount": 10, "remote": False})
    outpost = obs["outposts"][enemy]
    target = dict(outpost, kind="outpost") if outpost["hp"] > 0 else obs["bases"][enemy]
    spot = (8.2, 7.5) if team == "red" else (19.8, 7.5)   # in front of your side's steps up to the central highland
    if not me["deployed"] and distance(me, {"x": spot[0], "y": spot[1]}) > 0.5:
        return action(move=navigate(me, spot, obs["arena"]))
    fire = can_fire(me) and ballistic_reachable(me, target)
    return action(deploy=True, aim=aim_at(me, target), pitch=aim_pitch(me, target), fire=fire)
```

Ideas for improvement: choose firing positions and timing, switch between deployment and movement, use remote purchases, return to the supply zone or heal remotely when HP is low, and time your attacks with your teammates.
