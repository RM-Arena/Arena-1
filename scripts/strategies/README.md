# Arena-Strategies

[Arena-1](https://github.com/RM-Arena/Arena-1) 的独立策略分发仓库。
支持在线策略更新的客户端会在启动后及运行期间每 15 分钟检查更新，
也可以在策略库点击「检查更新」。用户无需安装 Git、登录 GitHub 或重新下载安装包。


当前策略库要求 **Arena-1 v0.7.0-beta.1 或更新版本**。`claude_opus55_xhigh_*` 策略由 **Claude Opus 5.5 xhigh** 编写，覆盖 2026 与 2027 两个赛季；其他作者保持各自署名。此次更新同步更名策略目录、展示元数据与归档内容。

## 发布策略

1. 在 `strategies/<策略名称>/` 新增或修改完整提交：`manifest.json`、策略 `.py` 源码，
   以及可选的 `showcase.json`、`profile.json`。
2. 策略代码改动后，用 Arena-1 的提交工具重新生成 manifest，保证源码哈希与版本正确。
   仅修改展示文件时不需要重新计算代码版本。
3. 将改动 push 到 `main`。GitHub Actions 自动校验源码、生成不可变 ZIP 与 `catalog.json`，
   并提交生成文件。工作流成功后，客户端下一次检查即可收到更新。不需要创建 Release。

本地也可以使用 Python 3.10+ 预览发布结果，无第三方依赖：

```sh
python publish.py --tracked
```

先 `git add` 新文件，再运行带 `--tracked` 的发布命令。
PR 可以先运行 `python publish.py` 检查，但未合并到 main 的策略不会分发。

## 文件结构

```text
strategies/<name>/     策略源码、提交清单和展示文件
publish.py            可独立运行的发布工具
library.json          最低客户端版本
catalog.json          客户端读取的发布索引（自动生成）
bundles/<sha256>.zip   以内容哈希命名的策略快照（自动生成）
```

同名在线策略覆盖客户端内置版本；用户自己上传的策略独立保留。
下载或校验失败时客户端继续使用已有缓存与内置策略。更新不修改安装目录，
旧快照会保留以支持正在进行的比赛。删除在线策略后，客户端仍可能显示同名内置后备版本。

客户端会检查下载大小、SHA256、归档路径、源码语法、提交版本、规则版本及展示文件。
下载仅用于存储，策略在用户选择比赛后才会通过原有策略执行器运行。
如果新策略依赖新的 SDK、规则或引擎功能，请提高 `library.json` 的 `min_client_version`；
旧客户端会继续使用已有策略，并提示需要升级应用。

现有不含在线更新功能的安装包需要升级一次，之后策略可独立更新。
只有客户端引擎、界面或 SDK 功能变化时才需要新的 Arena-1 安装包。

## 许可

沿用 Arena-1 的[非商业学习许可证](LICENSE)。
