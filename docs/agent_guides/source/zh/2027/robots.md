## 兵种机制

{{#c_heavy}}
### 重型机器人

重型机器人兼任 2026 的英雄与工程：开局没有发射机构，先用机械臂搬运能量单元完成科技核心装配，再在工作台装上模块化 42mm 发射机构，成为全队唯一的 42mm 火力。

**性能阶段**（不使用经验）：

{{heavy_stages}}

- 开局到 180 s（或装上发射机构为止）获得 50% 防御。在己方补给区内无敌；装配进行中在装配区内累计最多 45 s 无敌。
- **能量单元**：在己方资源岛（`zone_center(arena, "red_resource")`，蓝方对称）附近发送 `pick_unit=True` 拾取，机械臂会自动伸向最近的单元；最多同时携带 2 枚（`carried_units`）。每队一共 6 枚（`teams[己方]["energy_units_left"]`），用完不再补充。
- **装配**：载着能量单元开到己方装配区，发送 `assembly=等级` 开始；核心就位后每次动作带上当前步骤的命令：`assembly_insert=True` → `assembly_lift=True` → `assembly_flip=True` → `assembly_rotate=目标角度（度）` → `assembly_confirm=True`（1 级只有插入与确认，2 级多一个抬升）。机械臂处于自动模式时会自己对准核心；确认时底盘必须停稳。`observation["assemblies"][己方]` 的 `operation`、`cores[k]["operation"]`、`target_rotation`、`blocked_reason` 告诉你当前步骤和阻碍原因。
- 4 级需要携带 2 枚单元，`assembly_core=0` 操作自己的核心，`1` 操作借用的核心，双臂型号可用 `2` 同时操作。两个核心的目标角度独立；双臂同时工作时以 `assembly_rotate` 控制第一臂、`assembly_rotate2` 控制第二臂；单臂仍用 `assembly_rotate` 控制当前核心。成对步骤必须在 5 s 内在两个核心上完成（翻转除外）。
- **发射机构**（`launcher`）：`locked` → `unlocked` → `installing` → `fitted` → `installed`；也可以在解锁前先装：`locked` → `installing` → `fitted_locked`，获得使用权后自动变为 `fitted`。
  - 解锁：本队完成 3 级装配，或比赛时间到达 300 − M/50 − 2N/3 s（M 为本局对方基地血量领先己方的最大值，N 为对方控制度领先的最大值；当前值见 `teams[己方]["launcher_unlock_s"]`）。
  - 安装：开到己方工作台（`sdk.workbench_point(robot, arena)`，0.45 m 内）停稳（< 0.05 m/s），**每次动作**都发送 `install_launcher=True`，`launcher_progress` 涨到 1 后变为 `fitted`。中途移动或停发命令会退回 `unlocked`（未解锁时退回 `locked`）。
  - 提前安装（官方答疑）：未解锁使用权时也可以在工作台安装，装好后为 `fitted_locked`。此时发射机构不上电，`fire` 无效，对方装甲也屏蔽 42mm 伤害；使用权解锁后变为 `fitted`。模块重量从装上起计入底盘，50% 防御仍保留到 `installed` 或 180 s。
  - 装上后的第一发 42mm 用于裁判系统确认（变为 `installed`），不造成伤害。之后才是有效火力。
- 42mm 弹量只能兑换获得（就地 1 发 / 10 金币，远程 10 发 / 150 金币），全队上限 100 发。
- **扶正队友**：2027 没有工程机器人，重型的机械臂可以扶正翻倒的队友：停在 `sdk.rescue_point(robot, target)` 并发送 `rescue=队友编号`（串联腿型号会自己翻身）。

{{/c_heavy}}
{{#c_sentry}}
### 哨兵

哨兵全自动运行，没有经验与等级：400 血，热量上限 260，冷却 30/s，底盘功率 100 W，开局 300 发 17mm。

- **补给**：每过 60 s 累积一份 100 发的配给，进入己方补给区时一次性领取全部未领配给（`ammo_delivered` 事件）。也可以花金币兑换。
- **姿态**（`posture="attack"|"defense"|"move"`，默认 `move`）：切换后 5 s 内不能再切换。同一姿态累计使用 180 s 后效果衰减。每种姿态有 15 s 的强化预算（`posture_enhanced=True`），用完后自动退出强化。

{{sentry_postures}}

- `posture_time` 是三种姿态（进攻、防御、移动）各自的累计秒数。被判黄牌时哨兵底盘断电 2 s。
- 哨兵可以发起能量机关激活，但不获得经验；被击杀时按 1 级计算。

{{/c_sentry}}
{{#c_aerial}}
### 空中机器人系统

6 号是一个固定在己方机库平台上的机库，搭载 2–4 架全自动空中机器人（数量见型号）。空中机器人**不能射击**，只能用机身撞击**基地装甲**和**前哨站中层装甲**（不能撞能量机关、机库或机器人）。它们没有血量，不能被击毁，但：

- 每次有效撞击造成 200 伤害（受目标防御影响），并磨损一次护罩；护罩耐撞次数用完后该机失效（`state="disabled"`）。每被 17mm 击中一次磨损 0.25 次耐撞并被弹丸动量推开；被 42mm 击中直接失效。降落或坠地的空中机器人（`state="down"`）可以重新起飞。
- 有效撞击需要：法向速度 ≥ 1.5 m/s 且冲量足够（仿真阈值见 `simulation_assumptions["drone_impact"]`），同一块装甲 0.2 s 内只计一次。
- 电池按实际悬停功率消耗，**在机库内不充电**；电量耗尽即坠落。
- 飞行高度上限 2.35 m（围挡 2.4 m），离开场地判红牌。
- 前哨被己方完全控制时对方基地无敌，所以撞击基地通常要等对方前哨控制点被夺取之后；撞击对方前哨站任何时候都有效（重建后属于你方的前哨站除外）。

指挥方式：在 6 号的动作中设置 `drones={"1": 命令, "2": 命令, ...}`（键是从 1 开始的机号）：

| 命令 | 含义 |
| --- | --- |
| `{"launch": True}` | 从机库起飞（先垂直爬升约 0.6 s） |
| `{"goto": [x, y, z]}` | 飞向一个点（比例控制，越近越慢） |
| `{"move": [vx, vy, vz]}` | 速度意图，各分量 [−1, 1]，乘以该机参考速度 / 爬升速度 |
| `{"dock": True}` | 返回机库并停靠 |
| `{"land": True}` | 原地降落 |

`robot["drones"]` 给出每架的 `state`（`docked`/`flying`/`down`/`disabled`）、`x, y, z`、速度、`battery_wh`、`integrity`、`strikes`、`dock` 等。`sdk.strike_plan(drone, plate)` 返回先飞到装甲前方、对正后全速冲撞的命令；`sdk.hostile_plates(obs, "outpost"|"base")` 列出可撞击的装甲。

{{/c_aerial}}
{{#c_infantry}}
### 步兵

- 唯一获得经验的兵种，等级上限受装配进度限制（5 / 7 / 10）。
- 可发起能量机关激活；首次完成公路、高地、隧道跨越与首次登上制高点各 +300 经验。
- 适合占领控制点：步兵在对方前哨或中央高地卡上 5 s 即可夺取对方前哨控制点，是开启控制度和打基地的前提。
{{#c_s3}}
- 轮足型号支持 `leg_height`、`jump`、`lean`，不能直接横移；登阶型号（`step_climb_m` > 0）可以登上制高点三级台阶、跳上隧道顶。
{{/c_s3}}
{{#c_fold}}
- 折叠型号用 `transform=True` 折叠炮塔，`transform_progress` 到 1 后可以钻过 0.25 m 的隧道，取得 120 s 的冷却 ×1.5 增益；变形中不能射击。
{{/c_fold}}

{{/c_infantry}}
