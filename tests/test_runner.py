import os
import json
from pathlib import Path
import tempfile
import unittest
import queue
from unittest.mock import patch

from rmuc_arena.engine import Match
from rmuc_arena.runner import Policy, Battle, FrameLog, CPU_LIMIT, POLICY_TIMEOUT_LIMIT
from rmuc_arena.worker import MEMORY_LIMIT
from rmuc_arena.submissions import ROOT, save_submission
from rmuc_arena.cli import verify_replay


class LocalRunnerTests(unittest.TestCase):
    def test_frame_spool_replacement_slices_and_event_window(self):
        frames = FrameLog({"events": [], "tick": 0})
        self.addCleanup(frames.file.close)
        for tick in range(1, 1005):
            frames.append({"tick": tick, "events": [{"tick": tick}]})
        self.assertEqual(frames[-2:][0]["tick"], 1003)
        frames[-1] = {"tick": 1004, "events": [{"type": "stopped"}]}
        self.assertEqual(frames[-1]["events"], [{"type": "stopped"}])
        self.assertEqual(len(frames.events_since(-1)), 1000)
        self.assertEqual(frames.events_since(1003), [{"type": "stopped"}])
        self.assertEqual({**frames.static,**json.loads(list(frames.encoded())[-1])}, frames[-1])

    def test_compact_replay_static_geometry_is_shared(self):
        frames=FrameLog({'events':[],'tick':0,'arena':{'width':28},'official_rules':{'fixed':True}})
        self.addCleanup(frames.file.close)
        frames.append({'events':[],'tick':1,'arena':{'width':28},'official_rules':{'fixed':True}})
        self.assertNotIn('arena',json.loads(list(frames.encoded())[-1]))
        self.assertEqual(frames[1]['arena'],{'width':28})

    def policy(self, text, sandbox="trusted-local", timeout=.2):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "strategy.py"
        path.write_text(text)
        policy = Policy(path, 42, sandbox, timeout)
        self.addCleanup(policy.close)
        return policy

    def test_private_state_persists(self):
        p = self.policy('def act(obs, state):\n n=(state or 0)+1\n return {"1":{"aim":n}}, n\n')
        obs = Match().observation("red", [1])
        self.assertEqual(p.decide(obs)[0]["1"]["aim"], 1)
        self.assertEqual(p.decide(obs)[0]["1"]["aim"], 2)

    def test_foreign_robot_control_disables_policy(self):
        p = self.policy('def act(obs, state):\n return {"2":{}}, None\n')
        actions, error = p.decide(Match().observation("red", [1]))
        self.assertEqual(actions, {})
        self.assertIn("unowned", error)
        self.assertTrue(p.disabled)

    def test_action_protocol_is_bounded_and_rejects_unknown_fields(self):
        for value in ('{"1":{"hidden_data":"extra"}}', '{"1":{"move":"x"*1500}}'):
            with self.subTest(value=value):
                p=self.policy('def act(obs,state):\n return '+value+', None\n')
                commands,error=p.decide(Match().observation('red'))
                self.assertEqual(commands,{})
                self.assertIsNotNone(error)

    def test_crash_and_state_limits_disable_immediately(self):
        for code in ('def act(obs,state):\n raise RuntimeError("broken")\n',
                     'def act(obs,state):\n return {}, "x"*300000\n'):
            with self.subTest(code=code):
                p = self.policy(code, timeout=.03)
                actions, error = p.decide(Match().observation("red"))
                self.assertEqual(actions, {})
                self.assertIsNotNone(error)
                self.assertTrue(p.disabled)

    def test_hung_policy_is_disabled_after_consecutive_timeouts(self):
        p = self.policy('def act(obs,state):\n while True: pass\n', timeout=.03)
        with Match() as match:
            obs = match.observation('red')
        for attempt in range(1, POLICY_TIMEOUT_LIMIT + 1):
            actions, error = p.decide(obs)
            self.assertEqual(actions, {})
            self.assertEqual(error, 'decision exceeded deadline')
            self.assertEqual(p.consecutive_timeouts, attempt)
            self.assertEqual(p.disabled, attempt == POLICY_TIMEOUT_LIMIT)
        self.assertIsNotNone(p.process.poll())
        self.assertEqual(p.decide(obs), ({}, None))

    def test_transient_timeouts_discard_old_actions_preserve_state_and_reset_streak(self):
        p = self.policy('def act(obs,state):\n n=(state or 0)+1\n return {"1":{"aim":obs["tick"],"pitch":n}},n\n')
        with Match() as match:
            obs = match.observation('red', [1])
        pid = p.process.pid
        # Inject a missed response deadline without relying on OS scheduling.
        # Repeat with successful decisions between failures to test streak reset.
        for attempt in range(POLICY_TIMEOUT_LIMIT + 1):
            obs['tick'] = attempt * 2
            with patch.object(p.lines, 'get', side_effect=queue.Empty):
                self.assertEqual(p.decide(obs), ({}, 'decision exceeded deadline'))
            self.assertFalse(p.disabled)
            self.assertEqual(p.consecutive_timeouts, 1)
            obs['tick'] += 1
            actions, error = p.decide(obs)
            self.assertIsNone(error)
            self.assertEqual(actions['1'], {'aim': obs['tick'], 'pitch': (attempt + 1) * 2})
            self.assertEqual(p.consecutive_timeouts, 0)
            self.assertEqual(p.process.pid, pid)

    def test_late_worker_error_still_disables_policy(self):
        p = self.policy('def act(obs,state):\n raise RuntimeError("late failure")\n')
        with Match() as match:
            obs = match.observation('red')
        with patch.object(p.lines, 'get', side_effect=queue.Empty):
            self.assertEqual(p.decide(obs), ({}, 'decision exceeded deadline'))
        actions, error = p.decide(obs)
        self.assertEqual(actions, {})
        self.assertEqual(error, 'late failure')
        self.assertTrue(p.disabled)

    def test_slow_decision_can_finish_during_the_next_budget(self):
        p = self.policy('import time\ndef act(obs,state):\n if state is None: time.sleep(.3)\n return {"1":{"aim":obs["tick"]}},True\n')
        with Match() as match:
            obs = match.observation('red', [1])
        self.assertEqual(p.decide(obs), ({}, 'decision exceeded deadline'))
        self.assertFalse(p.disabled)
        obs['tick'] = 2
        self.assertEqual(p.decide(obs), ({'1': {'aim': 2}}, None))
        self.assertFalse(p.disabled)
        self.assertIsNone(p.pending_response)

    def test_both_teams_recover_from_one_missed_decision_and_replay_verifies(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'strategy.py'
            source.write_text('def act(obs,state):\n return {"1":{"aim":obs["tick"],"move":[.2,0]}},state\n')
            for team in ('red', 'blue'):
                save_submission(Path(temp) / team, 'team', {'team': source})
            with Battle(Path(temp) / 'red', Path(temp) / 'blue', duration=1, sandbox=self.policy_sandbox()) as b:
                red, blue = [p for _, _, p in b.policies]
                with patch.object(red.lines, 'get', side_effect=queue.Empty), patch.object(blue.lines, 'get', side_effect=queue.Empty):
                    b.step()
                self.assertEqual(b.actions[0], {'red': {}, 'blue': {}})
                self.assertEqual(len({d['id'] for d in b.diagnostics}), 2)
                self.assertTrue(all(not d['disabled'] and d['time'] == 0 for d in b.diagnostics))
                b.run()
                self.assertTrue(all(not p.disabled for _, _, p in b.policies))
                for team in ('red', 'blue'):
                    self.assertEqual(b.actions[2][team]['1']['aim'], 2)
                    self.assertEqual(b.actions[-1][team]['1']['aim'], 18)
                self.assertEqual(b.result()['policy_errors'], 2)
                replay = Path(temp) / 'replay.json'
                b.save(replay)
            self.assertEqual(verify_replay(replay)['verified_ticks'], 20)

    def policy_sandbox(self):
        return 'trusted-local'

    def test_state_may_reach_256_kib(self):
        p = self.policy('def act(obs,state):\n return {}, "x"*100000\n')
        actions, error = p.decide(Match().observation("red"))
        self.assertIsNone(error)
        self.assertFalse(p.disabled)

    def test_recorded_replay_verifies(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "replay.json"
            with Battle(ROOT / "examples" / "official_team", ROOT / "examples" / "official_hold", duration=2, sandbox="trusted-local") as b:
                b.run()
                b.save(path)
                digest = b.match.digest()
            self.assertEqual(verify_replay(path)["digest"], digest)

    def test_json_numeric_roundtrip_and_manual_stop_replays(self):
        for ticks in (0, 2):
            with self.subTest(ticks=ticks), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "replay.json"
                with Battle(ROOT / "examples" / "official_team", ROOT / "examples" / "official_hold", duration=2, sandbox="trusted-local") as b:
                    for _ in range(ticks):
                        b.step()
                    b.match.finish(None, "stopped")
                    b.frames[-1] = b.match.snapshot()
                    b.save(path)
                data = json.loads(path.read_text())
                data["frames"][0]["time"] = int(data["frames"][0]["time"])
                path.write_text(json.dumps(data))
                self.assertEqual(verify_replay(path)["verified_ticks"], ticks)


@unittest.skipUnless(os.environ.get("RMUC_DOCKER_TESTS") == "1", "Set RMUC_DOCKER_TESTS=1 to verify real containers")
class DockerIsolationTests(LocalRunnerTests):
    def policy_sandbox(self):
        return 'docker'

    def policy(self, text, sandbox="docker", timeout=.2):
        return super().policy(text, sandbox, timeout)

    def test_public_map_in_image_matches_the_live_engine(self):
        p=self.policy('import sdk\ndef act(obs,state):\n assert sdk._REFERENCE_ARENA == obs["arena"], "rebuild stale policy image"\n return {},state\n')
        with Match() as match:
            self.assertEqual(p.decide(match.observation('red')), ({},None))

    def test_files_network_and_runtime_resources(self):
        p = self.policy('''import os, socket
def act(obs, state):
 assert os.listdir('/submission') == ['strategy.py']
 assert 'sdk.py' in os.listdir('/runtime')
 assert not os.path.exists('/Users/sn')
 assert os.getuid() == 65534
 try:
  open('/submission/hack.py','w')
  raise AssertionError('write permitted')
 except OSError: pass
 sock=socket.socket(); sock.settimeout(.02)
 try:
  sock.connect(('1.1.1.1',80))
  raise AssertionError('network permitted')
 except OSError: pass
 assert open('/sys/fs/cgroup/memory.max').read().strip() == 'EXPECTED_MEMORY'
 assert open('/sys/fs/cgroup/pids.max').read().strip() == '1'
 try:
  os.fork()
  raise AssertionError('child process permitted')
 except OSError: pass
 quota, period = map(int, open('/sys/fs/cgroup/cpu.max').read().split())
 assert abs(quota / period - EXPECTED_CPU) < .0001
 return {}, None
'''.replace('EXPECTED_MEMORY', str(MEMORY_LIMIT)).replace('EXPECTED_CPU', str(CPU_LIMIT)))
        self.assertEqual(p.decide(Match().observation("red")), ({}, None))

    def test_six_processes_cannot_read_teammate_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entries = {}
            for i in (1,2,3,4,6,7):
                p = root / f"source-{i}.py"
                p.write_text('''import os
def act(obs,state):
 assert len(obs['controlled_ids']) == 1
 assert len(obs['robots']) == 6
 assert os.listdir('/submission') == ['strategy.py']
 assert len(obs['enemies']) == 0
 return {obs['controlled_ids'][0]: {'aim': (state or 0)}}, (state or 0)+1
''')
                entries[str(i)] = p
            save_submission(root / "squad", "squad", entries)
            with Battle(root / "squad", ROOT / "examples" / "official_hold", duration=1) as b:
                result = b.run()
                self.assertEqual(len(b.policies), 7)
                self.assertEqual(result["policy_errors"], 0)


if __name__ == "__main__":
    unittest.main()
