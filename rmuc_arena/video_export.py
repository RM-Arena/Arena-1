"""Local WebM -> H.264/AAC MP4 conversion with bounded uploads, temporary files and progress reports."""
import asyncio
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

MAX_VIDEO_BYTES = 1024 * 1024 * 1024
EXPORT_TIMEOUT = 30 * 60
# A client names its export so it can ask how far the transcode has come while the upload request
# is still open; finished reports are forgotten after a while.
JOB_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"
JOB_TTL = 10 * 60


class VideoExportError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def ffmpeg_executable():
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return shutil.which("ffmpeg")


def mp4_command(executable, source, target, duration=None):
    video_filter = "scale=ceil(iw/2)*2:ceil(ih/2)*2"
    if duration is not None:
        # Canvas capture emits fewer frames while paused or under renderer load.
        # Preserve wall-clock duration and keep the audio and video tracks aligned.
        video_filter += f",tpad=stop_mode=clone:stop_duration={duration:.3f}"
    # `-progress pipe:1` reports the encoded position on stdout, which is what the save dialog shows.
    command = [executable, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-xerror",
            "-progress", "pipe:1", "-nostats",
            "-max_alloc", "67108864", "-threads", "1", "-protocol_whitelist", "file,pipe",
            "-f", "matroska", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?",
            "-sn", "-dn", "-map_metadata", "-1", "-c:v", "libx264", "-threads", "1",
            "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-vf", video_filter, "-r", "30", "-fps_mode", "cfr",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    if duration is not None:
        command += ["-af", "apad", "-t", f"{duration:.3f}"]
    return command + ["-movflags", "+faststart", str(target)]


class VideoExporter:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = threading.Lock()
        self.jobs = {}

    def capabilities(self):
        return {"mp4": bool(ffmpeg_executable()), "max_bytes": MAX_VIDEO_BYTES}

    def job(self, job):
        """Where a named export stands: receiving, transcoding (encoded seconds and fraction), done or failed."""
        state = self.jobs.get(job)
        return {key: value for key, value in state.items() if key != "updated"} if state else None

    def _report(self, job, **state):
        if not job:
            return
        now = time.monotonic()
        for stale in [key for key, value in self.jobs.items() if now - value["updated"] > JOB_TTL]:
            del self.jobs[stale]
        self.jobs[job] = {**self.jobs.get(job, {}), **state, "updated": now}

    async def _encode(self, process, job, duration):
        async def progress():
            encoded = 0.0
            while line := await process.stdout.readline():
                key, _, value = line.decode("utf-8", "replace").strip().partition("=")
                # `out_time_ms` is microseconds too (a long-standing ffmpeg quirk); either may read N/A.
                if key in ("out_time_us", "out_time_ms") and value.isdigit():
                    encoded = max(encoded, int(value) / 1e6)
                    self._report(job, stage="transcoding", encoded=round(encoded, 2),
                                 progress=round(min(1.0, encoded / duration), 4) if duration else None)
        await asyncio.gather(progress(), process.stderr.read(), process.wait())

    async def export(self, chunks, duration=None, job=None):
        try:
            result = await self._export(chunks, duration, job)
        except VideoExportError as exc:
            self._report(job, stage="failed", error=str(exc))
            raise
        except BaseException:
            self._report(job, stage="failed", error="视频导出中断")
            raise
        self._report(job, stage="done", progress=1.0)
        return result

    async def _export(self, chunks, duration, job):
        executable = ffmpeg_executable()
        if not executable:
            raise VideoExportError("MP4 转码组件不可用，请更新应用或重新运行环境安装。", 503)
        if not self.lock.acquire(blocking=False):
            raise VideoExportError("已有视频正在导出，请等待完成后再试。", 409)
        temporary, process, ready = None, None, False
        self._report(job, stage="receiving", progress=None)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = tempfile.TemporaryDirectory(prefix="mp4-", dir=self.directory)
            source = Path(temporary.name) / "recording.webm"
            target = Path(temporary.name) / "recording.mp4"
            size = 0
            with source.open("wb") as handle:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > MAX_VIDEO_BYTES:
                        raise VideoExportError("录像文件不能超过 1 GiB。", 413)
                    handle.write(chunk)
            with source.open("rb") as handle:
                if handle.read(4) != b"\x1a\x45\xdf\xa3":
                    raise VideoExportError("录像文件为空或不是有效的 WebM 视频。")
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}
            self._report(job, stage="transcoding", encoded=0.0, progress=0.0 if duration else None)
            process = await asyncio.create_subprocess_exec(*mp4_command(executable, source, target, duration),
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, **options)
            try:
                await asyncio.wait_for(self._encode(process, job, duration), timeout=EXPORT_TIMEOUT)
            except asyncio.TimeoutError as exc:
                raise VideoExportError("MP4 转码超时，请缩短录像后重试。", 504) from exc
            if process.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
                raise VideoExportError("MP4 转码失败，录像可能不完整；请保存原始 WebM 后重试。")
            source.unlink()
            ready = True
            return target, temporary
        except OSError as exc:
            raise VideoExportError("视频导出失败，请检查本机剩余空间及转码组件。", 503) from exc
        finally:
            if process is not None and process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
            if temporary is not None and not ready:
                temporary.cleanup()
            self.lock.release()
