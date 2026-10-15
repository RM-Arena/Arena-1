# 安装与启动

从 [GitHub Releases](https://github.com/RM-Arena/Arena-1/releases) 下载与你的系统和处理器匹配的安装包。
如果尚未发布正式版本，可先[从源码运行](./development)。

| 系统 | 安装格式 | 架构 |
| --- | --- | --- |
| macOS | DMG / ZIP | Apple Silicon arm64、Intel x64 |
| Windows | 安装程序 EXE / ZIP | x64 |
| Linux | AppImage / DEB | x64 |

安装包内含 Python 运行环境、Rust 引擎和前端资源。日常使用无需安装 uv、Bun、Node.js 或 Rust。
显卡与驱动需支持 Chromium 的 WebGL 2 渲染。各平台构建和测试结果以仓库 Actions 为准。

Ubuntu 24.04 及更新版本优先使用 DEB 包，安装过程会配置所需的 Chromium 沙箱与 AppArmor 规则。
AppImage 是否能直接启动取决于发行版的用户命名空间策略；不要以关闭系统安全功能作为安装步骤。

## 第一次运行

1. 安装或解压应用，打开 Arena-1。
2. 在主页选择训练、RM 对战或自由对战。
3. 使用内置策略体验对局，或创建自己的策略开发任务。
4. 在“比赛与回放”查看保存的比赛；通过应用菜单打开数据目录。

应用会在本机回环地址启动私有服务，自动选择空闲端口。关闭应用会停止比赛并清理后台进程。
桌面版与浏览器版共享同一套界面和渲染配置。

## 策略执行模式

默认“可信本地策略”模式，无需 Docker，会以当前用户权限执行 Python 策略。
只在该模式下运行你信任的代码。菜单中的“执行模式”可以切换到 Docker 隔离，切换会停止当前比赛。

Docker 模式需要单独安装并启动 Docker，并构建项目沙箱镜像：

```sh
docker build -t rmuc-arena-policy:0.4 -f sandbox/Dockerfile .
```

Docker 不可用时应用不会静默改用本地执行。

## 数据位置

应用菜单“文件 → 打开数据目录”提供当前用户的数据位置。通常为：

- macOS：`~/Library/Application Support/Arena-1/`
- Windows：`%APPDATA%/Arena-1/`
- Linux：`~/.config/Arena-1/`

训练工作区、提交、比赛、回放、卡组及自定义模型均保存在此处，不写入安装目录。
更新应用时保留该目录即可保留数据；卸载前可先备份整个目录。

开发版构建尚未配置开发者签名及 macOS 公证。组织者发布签名版本后应优先使用签名安装包；
请仅从本仓库获取构建，按系统提示检查发布者，不需要关闭系统安全功能。
