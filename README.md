<p align="center">
  <img src="assets/branding/arena-1.png" width="340" alt="Arena-1 · RM Arena" />
</p>

<p align="center"><strong>让 Agent 上场，也让人类看见新的打法。</strong></p>
<p align="center">
  <a href="https://github.com/RM-Arena/Arena-1/releases">下载桌面 App</a> ·
  <a href="https://rm-arena.github.io/Arena-1/">项目文档</a> ·
  <a href="https://github.com/RM-Arena/Arena-Strategies">策略仓库</a> ·
  <a href="#微信交流群">微信交流群</a>
</p>

Arena-1 是改编自 **RoboMaster 超级对抗赛（RMUC）** 的机器人策略对战平台。让 Agent 编写 Python 策略，在物理仿真中比赛，也可以接管机器人亲自驾驶。

支持 **RMUC 2027（默认，5v5）** 与 **RMUC 2026（6v6）**，提供策略训练、自由组队、回放、高光、MVP 与 MP4 录像。

> 当前为 **Beta**：`v0.8.0-beta.1`。版本变化见 [CHANGELOG](CHANGELOG.md)。

[![RMUC 2027 实际对战：开局双方空中机器人冲撞前哨站](docs/media/rmuc2027-battle.gif)](docs/media/rmuc2027-battle.mp4)

<p align="center"><a href="https://www.bilibili.com/video/BV1rJJD6cEfG/">Bilibili 演示</a> · <a href="docs/media/rmuc2027-battle.mp4">2027 对战实录</a> · <a href="docs/media/battle.mp4">2026 对战实录</a></p>

## 场地与对战

选择策略与阵容即可开赛。支持观战、第一视角驾驶（按 **P** 接管）、赛后数据与录像导出。

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
    <td><img src="docs/media/rmuc2027-pilot.jpg" alt="第一视角驾驶" /><p align="center">第一视角驾驶：按 P 接管一台地面机器人</p></td>
    <td><img src="docs/media/rmuc2027-highlight.jpg" alt="对局高光" /><p align="center">对局高光：从本场回放自动剪出关键片段</p></td>
  </tr>
  <tr>
    <td><img src="docs/media/rmuc2027-lineup.jpg" alt="出战机库的合规检查" /><p align="center">出战机库：不符合 2027 规范的型号不能选</p></td>
    <td><img src="docs/media/rmuc2027-free-battle.jpg" alt="自由对战只列出合规型号" /><p align="center">自由对战：只列合规型号，被排除的型号附原因</p></td>
  </tr>
</table>

2027 围绕控制点、科技装配与基地攻防展开；2026 保留经典兵种和规则。详见 [2027 规则图解](https://rm-arena.github.io/Arena-1/guide/rules-2027)与[两季对照](https://rm-arena.github.io/Arena-1/guide/seasons)。

![2027 控制点结构与控制度条件](docs/media/control-2027.svg)

## 策略开发

生成任务目录，把 `AGENT_TASK.md` 交给 Agent；实现 `act(obs, state)`，通过练习对战迭代，再提交参赛版本。支持全队统筹、单机组队、多机协同与自由适配。

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

策略可以有不同的分工与路线，例如基地控制与绕后：

![DeepSeek 1017 基地控制路线](docs/media/dsv41-1017-base-control.png)

**新增或更新策略，请提交到 [Arena-Strategies](https://github.com/RM-Arena/Arena-Strategies)，勿上传到本仓库的 `examples/`。** 此处仅保留 [GPT-6.1-Sol-Max 三叉戟](examples/gpt61_sol_max_2027)作为内置示例；其他策略可在客户端策略库获取。

## 快速开始

普通使用直接[下载桌面 App](https://github.com/RM-Arena/Arena-1/releases)，选择策略后开赛。

从源码运行需准备 Python、uv、Node.js、Bun 和 Rust，详见[开发指南](https://rm-arena.github.io/Arena-1/guide/development)：

```sh
git clone https://github.com/RM-Arena/Arena-1.git
cd Arena-1
python scripts/project.py setup
python scripts/project.py run
```

命令行批量对局与强化学习环境：

```sh
uv run --locked python -m rmuc_arena run --games 8 --workers 2 --trusted-local --output replays/demo
uv run --locked python -m rmuc_arena env --num-envs 4 --compact
```

`--trusted-local` 用于可信策略；隔离运行见开发指南。更多用法见 [CLI 与强化学习](https://rm-arena.github.io/Arena-1/guide/cli)。

[规则入门](https://rm-arena.github.io/Arena-1/guide/what-is-arena) · [策略开发](https://rm-arena.github.io/Arena-1/guide/strategies) · [常见问题](https://rm-arena.github.io/Arena-1/guide/faq) · [贡献指南](CONTRIBUTING.md)

## 微信交流群

交流机器人策略、比赛规则与项目开发。当前二维码已过期，待更新。

<p align="center">
  <a href="docs/media/wechat-group.png"><img src="docs/media/wechat-group.png" width="300" alt="RM-Arena 微信交流群二维码，有效期至 2026 年 10 月 22 日" /></a>
</p>

**禁止商用，仅供非商业学习。** 详见 [LICENSE](LICENSE) 与[第三方素材说明](THIRD_PARTY_NOTICES.md)。本项目独立开发，不代表赛事方或商标权利人。
