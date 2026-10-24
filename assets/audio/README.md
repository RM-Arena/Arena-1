# 广播配乐与击打声

`frontend/src/audioPlaylist.ts` 对应各个播放阶段。首页/大厅、赛后数据与 MVP 使用 `compose_score.py` 原创合成的配乐；赛前选边、局内开场与对局高光使用随仓库发布的 `<cue>-theme.m4a`（同录音另带 `.mp3`，供不解码 AAC 的浏览器使用）。想在本机替换某个提示位，放 `<cue>-custom.m4a` / `.mp3` 到 `frontend/public/assets/audio/` 即可（该槽位被 `.gitignore` 排除，不会提交）。

| 阶段 | 文件 | 来源 / 编配 |
| --- | --- | --- |
| 首页/大厅/菜单 | arena-theme.m4a | 原创合成（110 BPM，D 小调混合管弦，87 秒无缝循环） |
| 出战机库 | hangar.m4a | 原创合成（100 BPM，机械感琶音与圆润低音） |
| 裁判自检 / 阵容介绍 | RM 对战用 home.mp3，自由对战用 intro-free.m4a | 用户提供的曲目 |
| 赛前选边 / 选机 | pick-theme.m4a → .mp3 | 用户提供的曲目 |
| 五秒倒计时 | countdown.m4a | 原创合成（独立五秒渐强，滚奏与低音鼓） |
| 局内开场 | match-theme.m4a → .mp3；放完循环 summoning-glory.m4a → .mp3 | 用户提供的曲目 |
| 胜利动画 | victory.m4a | 原创合成（126 BPM，铜管式合成音与庆祝旋律） |
| 赛后数据 | results-summary.m4a | 原创合成（90 BPM，降 E 大调钢琴固定音型与暖色铺底，85 秒） |
| MVP | mvp-fanfare.m4a | 原创合成（96 BPM，降 B 大调号角，50 秒） |
| 对局高光 | highlight-theme.m4a → .mp3 | 用户提供的曲目 |

`compose_score.py` 生成 arena-theme、results-summary 与 mvp-fanfare，统一到 −18 LUFS、−1.5 dBTP；`compose_broadcast.py` 生成 hangar、countdown、victory 与 self-check 生成源。`results-theme.*` / `mvp-theme.*` 保留为不解码 AAC 时的兜底，`self-check.m4a` 保留为生成源、不再播放。生成源需要 NumPy 与 SciPy，以及 macOS 的 afconvert 或 ffmpeg 编码 AAC，正常启动应用无需这些音频生成依赖。

## 响度与衔接

各提示位母带的整体响度仍有差异（`arena-theme` 约 -18.2 LUFS、`mvp-fanfare` 约 -18.0 LUFS，`summoning-glory` 约 -8.0 LUFS，`highlight-theme` 约 -32.2 LUFS），所以 `audioPlaylist.ts` 不再手调 `gain`：每个 cue 的 `lufs` 是整首曲子的实测值，播放增益由 `musicGain` 统一折算到 `MUSIC_LEVEL`（-16.5 LUFS）。局内开场接循环段、以及赛后胜利 → 数据 → 高光 → MVP 的几次切换因此电平一致。跨 cue 切换是交叉淡入淡出，`match` 更会在结尾前 2.4 秒就提前接入 `match_alt`；`match_alt` 的 `loopEnd` 停在 111.25 秒，避开母带尾部约 2.6 秒的静音。

换掉或重新生成某个文件后，用下面的命令测整体响度，并更新对应 cue 的 `lufs`（不要单独改增益）：

```bash
ffmpeg -hide_banner -nostats -i <file> -af loudnorm=print_format=json -f null - 2>&1 | grep '"input_i"'
```

```bash
python3 assets/audio/compose_score.py
python3 assets/audio/compose_broadcast.py
bun run test:audio
bun run build
```

音频资源随前端构建复制到 `frontend/dist/assets/audio/`。击打音效仍使用Web Audio实时合成、空间声像、房间混响和限幅；低中频钢板模态与低频冲击替代原来尖短的高频敲击。`audibleEvents` 仅对音频去重，保留比赛原始事件与视觉效果。
