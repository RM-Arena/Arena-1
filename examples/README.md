# 策略示例

这里只保留 `gpt61_sol_max_2027`（GPT-6.1-Sol-Max 三叉戟）。`rl_rollout.py` 是训练接口示例，不是参赛策略。

> 本仓库（fork）额外保留了整套 2027 策略目录（`claude_opus55_xhigh_2027_*`、`dsv41_*`、`gemini38_*`、
> `gpt61_2027_*` 等）。它们由 `scripts/robot_policy_2027.py` 生成，用于本地座舱直接选用与回归，
> 视觉与调参改动需要跟着这些副本一起生效；提交到上游时仍只保留 `gpt61_sol_max_2027`。
> 用 `python scripts/build_examples_2027.py` 重新生成，`python scripts/build_robot_presets.py` 更新预设卡。

请勿向本目录上传其他策略。所有新增和更新的策略请提交至
[Arena-Strategies](https://github.com/RM-Arena/Arena-Strategies)，按该仓库的赛季/厂商/策略目录结构提交。
