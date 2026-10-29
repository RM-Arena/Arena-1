# 广播配乐与击打声

`frontend/src/audioPlaylist.ts` 对应各个播放阶段。每个提示位的主题曲都以项目资产的形式随仓库发布：`<cue>-theme.m4a` 提供 AAC 版本，同一录音再配一份 `.mp3`，供不解码 AAC 的浏览器使用。想在本机替换某个提示位，放 `<cue>-custom.m4a` / `.mp3` 到 `frontend/public/assets/audio/` 即可（该槽位被 `.gitignore` 排除，不会提交）。

| 阶段 | 文件 | 来源 |
| --- | --- | --- |
| 首页/大厅/菜单 | arena-theme.m4a → .mp3 | 原创合成（compose_score.py）：110 BPM，D 小调混合管弦：滤波琶音前奏、弦乐跳弓与圆号主歌、铜管主旋律副歌、钢琴与合唱桥段，尾声收回前奏无缝循环（87 秒） |
| 出战机库 | hangar.m4a | 原创合成（100 BPM，机械感琶音与圆润低音） |
| 赛前过场 / 选边 | pick-theme.m4a → .mp3 | 用户提供的曲目 |
| 五秒倒计时 | countdown.m4a | 原创合成（独立五秒渐强，滚奏与低音鼓） |
| 局内开场 | match-theme.m4a → .mp3；放完循环 summoning-glory.m4a → .mp3 | 用户提供的曲目 |
| 胜利动画 | victory.m4a | 原创合成（126 BPM，铜管式合成音与庆祝旋律） |
| 赛后数据 | results-theme.m4a → .mp3 | 用户提供的曲目 |
| MVP | mvp-theme.m4a → .mp3 | 用户提供的曲目 |
| 对局高光 | highlight-theme.m4a → .mp3 | 用户提供的曲目 |

首页/大厅主题由 `compose_score.py` 原创合成：弦乐、铜管与合唱为带限锯齿波失谐合奏（合唱经元音共振峰滤波），钢琴为加法合成，钟琴为 FM 合成，鼓与打击乐为物理近似模型，再经合成厅堂混响、母带均衡与限幅，统一到 −18 LUFS、−1.5 dBTP。音符、滤波与混响尾音越过结尾时回绕到开头，循环处无缝。同一母带另出 192 kbps MP3 孪生文件，供不解码 AAC 的浏览器使用。机库、倒计时与胜利仍由 `compose_broadcast.py` 合成（self-check 保留为生成源）。全部非比赛配乐均为原创，没有剪取正式比赛曲。生成源需要 NumPy 与 SciPy，以及 macOS 的 afconvert 或 ffmpeg 编码 AAC、ffmpeg（或项目环境中的 imageio-ffmpeg）编码 MP3，正常启动应用无需这些音频生成依赖。

```bash
python3 assets/audio/compose_score.py
python3 assets/audio/compose_broadcast.py
bun run test:audio
bun run build
```

音频资源随前端构建复制到 `frontend/dist/assets/audio/`。播放器在解码后测量每首曲子的门限 RMS 响度（400 ms 分块，剔除静音与弱段），把所有提示位（赛前、局内、赛后数据、MVP 与高光）统一到同一目标电平（约 −10 dBFS），没有任何提示位再额外加高。因此用户替换的 `-custom` 曲目即使母带更响或更轻，也会被自动压回同一分贝。提示位切换使用约 1.4 秒的交叉淡入淡出，旧曲在新曲解码完成前继续播放，不会出现静音空档。击打音效仍使用Web Audio实时合成、空间声像、房间混响和限幅；低中频钢板模态与低频冲击替代原来尖短的高频敲击。`audibleEvents` 仅对音频去重，保留比赛原始事件与视觉效果。
