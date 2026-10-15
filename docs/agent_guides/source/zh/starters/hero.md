## 起步代码

工作目录里的 `strategy.py` 是完整可运行的模板（它能驱动任何编号），可以直接在其基础上改进。下面是一个只控制英雄的最小骨架，用来说明接口，并不是强策略：在基地兑换 42mm，前往己方一侧中央高地坡道下的固定位置，部署后攻击对方前哨站，前哨站被毁后改打基地。

```python
from sdk import action, aim_at, aim_pitch, ballistic_reachable, can_fire, distance, navigate


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
        return action(profile="ranged")
    if not me["alive"]:
        return action()                        # 等待自然复活；金币充足时可发送 revive=True
    team = obs["team"]
    enemy = "blue" if team == "red" else "red"
    side = 1 if team == "red" else -1
    if me["ammo"] == 0:                        # 回基地就地兑换：10 发 = 100 金币
        base = obs["bases"][team]
        home = (base["x"] + 1.5 * side, base["y"])
        return action(move=navigate(me, home, obs["arena"]), deploy=False,
                      buy_ammo={"amount": 10, "remote": False})
    outpost = obs["outposts"][enemy]
    target = dict(outpost, kind="outpost") if outpost["hp"] > 0 else obs["bases"][enemy]
    spot = (8.2, 7.5) if team == "red" else (19.8, 7.5)   # 己方一侧中央高地台阶前
    if not me["deployed"] and distance(me, {"x": spot[0], "y": spot[1]}) > 0.5:
        return action(move=navigate(me, spot, obs["arena"]))
    fire = can_fire(me) and ballistic_reachable(me, target)
    return action(deploy=True, aim=aim_at(me, target), pitch=aim_pitch(me, target), fire=fire)
```

可以改进的方向：选择射击位置与时机、在部署与机动之间切换、利用远程兑换、在血量低时回补给区或远程回血、与队友的进攻节奏配合。
