# 开发策略

Arena-1 的 Python 策略实现 `act(observation, state)`，返回动作和下一轮状态。
观察包含己方机器人、视野内敌人、裁判公开信息、经济和时间；不会直接提供视野外敌人的位置。

```python
def act(observation, state):
    actions = {}
    for slot in observation['controlled_ids']:
        actions[str(slot)] = {'move': [0, 0], 'fire': False}
    return actions, state
```

此示例只展示协议，比赛前应阅读工作区中对应模式的完整手册。

| 模式 | 文件 | 运行方式 |
| --- | --- | --- |
| team | strategy.py | 一个进程控制整队 |
| robot | strategy.py | 每个编号独立开发，组装为 squad |
| distributed | robot_1.py 等六份文件 | 一次提交，六个独立进程 |
| adaptive | strategy.py | 每次部署控制自身实例 |

## 练习与提交

桌面训练页生成的工作区已经配置对应服务地址和开发令牌。在该目录运行：

```sh
python -B arena.py status
python -B arena.py test
python -B arena.py results
python -B arena.py submit
```

`python` 应为本机可用的 Python 3；开发者也可以使用应用内的 Python 解释器。
以 `arena.py --help` 和任务手册中的参数为准。不要公开工作区中的令牌或私有练习记录。

## 接口与限制

策略决策频率为 10 Hz，默认单次决策时限 200 ms。源码限额、状态和动作限额以
`rmuc_arena/worker.py` 为唯一运行时定义。使用 `sdk.py` 的动作和几何工具，避免把型号编号当成自由赛的部署编号。
队内消息支持有限大小的定向消息与广播，在下一轮送达，不自动共享状态或视野。

完整中英文手册与硬件说明位于
[docs/agent_guides](https://github.com/RM-Arena/Arena-1/tree/main/docs/agent_guides)。
示例位于 [examples](https://github.com/RM-Arena/Arena-1/tree/main/examples)。
规则依据、模拟假设与实现边界见
[规则审计](https://github.com/RM-Arena/Arena-1/blob/main/docs/RULES_IMPLEMENTATION_AUDIT.md)。
