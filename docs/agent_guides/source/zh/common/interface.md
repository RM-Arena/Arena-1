## 接口参考

### act 函数

```python
def act(observation: dict, state) -> tuple[dict, object]:
    ...
    return actions, new_state
```

- 每 0.1 s 调用一次。比赛状态每 0.05 s 推进一步，所以 `tick` 每次决策增加 2；第一次调用时 `tick == 0`。
- `actions` 以编号字符串为键、动作字典为值，例如 {{#team}}{{^distributed}}`{"1": action(...), "7": action(...)}`{{/distributed}}{{#distributed}}`{"3": action(...)}`{{/distributed}}{{/team}}{{#robot}}{{^adaptive}}`{"{{slot}}": action(...)}`{{/adaptive}}{{#adaptive}}`{obs["controlled_ids"][0]: action(...)}`{{/adaptive}}{{/robot}}。没有给出动作的机器人本轮视为空动作（停下、不射击）。
- 动作在下一次决策前持续生效（0.1 s，即 2 个比赛步）。
- `state` 是你上一次返回的 `new_state`，第一次调用时为 `None`。它必须能序列化为 JSON，且不超过 32 KiB。模块级全局变量在同一局内也会保留，但推荐用 `state` 保存记忆，便于复现。
- `random` 模块已用固定种子初始化，同样的输入会得到同样的结果。不要依赖系统时间，请使用 `observation["time"]`。

### Observation

| 字段 | 内容 |
| --- | --- |
| `tick`、`time`、`remaining` | 比赛步数、已过秒数、剩余秒数 |
| `dt`、`policy_dt` | 比赛步长 0.05 s、决策间隔 0.1 s |
| `team` | `"red"` 或 `"blue"` |
| `controlled_ids` | 你可以控制的编号（字符串列表） |
| `robots` | {{^adaptive}}己方六台机器人的完整状态（见下表）{{/adaptive}}{{#adaptive}}比赛时当前己方实际阵容的完整状态；`slot` 是部署编号，`model_slot` 是硬件型号{{/adaptive}} |
| `enemies` | 当前可见的敌方机器人（含残骸）及其外观可见的全部状态，见下文「可见的敌方机器人」；空中机器人与残骸 `targetable=False` |
| `messages`、`message_inboxes` | 队内消息列表与按控制编号索引的收件箱；所有模式可用，见「队内通信」 |
| `vision` | 每个受控观察者（编号字符串为键）此刻看到的机器人：`{"enemies": [id…], "allies": [id…]}`；另有相机 `camera.origin`、`camera.direction`、水平/垂直视场角与 `range_m` |
| `bases`、`outposts` | 双方基地与前哨站：`x, y, z, hp, max_hp, armor_open, shield_hp, ever_destroyed, rotation, rotation_stopped` 等 |
| `teams` | 己方经济的完整状态（`resources` 金币、`purchased_17`/`purchased_42` 已兑换量、`tech_income`、`level_cap`、`completed_difficulties`、`rebuild_credits`、`fortress_ammo`、`attack_damage` 等）；对方只有 `attack_damage` |
| `zones` | 各增益点当前的 `owner`、`occupants`、`contested` |
| `runes` | 己方能量机关的状态与目标 |
| `assemblies` | 双方科技核心的装配状态 |
| `projectiles` | 可见弹丸：己方全部，加上视野内的敌方弹丸 |
| `arena` | 地图几何，见「比赛概览」 |
| `referee` | 裁判快照，见下节 |
| `specs`、`rulebook_rules`、`simulation_assumptions` | 参数摘要；完整数值请用 `sdk.RULES`、`sdk.DESIGNS` 或 `arena.json` |

`robots` 中每台机器人的常用字段：

| 字段 | 含义 |
| --- | --- |
| `id`、`slot`、`team`、`role` | 例如 `"red-3"`、`3`、`"red"`、`"infantry"`；`role` 取值为 `hero`、`engineer`、`infantry`、`aerial` |
| `x, y, z`、`vx, vy, vz` | 位置与速度；`z` 是车体参考点高度，悬架压缩时可能略低于地面 |
| `heading`、`aim`、`pitch` | 底盘朝向、云台世界水平角、云台俯仰角（相对底盘） |
| `quaternion`、`angular_velocity`、`grounded` | 车身姿态、角速度、是否着地 |
| `hp`、`max_hp`、`alive` | 血量。空中机器人 `max_hp == 0`，`alive` 表示支援是否开启 |
| `ammo` | 当前弹量 |
| `heat`、`max_heat`、`cooling_rate`、`overheated`、`heat_permanent_lock` | 热量状态 |
| `overspeed_locked`、`overspeed_lock_until`、`overspeed_permanent_lock`、`launcher_fault` | 发射初速度锁定与硬件弹速有效性 |
| `yellow_cards`、`red_card`、`fpv_blocked_until` | 黄牌计数、红牌罚下状态、相机遮挡结束时间 |
| `level`、`experience` | 等级与经验 |
| `profile`、`chassis_profile`、`weapon_profile` | 当前性能 |
| `power_limit`、`power_w`、`buffer_energy_j`、`energy`、`power_cutoff_until` | 功率与能量 |
| `weak`、`invulnerable`、`defense_buff`、`attack_multiplier`、`vulnerability`、`cooling_multiplier` | 状态与当前增益 |
| `respawn_progress`、`respawn_required`、`instant_revives` | 复活进度 |
| `last_shot_time`、`last_damage_time` | 判断脱战：当前时间减去两者都不小于 6 s |
| `pending_ammo`、`pending_heal` | 待到账的远程兑换与远程回血 |
| `deployed`、`deploy_at` | 英雄部署状态 |
| `support_active`、`support_time` | 空中支援是否开启、剩余免费时间 |
| `carried_units` | 工程携带的能量单元数 |
| `crouched` | 默认 I7 是否降低了云台 |
| `powered` | 底盘是否有电；被击毁、超功率断电或电池耗尽时为 `False`，此时底盘只能滑行 |
| `upright`、`tipped` | 车身竖直程度（1 为正立）；`tipped` 表示已翻倒，不能行驶 |
| `legs` | 双轮足型号的左右腿长（右、左，米）；其他机器人没有该字段 |
| `arm_joints`、`arm_tip`、`arm_mode`、`rescue_target`、`rescue_contact` | 工程机械臂的 7 个关节值、末端世界坐标、当前模式、正在扶正的队友及是否已夹住 |
| `speed_reference_mps`、`chassis_size_m`、`muzzle_height_m`、`armor_center_z_m` | 硬件参数 |

### 可见的敌方机器人

只要该进程控制的任一观察者能看到某台敌方机器人车身的任一部位（车体中心、云台顶部或四块装甲板中的任意一处，视线不被墙体、地形、结构或其他机器人挡住，且在视距内；地面观察者还要求该部位位于实际炮口方向的水平{{ground_fov_horizontal}}°、垂直{{ground_fov_vertical}}°视锥内），它就出现在 `enemies` 中，并带有外观上可见的全部状态：

- `id, slot, team, role, x, y, z, vx, vy, vz, angular_velocity, quaternion, heading`
- `aim, pitch`：云台指向（能看见炮管方向）
- `hp, max_hp, alive, powered, targetable, invulnerable`：血量与灯条状态；残骸 `alive=False`
- `upright, tipped, grounded, crouched, deployed, carried_units`
- 工程另有 `arm_joints, arm_tip, arm_mode`；双轮足另有 `legs`
- `chassis_size_m, armor_center_z_m, muzzle_height_m, design_name`
- `seen_by`：看到它的己方编号列表

视锥跟随实际云台方向、俯仰和车身姿态，不跟随底盘的平移方向；无人机保持原有全向覆盖。{{#independent}}本进程不自动合并队友的敌方观察。{{/independent}}{{#team}}{{^distributed}}`enemies` 是受控机器人实际视野的并集。{{/distributed}}{{/team}}己方全部机器人的位置和完整状态始终在 `robots` 中，裁判系统信息也不受视锥影响。

看不到的仍是敌方的弹量、热量、经验、金币与私有状态。

### 裁判快照 referee

`observation["referee"]`（或 `sdk.referee_info(observation)`）随每次决策推送，不需要联网。同一次 `act` 中读到的是一致的快照。

| 字段 | 内容 |
| --- | --- |
| `tick`、`time`、`remaining`、`status` | 比赛时钟与状态 |
| `robots` | 双方全部机器人的 `id, slot, team, role, hp, max_hp, alive`，**不含位置** |
| `bases`、`outposts` | 双方结构状态 |
| `economy` | 己方经济，与 `teams[己方]` 相同 |
| `events` | 近期播报（见下文），每条带 `id`、`type`、`time` |
| `winner`、`reason` | 比赛结束后的胜方与判定原因 |

播报分两类：

- **公开播报**：击毁 `destroy`、复活 `respawn`、前哨站重建 `outpost_rebuilt`、能量机关激活 `rune_activated`、装配成功 `assembly_success`、比赛结束 `finish`。
- **己方播报**：收入 `income`、兑换 `ammo_purchase`、远程弹量到账 `ammo_delivered`、远程回血生效 `remote_heal`、升级 `level_up`、过热 `overheat`、拾取能量单元 `unit_pickup`、装配开始 `assembly_start`、装配失败 `assembly_failed`、机械臂夹住队友 `rescue_grip`、扶正完成 `rescue_complete`（带 `target`）、双轮足起跳 `jump`。

同一条播报可能在相邻几次决策中重复出现，请用 `id` 去重。

```python
from sdk import referee_info

judge = referee_info(obs)
coins = judge["economy"]["resources"]
enemy_hp = {r["id"]: r["hp"] for r in judge["robots"]
            if r["team"] != obs["team"] and r["max_hp"] > 0}
```

### Action

请用 `sdk.action(...)` 构造动作，它会提前拒绝未知字段。{{#c_engineer}}工程没有发射器，`aim` / `pitch` 控制其模拟相机的观察方向。{{/c_engineer}}{{#robot}}下表只列出你的机器人用得到的字段。{{/robot}}

| 字段 | 取值 | 适用 | 说明 | 省略时 |
| --- | --- | --- | --- | --- |
| `move` | `(vx, vy)` | 全部 | 世界坐标速度意图，[−1, 1] | 停下 |
{{#c_ground}}
| `heading` | 弧度 | 地面 | 底盘朝向 | 转向运动方向 |
| `yaw_rate` | rad/s，±12 | 地面 | 底盘目标角速度（小陀螺），优先于 `heading` | — |
| `brake` | bool | 地面 | 无 `move` 时是否主动刹车 | `True` |
{{/c_ground}}
{{#c_s3}}
| `leg_height` | 米，见硬件限位 | 双轮足 | 腿长 | 型号默认值 |
| `jump` | 0–1 或 bool | 双轮足 | 起跳力度，着地时触发；冷却见硬件 | 不跳 |
| `lean` | rad，±0.35 | 双轮足 | 机体俯仰目标，正值前倾 | 0 |
{{/c_s3}}
| `aim` | 弧度或 `None` | 全部 | 云台/相机世界水平角 | 保持当前方向 |
| `pitch` | 弧度 | 全部 | 云台/相机世界俯仰角，向上为正 | 0.04 |
{{#c_shooter}}
| `fire` | bool | 射手 | 本次决策期间是否射击 | 不射击 |
{{/c_shooter}}
{{#c_ground}}
| `power` | 瓦，0–200 | 地面 | 底盘功率预算 | 当前功率上限 |
{{/c_ground}}
{{#c_s7}}
| `crouch` | bool | 默认 I7 | 降低云台；**每次动作都要带上**才能保持 | 站起（空间足够时） |
{{/c_s7}}
{{#c_buyer}}
| `profile` | 字符串或字典 | 英雄、步兵 | 性能选择，仅 `tick == 0` 有效 | 保持预选 |
| `buy_ammo` | `{"amount": n, "remote": bool}` | 英雄、步兵 | 兑换弹量 | — |
| `remote_heal` | bool | 英雄、步兵 | 远程回血 | — |
{{/c_buyer}}
{{#c_ground}}
| `revive` | bool | 地面 | 阵亡时立即复活 | — |
{{/c_ground}}
{{#c_hero}}
| `deploy` | bool | 英雄 | 部署 / 取消部署 | 保持现状 |
{{/c_hero}}
{{#c_aerial}}
| `support` | bool | 空中 | 开启 / 关闭空中支援 | 保持现状 |
| `altitude` | 米 | 空中 | 目标绝对高度 | 支援开启时 1.85 m |
{{/c_aerial}}
{{#c_engineer}}
| `pick_unit` | bool | 工程 | 拾取能量单元 | — |
| `assembly` | 1–4 | 工程 | 开始装配 | — |
| `assembly_insert`、`assembly_translate` | bool | 工程 | 插入、平移 | — |
| `assembly_rotate` | 度 | 工程 | 旋转到的目标角度 | — |
| `assembly_confirm` | bool | 工程 | 确认装配 | — |
| `rescue` | 编号 | 工程 | 用机械臂扶正该翻倒队友 | — |
| `arm` | 字典 | 工程 | 直接控制机械臂：`{"tip": [x,y,z], "dir": [..], "frame": "world"\|"robot"}`、`{"joints": [7 个值]}` 或 `{"stow": True}` | 自动 |
{{/c_engineer}}
{{#c_infantry}}
| `rune_start` | bool | 步兵 | 发起能量机关激活 | — |
{{/c_infantry}}

不适用于当前机器人或当前状态的操作不会生效，有的会以 `invalid_action` 事件记录在回放中。字段名拼错会让整个程序被停用；`sdk.action` 会在你的代码里提前报错。

### SDK

`sdk.py` 是比赛环境中唯一可以导入的辅助库。它只做公开计算，不会给出额外信息；你可以随时用自己的实现替代它。

| 函数或常量 | 作用 |
| --- | --- |
| `action(move=(0, 0), aim=None, fire=False, pitch=0.04, **operations)` | 构造动作，拒绝未知字段 |
| `referee_info(obs)` | 返回裁判快照 |
| `nearest_enemy(robot, obs)` | 最近的可见、存活、可攻击的敌人，没有则为 `None` |
| `aim_at(robot, target)` | 云台水平角：自动选择朝向自己的装甲板，并补偿自身速度 |
| `aim_pitch(robot, target)` | 俯仰角：考虑重力、空气阻力、炮口位置和自身速度 |
| `ballistic_reachable(robot, target)` | 目标是否在弹道可达范围内 |
| `intercept(robot, target)` | 按目标速度做简单的提前量预测，返回新的目标点 |
| `can_fire(robot)` | 现在能否再发一发 |
| `navigate(robot, point, arena)` | 绕开墙体与禁入区、沿坡道前进的移动方向，可直接作为 `move`；经 `action` 传入时，退出起伏路段的移动会同时保持底盘朝向 |
| `toward(robot, point)`、`distance(a, b)` | 单位方向向量、水平距离 |
| `terrain_height(arena, x, y)` | 地面高度 |
| `muzzle_speed(robot)` | 出膛速度 |
| `remote_heal_cost(t)`、`instant_revive_cost(robot, t)` | 远程回血、立即复活的费用 |
| `tipped_teammates(obs)` | 己方翻倒的机器人列表 |
| `rescue_point(engineer, target)` | 工程扶正 `target` 时的停车点 |
| `sight_block_point(engineer, viewer, protected)` | 遮挡 `viewer` 看向 `protected` 视线的机械臂末端位置 |
| `fly_slope_lane(arena, team)` | 己方飞坡几何：唇口、坡顶、高度与着陆台 |
| `RULES`、`DESIGNS`、`TEAM_SLOTS` | 完整规则参数、机器人设计、编号列表 |

瞄准前哨站时传入 `dict(obs["outposts"][对方], kind="outpost")`，瞄准能量机关目标时传入 `dict(target, kind="rune_target")`。`sdk` 在导入时预先计算导航图，这部分时间不计入决策时限。

{{^adaptive}}
{{> common/communication}}
{{/adaptive}}
