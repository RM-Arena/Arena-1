## 起步代码

工作目录里的 `strategy.py` 是完整可运行的模板（它能驱动任何编号），可以直接在其基础上改进。下面是一个只控制步兵的最小骨架，用来说明接口，并不是强策略：弹量不足时回基地兑换，然后靠近对方前哨站（被毁后改为基地），优先射击视野内的敌人。

```python
from sdk import (action, aim_at, aim_pitch, ballistic_reachable, can_fire, distance,
                 intercept, navigate, nearest_enemy)

PROFILE = {{profile_code}}   # {{slot}} 号的预选性能，只在 tick == 0 时生效


def act(obs, state):
    slot = obs["controlled_ids"][0]
    me = next(r for r in obs["robots"] if str(r["slot"]) == slot)
    try:
        command = decide(me, obs)
    except Exception:
        command = action()                     # 出错时原地待命，避免整个程序被停用
    return {slot: command}, state


def decide(me, obs):
    if obs["tick"] == 0:
        return action(profile=PROFILE)
    if not me["alive"]:
        return action()                        # 等待自然复活；金币充足时可发送 revive=True
    team = obs["team"]
    enemy_team = "blue" if team == "red" else "red"
    side = 1 if team == "red" else -1
    if me["ammo"] < 20:                        # 回基地就地兑换：50 发 = 50 金币
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

可以改进的方向：何时启动和击打能量机关（`rune_start=True` 与 `runes[己方]["targets"]`）、利用增益点和地形跨越、何时回补给区或远程回血、占领堡垒、根据队友的位置与血量选择战场。
