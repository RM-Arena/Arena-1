# 从源码运行

开发依赖：Python 3.12（最低 3.10）、uv、Node.js 22+、Bun 1.3.14+、stable Rust / Cargo。
Windows 使用 PowerShell、原生 Python 和 MSVC Rust 工具链；需要 Visual Studio C++ Build Tools。
Linux 运行桌面窗口需要图形桌面及 Electron 所需的系统库。

```sh
git clone https://github.com/RM-Arena/Arena-1.git
cd Arena-1
python scripts/project.py setup
python scripts/project.py desktop
```

在将解释器命名为 `python3` 的系统上，将命令中的 `python` 换成 `python3`。
首次准备需要联网下载依赖，后续运行不需要重新编译。

## 浏览器开发

```sh
python scripts/project.py run
```

打开 `http://127.0.0.1:8765`。前端热更新可另开终端运行 `bun run dev`，Vite 将 API 和
WebSocket 代理至 Python 服务。现有 `scripts/start.sh` 仍用于 macOS / Linux 一键准备和启动。

端口 8765 若已被别的程序占用（Windows 上输入法、Hyper-V 端口保留都会占它，`project.py` 会直接给出提示），
换一个端口即可：`python scripts/project.py run --port 8800`，访问 `http://127.0.0.1:8800`。

## 按赛季运行一局

CLI 默认使用内置的 Sol Max 三叉戟进行 2027 自博弈，地图按策略赛季推断；也可以显式指定：

```sh
uv run python -m rmuc_arena match --trusted-local --map rmuc2027 --duration 30
uv run --locked python -m rmuc_arena strategies sync
uv run python -m rmuc_arena match --trusted-local --map rmuc2026 --duration 30 --red claude_opus55_xhigh_team --blue claude_opus55_xhigh_hold
```

30 秒只用于检查启动与基本行为，完整判胜使用 420 秒。2026 和 2027 的策略、阵容与地图不能混用。命令里的 `claude_opus55_xhigh_*` 标明策略由 Claude Opus 5.5 xhigh 编写；界面提供便于比较的基线、守势与型号名称。

并行批量比赛和持久训练环境见 [CLI、并行与强化学习](./cli)。

## 更新规则、示例与文档插图

```sh
python scripts/configure_rmuc2027.py
uv run python scripts/build_examples_2027.py
uv run python scripts/build_robot_presets.py
uv run python scripts/build_agent_guides.py
python scripts/build_doc_diagrams.py
```

按修改范围运行相应生成器。2027 规则、场地和型号的入口分别是 `configure_rmuc2027.py`、`chapter4_2027_layout.py` 和 `robot_designs_2027.py`；两季合规检查在 `robot_compliance.py`。修改 Rust 引擎或它嵌入的规则配置后需要重新编译。

新手文档在 `site/guide/`，实际截图和 SVG 示意图在 `docs/media/`。`scripts/prepare-site.cjs` 把素材复制到站点公共目录；场地地点图读取 `config/rules.json`，修改配置后应重新生成并检查排版。原始规则与接口手册保留在 `docs/agent_guides`，不要把新手图解当成完整接口定义。

## 验证

```sh
python scripts/project.py test
bun run build
bun run docs:build
uv run python scripts/build_agent_guides.py --check
python scripts/build_doc_diagrams.py --check
uv run python scripts/check_release.py
```

Docker 隔离测试需构建沙箱镜像，并设置 `RMUC_DOCKER_TESTS=1`。
物理与策略数值测试不依赖浏览器。桌面端到端测试使用真实 Electron 与打包后端，Linux CI 使用 Xvfb。

长局策略表现单独运行：`uv run python scripts/benchmark_strategy.py`，也可以手动运行
Actions 的 `Strategy outcome benchmark`。其中“80 秒内完成指定开局路线”的指标在当前
macOS 参考环境通过，Linux 尚未达到；这类指标不作为应用功能可移植性的保证。
常规跨平台测试仍包含导航逻辑和物理飞坡机制检查。

不要提交 `node_modules`、虚拟环境、构建目录、比赛数据、开发令牌或个人策略工作区。

## 手册来源

模型生成与常规测试使用 `config/rules.json` 中已固定的来源记录，不依赖开发者的 Downloads 目录。
如需用自己持有的原版 PDF 核验来源，可设置 `RMUC_RULES_PDF` 或 `RMUC_CONSTRUCTION_PDF`；
脚本会检查文件指纹与固定的 2026 V1.0.0 版本一致。原始 PDF 不随仓库分发。

2027 的来源与歧义处理另见[规则对应与适配说明](https://github.com/RM-Arena/Arena-1/blob/main/docs/RULES_2027_IMPLEMENTATION.md)。上述两个 PDF 环境变量用于 2026 来源核验，不会自动切换为 2027。
