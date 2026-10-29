from pathlib import Path
import tempfile
import time
import unittest

from fastapi.testclient import TestClient
from rmuc_arena.server import create_app


class MatchDeleteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.app=create_app("trusted-local",self.root/"submissions",self.root/"data",test_mode=True)
        self.client=TestClient(self.app)
        self.addCleanup(self.app.state.arena.shutdown)
        self.store=self.app.state.arena.store

    def test_finished_match_record_and_replay_are_removed(self):
        self.client.post('/api/control',json={'command':'speed','speed':8})
        response=self.client.post('/api/start',json={'duration':1})
        self.assertEqual(response.status_code,200,response.text)
        match_id=response.json()['match_id']
        # A one-second match still has to be built, ticked and saved; a heavily loaded CI runner
        # needs far more than ten seconds for that, so poll for the saved replay instead of the flag.
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            if not self.app.state.arena.state()['busy'] and self.store.replay_path(match_id):break
            time.sleep(.02)
        replay=self.store.replay_path(match_id)
        self.assertTrue(replay.is_file())
        self.assertEqual(self.client.delete('/api/matches/'+match_id,headers={'Origin':'https://other.example'}).status_code,403)
        self.assertTrue(replay.is_file())
        response=self.client.delete('/api/matches/'+match_id)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json(),{'deleted':match_id})
        self.assertFalse(replay.exists())
        self.assertEqual(self.client.get('/api/matches/'+match_id).status_code,404)
        self.assertEqual(self.client.get('/api/replays/'+match_id).status_code,404)
        self.assertEqual(self.client.get('/api/matches').json(),[])
        self.assertEqual(self.client.delete('/api/matches/'+match_id).status_code,404)

    def test_running_match_cannot_be_deleted(self):
        self.store.create('running0000000001',{'teams':{}})
        self.assertEqual(self.client.delete('/api/matches/running0000000001').status_code,409)
        self.assertIsNotNone(self.store.match('running0000000001'))

    def test_replay_outside_the_journal_is_never_unlinked(self):
        outside=self.root/'keep.json'
        outside.write_text('{}')
        self.store.create('outside000000001',{'teams':{}})
        with self.store.connect() as db:
            db.execute("UPDATE matches SET status='finished',replay_path=? WHERE id=?",(str(outside),'outside000000001'))
        self.assertEqual(self.client.delete('/api/matches/outside000000001').status_code,200)
        self.assertIsNone(self.store.match('outside000000001'))
        self.assertTrue(outside.is_file())


if __name__=='__main__':
    unittest.main()
