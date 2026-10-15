## Starter Code and Strategy Tips

The {{source_files}} in your workspace is already a complete, runnable template you can improve directly. The minimal skeleton below only illustrates the 2027 interface and is not a strong strategy:

```python
from sdk import (action, aim_at, aim_pitch, can_fire, nearest_enemy, navigate,
                 workbench_point, launcher_ready, drones, hostile_plates, strike_plan)


def act(obs, state):
    actions = {}
    for robot in obs["robots"]:
        slot = str(robot["slot"])
        if slot not in obs["controlled_ids"]:
            continue
        try:
            actions[slot] = decide(robot, obs)
        except Exception:
            actions[slot] = action()        # hold still on errors instead of being disabled
    return actions, state


def decide(robot, obs):
    arena = obs["arena"]
    if robot["role"] == "aerial":
        commands = {}
        plates = hostile_plates(obs, "outpost")
        for d in drones(robot):
            if not plates or d["battery_wh"] < 0.4:
                commands[str(d["index"])] = {"dock": True}
            elif d["state"] == "docked":
                commands[str(d["index"])] = {"launch": True}
            else:
                mode, value = strike_plan(d, plates[0])
                commands[str(d["index"])] = {"goto": list(value)} if mode == "approach" else {"move": list(value)}
        return action(drones=commands)
    if not robot["alive"]:
        return action(revive=True)          # no effect without enough coins
    if robot["role"] == "heavy" and launcher_ready(robot):
        point = workbench_point(robot, arena)
        near = abs(robot["x"] - point[0]) + abs(robot["y"] - point[1]) < 0.3
        return action(move=(0, 0) if near else navigate(robot, point, arena), install_launcher=near)
    if obs["time"] > 1.2 and robot["ammo"] < 20 and robot["role"] != "heavy":
        return action(buy_ammo={"amount": 100, "remote": True})
    enemy = nearest_enemy(robot, obs)
    if enemy is None:
        return action(posture="move") if robot["role"] == "sentry" else action()
    return action(aim=aim_at(robot, enemy), pitch=aim_pitch(robot, enemy), fire=can_fire(robot))
```

**Strategy tips**

- **Control degree decides timeouts.** Capture the enemy outpost position early by holding its outpost or central card with infantry for 5 s, and keep your own outpost position to earn +1 per second. Holding both base positions (the enemy fortress) earns +3 per second.
- **Take the enemy outpost position before attacking the base**: while a team fully controls its own outpost position, its base is immune to all damage. Destroying the enemy outpost downgrades its control; holding the cards for 5 s more takes it over and rebuilds the outpost as yours.
- **The heavy robot's rhythm**: energy units → level 1/2/3 assemblies (income, infantry level cap, team defense) → fit the 42 mm launcher at the workbench → buy 42 mm and hit the outpost and base. A team that falls behind gets its launcher unlocked earlier by the time rule.
- **Aerial robots are consumables**: batteries do not recharge in the hangar and guards survive only a few strikes. Concentrate impacts on the enemy outpost (always valid) or a base that has lost its invulnerability, and stay out of enemy 42 mm fire.
- **The sentry** starts with ammo and suits guarding your outpost and the central highland; switch to `attack` for faster cooling, to `defense` when in danger, and spend enhancement at key moments. Return to the supply zone each minute for 100 rounds.
- Practice with several seeds and `--swap-sides` so the strategy does not work only on one side.

## Appendix: Common Mistakes

- Thinking in 2026 terms: expecting a slot 2 engineer, base HP as the first timeout criterion, or slot 6 firing with `support=True`. 2027 aerial robots only ram.
- Sending `fire=True` with the heavy robot before its launcher is `fitted`: nothing fires. The first shot after fitting deals no damage.
- Sending `install_launcher=True` once: park still at the workbench and send it in **every action**.
- Starting an assembly without a carried energy unit, or level 4 with only one.
- Pounding a base while its outpost position is still fully controlled by its owner — the base is invulnerable then.
- Hovering aerial robots without purpose: an empty battery makes them fall, and the hangar does not recharge them.
- Switching sentry postures too often: no switch for 5 s after each.
- Buying amounts that are not batch multiples (17 mm local multiples of 10, remote of 100; 42 mm remote of 10): the request is ignored.
- Raising an exception or timing out in `act`, which disables the program for the rest of the match. Catch exceptions inside `act` and check the worst-case time.
- Submitting for the first time at the deadline.
