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
- `state` 是你上一次返回的 `new_state`，第一次调用时为 `None`。它必须能序列化为 JSON，且不超过 32 KiB。
- `random` 模块已用固定种子初始化。不要依赖系统时间，请使用 `observation["time"]`。

### Observation

| 字段 | 内容 |
| --- | --- |
| `season` | `"2027"`；同一份代码可以据此区分 2026 / 2027 规则 |
| `tick`、`time`、`remaining` | 比赛步数、已过秒数、剩余秒数 |
| `team`、`controlled_ids` | `"red"` 或 `"blue"`；你可以控制的编号（字符串列表） |
| `robots` | 己方全部机器人的完整状态（见下表） |
| `enemies`、`enemy_drones` | 当前可见的敌方机器人（含残骸）与敌方空中机器人 |
| `messages`、`message_inboxes` | 队内消息 |
| `vision` | 每个受控观察者看到的机器人与相机参数 |
| `positions` | 四个控制点：`owner, kind, zones, controller, control（full/temporary）, progress, active` |
| `bases`、`outposts` | 基地与前哨站：`x, y, z, hp, max_hp, owner, armor_open, ever_destroyed, rotation, rotation_stopped, armor_plates` |
| `teams` | 己方经济：`resources` 金币、`purchased_17/42`、`tech_income`、`level_cap`、`completed_difficulties`、`control` 控制度、`energy_units_left`、`launcher_unlock_s`、`fortress_ammo`、`attack_damage` 等；对方只有 `attack_damage` 与 `control` |
| `zones` | 各增益卡当前的 `owner`、`occupants`、`contested` |
| `runes`、`assemblies` | 己方能量机关；双方科技核心装配状态（含 `cores`、`operation`、`blocked_reason`） |
| `projectiles` | 可见弹丸 |
| `arena` | 地图几何 |
| `referee` | 裁判快照：`robots`（不含位置）、`bases`、`outposts`、`positions`、`control`（双方控制度）、`logistics`（己方 λ）、`economy`、`events` |
| `logistics`、`logistics_effects` | 己方后勤系数 λ，以及表 5-19 在当前基地血量下的实际缩放：`respawn_time_scale`、`supply_heal_scale`、`remote_heal_scale`、`interaction_bandwidth_bytes`（每条消息的有效字节上限）、`fpv_resolution`（`width`、`height`、`pixels_scale`） |

`robots` 中每台机器人的常用字段：

| 字段 | 含义 |
| --- | --- |
| `id`、`slot`、`model_slot`、`team`、`role` | `role` 取值 `heavy`、`infantry`、`aerial`、`sentry` |
| `x, y, z`、`vx, vy, vz`、`heading`、`aim`、`pitch` | 位置、速度、底盘朝向、云台水平角与俯仰 |
| `hp`、`max_hp`、`alive`、`weak`、`invulnerable` | 血量与状态 |
| `ammo`、`heat`、`max_heat`、`cooling_rate`、`overheated` | 弹量与热量 |
| `level`、`experience` | 等级与经验（步兵有效；重型等级来自装配） |
| `defense_buff`、`attack_multiplier`、`vulnerability`、`cooling_multiplier` | 当前增益 |
| `power_limit`、`buffer_energy_j`、`powered` | 功率 |
| `respawn_progress`、`respawn_required` | 复活进度 |
| `last_shot_time`、`last_damage_time` | 脱战判断：当前时间减去两者都不小于 6 s |
| `pending_ammo`、`pending_heal` | 待到账的远程兑换与回血 |
| `launcher`、`launcher_progress` | 重型发射机构状态与安装进度 |
| `carried_units`、`arm_joints`、`arm_tip`、`arm_mode` | 重型携带的能量单元与机械臂 |
| `posture`、`posture_enhanced`、`posture_time`、`posture_enhanced_time`、`posture_ready_at` | 哨兵姿态 |
| `drones` | 空中机器人系统的每架空中机器人 |
| `legs`、`transform_progress`、`upright`、`tipped` | 轮足腿长、折叠进度、翻倒状态 |

### Action

请用 `sdk.action(...)` 构造动作，它会提前拒绝未知字段。{{#robot}}下表只列出你的机器人用得到的字段。{{/robot}}

| 字段 | 取值 | 适用 | 说明 |
| --- | --- | --- | --- |
{{#c_ground}}
| `move` | `(vx, vy)` | 地面 | 世界坐标速度意图，[−1, 1] |
| `heading` | 弧度 | 地面 | 底盘朝向 |
| `yaw_rate` | rad/s，±12 | 地面 | 底盘目标角速度（小陀螺），优先于 `heading` |
| `aim`、`pitch` | 弧度 | 地面 | 云台世界水平角、俯仰角 |
| `fire` | bool | 地面射手 | 本次决策期间是否射击 |
| `power` | 瓦 | 地面 | 底盘功率预算 |
| `buy_ammo` | `{"amount": n, "remote": bool}` | 重型、步兵、哨兵 | 兑换弹量 |
| `remote_heal` | bool | 地面 | 远程回血 |
| `revive` | bool | 地面 | 阵亡时立即复活 |
{{/c_ground}}
{{#c_s3}}
| `leg_height`、`jump`、`lean` | 米 / 0–1 / rad | 轮足 | 腿长、起跳、机体俯仰 |
{{/c_s3}}
{{#c_fold}}
| `transform` | bool | 折叠型号 | 折叠 / 展开炮塔 |
{{/c_fold}}
{{#c_infantry}}
| `profile` | 字符串或字典 | 步兵 | 性能选择，仅 `tick == 0` 有效 |
| `rune_start` | bool | 步兵、哨兵 | 发起能量机关激活 |
{{/c_infantry}}
{{#c_heavy}}
| `pick_unit` | bool | 重型 | 在己方资源岛拾取能量单元 |
| `assembly` | 1–4 | 重型 | 开始装配 |
| `assembly_insert`、`assembly_lift`、`assembly_flip` | bool | 重型 | 插入、抬升、翻转 |
| `assembly_rotate` | 度 | 重型 | 旋转到的目标角度 |
| `assembly_confirm` | bool | 重型 | 确认装配 |
| `assembly_core` | 0 / 1 / 2 | 重型 | 4 级装配操作的核心（2 = 双臂同时） |
| `install_launcher` | bool | 重型 | 在工作台安装发射机构，须持续发送 |
| `rescue` | 编号 | 重型 | 用机械臂扶正该翻倒队友 |
| `arm`、`arm2` | 字典 | 重型 | 直接控制机械臂（`{"tip": [...], "dir": [...]}`、`{"joints": [...]}` 或 `{"stow": True}`）；省略为自动 |
{{/c_heavy}}
{{#c_sentry}}
| `posture` | `"attack"`、`"defense"`、`"move"` | 哨兵 | 切换姿态，5 s 冷却 |
| `posture_enhanced` | bool | 哨兵 | 开启 / 关闭当前姿态的强化 |
| `rune_start` | bool | 哨兵 | 发起能量机关激活 |
{{/c_sentry}}
{{#c_aerial}}
| `drones` | `{"1": 命令, ...}` | 空中机器人系统 | 每架空中机器人的命令，见「空中机器人系统」 |
{{/c_aerial}}
| `messages` | 列表 | 全部 | 队内消息，见「队内通信」 |

不适用于当前机器人或当前状态的操作不会生效，有的会以 `invalid_action` 事件记录在回放中。字段名拼错会让整个程序被停用；`sdk.action` 会在你的代码里提前报错。

### SDK

`sdk.py` 是比赛环境中唯一可以导入的辅助库。它只做公开计算，不会给出额外信息。2026 的通用函数（`nearest_enemy`、`aim_at`、`aim_pitch`、`ballistic_reachable`、`intercept`、`can_fire`、`navigate`、`toward`、`distance`、`terrain_height`、`referee_info`、`message`）在 2027 同样可用，并已按赛季处理 42mm 弹道、重型发射机构状态与禁区。2027 新增：

| 函数或常量 | 作用 |
| --- | --- |
| `rules(obs)`、`RULES_2027`、`season_of(obs)` | 当前赛季的完整规则参数 |
| `TEAM_SLOTS_2027`、`DESIGNS` | 2027 编号与机器人设计 |
| `position(obs, name)`、`controls(obs, name, team=None)`、`control_degree(obs, team=None)` | 控制点与控制度 |
| `zone_center(arena, zone_id)` | 增益卡中心，例如 `"blue_central"`、`"red_supply"` |
| `workbench_point(robot, arena)`、`launcher_ready(robot)` | 工作台停靠点；发射机构是否已解锁待安装（未解锁时也可提前安装，见「重型机器人」） |
| `resource_pickup_point(robot, arena)`、`assembly_work_point(robot, arena)` | 资源岛拾取点、装配停车点 |
| `drones(robot)`、`strike_plan(drone, plate)`、`hostile_plates(obs, kind)` | 空中机器人列表、撞击规划、可撞击的装甲 |

瞄准前哨站时传入 `dict(obs["outposts"][对方], kind="outpost")`，瞄准能量机关目标时传入 `dict(target, kind="rune_target")`。`sdk` 在导入时预先计算两个赛季的导航图，这部分时间不计入决策时限。

{{^adaptive}}
{{> common/communication}}
{{/adaptive}}
