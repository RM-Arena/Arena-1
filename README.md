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

[![RMUC 2027 实际对战：开局双方空中机器人冲撞前哨站](docs/media/rmuc2027-battle.gif)](docs/media/rmuc2027-battle.mp4)

<p align="center"><sub>RMUC 2027 开局 11 秒：双方空中机器人预判旋转装甲，定时冲撞对方前哨站（<a href="docs/media/rmuc2027-battle.mp4">MP4</a>）· <a href="docs/media/battle.mp4">RMUC 2026 对战录像</a></sub></p>

## 为什么做 Arena-1

- **给 Agent 一个足够难的赛场。** RM 把局部视野、机动、射击、资源管理、机构操作和多机协同放在同一场比赛中，是检验 Agent 规划、编程与协作能力的好 testbed。
- **让人类提前看见可能的打法。** 从 Agent 的反复对抗中，快速观察战术组合、配合方式与攻防节奏，为真实比赛中的策略探索提供启发与前瞻。

## RMUC 2027 一览

- **控制点与控制度**：双方各有前哨控制点和基地控制点，占卡 5 秒即可夺取；到时先比控制度。己方前哨控制点被自己完全控制时，基地无敌。
- **新兵种**：
  - 重型机器人：搬运能量单元完成 1–4 级科技装配，解锁后在工作台装上模块化 42mm。
  - 全自动哨兵：进攻、防御、移动三种姿态。
  - 空中机器人系统：机库加全自动空中机器人，只能撞击建筑装甲。
- **新场地**：中央高地与装配台、能量机关龙门、机库平台、制高点台阶、公路起伏路段与三种隧道。
- **合规检查**：出战阵容和自由对战只允许符合所选赛季《机器人制作规范手册》的型号，不合规的会显示原因。

<table>
  <tr>
    <td><img src="docs/media/rmuc2027-battle.jpg" alt="RMUC 2027 RM 对战界面" /><p align="center">RM 对战 · RMUC 2027 5v5，计分板显示控制度</p></td>
    <td><img src="docs/media/rmuc2027-field.jpg" alt="RMUC 2027 场地全景" /><p align="center">2027 场地：中央高地、装配台与能量机关龙门、制高点、公路与隧道</p></td>
  </tr>
  <tr>
    <td><img src="docs/media/rmuc2027-drones.jpg" alt="空中机器人撞击前哨站" /><p align="center">空中机器人冲撞前哨站中层装甲</p></td>
    <td><img src="docs/media/rmuc2027-heavy.jpg" alt="重型机器人装配科技核心" /><p align="center">重型机器人在装配台装配科技核心</p></td>
  </tr>
  <tr>
    <td><img src="docs/media/rmuc2027-lineup.jpg" alt="出战机库的合规检查" /><p align="center">出战机库：不符合 2027 规范的型号不能选</p></td>
    <td><img src="docs/media/rmuc2027-free-battle.jpg" alt="自由对战只列出合规型号" /><p align="center">自由对战：只列合规型号，被排除的型号附原因</p></td>
  </tr>
</table>

规则对应与适配说明见 [RULES_2027_IMPLEMENTATION.md](docs/RULES_2027_IMPLEMENTATION.md)，型号设计见 [ROBOT_HARDWARE_DESIGNS.md](docs/ROBOT_HARDWARE_DESIGNS.md)。

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

训练、策略库等功能两个赛季通用（以下截图来自 RMUC 2026 界面）：

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

## 源码安装与开发 Quick Start

普通使用直接下载[桌面 App](https://github.com/RM-Arena/Arena-1/releases/latest) 即可。从源码运行和开发需要：

- Python 3.12（最低 3.10）和 [uv](https://docs.astral.sh/uv/)
- Node.js 22+ 和 [Bun](https://bun.sh/) 1.3.14+
- stable Rust / Cargo（Windows 用 MSVC 工具链）
- 可选：Docker（隔离运行策略）、Blender（重新生成 3D 资产）

**1. 准备并启动**

```sh
git clone https://github.com/RM-Arena/Arena-1.git
cd Arena-1
python scripts/project.py setup     # uv sync、bun install、编译 Rust 引擎、构建前端
python scripts/project.py run       # 浏览器打开 http://127.0.0.1:8765
python scripts/project.py desktop   # 或者以桌面窗口运行
```

`run` 默认以“可信本地策略”模式执行 Python 策略，只运行你信任的代码。要用 Docker 隔离，先执行 `python scripts/project.py setup --docker` 构建沙箱镜像，再用 `python scripts/project.py run --docker` 启动。

**2. 开发循环**

```sh
bun run dev                                                     # 前端热更新：http://127.0.0.1:5173，API 代理到 8765
cargo build --release --manifest-path simulation/Cargo.toml     # 改了 Rust 引擎或 config/rules.json 后重新编译
python scripts/configure_rmuc2027.py                            # 改了 2027 场地、型号或合规规则后重新生成配置
uv run python scripts/build_examples_2027.py                    # 改了 scripts/robot_policy_2027.py 后重新生成 2027 官方策略
uv run python scripts/build_robot_presets.py                    # 重新生成各型号的预置策略
uv run python scripts/build_agent_guides.py                     # 重新生成中英文参赛手册
```

**3. 命令行对局与测试**

```sh
uv run python -m rmuc_arena match --trusted-local --duration 60           # 2027 官方全队策略对守势策略
uv run python -m rmuc_arena match --trusted-local --duration 60 \
  --red examples/official_team --blue examples/official_hold              # 2026 策略自动使用 2026 地图
python scripts/project.py test                                            # Rust、Python、JS 与桌面端测试
```

接口、规则与开发细节见[项目文档](https://rm-arena.github.io/Arena-1/)和[从源码运行](site/guide/development.md)。

**禁止商用，仅供非商业学习使用。** 详见 [LICENSE](LICENSE) 与[第三方素材说明](THIRD_PARTY_NOTICES.md)。本项目独立开发，不代表赛事方或商标权利人。
