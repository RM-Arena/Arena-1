# 广播配乐与击打声

`frontend/src/audioPlaylist.ts` 对应各个播放阶段。每个提示位的主题曲都以项目资产的形式随仓库发布：`<cue>-theme.m4a` 提供 AAC 版本，同一录音再配一份 `.mp3`，供不解码 AAC 的浏览器使用。想在本机替换某个提示位，放 `<cue>-custom.m4a` / `.mp3` 到 `frontend/public/assets/audio/` 即可（该槽位被 `.gitignore` 排除，不会提交）。

| 阶段 | 文件 | 来源 |
| --- | --- | --- |
| 大厅/菜单 | lobby.m4a | 原创合成（86 BPM，柔和合成铺底、电钢琴与轻节奏） |
| 出战机库 | hangar.m4a | 原创合成（100 BPM，机械感琶音与圆润低音） |
| 赛前过场 / 选边 | pick-theme.m4a → .mp3 | 用户提供的曲目 |
| 五秒倒计时 | countdown.m4a | 原创合成（独立五秒渐强，滚奏与低音鼓） |
| 局内开场 | match-theme.m4a → .mp3；放完循环 summoning-glory.m4a → .mp3 | 用户提供的曲目 |
| 胜利动画 | victory.m4a | 原创合成（126 BPM，铜管式合成音与庆祝旋律） |
| 赛后数据 | results-theme.m4a → .mp3 | 用户提供的曲目 |
| MVP | mvp-theme.m4a → .mp3 | 用户提供的曲目 |
| 对局高光 | highlight-theme.m4a → .mp3 | 用户提供的曲目 |

`compose_broadcast.py` 只负责原创合成的部分（lobby、hangar、countdown、victory，以及保留为生成源的 self-check、results、mvp）：`results.m4a` 与 `mvp.m4a` 仍会随脚本生成，但赛后数据与 MVP 两个画面现在由 `results-theme.*` / `mvp-theme.*` 接管。生成源需要 NumPy 与 ffmpeg，正常启动应用无需这些音频生成依赖。

```bash
python3 assets/audio/compose_broadcast.py
bun run test:audio
bun run build
```

音频资源随前端构建复制到 `frontend/dist/assets/audio/`。击打音效仍使用Web Audio实时合成、空间声像、房间混响和限幅；低中频钢板模态与低频冲击替代原来尖短的高频敲击。`audibleEvents` 仅对音频去重，保留比赛原始事件与视觉效果。
