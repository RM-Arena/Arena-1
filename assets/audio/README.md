# 广播配乐与击打声

`frontend/src/audioPlaylist.ts` 对应八个播放阶段。正式比赛单独使用已有的 `summoning-glory.m4a`，每次进入比赛从0秒开始，完整播放并循环；暂停后继续保持位置。正式比赛之外均使用其他文件：

| 阶段 | 文件 | 编配 |
| --- | --- | --- |
| 首页/大厅/菜单 | arena-theme.m4a | 110 BPM，D 小调混合管弦：滤波琶音前奏、弦乐跳弓与圆号主歌、铜管主旋律副歌、钢琴与合唱桥段，尾声收回前奏无缝循环（87 秒） |
| 出战机库 | hangar.m4a | 100 BPM，机械感琶音与圆润低音 |
| 裁判自检 / 阵容介绍 | RM 对战用 home.mp3，自由对战用 intro-free.m4a | 用户提供的曲目；intro-free 由 bgm2.flac 转为 48 kHz AAC 192 kbps，去掉开头静音并把响度调到约 −17 LUFS。self-check.m4a 保留为生成源，不再播放 |
| 五秒倒计时 | countdown.m4a | 独立五秒渐强，滚奏与低音鼓 |
| 胜利动画 | victory.m4a | 126 BPM，铜管式合成音与庆祝旋律 |
| 赛后数据 | results-summary.m4a | 90 BPM，降 E 大调钢琴固定音型与暖色铺底，依次加入轻节奏与木琴旋律、弦乐旋律、合唱（85 秒） |
| MVP | mvp-fanfare.m4a | 96 BPM，降 B 大调号角：开场全奏重击、持续低音上的弦乐固定音型、小号与圆号主题、主和弦高潮，两小节渐强接回开场（50 秒） |

首页/大厅、赛后数据与 MVP 三首由 `compose_score.py` 原创合成：弦乐、铜管与合唱为带限锯齿波失谐合奏（合唱经元音共振峰滤波），钢琴为加法合成，钟琴/木琴为 FM 与模态合成，鼓与打击乐为物理近似模型，再经合成厅堂混响、母带均衡与限幅，统一到 −18 LUFS、−1.5 dBTP。音符、滤波与混响尾音越过结尾时回绕到开头，循环处无缝。机库、自检、胜利与倒计时仍由 `compose_broadcast.py` 合成。全部非比赛配乐均为原创，没有剪取正式比赛曲。生成源需要 NumPy 与 SciPy，以及 macOS 的 afconvert 或 ffmpeg 编码 AAC，正常启动应用无需这些音频生成依赖。

```bash
python3 assets/audio/compose_score.py
python3 assets/audio/compose_broadcast.py
bun run test:audio
bun run build
```

音频资源随前端构建复制到 `frontend/dist/assets/audio/`。击打音效仍使用Web Audio实时合成、空间声像、房间混响和限幅；低中频钢板模态与低频冲击替代原来尖短的高频敲击。`audibleEvents` 仅对音频去重，保留比赛原始事件与视觉效果。
