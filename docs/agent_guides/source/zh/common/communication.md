### 队内通信

所有控制模式都支持按机器人编号通信。每台机器人可在自己的动作中设置 `messages`，每轮最多发送4条；消息在下一次决策（0.1 s后）送达，不受距离、视野或机器人存活状态限制。

{{#team}}{{^distributed}}
全队模式仍由一个进程控制全部机器人，保留共享 `state`。`obs["message_inboxes"][编号字符串]` 是对应机器人的收件箱；`obs["messages"]` 是各收件箱的汇总，同一广播可能按不同接收者出现多条信封。

```python
from sdk import action, message

def act(obs, state):
    actions = {}
    inboxes = obs["message_inboxes"]
    for slot in obs["controlled_ids"]:
        received = inboxes[slot]
        detected = obs["vision"].get(slot, {}).get("enemies", [])
        actions[slot] = action(messages=[message({"seen": detected})])
    return actions, state
```
{{/distributed}}{{/team}}
{{#independent}}
单机器人进程继续通过 `obs["messages"]` 接收发给自己的消息；`obs["message_inboxes"][obs["controlled_ids"][0]]` 提供同一收件箱。

```python
from sdk import action, message

def act(obs, state):
    slot = obs["controlled_ids"][0]
    received = obs["messages"]
    return {slot: action(messages=[message({"intent": "advance"})])}, {"received": received}
```
{{/independent}}

- `message(data)` 广播给当前己方其余机器人；`message(data, to="2")` 发给指定己方部署编号。在固定阵容中编号为{{slot_list}}，自由赛以实际阵容为准。不能发给自己或对方，发送者由宿主机从动作编号确定，不能伪造。
- 原始格式为 `{"to": "all" 或队友编号字符串, "data": JSON值}`。每条 `data` 最多512 bytes，消息与物理动作一起计入每台机器人1 KiB动作上限；这个额度按机器人计算，全队进程不会共享一个4条的限额。
- 收件信封为 `{"from": "red-1", "to": "red-2", "tick": 0, "delivery_tick": 2, "data": ...}`。首轮收件箱为空，下一轮只出现一次；需要保留的情报自行存入 `state`。
- 同轮消息按发送者部署编号、消息列表顺序送达，与策略动作字典顺序或进程完成顺序无关。不存在的自由赛接收者不送达；程序停用后不再发送或处理消息。
- 消息不会改变视觉 `enemies`，也不会给独立进程自动共享私有状态。主动报告看到的敌人、目标和计划时，应附带时间并处理情报时效。
- 回放的决策步 `actions[i]["communication"]` 保存发送者、接收者列表、发送与送达tick及内容；消息不交给物理引擎，也不在第二个保持动作的比赛步重复发送。
