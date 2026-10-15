## Starter Code

The `strategy.py` in your workspace is a complete, runnable template (it drives any slot and includes full level 1–4 assembly logic) that you can improve directly. Below is a minimal engineer-only skeleton that illustrates the interface; it is not a strong strategy. It picks up energy units in the resource zone and completes levels 1–3 in the assembly zone in unlock order.

```python
from sdk import action, distance, navigate, assembly_work_point


def act(obs, state):
    slot = obs["controlled_ids"][0]
    me = next(r for r in obs["robots"] if str(r["slot"]) == slot)
    try:
        command = decide(me, obs)
    except Exception:
        command = action()                     # on error, hold still instead of disabling the program
    return {slot: command}, state


def decide(me, obs):
    if not me["alive"]:
        return action()                        # wait for natural respawn; send revive=True if coins allow
    team = obs["team"]
    zones = {z["id"]: z for z in obs["arena"]["zones"]}
    resource, assembly = zones[team + "_resource"], zones[team + "_assembly"]
    core = obs["assemblies"][team]
    done = obs["teams"][team]["completed_difficulties"]
    busy = core["stage"] in ("moving", "inserting", "buffered")
    in_resource = distance(me, resource) <= resource["radius"]
    if not busy and (me["carried_units"] == 0 or (in_resource and me["carried_units"] < 2)):
        return action(move=go(me, resource, obs), pick_unit=True)
    # highest difficulty available now (this skeleton skips level 4)
    level = max(d for d in (1, 2, 3) if obs["time"] >= (d - 1) * 60 and (d == 1 or d - 1 in done))
    x, y = assembly_work_point(me, obs["arena"])
    work = {"x": x, "y": y}
    settled = distance(me, work) <= 0.06
    return action(move=(0, 0) if settled else navigate(me, (x, y), obs["arena"]),
                  brake=settled, assembly=level, assembly_insert=True,
                  assembly_translate=True, assembly_rotate=core["target_rotation"],
                  assembly_confirm=True)


def go(me, zone, obs):
    if distance(me, zone) <= 0.3:
        return (0.0, 0.0)
    return navigate(me, (zone["x"], zone["y"]), obs["arena"])
```

Ideas for improvement: plan the round trips, carry 2 units at a time, attempt level 4 at the right moment, rebuild the outpost when it falls (only 5 s for you), and stay out of enemy fire.
