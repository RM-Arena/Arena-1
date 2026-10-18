"""The referee defaults and independent dual-arm commands survive public APIs."""
import json
import queue
import time
import unittest

from rmuc_arena import sdk
from rmuc_arena.models import model_catalog
from rmuc_arena.runner import Policy


class RuleInterfaces2027Tests(unittest.TestCase):
    def test_catalog_uses_the_rulebook_unselected_profiles(self):
        for model in (2731,2732,305):
            stats=model_catalog()[str(model)]['initial_stats_by_season']['2027']
            self.assertEqual((stats['hp'],stats['power_w'],stats['max_heat'],stats['cooling']),
                             (200,45,40,12))

    def test_sdk_and_worker_preserve_independent_second_arm_rotation(self):
        command=sdk.action(assembly_core=2,assembly_rotate=35,assembly_rotate2=-60)
        policy=Policy.__new__(Policy)
        policy.pending_response=({'1'},False)
        policy.lines=queue.Queue()
        policy.lines.put(json.dumps({'actions':{'1':command}}).encode())
        actions=policy._receive(time.monotonic()+1)
        self.assertEqual(actions['1']['assembly_rotate'],35)
        self.assertEqual(actions['1']['assembly_rotate2'],-60)
