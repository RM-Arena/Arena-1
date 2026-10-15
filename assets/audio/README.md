# 广播配乐与击打声

`frontend/src/audioPlaylist.ts` 对应八个播放阶段。正式比赛单独使用已有的 `summoning-glory.m4a`，每次进入比赛从0秒开始，完整播放并循环；暂停后继续保持位置。正式比赛之外均使用其他文件：

| 阶段 | 文件 | 编配 |
| --- | --- | --- |
| 大厅/菜单 | lobby.m4a | 86 BPM，柔和合成铺底、电钢琴与轻节奏 |
| 出战机库 | hangar.m4a | 100 BPM，机械感琶音与圆润低音 |
| 裁判自检 / 阵容介绍 | RM 对战用 home.mp3，自由对战用 intro-free.m4a | 用户提供的曲目；intro-free 由 bgm2.flac 转为 48 kHz AAC 192 kbps，去掉开头静音并把响度调到约 −17 LUFS。self-check.m4a 保留为生成源，不再播放 |
| 五秒倒计时 | countdown.m4a | 独立五秒渐强，滚奏与低音鼓 |
| 胜利动画 | victory.m4a | 126 BPM，铜管式合成音与庆祝旋律 |
| 赛后数据 | results.m4a | 82 BPM，较平静的电钢琴与和声 |
| MVP | mvp.m4a | 110 BPM，聚焦英雄的主旋律与节奏 |

上述七个非比赛配乐由 `compose_broadcast.py` 原创合成，没有剪取正式比赛曲。曲目采用不同和声、旋律、音色与节奏，导出AAC并统一响度。生成源需要NumPy与ffmpeg，正常启动应用无需这些音频生成依赖。

```bash
python3 assets/audio/compose_broadcast.py
bun run test:audio
bun run build
```

音频资源随前端构建复制到 `frontend/dist/assets/audio/`。击打音效仍使用Web Audio实时合成、空间声像、房间混响和限幅；低中频钢板模态与低频冲击替代原来尖短的高频敲击。`audibleEvents` 仅对音频去重，保留比赛原始事件与视觉效果。
