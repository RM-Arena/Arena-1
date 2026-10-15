## 练习与提交

所有命令都在你的工作目录中运行：

```bash
python3 -B arena.py status                  # 剩余时间、已提交版本、练习任务
python3 -B arena.py test [选项]              # 用当前 {{source_summary}} 启动一批练习对局
python3 -B arena.py results JOB_ID           # 查看练习进度与结果
python3 -B arena.py replay JOB_ID --game 0   # 把第 0 局的完整回放保存到 practice/
python3 -B arena.py submit                   # 提交当前 {{source_summary}}
```

### 练习对局

| 选项 | 默认 | 说明 |
| --- | --- | --- |
| `--opponent` | `baseline` | `baseline`：公开基准策略（偏防守）；`self`：和当前代码自己对战；也可以填 `status` 中列出的你自己已提交的版本号 |
| `--duration` | 30 | 每局时长（秒），1–420；正式比赛为 420 |
| `--games` | 1 | 局数，种子从 `--seed` 起依次加 1 |
| `--seed` | 42 | 第一局的种子 |
| `--swap-sides` | 关闭 | 每个种子红蓝各打一局，局数翻倍 |

```bash
python3 -B arena.py test --opponent baseline --duration 30
python3 -B arena.py test --opponent self --duration 420 --games 4 --swap-sides
python3 -B arena.py test --opponent 版本号 --duration 420 --games 2 --seed 200
```

- 启动时会给当前 {{source_files}} 拍快照，之后修改文件不影响这批对局。
- 同一时间只能运行一批练习，服务繁忙时会排队。排队和运行时间都计入开发时间；一局 420 s 的对局需要数分钟真实时间，请据此安排。
- 练习使用与正式比赛相同的容器和限制，不计排名，也不消耗正式比赛次数。
{{#team}}
- 练习中你的程序控制己方全部机器人；`self` 对战时双方都是你的代码。
{{/team}}
{{#robot}}
{{^adaptive}}
- 练习中你的程序只控制 {{slot}} 号，**其余{{count_others}}台由公开的示例策略控制**；`self` 对战时双方的 {{slot}} 号都是你的代码，其余仍是示例策略。示例队友只是陪练，不代表正式比赛中队友的行为。
{{/adaptive}}
{{#adaptive}}
- 练习使用变化的卡组：你的代码控制一个所选型号的实例，部署编号以 `controlled_ids[0]` 为准；队友数量和型号由练习安排，运行公开示例。`self` 对局双方各有你的一个实例，其余由示例控制。
{{/adaptive}}
{{/robot}}

### 结果与回放

- `results` 返回每局的胜方、判定原因、结束时间、你所在的一方（`candidate_team`）、双方队伍数据（攻击伤害、击杀、金币等），以及你的程序出错的次数（`policy_errors`）。程序出错时，`diagnostics` 会附带错误信息和最近的日志（包括 `print` 输出）。
- `replay` 把完整回放保存到 `practice/`：包括每一步的全场状态、双方动作和事件，可以用自己写的脚本分析。420 s 对局的回放约 300 MB，请按需下载。

### 提交

- `submit` 把当前 {{source_files}} 保存为一个不可修改的版本，并返回版本号。
- 可以多次提交，**截止前最后一次成功提交即参赛版本**。之前提交的版本可以用作练习对手（`--opponent 版本号`）。
- 提交前确认：练习中没有错误或超时；没有依赖 `practice/` 里的文件；最坏情况下的耗时远低于 200 ms。
- 不要把最后一次提交拖到截止前一刻，也不要把练习过但没提交的代码当成最终版本。截止后仍可查看已有的结果和回放，但不能再练习或提交。
