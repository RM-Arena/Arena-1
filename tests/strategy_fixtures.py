"""Historical regression inputs live in Arena-Strategies, never in application examples."""
import os
from pathlib import Path
from rmuc_arena.paths import ROOT

REPOSITORY = Path(os.environ.get('ARENA_STRATEGIES_SOURCE', ROOT / '.arena_data/strategy-tests')).resolve()
STRATEGIES = REPOSITORY / 'fixtures/arena1-4303d7c/examples'
if not (STRATEGIES / 'claude_opus55_xhigh_2027_team/manifest.json').is_file():
    raise RuntimeError('Regression strategies are missing. Clone RM-Arena/Arena-Strategies and set ARENA_STRATEGIES_SOURCE to its checkout; see tests/README.md.')
os.environ['RMUC_TEST_STRATEGIES'] = str(STRATEGIES)
