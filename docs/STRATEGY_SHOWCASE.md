# 策略展示文件 showcase.json

策略库不展示源代码，而是用 `showcase.json` 把策略画成看得懂的战术卡：风格雷达、七分钟阶段时间线、战术地图上的路线与站位、关键决策和优劣势。**完成策略开发后，在提交前写好这个文件**；网页上传策略时也必须一并上传。它只用于展示，不影响比赛，也不改变策略版本号。

- 文件名固定为 `showcase.json`，UTF-8 编码的 JSON，最大 64 KiB。
- 内容必须如实描述你写的程序，不要写程序做不到的事。
- 文字面向观众：简短、具体，用比赛术语，不贴代码。
- 坐标单位为米，统一以**己方视角**填写：己方基地在左侧 (2.4, 7.5)，敌方基地在右侧 (25.6, 7.5)。场地 x 为 0–28，y 为 0–15。

常用地标（己方视角）：己方前哨站 (11.0, 11.4)，敌方前哨站 (17.0, 3.6)，己方堡垒 (6.6, 7.5)，敌方堡垒 (21.4, 7.5)，中央能量机关 (14.0, 7.5)，己方高地 (9.2–10.8, 7.5)，己方装配区 (13.3, 6.8)，己方补给区 (1.4, 12.3)，己方资源区 (1.0, 13.1)，己方飞坡 (10.6–16.3, 14.4)，停机坪 (1.4, 1.85)。

## 字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `format` | 是 | 固定为 `"rmuc-showcase-v1"` |
| `title` | 是 | 策略名，≤ 40 字 |
| `tagline` | 是 | 一句话打法，≤ 80 字 |
| `summary` | 是 | 2–4 句概述，≤ 600 字 |
| `style` | 是 | 六项 0–100 的整数：`aggression` 进攻、`defense` 防守、`economy` 经济/科技、`objective` 目标（前哨/基地/能量机关）、`teamwork` 协同、`adaptability` 应变 |
| `phases` | 是 | 1–8 个阶段，按时间顺序且不重叠，`from`/`to` 为比赛秒数（0–420），`title` ≤ 24 字，`goal` ≤ 160 字，`focus` 取 `attack`、`defense`、`economy`、`objective`、`support` 之一 |
| `units` | 否 | 至多 16 项，每台机器人或一组机器人的分工：`name` ≤ 16 字（如 "1号英雄"、"步兵组"、"本机"），`role` ≤ 20 字，`task` ≤ 160 字，`route` 至多 12 个 `[x, y]` 路线点，`anchor` 可选的主要站位 `[x, y]` |
| `rules` | 否 | 至多 10 条关键决策：`when` ≤ 60 字的条件，`then` ≤ 80 字的动作 |
| `priorities` | 否 | 至多 6 个目标优先级，按先后排列，每项 ≤ 24 字 |
| `strengths` / `weaknesses` | 否 | 各至多 5 条，每条 ≤ 80 字 |
| `generated_by` | 否 | 生成本策略的模型，如 `{"provider": "anthropic", "model": "Claude Opus 5.5"}` |

`provider` 可取：`openai`、`anthropic`、`google`、`meta`、`spacexai`、`moonshot`、`zai`、`xiaomi`、`deepseek`、`qwen`、`tencent-hy`、`bytedance-seed`、`human`。

单机策略（单机专精、自由适配）的 `units` 一般只写 `"本机"` 一项；全队策略按编号写六台或按小组写。

## 示例

```json
{
  "format": "rmuc-showcase-v1",
  "title": "钢铁洪流",
  "tagline": "英雄远程拆前哨，步兵三路压上高地",
  "summary": "开局工程抢资源、空中机器人打能量机关。英雄在己方高地远程拆敌方前哨站，步兵护送并压制敌方步兵。前哨倒下后全队推进基地，残血机器人回补给区复活。",
  "style": {"aggression": 78, "defense": 42, "economy": 60, "objective": 90, "teamwork": 72, "adaptability": 55},
  "phases": [
    {"from": 0, "to": 45, "title": "开局布阵", "goal": "工程拾取资源，步兵占领己方高地", "focus": "economy"},
    {"from": 45, "to": 200, "title": "拆除前哨", "goal": "英雄远程集火敌方前哨站，步兵掩护", "focus": "objective"},
    {"from": 200, "to": 420, "title": "总攻基地", "goal": "全队推进，集火基地装甲", "focus": "attack"}
  ],
  "units": [
    {"name": "1号英雄", "role": "远程炮台", "task": "在高地边缘架炮，优先打前哨站", "route": [[1.6, 6.05], [9.2, 7.5]], "anchor": [10.2, 7.0]},
    {"name": "2号工程", "role": "经济核心", "task": "资源区拾取，随后装配科技核心", "route": [[1.6, 8.95], [1.0, 13.1], [13.3, 6.8]]}
  ],
  "rules": [{"when": "基地血量低于 2000", "then": "步兵全部回防堡垒"}],
  "priorities": ["敌方前哨站", "敌方英雄", "敌方基地"],
  "strengths": ["前哨站倒得快"],
  "weaknesses": ["被绕后时英雄缺少保护"],
  "generated_by": {"provider": "anthropic", "model": "Claude Opus 5.5"}
}
```

---

# Strategy showcase file: showcase.json

The strategy gallery never shows source code. It renders `showcase.json` as a readable tactics card: a style radar, a seven-minute phase timeline, routes and positions on the tactical map, key decisions, strengths and weaknesses. **Write this file once the strategy is finished, before you submit.** Uploads through the web page must include it too. It is display-only: it does not affect matches or the strategy version.

- The file is always named `showcase.json`, UTF-8 JSON, at most 64 KiB.
- Describe what your program really does; do not claim behaviour it lacks.
- Write for spectators: short, concrete, in match terms, no code.
- Coordinates are metres from **your own side**: your base on the left at (2.4, 7.5), the enemy base on the right at (25.6, 7.5); x runs 0–28 and y 0–15.

Landmarks (own side): own outpost (11.0, 11.4), enemy outpost (17.0, 3.6), own fortress (6.6, 7.5), enemy fortress (21.4, 7.5), central rune (14.0, 7.5), own highland (9.2–10.8, 7.5), own assembly zone (13.3, 6.8), own supply zone (1.4, 12.3), own resource zone (1.0, 13.1), own fly slope (10.6–16.3, 14.4), aerial pad (1.4, 1.85).

The fields are those in the Chinese table above: `format` (`"rmuc-showcase-v1"`), `title` (≤ 40), `tagline` (≤ 80), `summary` (≤ 600), `style` (six integers 0–100: `aggression`, `defense`, `economy`, `objective`, `teamwork`, `adaptability`), `phases` (1–8 ordered, non-overlapping, `from`/`to` in match seconds 0–420, `title` ≤ 24, `goal` ≤ 160, `focus` one of `attack`, `defense`, `economy`, `objective`, `support`), and the optional `units` (≤ 16 with `name` ≤ 16, `role` ≤ 20, `task` ≤ 160, `route` ≤ 12 points, optional `anchor`), `rules` (≤ 10 `when`/`then`), `priorities` (≤ 6), `strengths` and `weaknesses` (≤ 5 each) and `generated_by` (`provider` from the list above, plus `model`). Single-robot strategies usually list one unit for themselves. The example above is a complete file.
