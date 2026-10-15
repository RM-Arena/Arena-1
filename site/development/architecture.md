# 系统架构

```text
Electron 桌面窗口
  └─ React / Three.js / WebGL 2
       └─ HTTP + WebSocket → 本机 Python / FastAPI
                               ├─ Rust / Rapier 仿真进程
                               ├─ Python 策略进程（或 Docker 容器）
                               └─ 用户数据目录
```

桌面版复用浏览器版的生产构建，不分叉渲染器、不压缩纹理或简化模型。抗锯齿、阴影、
像素比、色调映射和曝光由现有 `frontend/src/ArenaScene.tsx` 统一定义。

Rust 物理仿真采用 120 Hz 内部步进，对外每 0.05 秒更新一帧，策略每两帧决策一次。
随机种子、规则与引擎指纹随回放保存。跨架构的数值结果仍需通过 CI 与同轨迹对比验证，
不能仅凭相同种子假定所有构建逐字节一致。

## 桌面进程生命周期

Electron 启动打包后的 Python，后者原子绑定一个可用的本机端口，再初始化服务。
父进程核验实例标识和健康状态后加载界面，避免误连接到已存在的其他服务。
应用退出时通过标准输入通知后端正常结束；父进程连接断开也触发后端退出。

默认使用可信本地模式。Docker 模式保持原有网络、文件系统、进程和资源隔离规则。
两者不会静默互相降级。

## 平台适配

- 引擎响应通过读取线程与队列传递，兼容 Windows 子进程管道。
- 注册表使用 POSIX flock 或 Windows 字节范围锁，防止多进程更新丢失。
- 本地策略退出使用对应系统的进程树清理方式。
- Windows 使用 `.exe` 与 `.venv/Scripts` 路径。
- 资源位于安装包中，训练、提交及回放写入每个用户独立的数据目录。

## 目录

| 目录 | 用途 |
| --- | --- |
| desktop | Electron 窗口、菜单和后端生命周期 |
| rmuc_arena | 服务、策略执行、训练、提交和回放 |
| simulation | Rust 仿真与物理测试 |
| frontend | React / Three.js 界面与资源 |
| assets | Blender 与音频生成源 |
| examples | 可运行的策略与展示文件 |
| tests | Python 回归与接口测试 |
| scripts | 构建、验证和跨平台开发命令 |
| site | GitHub Pages 文档站 |
| docs | 完整规则手册、硬件设计和实现审计 |
