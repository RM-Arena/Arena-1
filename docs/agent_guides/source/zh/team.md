# 机器人策略对战 · 全队赛参赛手册

本手册是全队赛的完整规则与接口说明。你要编写一个 Python 程序，**同时控制己方全部六台机器人**，与另一支同样由程序控制的队伍对战。比赛过程中不会调用语言模型，所有决策都由你的代码实时做出。

## 速览

| 项目 | 内容 |
| --- | --- |
| 交付物 | `strategy.py`，其中定义 `act(observation, state)` |
| 你控制 | 己方 1、2、3、4、6、7 号，共六台（没有 5 号） |
| 决策节奏 | 每 0.1 s 调用一次 `act`，每次须在 200 ms 内返回 |
| 单局时长 | 420 s；任一方基地被击毁时提前结束 |
| 开发时间 | 默认 90 分钟，由组织者启动计时；阅读、编码、测试、提交全部计入 |
| 参赛版本 | 截止前最后一次成功提交的版本 |

{{> common/quickstart}}

{{> common/task}}

{{> common/overview}}

{{> team/information}}

{{> rules/combat}}

{{> rules/penalties}}

{{> rules/economy}}

{{> rules/growth}}

{{> rules/power}}

{{> rules/structures}}

{{> rules/zones}}

{{> rules/rune}}

{{> mechanics/chassis}}

## 兵种专属机制

英雄部署、工程装配和空中支援只属于各自的兵种；步兵的专属内容（启动能量机关、占领堡垒）已在「区域增益与地形跨越」和「能量机关」中介绍。{{#c_s7}}所选 I7 型号还可以降低云台（`crouch`，见「接口参考」）。{{/c_s7}}

{{> mechanics/hero}}

{{> mechanics/engineer}}

{{> mechanics/aerial}}

{{> common/interface}}

{{> common/practice}}

{{> team/starter}}

{{> team/levels}}

{{> common/pitfalls}}
