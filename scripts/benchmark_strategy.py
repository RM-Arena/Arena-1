"""Run long-horizon strategy outcome benchmarks separately from runtime checks."""
import json
import os
import platform
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS = [
    "tests.test_siege_team.SiegeTeamTests.test_opening_reaches_the_deck_tunnel_and_own_fly_lane_on_both_sides",
    "tests.test_siege_team.SiegeTeamTests.test_wheel_legged_infantry_climb_the_stairs_and_earn_the_highland_buff",
    "tests.test_season_2027.Season2027BattleTests.test_heavy_robot_mines_two_units_and_completes_a_core_level",
    "tests.test_gpt61_max_2027.SolMax2027Tests.test_all_six_serial_legs_cross_and_return_to_supply_in_the_actual_engine",
    "tests.test_sol_max_coordination_2027.SolMaxCoordinationTests.test_six_robots_depart_again_from_supply_and_base_without_state_injection",
    "tests.test_sol_max_vision_2027.SolMaxVisionTests.test_reference_intruder_crosses_the_field_and_is_seen",
]
print(json.dumps({"platform": platform.platform(), "python": platform.python_version(),
                  "benchmark": "reference strategy physical outcomes", "cases": len(BENCHMARKS)}), flush=True)
raise SystemExit(subprocess.run([sys.executable, "-B", "-m", "unittest", "-v", *BENCHMARKS],
    cwd=ROOT, env={**os.environ, "RMUC_STRATEGY_BENCHMARKS": "1", "PYTHONUTF8": "1"}).returncode)
