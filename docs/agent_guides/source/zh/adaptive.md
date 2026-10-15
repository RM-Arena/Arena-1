# 模式 D · 自适应单机器人策略（{{robot_title}}型号）

你只开发一台 **{{robot_title}}型号**机器人的 Python 策略。**开发阶段不预告最终阵容、己方数量或队友型号**；用户在 Web 卡组中自由选择上场机器人，同一型号与同一份策略都可以重复部署。每次部署有独立进程、随机种子和私有 `state`，策略文件之间不能共享内存。

比赛开始后，`observation["robots"]` 给出当前己方完整实际阵容，你可以读取它并适应队友；但只能返回 `controlled_ids` 中自身实例的动作。不要把硬件型号当成部署编号，不要假设固定队友数量。

## 速览

| 项目 | 内容 |
| --- | --- |
| 交付物 | `strategy.py`，定义 `act(observation, state)` |
| 控制对象 | 一台 {{robot_title}}型号机器人的部署实例，编号比赛时由 `controlled_ids[0]` 给出 |
| 队友信息 | 开发时不预告；比赛时完整己方阵容可读 |
| 决策 | 每 0.1 s 一次，每次最多 200 ms；只控制自身 |
| 队内通信 | 可以广播或发给指定部署实例；下一轮送达 |
| 比赛 | 420 s；基地被摧毁时提前结束；卡组对战单独保存，不计官方 Elo |

{{> common/task}}

## 比赛与自身硬件

地图为 28 × 15 m，双方各有基地、前哨、科技核心和能量机关。共享己方金币、基地与团队增益。胜负依次按基地血量、前哨是否从未被摧毁、前哨血量、攻击伤害与存活地面机器人的总血量判定。

{{own_hardware}}

{{> rules/combat}}
{{> rules/penalties}}
{{> rules/economy}}
{{> rules/growth}}
{{> rules/power}}
{{> rules/structures}}
{{> rules/zones}}
{{> rules/rune}}
{{#c_ground}}{{> mechanics/chassis}}{{/c_ground}}
{{#hero}}{{> mechanics/hero}}{{/hero}}
{{#engineer}}{{> mechanics/engineer}}{{/engineer}}
{{#aerial}}{{> mechanics/aerial}}{{/aerial}}

{{> common/interface}}

### D 模式的编号与通信

`robot["model_slot"]` 表示硬件型号，`robot["slot"]` 表示本局部署编号；重复型号也有不同编号。`TEAM_SLOTS`、`TEAM_SIZE` 是固定阵容模式的旧辅助常量，不能用于推断本局数量。请从比赛观察中读取实际阵容。

```python
from sdk import action, message

def act(obs, state):
    slot = obs["controlled_ids"][0]
    own = next(r for r in obs["robots"] if str(r["slot"]) == slot)
    teammates = [r for r in obs["robots"] if str(r["slot"]) != slot]
    outgoing = [message({"intent": "cover", "model": own["model_slot"]})]
    # 发给具体队友：message(data, to=str(teammates[0]["slot"]))
    return {slot: action(messages=outgoing)}, {"teammates": [r["id"] for r in teammates]}
```

消息每轮最多 4 条，`data` 是最多 512 bytes 的 JSON 值，与其他动作一起计入自身动作的 1 KiB 上限。`to="all"` 广播给当前其余队友，或指定队友部署编号字符串（不是型号）。消息仅在己方转发；不存在的目标不送达。本轮发送在下一次决策（0.1 s 后）通过 `obs["messages"]` 接收一次，格式含 `from`、`to`、`tick`、`delivery_tick`、`data`。通信不共享私有 state，也不自动合并敌方视野。

## 练习与提交

练习采用不同的队友数量和型号；它们只是练习样例，不能假定正式上场使用同样阵容。模板不依赖固定数量，按比赛时实际观察选择动作。

{{> common/practice}}
