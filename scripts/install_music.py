"""Install one of your own audio files over a game music slot.

The game ships its own soundtrack and never downloads music from video sites: whatever you play has to
be a file you already hold the rights to (your own recording, a licensed track, or a publisher's own
download). This helper puts such a file in the per-machine override slot of a cue, so the next page
reload uses it without overwriting the shipped asset:

  python scripts/install_music.py "D:/music/summoning glory.mp3" --slot match

Slots, the moments they score, and the project asset each one replaces:

  match      倒计时「5」起播的开场（放完接老曲循环）        match-theme.m4a / .mp3
  pick       赛前选边 / 选机体                              pick-theme.m4a / .mp3
  highlight  赛后对局高光                                   highlight-theme.m4a / .mp3
  results    赛后数据面板                                   results-theme.m4a / .mp3
  mvp        MVP 结算卡片                                   mvp-theme.m4a / .mp3

The file is written as `frontend/public/assets/audio/<slot>-custom.m4a` and `.mp3`, which the player
tries before the shipped theme. Both are written when ffmpeg is available; without it an
already-compressed MP3/M4A is copied as-is (MP3 preferred, because some browsers refuse AAC) and
anything else is refused with the install hint. The override files are ignored by git.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SLOTS = {
    "match": "倒计时「5」起播的开场（放完接老曲循环）",
    "pick": "赛前选边 / 选机体",
    "highlight": "赛后对局高光",
    "results": "赛后数据面板",
    "mvp": "MVP 结算",
}
AUDIO_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public" / "assets" / "audio"
PLAYABLE = {".mp3", ".m4a", ".aac", ".ogg", ".wav", ".flac"}


def which(name: str) -> str | None:
    found = shutil.which(name)
    if found or name != "ffmpeg":
        return found
    # `uv run --with imageio-ffmpeg` / a pip install of it ships a static binary that is not on PATH.
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def sniff(source: Path) -> tuple[str, bool]:
    """What the bytes actually are, and whether a video track is riding along.

    A download from a video site is an ISO-BMFF (MP4) container even when it is named `.mp3`, and it
    usually carries a `vide` track next to the audio. The extension decides which chain slot the file
    is written to, so it has to follow the bytes rather than the name.
    """
    with source.open("rb") as stream:
        head = stream.read(12)
    if head[4:8] == b"ftyp":
        with source.open("rb") as stream:
            chunk = stream.read(1 << 20)
        # `vide`/`soun` handlers live in `moov`, which a download keeps near the head or the tail;
        # either way a byte search over both ends is enough to warn.
        has_video = b"vide" in chunk
        if not has_video:
            with source.open("rb") as stream:
                stream.seek(max(0, source.stat().st_size - (1 << 20)))
                has_video = b"vide" in stream.read()
        return ".m4a", has_video
    if head[:3] == b"ID3" or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return ".mp3", False
    return source.suffix.lower(), False


def transcode(source: Path, ffmpeg: str, stem: Path) -> list[Path]:
    """Write both web-friendly files, letting ffmpeg do the resampling and loudness shaping."""
    written = []
    jobs = [
        (stem.with_suffix(".m4a"), ["-c:a", "aac", "-b:a", "192k"]),
        (stem.with_suffix(".mp3"), ["-c:a", "libmp3lame", "-b:a", "192k"]),
    ]
    for target, codec in jobs:
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(source), "-vn", *codec, str(target)],
            check=True,
        )
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把你自己拥有版权的音频装进某个音乐提示位")
    parser.add_argument("source", type=Path, help="音频或视频文件（ffmpeg 存在时可直接用视频，只取音轨）")
    parser.add_argument("--slot", required=True, choices=sorted(SLOTS), help="要替换的音乐提示位")
    args = parser.parse_args(argv)

    source: Path = args.source
    if not source.is_file():
        print(f"找不到文件：{source}", file=sys.stderr)
        return 2
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    stem = AUDIO_DIR / f"{args.slot}-custom"

    ffmpeg = which("ffmpeg")
    container, has_video = sniff(source)
    if ffmpeg:
        written = transcode(source, ffmpeg, stem)
    else:
        if container not in {".mp3", ".m4a", ".aac"}:
            print(
                f"没有 ffmpeg，无法把 {container or '未知格式'} 转成网页可播的格式。\n"
                "装一个再试：winget install --id Gyan.FFmpeg   （或先自己导出成 mp3）",
                file=sys.stderr,
            )
            return 3
        # The slot name follows the bytes, not the download's name: an ISO-BMFF file called `.mp3`
        # would otherwise be served as the wrong type in a browser that trusts the extension.
        target = stem.with_suffix(".m4a" if container == ".m4a" else ".mp3")
        shutil.copyfile(source, target)
        written = [target]
    # A stale file from an earlier install in another extension would shadow this one in the chain.
    for other in {".m4a", ".mp3"} - {path.suffix for path in written}:
        stale = stem.with_suffix(other)
        if stale.exists():
            stale.unlink()

    print(f"{SLOTS[args.slot]}：{source.name} 已装好")
    for path in written:
        print(f"  {path.relative_to(AUDIO_DIR.parent.parent.parent.parent)}  ({path.stat().st_size // 1024} KB)")
    if has_video and not ffmpeg:
        print("  注意：这个文件其实带视频轨（下载站常见），现在只用它的音轨；"
              "想瘦身可以装 ffmpeg 后重跑一次，会抽成纯音频的 m4a + mp3。")
    print("刷新页面即可听到。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
