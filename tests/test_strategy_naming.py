"""Strategy publication names, confirmed attribution and pre-0.7 compatibility."""
from tests.strategy_fixtures import STRATEGIES
import json
from pathlib import Path
import re
import tempfile
import unittest

from rmuc_arena.showcase import load_profile
from rmuc_arena.strategy_names import CLAUDE_AGENT, LEGACY_CATEGORY, canonical_key, normalize_metadata
from rmuc_arena.submissions import ROOT


class StrategyNamingTests(unittest.TestCase):
    def test_both_seasons_credit_every_renamed_strategy(self):
        for path in (STRATEGIES).glob('claude_opus55_xhigh*'):
            if (path/'manifest.json').exists():
                with self.subTest(path=path.name):
                    self.assertEqual(load_profile(path)['agent'], CLAUDE_AGENT)
                    profile=json.loads((path/'profile.json').read_text())
                    self.assertEqual(profile['agent'], CLAUDE_AGENT)

    def test_saved_keys_and_replay_credits_normalize_without_changing_user_agents(self):
        self.assertEqual(canonical_key(LEGACY_CATEGORY+'_2027_adaptive_2711_guard'), 'claude_opus55_xhigh_2027_adaptive_2711_guard')
        self.assertEqual(canonical_key('my-team'), 'my-team')
        meta={'teams':{'red':{'name':LEGACY_CATEGORY+'_team','agent':{'provider':LEGACY_CATEGORY}},'blue':{'name':'my-team','agent':{'provider':'anthropic','model':'Sonnet'}}}}
        normalized=normalize_metadata(meta)
        self.assertEqual(normalized['teams']['red']['agent'], CLAUDE_AGENT)
        self.assertEqual(normalized['teams']['blue']['agent'], meta['teams']['blue']['agent'])
        self.assertEqual(meta['teams']['red']['name'], LEGACY_CATEGORY+'_team')
        local={'teams':{'red':{'name':'claude_opus55_xhigh_team','agent':{'provider':'human'}}}}
        self.assertEqual(normalize_metadata(local)['teams']['red']['agent']['provider'],'human')

    def test_owned_strategy_paths_and_payloads_have_no_obsolete_category(self):
        pattern=re.compile(LEGACY_CATEGORY+'|\u5b98\u65b9',re.I)
        for path in (STRATEGIES).rglob('*'):
            if path.is_file() and path.suffix in ('.py','.json'):
                with self.subTest(path=str(path)):
                    self.assertIsNone(pattern.search(str(path)))
                    self.assertIsNone(pattern.search(path.read_text()))

    def test_saved_deck_presets_and_start_requests_accept_pre_07_keys(self):
        from fastapi.testclient import TestClient
        from rmuc_arena.server import create_app
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            app=create_app('trusted-local',root/'submissions',root/'data',test_mode=True)
            service=app.state.arena
            try:
                client=TestClient(app)
                old=LEGACY_CATEGORY
                preset={'name':'old','decks':{'red':[old+'_adaptive_3'],'blue':[old+'_adaptive_7']},'controllers':{'red':{'mode':'independent','strategy':old+'_team'},'blue':{'mode':'independent','strategy':old+'_hold'}}}
                (service.store.directory/'deck-presets.json').write_text(json.dumps({'old':preset}))
                restored=client.get('/api/deck-presets').json()[0]
                self.assertEqual(restored['decks']['red'],['claude_opus55_xhigh_adaptive_3'])
                self.assertEqual(restored['controllers']['blue']['strategy'],'claude_opus55_xhigh_hold')
                response=client.post('/api/start',json={'red':old+'_team','blue':old+'_hold','duration':1})
                self.assertEqual(response.status_code,200,response.text)
                service.thread.join(timeout=30)
                record=service.store.match(response.json()['match_id'])
                self.assertEqual(record['metadata']['teams']['red']['name'],'claude_opus55_xhigh_team')
                self.assertEqual(record['metadata']['teams']['red']['agent'],CLAUDE_AGENT)
            finally:
                service.shutdown()
                app.state.training.shutdown()
