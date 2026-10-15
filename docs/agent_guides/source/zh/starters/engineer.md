## 起步代码

工作目录里的 `strategy.py` 是完整可运行的模板（它能驱动任何编号，包括完整的 1–4 级装配逻辑），可以直接在其基础上改进。下面是一个只控制工程的最小骨架，用来说明接口，并不是强策略：在资源区拾取能量单元，到装配区按解锁顺序完成 1–3 级装配。

```python
from sdk import action, distance, navigate, assembly_work_point


def act(obs, state):
    slot = obs["controlled_ids"][0]
    me = next(r for r in obs["robots"] if str(r["slot"]) == slot)
    try:
        command = decide(me, obs)
    except Exception:
        command = action()                     # 出错时原地待命，避免整个程序被停用
    return {slot: command}, state


def decide(me, obs):
    if not me["alive"]:
        return action()                        # 等待自然复活；金币充足时可发送 revive=True
    team = obs["team"]
    zones = {z["id"]: z for z in obs["arena"]["zones"]}
    resource, assembly = zones[team + "_resource"], zones[team + "_assembly"]
    core = obs["assemblies"][team]
    done = obs["teams"][team]["completed_difficulties"]
    busy = core["stage"] in ("moving", "inserting", "buffered")
    in_resource = distance(me, resource) <= resource["radius"]
    if not busy and (me["carried_units"] == 0 or (in_resource and me["carried_units"] < 2)):
        return action(move=go(me, resource, obs), pick_unit=True)
    # 当前能做的最高难度（这个骨架不做 4 级）
    level = max(d for d in (1, 2, 3) if obs["time"] >= (d - 1) * 60 and (d == 1 or d - 1 in done))
    x, y = assembly_work_point(me, obs["arena"])
    work = {"x": x, "y": y}
    settled = distance(me, work) <= 0.06
    return action(move=(0, 0) if settled else navigate(me, (x, y), obs["arena"]),
                  brake=settled, assembly=level, assembly_insert=True,
                  assembly_translate=True, assembly_rotate=core["target_rotation"],
                  assembly_confirm=True)


def go(me, zone, obs):
    if distance(me, zone) <= 0.3:
        return (0.0, 0.0)
    return navigate(me, (zone["x"], zone["y"]), obs["arena"])
```

可以改进的方向：规划往返路线、一次携带 2 个单元、在合适时机挑战 4 级、在前哨站被毁时去重建（只需 5 s）、躲避敌人火力。
