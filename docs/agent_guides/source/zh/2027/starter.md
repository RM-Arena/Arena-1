## 起步代码与策略建议

工作目录里的 {{source_files}} 已经是完整可运行的模板，可以直接在它的基础上改进。下面的最小骨架只用来说明 2027 接口，并不是一个强策略：

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
            actions[slot] = action()        # 出错时原地待命，避免整个程序被停用
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
        return action(revive=True)          # 金币不足时不会生效
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

**策略建议**

- **控制度决定到时胜负。** 尽早用步兵占住对方前哨或中央高地卡 5 s，夺取对方前哨控制点；同时守住自己的前哨控制点，才能每秒 +1。能同时控制双方基地控制点（对方堡垒）时每秒 +3。
- **先让对方失去前哨控制点，才打得动基地**：对方完全控制自己的前哨控制点时，其基地免疫一切伤害。击毁对方前哨会让控制权降级；之后再占领 5 s 就能接管并把它重建成你的前哨。
- **重型的节奏**：开局取能量单元 → 1/2/3 级装配（收入、步兵等级上限、全队防御）→ 工作台装 42mm → 兑换 42mm 打前哨与基地。落后时发射机构会按时间规则提前解锁。
- **空中机器人是消耗品**：电池不在机库充电、护罩耐撞次数有限。把撞击集中在对方前哨（随时有效）或已经失去无敌的基地上，并避开对方 42mm。
- **哨兵**：开局有弹，适合守己方前哨与中央高地；进攻时用 `attack` 姿态提高冷却，危险时切 `defense` 并在关键时刻开启强化。每分钟回补给区领取 100 发。
- 用多个种子并加上 `--swap-sides` 练习，避免策略只在某一侧有效。

## 附录：常见错误

- 用 2026 的思路：以为编号有 2 号工程、以为到时先比基地血量、以为 6 号可以 `support=True` 开火。2027 的空中机器人只能撞击。
- 重型在发射机构 `fitted` 之前发送 `fire=True`：不会发射。装上后的第一发不造成伤害。
- 安装发射机构时只发一次 `install_launcher=True`：必须在工作台停稳并**每次动作**都发送。
- 装配时没有携带能量单元，或 4 级只带了 1 枚。
- 在对方前哨控制点仍被对方完全控制时猛攻基地——基地此时无敌。
- 空中机器人一直悬停耗电：电量耗尽会坠落，而且在机库里不充电。
- 哨兵频繁切换姿态：每次切换后 5 s 内不能再切换。
- 兑换数量不是批量的整数倍（17mm 就地 10 的倍数、远程 100 的倍数；42mm 远程 10 的倍数），请求被直接忽略。
- `act` 抛出异常或超时，导致整局被停用。请在 `act` 内捕获异常，并检查最坏情况的耗时。
- 直到截止前才第一次提交。
