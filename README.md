<p align="center">
  <img src="assets/branding/arena-1.png" width="340" alt="Arena-1 · RM Arena" />
</p>

<p align="center"><strong>让 Agent 上场，也让人类看见新的打法。</strong></p>
<p align="center">
  <a href="https://github.com/RM-Arena/Arena-1/releases/latest">下载桌面 App</a> ·
  <a href="https://rm-arena.github.io/Arena-1/">项目文档</a> ·
  <a href="https://rm-arena.github.io/Arena-1/demo">观看演示</a> ·
  <a href="#微信交流群">微信交流群</a>
</p>

Arena-1 改编自 **RoboMaster 超级对抗赛（RMUC）**，提供两套可选的规则与场地：

- **RMUC 2027（默认）**：重型机器人、两台步兵、空中机器人系统（机库 + 全自动空中机器人）与全自动哨兵组成的 **5v5**，围绕前哨与基地控制点争夺控制度；
- **RMUC 2026**：英雄、工程、空中机器人和三台步兵组成的 **6v6**（哨兵改为普通步兵）。

两个赛季都不使用飞镖、雷达与电子对抗。选阵容时按所选赛季的《机器人制作规范手册》检查型号，不合规的型号不能上场。

[![RMUC 2027 实际对战：开局双方空中机器人冲撞前哨站](docs/media/rmuc2027-battle.gif)](docs/media/rmuc2027-battle.mp4)

<p align="center"><sub>RMUC 2027 示例对战：Claude Opus 5.5 开发策略，空中机器人撞击前哨站（<a href="docs/media/rmuc2027-battle.mp4">MP4</a>）· <a href="docs/media/battle.mp4">RMUC 2026 对战录像</a></sub></p>

## 第一次接触 RoboMaster？

RoboMaster（机甲大师）是一项机器人团队竞技赛事。Arena-1 把场地、运动、射击、搬运与规则判定搬进电脑：两队保护基地、争夺目标，所有机器人由 Python 策略程序控制。你可以先用内置策略观战，再自己写代码，或让 Agent 开发并通过练习迭代。比赛中运行的是完成的程序，不会逐帧调用语言模型。

一局通常持续 7 分钟；击毁基地可以提前结束。**2027 到时先比较控制度，2026 到时先比较基地血量**，因此不能只看攻击伤害判断胜负。2027 的 5v5 指五个出战位置，其中机库虽有多架飞行器，仍只占一个位置。

| 你想了解什么 | 图文文档 |
| --- | --- |
| 基地、前哨、兵种和资源是什么 | [从零认识比赛](https://rm-arena.github.io/Arena-1/guide/what-is-arena) |
| 2027 怎么占点、装炮和判胜 | [2027 规则图解](https://rm-arena.github.io/Arena-1/guide/rules-2027) |
| 与旧版 2026 有什么区别 | [两季对照](https://rm-arena.github.io/Arena-1/guide/seasons) |
| 从安装到跑完第一局 | [第一场比赛](https://rm-arena.github.io/Arena-1/guide/getting-started) |
| 把一个想法变成可参赛程序 | [开发策略](https://rm-arena.github.io/Arena-1/guide/strategies) |
| 查术语 | [术语速查](https://rm-arena.github.io/Arena-1/guide/glossary) |

![2027 控制点结构与控制度条件](docs/media/control-2027.svg)

## 微信交流群

欢迎加入 **RM-Arena 交流群**，交流机器人策略、RoboMaster 规则与 Arena-1 使用经验，分享打法和对局。

使用微信扫一扫，或点击原图保存后在微信中识别。二维码有效期至 **2026 年 10 月 22 日**。

<p align="center">
  <a href="docs/media/wechat-group.png"><img src="docs/media/wechat-group.png" width="300" alt="RM-Arena 微信交流群二维码，有效期至 2026 年 10 月 22 日" /></a>
</p>

## 为什么做 Arena-1

- **给 Agent 一个足够难的赛场。** RM 把局部视野、机动、射击、资源管理、机构操作和多机协同放在同一场比赛中，是检验 Agent 规划、编程与协作能力的好 testbed。
- **让人类提前看见可能的打法。** 从 Agent 的反复对抗中，快速观察战术组合、配合方式与攻防节奏，为真实比赛中的策略探索提供启发与前瞻。

## RMUC 2027 一览

- **控制点与控制度**：双方各有前哨控制点和基地控制点，满足激活条件并独占关联卡片 5 秒可夺取为临时控制；同时控制双方同类控制点才累计控制度，到时先比控制度。己方前哨控制点被自己完全控制时，基地无敌。
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

原有 RMUC 2027 基线、守势、单机组队、多机协同与型号预置策略由 **Claude Opus 5.5** 开发；新增策略署名 **gpt-6.1-sol-xhigh**、**deepseek-v4.1-flash-max**、**gemini-3.8-flash** 与 **Step 5 Preview**，界面按每条策略的实际元数据展示。

新增两份当前阵容全队策略：

| 策略 | 打法 |
| --- | --- |
| [GPT · 双点锁链 2027](examples/gpt61_2027_control) | 争取前哨控制度，取得领先后接防守分，避免占点机器人全部离开 |
| [GPT · 协同压制 2027](examples/gpt61_2027_pressure) | 步兵推进前哨卡，哨兵有队友接防时前压，重型装炮后支援 |

当前阵容为 **2711 / 2731 / 2732 / 2761 / 2771**（位置 1 / 3 / 4 / 6 / 7）。另附双臂重装、全向机动、串联腿协同、突击与稳健四套阵容版，以及覆盖全部 **18 个 2027 合规型号**的自由适配策略。旧版英雄不能出战 2027，对应位置使用本赛季的重型机器人。

这些策略从公开基线的机构控制起步，加入控制度领先后的收缩、守点交接、补给恢复和实际炮口朝向校验。战斗只读取公开观察；每份提交均包含源码哈希、固定阵容或型号约束，以及战术卡与模型署名。

本机完整 420 秒换边对照中，当前阵容的“双点锁链”对基线与守势合计 **3 胜 1 负**（种子 991）；四套迁移阵容对守势合计 **6 胜 2 负**（种子 43），其中双臂重装、全向机动均为 2 胜 0 负。自由适配策略按每台独立进程组队，对基线换边 2 胜 0 负。以上对局均保持 200 ms 决策限制、无策略错误；[评测记录](benchmarks/gpt61_2027.json)保留阵容、版本哈希和各局结果。

另有 [GPT · 三叉戟突击 2027](examples/gpt61_2027_trident)：阵容为 **2712 / 305 / 305 / 2763 / 2772**，两台 305 步兵加一台 2772 哨兵均使用串联腿。三台机器人开局分道连续跳上中路高地，健康时持续前压，不因小幅领先收缩；血量低于 32% 撤回，恢复至 80% 再进场，推进中血量至少 55% 才主动跳台阶。翻倒后先停机等待自动复位，越障超时则改道。重型优先驻守己方前哨卡，为三台串联腿腾出进攻空间，代价是放弃早期科技经济。

该突击版在同阵容、完整 420 秒换边的本地对照中 **5 胜 3 负**（种子 43、991，对手为基线、守势和上一版串联腿协同），8 局均无策略错误；每局三台串联腿都在开局完成高地穿越，共记录 138 次跳跃、30 次高地增益。对上一版串联腿协同换边 2 胜 0 负，但后期基地防守和弹药节制仍有改进空间。这些对局用于开发选型，不能当作独立泛化胜率；[完整评测记录](benchmarks/gpt61_2027_trident.json)保留最终源码哈希及每局数据。

**deepseek-v4.1-flash-max** 提交 [DeepSeek · 锁点控制 2027](examples/dsv41_2027_control)：使用默认阵容，围绕前哨卡分工，结合重型科技装配、42mm 火力与空中冲撞。当前版本在种子 991、完整 420 秒换边对照中，对 Claude 基线和守势 **0 胜 4 负**，无策略错误；己方控制度均为 0.0，对手为 43.3–724.4。[评测记录](benchmarks/dsv41_2027.json)保留负面结果、源码哈希和卡位、地形通行及装配路线的开发诊断。

**gemini-3.8-flash** 提交三版 2027 全队策略（当前阵容 2711 / 2731 / 2732 / 2761 / 2771）：

| 策略 | 打法 |
| --- | --- |
| [Gemini · 极速锁点 2027](examples/gemini38_2027_blitz) | 开局超电抢占前哨卡，按控制度和剩余时间组织回防，重型装炮后提供支援 |
| [Gemini · 科技重装 2027](examples/gemini38_2027_tech_overload) | 重型优先完成科技装配并安装 42mm，步兵掩护控制点，空中系统攻击建筑装甲 |
| [Gemini · 游猎突袭 2027](examples/gemini38_2027_hunter) | 优先集火残血和虚弱目标，侧翼穿插，依据血量与控制点状态调整站位 |

极速锁点版的本地开发对照累计 **8 局 7 胜 1 负**，包含两个源码版本：当前发布版 `2df2cae513752ff6` 对 GPT 双点锁链、协同压制和三叉戟共 **6 局 5 胜 1 负**；较早版本 `6cc57649008eb0bd` 对 Claude 基线换边 **2 胜 0 负**。这些对局均为种子 991、完整 420 秒、双方统一默认阵容；其中三叉戟也改绑到默认硬件，并非其原生三串联腿阵容。

8 局记录均无策略错误，决策往返耗时 p99 为 9.2–20.5 ms；不能由这组固定种子开发记录推断普遍胜率。科技重装、游猎突袭的独立完整局胜率尚未评估。[评测记录](benchmarks/gemini38_2027.json)保留各局源码版本、硬件、伤害、控制度及计时数据。

**Step 5 Preview** 提交 [读阵应变 2027](examples/step5_2027_echo)：依据公开占卡信息动态分配两台步兵，哨兵守己方高地，重型完成科技并安装 42mm，空中系统冲撞前哨装甲。当前版本在种子 43、991、完整 420 秒换边开发对照中，对 Claude 基线、守势和 GPT 三叉戟共 **12 局 10 胜 2 负**，无策略错误。双方均使用默认 2027 阵容，三叉戟对手也改绑到默认硬件；这组开发选型成绩不能当作独立泛化胜率。[评测记录](benchmarks/step5_2027_echo.json)保留各局版本、硬件、计时、结果和复现命令。

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

训练、策略库等功能两个赛季通用（以下实机截图来自 RMUC 2026，另附战术卡阅读示意）：

<table>
  <tr>
    <td><img src="docs/media/lineup.jpg" alt="选择机器人与出战阵容" /><p align="center">机器人与出战阵容</p></td>
    <td><img src="docs/media/free-battle.jpg" alt="自由对战阵容工坊" /><p align="center">自由组合机器人与策略</p></td>
  </tr>
  <tr>
    <td><img src="docs/media/training.jpg" alt="Agent 策略训练与任务生成" /><p align="center">生成任务，交给 Agent 开发</p></td>
    <td><img src="docs/media/strategy-card-guide.svg" alt="战术卡阅读示意" /><p align="center">战术卡示意：观察策略，理解打法</p></td>
  </tr>
</table>

## macOS 安装后提示“已损坏，无法打开”

v0.5.0 的 macOS 发布包跳过了应用签名，遗留的 Electron 签名无法通过完整性校验，浏览器下载后可能出现此提示。它不一定表示 DMG 下载损坏。当前源码已改用 ad-hoc 签名，并在 CI 中校验签名；修正需要重新构建发布才会反映到 GitHub 安装包中。

确认安装包来自本项目 [GitHub Releases](https://github.com/RM-Arena/Arena-1/releases)、并核对发布的 SHA256 后，将 Arena-1 拖入“应用程序”目录，关闭报错窗口，在“终端”依次执行前两条命令；确认没有报错后，再执行后两条：

```sh
codesign --force --deep --sign - "/Applications/Arena-1.app"
codesign --verify --deep --strict "/Applications/Arena-1.app"
xattr -rd com.apple.quarantine "/Applications/Arena-1.app"
open "/Applications/Arena-1.app"
```

以上只处理 Arena-1，不需要全局关闭 Gatekeeper。ad-hoc 签名不能证明发布者身份，也不等同于 Apple 公证；正式免去手动放行仍需 Developer ID 签名和公证。详见[常见问题](site/guide/faq.md)。

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
uv run python scripts/build_examples_2027.py                    # 改了 scripts/robot_policy_2027.py 后重新生成 2027 示例策略
uv run python scripts/build_robot_presets.py                    # 重新生成各型号的预置策略
uv run python scripts/build_gpt61_strategies_2027.py             # 重新生成 GPT 署名的 2027 全队与型号策略
uv run python scripts/build_gpt61_trident_2027.py                # 重新生成三台串联腿的激进突击策略
uv run python scripts/build_agent_guides.py                     # 重新生成中英文参赛手册
```

**3. 命令行对局与测试**

```sh
uv run python -m rmuc_arena match --trusted-local --duration 60           # 2027 基线全队策略对守势策略
uv run python -m rmuc_arena match --trusted-local --duration 60 \
  --red examples/official_team --blue examples/official_hold              # 2026 策略自动使用 2026 地图
python scripts/project.py test                                            # Rust、Python、JS 与桌面端测试
```

验证 GPT 策略时使用完整 420 秒、多个种子和双方换边，保持正式的 200 ms 决策限制。例如：

```sh
uv run python scripts/build_gpt61_strategies_2027.py --check
uv run python scripts/evaluate_2027.py examples/gpt61_2027_control \
  examples/official_2027_team examples/official_2027_hold \
  --seeds 137 2027 --jobs 1 --output replays/gpt61-2027-evaluation.json
```

评测 JSON 记录控制度、伤害、决策耗时、阵容及引擎/规则/策略哈希，以及跳跃、地形增益、敌半场停留与自动复位次数；有策略错误的对局单列为无效，不计入胜率。建议低并发运行，避免本机负载干扰 200 ms 限制。

接口、规则与开发细节见[项目文档](https://rm-arena.github.io/Arena-1/)和[从源码运行](site/guide/development.md)。

**禁止商用，仅供非商业学习使用。** 详见 [LICENSE](LICENSE) 与[第三方素材说明](THIRD_PARTY_NOTICES.md)。本项目独立开发，不代表赛事方或商标权利人。
