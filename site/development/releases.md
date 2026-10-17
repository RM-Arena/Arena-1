# 构建与发布

## 本机构建

完成源码环境准备后：

```sh
bun run desktop:prepare
bun run desktop:pack
```

`desktop:prepare` 构建当前与历史 Rust 引擎、生产前端，并下载独立 Python 运行环境。
Python 依赖按 `uv.lock` 的版本与哈希安装。运行时保存在 `build/desktop-runtime/`，
`resources.sha256.json` 记录打包资源指纹。

`desktop:pack` 生成可运行的未压缩应用；`bun run desktop:dist` 生成当前系统的安装包。
不要在不同处理器架构之间复制 Python 或 Rust 二进制。各系统应在对应原生 runner 构建。

## 自动化

- `Checks`：Windows / macOS / Linux 原生测试，另有 Linux Docker 隔离测试。
- `Desktop installers`：手动运行或推送 `v*` 标签，构建四种系统/架构组合并上传安装包和 SHA256。
- 标签构建全部成功后，创建 GitHub Release 并附上安装包。
- `Documentation`：main 分支相关文档改动后构建 VitePress，部署到 GitHub Pages。

macOS 开发构建使用 ad-hoc 签名（`mac.identity: "-"`），封装应用及内嵌二进制的完整性；
CI 在收集安装包前执行 `codesign --verify --deep --strict`，校验失败即停止发布。
ad-hoc 签名不提供 Apple 开发者身份认证，也不等同于公证，浏览器下载后仍可能被 Gatekeeper 拦截。
旧版安装包提示“已损坏”时，参见[macOS 启动问题](../guide/faq#macos-damaged)。

正式面向公众分发且希望免去手动放行时，需要配置 Developer ID Application 签名与 macOS 公证，
并启用相应的 hardened runtime 和 entitlements。私钥和账户凭据仅通过 CI secrets 提供，不能放入仓库。
当前配置未提供 Developer ID 签名或公证。

## 发布核对

确认测试通过、许可证与第三方声明完整，确认运行数据和凭据未进入版本控制，
检查安装后无需开发工具即可启动，退出后没有遗留后台服务。检查画面、音频、策略训练、
标准/自由对战、导入导出、录像与回放，记录每个平台实际验证结果。

## 策略独立发布

策略分发仓库为 [RM-Arena/Arena-Strategies](https://github.com/RM-Arena/Arena-Strategies)。
支持在线更新的客户端在启动后后台检查，并每 15 分钟自动检查一次；
策略库中的「检查更新」可以立即触发检查。用户无需 Git、GitHub 账号或额外令牌。

客户端先校验下载大小、SHA256、归档路径、源码语法、manifest 版本、规则与展示文件，
全部通过后才切换到新快照。同名在线策略优先于内置版本，用户上传的策略单独保留。
下载失败或断网时继续使用缓存与内置策略；运行中的比赛继续读取原版本文件。
缓存保存在用户数据目录下的 `.arena_data/strategy-library/`，不修改安装目录。

维护策略时，在独立仓库修改 `strategies/<名称>/` 并 push 到 `main`；
Actions 自动生成并提交 `catalog.json` 与 `bundles/<sha256>.zip`，无需创建 Release。
代码修改后需要通过原有提交工具重建 manifest 的源码哈希与版本。
如果策略依赖新的引擎、规则或 SDK，提高该仓库 `library.json` 中的 `min_client_version`。

第一次初始化独立仓库时，可从主仓库导出当前已跟踪且兼容的示例：

```sh
uv run --locked python scripts/strategies/export.py --output build/strategy-repository
```

此命令包含独立发布脚本、Actions 工作流、许可和初始策略包，不导出未跟踪的本地实验。
后续策略直接在独立仓库维护；主仓库 `examples/` 保留为离线后备。

**旧安装包需要先升级到支持在线更新的版本一次。** 此后仅策略更新不需要新的安装包；
引擎、UI 或 SDK 更新仍走正常桌面发布流程。需要关闭联网检查时，设置环境变量
`RMUC_STRATEGY_UPDATES=0`，已有缓存仍可使用。

## 文档站

```sh
bun run docs:dev
bun run docs:build
```

站点基路径为 `/Arena-1/`，发布地址为
[rm-arena.github.io/Arena-1](https://rm-arena.github.io/Arena-1/)。
它是静态项目文档；比赛和策略执行仍在本地桌面应用或本机服务中进行。
