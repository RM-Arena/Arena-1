## 起步代码与策略建议

工作目录里的 `strategy.py` 已经是完整可运行的模板，覆盖补弹、复活、工程装配、空中支援和攻击建筑，可以直接在它的基础上改进。下面的最小骨架只用来说明接口，并不是一个强策略：

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
            actions[slot] = action()        # 出错时原地待命，避免整个程序被停用
    return actions, state


def decide(robot, obs):
    if robot["role"] == "aerial":
        return action(support=True, altitude=1.9)
    if not robot["alive"]:
        return action(revive=True)          # 金币不足时不会生效
    if robot["role"] == "engineer":
        return action()                     # 换成模板中的拾取与装配逻辑
    enemy = nearest_enemy(robot, obs)
    if enemy is None:
        return action()
    spare_heat = robot["role"] == "hero" or robot["heat"] + 20 <= robot["max_heat"]
    return action(aim=aim_at(robot, enemy), pitch=aim_pitch(robot, enemy),
                  fire=can_fire(robot) and spare_heat)
```

**策略建议**

- 先把经济跑起来：开局 1 s 后尽快兑换弹量；让工程尽早完成 1 级装配并逐级推进，科技收入是最大的金币来源，等级上限也取决于它。
- 胜负首先看基地，其次看前哨站。不要为了无关的击杀放弃守护己方前哨站或进攻对方建筑的机会。
- 对方基地护甲闭合时只有 42mm 能造成伤害，英雄（尤其是部署状态）是攻击基地的主力。
- 空中支援的免费时间有限，超出后按秒消耗金币；把它用在关键时刻。
- 注意热量和弹量，避免永久锁定；注意功率缓冲，避免断电。
- 用多个种子并加上 `--swap-sides` 练习，避免策略只在某一侧或某个种子上有效。
