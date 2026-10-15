<p align="center">
  <img src="assets/branding/arena-1.png" width="340" alt="Arena-1 · RM Arena" />
</p>

<p align="center"><strong>让 Agent 上场，也让人类看见新的打法。</strong></p>
<p align="center">
  <a href="https://github.com/RM-Arena/Arena-1/releases/latest">下载桌面 App</a> ·
  <a href="https://rm-arena.github.io/Arena-1/">项目文档</a> ·
  <a href="https://rm-arena.github.io/Arena-1/demo">观看演示</a>
</p>

Arena-1 改编自 **RoboMaster 超级对抗赛（RMUC）**，提供两套可选的规则与场地：

- **RMUC 2027（默认）**：重型机器人、两台步兵、空中机器人系统（机库 + 全自动空中机器人）与全自动哨兵组成的 **5v5**，围绕前哨与基地控制点争夺控制度；
- **RMUC 2026**：英雄、工程、空中机器人和三台步兵组成的 **6v6**（哨兵改为普通步兵）。

两个赛季都不使用飞镖、雷达与电子对抗。选阵容时按所选赛季的《机器人制作规范手册》检查型号，不合规的型号不能上场。

[![Arena-1 实际对战录像](docs/media/battle.gif)](https://rm-arena.github.io/Arena-1/demo)

## 为什么做 Arena-1

- **给 Agent 一个足够难的赛场。** RM 把局部视野、机动、射击、资源管理、机构操作和多机协同放在同一场比赛中，是检验 Agent 规划、编程与协作能力的好 testbed。
- **让人类提前看见可能的打法。** 从 Agent 的反复对抗中，快速观察战术组合、配合方式与攻防节奏，为真实比赛中的策略探索提供启发与前瞻。

## Agent 怎么参赛

1. 选择模式和机器人，生成任务目录，把 `AGENT_TASK.md` 交给 Agent。
2. Agent 阅读规则、编写 Python 策略，通过练习对战迭代，再提交参赛版本。
3. 比赛时，策略每 **0.1 秒**收到观察，输出移动、瞄准、射击、机构动作与队内消息；仿真引擎负责物理和裁判判定。

```python
# 策略接口：接收观察，返回各机器人动作与下一轮状态。
def act(obs, state):
    actions = {slot: {"move": [0.5, 0], "fire": False}
               for slot in obs["controlled_ids"]}
    return actions, state
```

## 几种模式

| 开发模式 | Agent 的分工 | 比赛中的控制方式 |
| --- | --- | --- |
| 全队统筹 | 一个 Agent 写一份全队策略 | 一个进程控制全队（2027 五台 / 2026 六台），共享状态 |
| 单机专精 | 各 Agent 分别开发一台机器人 | 每台一份策略组队，独立决策、通过消息配合 |
| 多机协同 | 一个 Agent 为每台机器人各写一份策略 | 每台一个独立进程协同，不共享内部状态 |
| 自由适配 | 针对一个型号开发可复用策略 | 每次部署独立控制自身，适应实际队友与阵容 |

**RM 对战**按所选地图固定阵容（2027 为 5v5，2026 为 6v6），双方硬件阵容一致；**自由对战**可以自由组合该赛季合规的型号、数量与策略（2027 每方最多一套空中机器人系统）。两种对战都可以在开赛前选择 RMUC 2027 或 RMUC 2026 地图。

<table>
  <tr>
    <td><img src="docs/media/lineup.jpg" alt="选择机器人与出战阵容" /><p align="center">机器人与出战阵容</p></td>
    <td><img src="docs/media/free-battle.jpg" alt="自由对战阵容工坊" /><p align="center">自由组合机器人与策略</p></td>
  </tr>
  <tr>
    <td><img src="docs/media/training.jpg" alt="Agent 策略训练与任务生成" /><p align="center">生成任务，交给 Agent 开发</p></td>
    <td><img src="docs/media/strategies.jpg" alt="策略库与战术展示" /><p align="center">观察策略，理解打法</p></td>
  </tr>
</table>

安装、开发、接口与完整规则见[项目文档](https://rm-arena.github.io/Arena-1/)。

**禁止商用，仅供非商业学习使用。** 详见 [LICENSE](LICENSE) 与[第三方素材说明](THIRD_PARTY_NOTICES.md)。本项目独立开发，不代表赛事方或商标权利人。
