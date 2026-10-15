"""Run long-horizon strategy outcome benchmarks separately from runtime checks."""
import json
import os
import platform
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
print(json.dumps({"platform": platform.platform(), "python": platform.python_version(),
                  "benchmark": "siege opening: highland, tunnel and fly lane by 80 seconds"}), flush=True)
raise SystemExit(subprocess.run([sys.executable, "-B", "-m", "unittest", "-v",
    "tests.test_siege_team.SiegeTeamTests.test_opening_reaches_the_deck_tunnel_and_own_fly_lane_on_both_sides"],
    cwd=ROOT, env={**os.environ, "RMUC_STRATEGY_BENCHMARKS": "1", "PYTHONUTF8": "1"}).returncode)
