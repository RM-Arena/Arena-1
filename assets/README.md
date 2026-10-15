# 3D 资产

`blender/build_assets.py` 是资产源程序。它读取 `config/rules.json`，创建英雄、工程、三套步兵、空中机器人、基地、前哨站、双面能量机关、科技核心与 RMUC 2026 地图，保存 `.blend`，导出 `frontend/public/assets/*.glb`。旧版资产保留用于历史回放。

```bash
blender --background --factory-startup --disable-autoexec --python assets/blender/build_assets.py
```

macOS 已安装 Blender 时也可以使用 `/Applications/Blender.app/Contents/MacOS/Blender`。

- 单位为米，机器人前方为 +X。Blender 的 Z 高度在 glTF 导出后成为 Three.js 的 Y。
- `Chassis`、`Turret`、`GunPitch`、`Wheel_*`、`Rotor_*` 和 `ArmorRotor` 是观战端控制的动画节点。
- `TeamPrimary`、`TeamGlow` 材质由前端根据红蓝阵营着色。
- 静态几何体按材质合并，保留动画节点，降低 draw call 数量。
- 地图掩体、坡道和高台读取与 Rust 相同的尺寸；外围设施位于可通行区域之外。
- 原始模型由项目中的 Blender 程序生成，未使用外部下载的角色或地图模型。

修改模型后重新导出，再运行 `bun run build`。修改地图规则还需重新编译 Rust；后端会拒绝使用规则指纹过期的二进制。

当前第四章版本的布局在 `scripts/chapter4_layout.py`，精细模型源在 `blender/chapter4.py`。输出为 `map-rmuc2026-ch4v3.glb`（`ch4v2` 保留给旧回放）、`base-ch4.glb`、`outpost-ch4.glb`、`rune-ch4v2.glb` 和 `tech-core-ch4v2.glb`；帧中的 `arena.asset` 与 `structure_assets` 决定加载哪一版模型，历史回放继续使用旧资产。尺寸来源和未标注部分的处理见 `docs/RULES_IMPLEMENTATION_AUDIT.md`。

六台制作规范模型由 `blender/robot_specs.py` 和 `config/rules.json.robot_designs` 生成；为起伏路段改型后的地面型号输出 `robot-N-spec2026v4.glb`，空中型号仍为 `robot-6-spec2026v2.glb` / `robot-60x-spec2026v3.glb`，旧版地面资产保留给历史回放。各模型含刚性75°装甲、精细轮组/悬架/云台，工程机械臂和双轮足连杆均保留动画节点；空中含完整25mm护罩网、保护杆、备用绳和向上航行灯。构建时采样扫描云台、工程臂与双轮足的收纳/展开包络，输出 `robot-N-envelope.json`。红蓝共用同一模型，只替换队伍材质。

增量构建可指定 `RMUC_ASSETS=robots,structures,map`；机器人可用 `RMUC_ROBOTS=2,3` 筛选。省略变量时执行完整构建。旧版 GLB 保留，当前配置加载 v2 资源。

- 工程动画节点：`ArmSlew`、`ArmMastStage`、`ArmLift`、`ArmReach`、`ArmWristYaw/Pitch/Roll`、`GripperJaw_0/1`；关节目标与仿真的 `arm_joints` 一致。
- 双轮足：`LegRF/RB/LF/LB_Upper/Lower` 和 `Wheel_0/1`；五连杆几何保存在 GLB 的 `leg_geometry` extras 中，前端按腿长解算。
- 串联腿（305）：`LegR/L_Thigh`（髋关节处）、`LegR/L_Shank`（膝关节处）和 `Wheel_0/1`；`leg_geometry` 带 `type: serial`，前端按腿长和引擎的 `hip_angle` 解算，髋角可整周旋转。
- 能量机关：每队一个 `RuneFace`，共同轴线两侧各 0.35 m；`RuneRotor`、`RuneArm_0..4`、箭头/靶区/激活环材质分别驱动灯效。 有效命中后灯臂显示金色，普通撞击短暂白闪；激活后整面灯效保持阵营色常亮，至 `active_until` 结束。反馈使用比赛时间，暂停、倍速与回放定位保持一致。
- 科技核心：`CoreCarriage/Lift/Yaw/Pitch/Roll` 对应装配坐标系的位姿，`CoreUnit` 显示插入的能量单元。

尺寸校验属于采样姿态检查；碰撞体使用低复杂度组合形状。机器人部件与未标注场地细节是本项目的工程设计，未作为官方完整 CAD 复刻。

## RMUC 2027

2027 资产源程序为 `blender/season2027.py`（由 `build_assets.py` 加载，复用第四章与制作规范模型的构建函数）。`RMUC_ASSETS=season2027` 只构建 2027 资产，`robots2027`、`map2027` 分别只构建机器人或地图，可再用 `RMUC_ROBOTS=2711,2761` 筛选；不会重新导出 2026 资产。完整构建时，`robots` 与 `map` 也会把 `season` 为 2027 的型号和地图交给这些构建函数。

```bash
RMUC_ASSETS=season2027 blender --background --factory-startup --disable-autoexec --python assets/blender/build_assets.py
```

- 地图 `map-rmuc2027.glb` 读取 `maps.rmuc2027`（由 `scripts/chapter4_2027_layout.py` 生成）。包含：0.3 m 中央高地、靠堡垒一侧的 0.2 m 台阶带和 0.4 m 边沿、两端 12° 坡；0.4 m 装配台（12° 斜边）和能量机关龙门；龙门立柱外侧的 0.4 m 机库平台（比装配台高 1.2 m，属于地图网格）；0.2 m 梯形高地和 23° 细阶坡；0.8 m 制高点、三级 0.2 m 台阶和护墙；0.2 m 公路、11°/15° 坡、起伏路段（70 mm 高，240 mm 间距）；每侧三条隧道（侧墙和顶板）；0.15 m 堡垒、0.2 m 基地台、0.4 m 前哨站台；补给区的工作台（0.75×0.45 m，顶面 0.40 m）和资源岛（6 个能量单元，Ø0.454 m 环，中心高 0.70 m）；飞镖站只作布景。地形顶面在中线处按 1.5° 屋脊式地板分割，高度与引擎地形一致；23° 坡的视觉细阶与 2026 版相同，物理仍为平滑坡。涂装包括队伍色的边界、出发区和增益卡轮廓，以及白色通行标识。资源岛中心待取的能量单元是 `AvailableUnit_<team>`，被抓起时由观战端隐藏。
- 重装机器人 `robot-2711/2712/2713-spec2027.glb`：底盘和机械臂节点与工程机器人相同（`ArmSlew`、`ArmMastStage`、`ArmLift`、`ArmReach`、`ArmWristYaw/Pitch/Roll`、`GripperJaw_0/1`，双臂另有 `Aux_` 前缀），升降行程 0.64 m。升降桅杆在车体前角（`arm.base_m`，距底盘中心 0.275 m），云台座 `Turret` 立在底盘中心的立柱上，与引擎的枪口轴心同轴；机械臂在任意升降高度都在云台与发射模块的偏航扫掠范围之外，只有枪管对准抬起机械臂所在的前角时才会相碰。`LauncherModule` 含完整的模块化 42 mm 发射机构，包括托架、俯仰支架、`GunPitch`（枪管、摩擦轮、42 mm 测速模块、弹仓和相机），尺寸约 0.385×0.30×0.26 m，未装配时由观战端隐藏。裸云台座（偏航环、定位销和接插件）不属于该节点，偏航电机固定在立柱顶板下方。不含发射模块时，收纳尺寸不超过 0.6 m。
- 步兵 2731/2732 和哨兵 2771/2772 沿用基础型号（304/301/303/305）的构建函数和全部动画节点，并加上 2027 涂装：橙色饰条、徽标，以及弹仓上的“27”环带。哨兵另有加高的弹仓料斗和顶部状态灯 `StatusBeacon`（随 `Turret` 转动）。
- 空中系统 2761/2762/2763 的 `robot-27x-spec2027.glb` 只含机库：0.30×0.30×0.20 m，前方为 +X，原点在底面中心。顶部有 `drone_count` 个停机位，`DroneBay_<k>` 标记停机坪中心和顶面；后侧嵌有裁判灯条，前侧有状态灯和图传。根节点 extras 含 `drone_count`、`drone_size_m` 和 `drone_asset`。机库没有 `Chassis` 节点，因此保持静止。
- `drone-27x-spec2027.glb` 是单架四旋翼，外形边长等于 `drone.size_m`（0.141/0.095/0.120 m）。每个桨叶的上、下和四周都有封闭护罩，格栅孔为 10 mm。顶部有 7 灯导航环（`TeamGlow`）。原点在几何中心，前方为 +X，动画节点为 `Rotor_0..3`。
- `robot-27xx-envelope.json` 按 2027 规则的收纳和展开尺寸采样；重装机器人的收纳尺寸不计发射模块，超限项记录在 `issues` 中。
