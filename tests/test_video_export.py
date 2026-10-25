import asyncio
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from rmuc_arena.server import create_app
from rmuc_arena.video_export import MAX_VIDEO_BYTES, VideoExporter, VideoExportError, ffmpeg_executable


class VideoExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = ffmpeg_executable()
        if not cls.ffmpeg:
            raise RuntimeError("Install the locked dependencies to run video export tests")
        cls.samples = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.samples.cleanup)
        cls.webm = Path(cls.samples.name) / "sample.webm"
        subprocess.run([cls.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", "testsrc2=size=320x180:rate=30", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                        "-t", "0.5", "-c:v", "libvpx-vp9", "-threads", "1", "-c:a", "libopus", str(cls.webm)],
                       check=True, capture_output=True, timeout=30)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = create_app("trusted-local", self.root / "submissions", self.root / "data", test_mode=True)
        self.client = TestClient(self.app)
        self.addCleanup(self.app.state.arena.shutdown)
        self.addCleanup(self.app.state.training.shutdown)
        self.exporter = self.app.state.video_exporter

    def post(self, content=None, **kwargs):
        return self.client.post("/api/video-export", content=self.webm.read_bytes() if content is None else content,
                                headers={"Content-Type": "video/webm", **kwargs})

    def assert_cleaned(self):
        self.assertFalse(self.exporter.lock.locked())
        self.assertFalse(self.exporter.directory.exists() and list(self.exporter.directory.iterdir()))

    def test_real_mp4_has_h264_video_aac_audio_and_preserves_dimensions(self):
        self.assertTrue(self.client.get("/api/video-export").json()["mp4"])
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text[:200] if response.status_code != 200 else "")
        self.assertEqual(response.headers["content-type"], "video/mp4")
        self.assertIn('filename="rmuc-arena.mp4"', response.headers["content-disposition"])
        self.assertEqual(response.content[4:8], b"ftyp")
        output = self.root / "export.mp4"
        output.write_bytes(response.content)
        decoded = subprocess.run([self.ffmpeg, "-hide_banner", "-i", str(output), "-f", "null", "-"],
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(decoded.returncode, 0, decoded.stderr)
        self.assertIn("Video: h264", decoded.stderr)
        self.assertIn("yuv420p", decoded.stderr)
        self.assertIn("320x180", decoded.stderr)
        self.assertIn("30 fps", decoded.stderr)
        self.assertIn("Audio: aac", decoded.stderr)
        self.assertLess(response.content.index(b"moov"), response.content.index(b"mdat"))
        self.assert_cleaned()

    def test_named_export_reports_transcode_progress(self):
        self.assertEqual(self.client.get("/api/video-export/jobs/unknownjob1").status_code, 404)
        response = self.client.post("/api/video-export?duration=0.5&job=clip-test-0001", content=self.webm.read_bytes(),
                                    headers={"Content-Type": "video/webm"})
        self.assertEqual(response.status_code, 200, response.text[:200] if response.status_code != 200 else "")
        state = self.client.get("/api/video-export/jobs/clip-test-0001").json()
        self.assertEqual(state["stage"], "done")
        self.assertEqual(state["progress"], 1.0)
        self.assertGreater(state["encoded"], 0)
        failed = self.client.post("/api/video-export?job=clip-test-0002", content=b"not a recording", headers={"Content-Type": "video/webm"})
        self.assertEqual(failed.status_code, 400)
        state = self.client.get("/api/video-export/jobs/clip-test-0002").json()
        self.assertEqual(state["stage"], "failed")
        self.assertIn("WebM", state["error"])
        for job in ("short", "bad%2Fexport-id"):
            self.assertEqual(self.client.post("/api/video-export?job=" + job, content=b"", headers={"Content-Type": "video/webm"}).status_code, 422)
        self.assert_cleaned()

    def test_recordings_without_audio_still_export(self):
        silent = self.root / "silent.webm"
        subprocess.run([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(self.webm),
                        "-an", "-c:v", "copy", str(silent)], check=True, capture_output=True, timeout=30)
        self.assertEqual(self.post(silent.read_bytes()).status_code, 200)
        self.assert_cleaned()

    def test_capture_duration_keeps_audio_and_video_aligned_when_rendering_stalls(self):
        response = self.client.post("/api/video-export?duration=1.2", content=self.webm.read_bytes(), headers={"Content-Type": "video/webm"})
        self.assertEqual(response.status_code, 200, response.text[:200] if response.status_code != 200 else "")
        output = self.root / "padded.mp4"
        output.write_bytes(response.content)
        metadata = subprocess.run([self.ffmpeg, "-hide_banner", "-i", str(output), "-f", "null", "-"], capture_output=True, text=True, timeout=30)
        self.assertEqual(metadata.returncode, 0, metadata.stderr)
        self.assertIn("00:00:01.20", metadata.stderr)
        self.assertIn("Video: h264", metadata.stderr)
        self.assertIn("Audio: aac", metadata.stderr)
        self.assert_cleaned()
        for duration in ("0", "-1", "nan", "inf", "3601"):
            self.assertEqual(self.client.post("/api/video-export?duration=" + duration, content=b"", headers={"Content-Type": "video/webm"}).status_code, 422)

    def test_invalid_and_truncated_recordings_are_rejected_and_cleaned(self):
        for data in (b"", b"not a recording", b"\x1a\x45\xdf\xa3broken video"):
            with self.subTest(data=data):
                self.assertEqual(self.post(data).status_code, 400)
                self.assert_cleaned()

    def test_request_boundaries_and_streamed_size_limit(self):
        self.assertEqual(self.post(**{"Origin": "https://other.example"}).status_code, 403)
        self.assertEqual(self.post(**{"Content-Type": "application/json"}).status_code, 415)
        self.assertEqual(self.post(**{"Content-Length": str(MAX_VIDEO_BYTES + 1)}).status_code, 413)
        with patch("rmuc_arena.video_export.MAX_VIDEO_BYTES", 8):
            self.assertEqual(self.post(iter([b"\x1a\x45\xdf\xa3", b"more than 8 bytes"])).status_code, 413)
        self.assert_cleaned()

    def test_missing_encoder_and_concurrent_export_return_clear_errors(self):
        with patch("rmuc_arena.video_export.ffmpeg_executable", return_value=None):
            self.assertFalse(self.client.get("/api/video-export").json()["mp4"])
            self.assertEqual(self.post().status_code, 503)
        self.exporter.lock.acquire()
        try:
            self.assertEqual(self.post().status_code, 409)
        finally:
            self.exporter.lock.release()
        self.assert_cleaned()


class VideoExportCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_kills_encoder_and_releases_files_and_lock(self):
        class Stream:
            async def readline(self):
                await asyncio.sleep(60)
            async def read(self):
                await asyncio.sleep(60)
        class Process:
            returncode = None
            stdout = stderr = Stream()
            def kill(self):
                self.returncode = -9
            async def wait(self):
                return self.returncode
        async def chunks():
            yield b"\x1a\x45\xdf\xa3video"
        with tempfile.TemporaryDirectory() as root:
            exporter, process = VideoExporter(Path(root)), Process()
            with patch("rmuc_arena.video_export.EXPORT_TIMEOUT", .01), patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)):
                with self.assertRaises(VideoExportError) as error:
                    await exporter.export(chunks())
            self.assertEqual(error.exception.status_code, 504)
            self.assertEqual(process.returncode, -9)
            self.assertFalse(exporter.lock.locked())
            self.assertEqual(list(Path(root).iterdir()), [])

    async def test_interrupted_upload_releases_files_and_lock(self):
        async def interrupted():
            yield b"\x1a\x45\xdf\xa3"
            raise asyncio.CancelledError()
        with tempfile.TemporaryDirectory() as root:
            exporter = VideoExporter(Path(root))
            with self.assertRaises(asyncio.CancelledError):
                await exporter.export(interrupted())
            self.assertFalse(exporter.lock.locked())
            self.assertEqual(list(Path(root).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
