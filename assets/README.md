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
