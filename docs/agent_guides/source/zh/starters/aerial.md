## 起步代码

工作目录里的 `strategy.py` 是完整可运行的模板（它能驱动任何编号），可以直接在其基础上改进。下面是一个只控制空中机器人的最小骨架，用来说明接口，并不是强策略：有免费支援时间或金币充足时起飞，飞到航道靠中线的一端，攻击视野内的敌人。

```python
from sdk import (action, aim_at, aim_pitch, ballistic_reachable, can_fire, intercept,
                 navigate, nearest_enemy)

RESERVE = 200   # 免费时间用完后，给队友保留的金币


def act(obs, state):
    slot = obs["controlled_ids"][0]
    me = next(r for r in obs["robots"] if str(r["slot"]) == slot)
    try:
        command = decide(me, obs)
    except Exception:
        command = action()                     # 出错时保持现状，避免整个程序被停用
    return {slot: command}, state


def decide(me, obs):
    team = obs["team"]
    coins = obs["teams"][team]["resources"]
    if me["support_time"] <= 0 and coins < RESERVE:
        return action(support=False)           # 返回停机坪，不再花钱
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

可以改进的方向：按比赛阶段分配支援时间、配合步兵击打能量机关、选择能看到更多敌人的位置、在热量与弹量之间取舍。
