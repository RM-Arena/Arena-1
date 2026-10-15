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

## 验证

```sh
python scripts/project.py test
bun run build
bun run docs:build
uv run python scripts/build_agent_guides.py --check
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
