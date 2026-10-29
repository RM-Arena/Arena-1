# CLI、并行对局与强化学习

安装项目后可使用 `rmuc-arena`；从源码运行时，以下命令均可写为 `uv run --locked python -m rmuc_arena …`。查看所有命令：

```sh
rmuc-arena --help
rmuc-arena run --help
rmuc-arena env --help
rmuc-arena doctor
```

CLI 的比赛和训练不依赖浏览器、Electron 或 HTTP 服务，也不修改本机 Elo。输出使用 JSON；批量比赛逐行输出 JSONL，进度只写 stderr。

## 并行跑比赛

```sh
# 32 个连续种子，最多 4 局同时运行；默认 Docker 策略隔离。
rmuc-arena run --games 32 --seed 100 --workers 4 --output replays/eval-001

# 指定策略、种子与红蓝换边；下例信任仓库内的示例代码。
rmuc-arena batch --red claude_opus55_xhigh_2027_team \
  --blue claude_opus55_xhigh_2027_hold \
  --seeds 11 23 47 --swap-sides --workers 4 --trusted-local \
  --duration 60 --output replays/eval-002 --progress

# 调整并发数后续跑：已成功的任务跳过，失败或未完成的任务重试。
rmuc-arena run --games 32 --seed 100 --workers 2 \
  --output replays/eval-001 --resume
```

`run`、`batch`、`headless` 和 `match` 共用调度器，`-j` 是 `--workers` 的简写。`--games` 为连续种子个数，`--seeds` 为显式种子列表，两者互斥；`--swap-sides` 会把实际局数翻倍。每局在独立 Python 工作进程中拥有自己的 Rust 仿真进程和策略进程。调度器限制并发数，不会为全部任务一次性启动进程。

`--timeout` 控制每份策略的决策预算，默认 **0.2 秒**；并行运行不会放宽这个默认值。`--match-timeout` 是包含策略启动时间的单局墙钟上限。`--fail-fast` 在出现错误或策略超时后停止调度新任务。Ctrl+C（POSIX 也支持 SIGTERM）会通知正在执行的比赛退出，并保留已经落盘的结果。

并行度过高时，CPU 争用可能造成策略超时；可减小 `--workers` 并用同一个输出目录 `--resume`。不要直接把一台机器的逻辑核数当成必然适用的并行度。

### 输出与回放

输出目录包含：

| 文件 | 内容 |
| --- | --- |
| `run.json` | 任务清单、策略版本、引擎/规则/SDK 指纹与配置 |
| `results.jsonl` | 按完成顺序写入的单局结果；`index` / `job_id` 保留原调度顺序 |
| `summary.json` | 有效比赛的胜负统计、错误数、完成数、耗时与并发数 |
| `replays/000000.json` | 仅在启用录制时生成 |

每个比赛结果含 `seed`、`swapped`、`status`、`outcome`、最终状态摘要、digest、策略元数据和工作进程 PID。`outcome` 始终相对于最初的策略 A，即换边前的红方。含策略错误、失败或被中断的比赛不进入有效胜负统计。

默认批量比赛不创建回放 spool，不保留逐帧状态和动作历史，以减少训练期间的磁盘与内存开销。

```sh
rmuc-arena run --games 8 -j 4 --replays all --output replays/recorded
rmuc-arena run --games 8 -j 4 --replays errors --output replays/debug
rmuc-arena match --trusted-local --duration 30 --output replays/single.json
rmuc-arena replay info replays/single.json
rmuc-arena replay verify replays/single.json
```

`errors` 会在运行期间录制，但只保留异常比赛。单个 `.json` 输出仍支持旧的单局用法，其 stdout 保留单行结果，运行日志和汇总在同名 `.run` 目录中；多局比赛必须使用目录。已有运行目录默认拒绝覆盖。续跑会验证策略版本和引擎、规则、SDK、种子及配置；有变化时应新建运行目录。只允许同一时刻有一个调度器写入该目录。

### 阵容、战场参数与自由对战

```sh
rmuc-arena settings --season 2027 --output battle-defaults.json
rmuc-arena settings --season 2027 --schema
rmuc-arena models --season 2027 --role infantry
rmuc-arena models --season 2027 --model 2731

rmuc-arena run --season 2027 --games 16 -j 4 \
  --settings battle-settings-2027.json --output replays/custom
```

`--settings` 接受设置页导出的平面参数 JSON，或直接传 JSON 对象。标准对局中红蓝各自使用策略锁定的合规阵容，只要求双方赛季一致；`--lineup` 接受 JSON 或文件，供未声明阵容的一方使用。地图省略时由策略赛季推断；只指定 `--season 2026` 时会使用该季的默认策略。

自由对战绑定已保存的单机策略，型号和阵容约束由现有引擎校验。可重复部署同型号策略：

```sh
rmuc-arena run --mode deck --season 2027 --games 8 -j 4 \
  --red-deck '["claude_opus55_xhigh_2027_adaptive_2731","claude_opus55_xhigh_2027_adaptive_2771"]' \
  --blue-deck '["claude_opus55_xhigh_2027_adaptive_2732"]' \
  --trusted-local --output replays/free-eval
```

某一方改用全队控制时，加 `--red-control team --red-team-strategy <key>` 或对应蓝方参数。换边会同时交换卡组与控制器。

### 不同配置组成一个任务集

`--jobs jobs.json` 接受 JSON 数组。每个元素是一局配置，可覆盖策略、seed、duration、season、map、lineup、settings、mode、卡组、控制器和 `swap_sides`。字段名使用下划线；文件中的相对路径以 `jobs.json` 所在目录为基准。不可同时使用 `--games` / `--seeds`。

```json
[
  {"seed": 11, "season": "2027", "duration": 30, "swap_sides": true},
  {"seed": 12, "season": "2026", "duration": 30}
]
```

```sh
rmuc-arena run --jobs jobs.json -j 3 --trusted-local --output replays/mixed
```

## 强化学习环境

`env` 提供持续运行的环境进程，而不是反复启动完整 CLI。每个环境的 `reset` 复用 Rust 进程，清空仿真和策略私有状态。默认控制双方，便于自博弈；也可以给学习侧指定一个已保存的对手策略。未显式选择赛季和共同阵容时，会采用对手的赛季与已注册阵容。

### Python 接口

```python
from rmuc_arena.vector_env import VectorArena

# multiprocessing 的 spawn 需要标准的 __main__ 保护。
if __name__ == "__main__":
    with VectorArena(4, duration=30, compact=True) as envs:
        states = envs.reset(seeds=[100, 101, 102, 103])
        for _ in range(100):
            actions = [{"red": {}, "blue": {}} for _ in states]
            states = envs.step(actions)
            ended = [i for i, s in enumerate(states)
                     if s["terminated"] or s["truncated"]]
            if ended:
                resets = envs.reset(seeds=[1000 + i for i in ended], env_ids=ended)
                for i, reset in zip(ended, resets):
                    states[i] = reset
```

动作就是策略 SDK 的按编号字典，例如 `{"red":{"3":{"move":[1,0],"fire":true}}}`。未知字段、越权机器人和跨队通信仍会被拒绝。`--action-repeat` 默认 2 个物理 tick，即 0.1 秒仿真时间；较大的偶数值会在多个策略周期保持学习侧动作。策略对手仍每 2 tick 决策一次。

返回结构：

- `observations.red/blue`：与策略 SDK 相同的局部观测和队内消息。
- `rewards.red/blue`：零和奖励。默认正常结束时胜方 +1、负方 -1、平局 0；`reward="score"` 额外加入双方攻击伤害增量差乘 `score_scale`（默认 0.001）。
- `terminated`：比赛按引擎规则自然结束，包含比赛计时结束的判定。
- `truncated`：训练器的 `max_steps` 提前截断；截断本身不发胜负奖励。
- `info`：seed、episode、tick、事件、胜负、策略错误数、引擎/规则指纹、工作进程和仿真 PID；结束时额外返回 digest。

环境不会自动 reset，终局观测会保留。对部分环境 reset 不影响其他环境。`compact=True` 在 reset 时发送场地和规则静态摘要，后续省略重复字段；动态机器人型号信息仍保留。`full_state=True` 为中心化训练额外返回 `info.state`，这属于特权状态，不应用作受限策略的实战观测。

`ArenaEnv` 是单环境接口；`VectorArena` 为每个环境启动独立进程。它们不强制固定长度的观测张量、动作向量或训练框架，可以由调用方编码为神经网络输入，也可以直接使用原始 SDK 结构。

单机器人技能和分层 PPO 训练由独立的 [Arena-RL](https://github.com/RM-Arena/Arena-RL) 仓库维护，复用这些接口和同一个 Rust 模拟器。

训练可以在 reset 时设置初始位置、朝向和弹量，方便从坡底、目标附近开始课程：

```python
states = envs.reset(
    [11], env_ids=[0],
    scenarios=[{"robots": {"red-3": {"x": 4.7, "y": 5.1, "heading": 0, "ammo": 200}}}],
)
```

对应 JSONL reset 请求可传入 `scenarios` 数组，与 `env_ids` / `seeds` 一一对应。场景只在初始化时应用；位置受场地边界约束，未知字段会被拒绝。此类环境保持测试对局身份，初始条件写入回放，验证器也从相同场景开始复现。机器人策略动作不能修改这些初始条件。

学习程序在外部提交动作，因此自身的 GPU 推理不受策略比赛的 200 ms 预算约束；保存的对手策略仍默认采用该预算。此接口用于本机训练，不向训练器开放修改物理或裁判状态的动作。

运行完整的 reset/step/部分重置示例：

```sh
uv run --locked python examples/rl_rollout.py --envs 4 --steps 200 --duration 10
uv run --locked python examples/rl_rollout.py --envs 4 --steps 200 \
  --opponent claude_opus55_xhigh_2027_hold --trusted-local
```

### JSONL 接口

其他语言或训练框架可以直接通过标准输入/输出通信，无需 HTTP 服务：

```sh
rmuc-arena env --num-envs 2 --season 2027 --compact
rmuc-arena env --num-envs 4 --opponent claude_opus55_xhigh_2027_hold --trusted-local
```

启动先输出 `{"type":"ready","protocol":"arena-env-v1",...}`。随后一行请求对应一行响应：

```json
{"id":"reset-1","op":"reset","seeds":[11,12]}
{"id":"step-1","op":"step","actions":[{"red":{},"blue":{}},{"red":{},"blue":{}}]}
{"id":"reset-one","op":"reset","env_ids":[1],"seeds":[13]}
{"id":"close","op":"close"}
```

响应包含原 `id`、`ok`、`type` 和按所选 `env_ids` 顺序排列的 `results`；每个环境有自己的 `env_id`、`ok`、`result` 或 `error`。单个环境的非法动作不会停止其他环境。多环境请求不是事务：部分环境报错时，成功环境可能已经推进，应读取各自响应。Python 高层接口此时抛出 `VectorEnvError`，完整响应保存在 `.responses`；也可使用 `VectorArena.request()` 自行处理。

`--record` 启用回放后，可发送 `{"op":"save_replay","env_ids":[0],"paths":["replays/episode.json"]}`。回放可在现有播放器中观看并逐帧验证。EOF、`close` 或 Ctrl+C 会回收环境进程及其仿真和策略子进程。`--rpc-timeout` 控制故障演员的响应上限，不是模型推理的时间上限。

自由阵容的训练可使用 `--lineups`，格式为 `{"red":[{"slot":1,"model":2731}],"blue":[{"slot":1,"model":2771}]}`。不与共同 `--lineup` 同时使用；2027 型号合规及每方最多一套空中机器人系统等约束继续由引擎执行。

## 策略管理

```sh
rmuc-arena strategies sync
rmuc-arena strategies list --season 2027 --mode team
rmuc-arena strategies list --search Claude
rmuc-arena strategies show claude_opus55_xhigh_2027_team
rmuc-arena validate claude_opus55_xhigh_2027_team
```

可用目录路径、策略 key，或 `bundled:<key>`、`remote:<key>`、`local:<key>` 明确选择来源。列表查询只读取已有的在线缓存，不会下载或执行策略。`strategies sync` 主动执行一次下载与校验，`--cache` 可指定独立缓存目录。

开发流程继续使用 `new-agent`、`start-training`、`refresh-agent`、`submit` 和 `assemble`。将训练器生成的模型决策包装为正常 `act(observation, state)` 策略后，仍通过提交校验和比赛执行器参加策略对局。
