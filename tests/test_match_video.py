from pathlib import Path
import subprocess
import tempfile
import unittest

from fastapi.testclient import TestClient
from rmuc_arena.server import create_app
from rmuc_arena.store import Store
from rmuc_arena.video_export import ffmpeg_executable


class MatchVideoTests(unittest.TestCase):
    def test_saved_mp4_survives_restart_streams_with_ranges_and_deletes_with_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            webm = root/'sample.webm'
            subprocess.run([ffmpeg_executable(), '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                            '-i', 'testsrc2=size=320x180:rate=30', '-t', '0.3', '-c:v', 'libvpx-vp9',
                            '-threads', '1', str(webm)], check=True, capture_output=True, timeout=30)
            app = create_app('trusted-local', root/'submissions', root/'data', test_mode=True)
            service = app.state.arena
            client = TestClient(app)
            match_id = 'video00000000001'
            meta = {'teams': {}, 'test_match': True, 'save_mp4': True}
            try:
                service.store.create(match_id, meta)
                self.assertEqual(client.post(f'/api/matches/{match_id}/video', content=webm.read_bytes(), headers={'Content-Type': 'video/webm'}).status_code, 409)
                service.store.finish(match_id, {'winner': None, 'reason': 'stopped'})
                response = client.post(f'/api/matches/{match_id}/video?duration=0.3', content=webm.read_bytes(), headers={'Content-Type': 'video/webm'})
                self.assertEqual(response.status_code, 200, response.text)
                record = client.get('/api/matches/'+match_id).json()
                self.assertTrue(record['has_video'])
                self.assertEqual(record['video_status'], 'ready')
                self.assertNotIn('video_path', record)
                self.assertGreater(record['video_bytes'], 0)
                path = service.store.video_path(match_id)
                restarted = Store(root/'data')
                self.assertEqual(restarted.match(match_id)['video_status'], 'ready')
                self.assertEqual(restarted.video_path(match_id), path)
                video = client.get(response.json()['url'])
                self.assertEqual(video.headers['content-type'], 'video/mp4')
                self.assertEqual(video.content[4:8], b'ftyp')
                partial = client.get(response.json()['url'], headers={'Range': 'bytes=0-15'})
                self.assertEqual(partial.status_code, 206)
                self.assertEqual(len(partial.content), 16)
                self.assertEqual(client.delete('/api/matches/'+match_id).status_code, 200)
                self.assertFalse(path.exists())
                self.assertEqual(client.get(response.json()['url']).status_code, 404)
            finally:
                service.shutdown()
                app.state.training.shutdown()

    def test_failed_upload_remains_retryable_and_export_blocks_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app('trusted-local', Path(directory)/'submissions', Path(directory)/'data', test_mode=True)
            service = app.state.arena
            client = TestClient(app)
            try:
                service.store.create('test', {'teams': {}, 'save_mp4': True})
                service.store.finish('test', {'winner': None, 'reason': 'stopped'})
                response = client.post('/api/matches/test/video', content=b'invalid', headers={'Content-Type': 'video/webm'})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(service.store.match('test')['video_status'], 'failed')
                self.assertFalse(service.store.match('test')['has_video'])
                service.store.video_status('test', 'processing')
                self.assertEqual(client.delete('/api/matches/test').status_code, 409)
                self.assertEqual(client.post('/api/matches/missing/video', content=b'x', headers={'Content-Type': 'video/webm'}).status_code, 404)
            finally:
                service.shutdown()
                app.state.training.shutdown()
