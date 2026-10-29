"""Evaluate team strategies on both sides and save reproducible match summaries.

Example: .venv/bin/python scripts/evaluate_team.py examples/siege_team \
    examples/claude_opus55_xhigh_team examples/claude_opus55_xhigh_hold --seeds 1 7 23 \
    --output replays/siege-evaluation.json

Strategy files are snapshotted into temporary, validated submissions. The
evaluation uses the normal runner, including its per-decision time limit.
"""
import argparse
import hashlib
import json
import multiprocessing
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def snapshot(path, directory):
    from rmuc_arena.submissions import load_submission, save_submission
    path = Path(path).resolve()
    if path.is_dir():
        manifest, entries = load_submission(path)
        if manifest["mode"] not in ("team", "squad"):
            raise ValueError("Evaluation requires a team or an assembled squad")
        target = directory / manifest["version"]
        if not target.exists():
            save_submission(target, manifest["mode"], entries, manifest.get("robot"),team_lineup=manifest.get("team_lineup"))
        return target
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    target = directory / digest
    if not target.exists():
        save_submission(target, "team", {"team": path})
    return target


def play(job):
    from rmuc_arena.runner import Battle
    candidate, opponent, name, seed, side, sandbox, duration = job
    red, blue = (candidate, opponent) if side == "red" else (opponent, candidate)
    other = "blue" if side == "red" else "red"
    started = time.monotonic()
    sdk_hash = hashlib.sha256((ROOT / "rmuc_arena/sdk.py").read_bytes()).hexdigest()
    marks, events, timing = [], [], {"red": [], "blue": []}
    robot_trace, activity = [], {}
    from rmuc_arena.models import normalize_team_lineup
    from rmuc_arena.submissions import load_submission
    lineup = normalize_team_lineup(load_submission(Path(candidate))[0].get("team_lineup"))   # opponents play on it
    with Battle(Path(red), Path(blue), seed, duration, sandbox=sandbox, team_lineup=lineup, practice_lineup=True) as battle:
        for team, _, policy in battle.policies:
            original = policy.decide

            def measured(obs, *args, original=original, team=team, **kwargs):
                begin = time.perf_counter()
                result = original(obs, *args, **kwargs)
                timing[team].append((time.perf_counter() - begin) * 1000)
                return result

            policy.decide = measured
        while battle.match.status != "finished":
            frame = battle.step()
            for robot in frame["robots"]:
                if robot["team"] != side:
                    continue
                stats = activity.setdefault(robot["id"], {"alive_tipped_s": 0., "dead_s": 0., "alive_no_ammo_s": 0., "shots": 0,"shots_mid":0,"enemy_half_s":0.,"mid_idle_s":0.,"fortress_hold_peak":0.})
                stats["alive_tipped_s"] += .05 * bool(robot["alive"] and robot.get("tipped"))
                stats["dead_s"] += .05 * (not robot["alive"])
                stats["alive_no_ammo_s"] += .05 * bool(robot["alive"] and robot["role"] in ("hero", "infantry") and robot["ammo"] == 0)
                stats['enemy_half_s'] += .05 * bool(robot['alive'] and ((robot['x']>14) if side=='red' else (robot['x']<14)))
                stats['fortress_hold_peak'] = max(stats['fortress_hold_peak'],robot.get('fortress_hold',0))
                stats['mid_idle_s'] += .05 * bool(60<=frame['time']<180 and robot['alive'] and not robot.get('tipped') and robot['role'] in ('hero','infantry') and robot['ammo']>0 and robot['vx']**2+robot['vy']**2<.0064 and frame['time']-robot.get('last_shot_time',0)>6)
            for event in frame["events"]:
                if event["type"] == "shot" and event.get("robot") in activity:
                    activity[event["robot"]]["shots"] += 1
                    activity[event['robot']]['shots_mid'] += int(60<=frame['time']<180)
                if event["type"] in ("destroy", "assembly_success", "outpost_rebuilt", "rune_activated","terrain_buff","base_armor_opened","base_hit","hit","rescue_grip","rescue_complete"):
                    events.append(event)
            if frame["tick"] % 200 == 0 or frame["status"] == "finished":
                robot_trace.append({"time": frame["time"], "robots": [
                    {k: robot.get(k) for k in ("id", "x", "y", "z", "hp", "ammo", "heat", "alive", "tipped", "upright", "grounded", "level", "damage", "arm_mode", "carried_units")}
                    for robot in frame["robots"] if robot["team"] == side]})
            if frame["tick"] % 600 == 0 or frame["status"] == "finished":
                marks.append({"time": frame["time"], **{
                    team: {"base_hp": frame["bases"][team]["hp"],
                           "outpost_hp": frame["outposts"][team]["hp"],
                           "coins": frame["teams"][team]["resources"],
                           "tech": frame["teams"][team]["completed_difficulties"],
                           "damage": frame["teams"][team]["attack_damage"]}
                    for team in ("red", "blue")}})
        values = sorted(timing[side])
        result = {"opponent": name, "seed": seed, "side": side,
                  "candidate_version": battle.metadata["teams"][side]["version"],
                  "opponent_version": battle.metadata["teams"][other]["version"],
                  "sdk_hash": sdk_hash,
                  "outcome": "win" if frame["winner"] == side else "draw" if frame["winner"] is None else "loss",
                  "reason": frame["reason"], "time": frame["time"],
                  "candidate": marks[-1][side], "opponent_final": marks[-1][other],
                  "diagnostics": battle.diagnostics,
                  "valid": not battle.diagnostics,
                  "decision_ms": {"count": len(values), "max": max(values, default=0),
                                  "p99": values[min(len(values)-1, int(len(values)*.99))] if values else 0},
                  "robots": [{k: r[k] for k in ("id", "hp", "level", "damage", "kills", "ammo", "x", "y")}
                             for r in frame["robots"]],
                  "robot_trace": robot_trace, "activity": activity,
                  "timeline": marks, "events": events, "digest": battle.match.digest(),
                  "rules_hash": frame["rules_hash"], "engine_hash": frame["engine_hash"],
                  "wall_seconds": time.monotonic() - started}
    # Closing the workers also releases their final, partial stderr chunks.
    result["logs"] = {team: list(policy.logs) for team, _, policy in battle.policies if policy.logs}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("opponents", nargs="+", type=Path)
    parser.add_argument("--seeds", nargs="+", type=int, default=[1, 7, 23])
    parser.add_argument("--sides", nargs="+", choices=["red", "blue"], default=["red", "blue"])
    parser.add_argument("--sandbox", choices=["trusted-local", "docker"], default="trusted-local")
    parser.add_argument("--duration", type=int, default=420)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.duration <= 420 or not 1 <= args.jobs <= 8:
        parser.error("duration must be 1–420; jobs must be 1–8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rmuc-evaluate-") as folder:
        directory = Path(folder)
        candidate = snapshot(args.candidate, directory)
        opponents = [(snapshot(p, directory), str(p)) for p in args.opponents]
        report = {"candidate": str(args.candidate), "sandbox": args.sandbox, "duration": args.duration,
                  "candidate_manifest": json.loads((candidate / "manifest.json").read_text()),
                  "matches": []}
        jobs = [(str(candidate), str(path), name, seed, side, args.sandbox, args.duration)
                for path, name in opponents for seed in args.seeds for side in args.sides]
        with multiprocessing.get_context("spawn").Pool(args.jobs) as pool:
            for result in pool.imap_unordered(play, jobs):
                report["matches"].append(result)
                a, b = result["candidate"], result["opponent_final"]
                print(f"{result['opponent']} seed={result['seed']} side={result['side']} {result['outcome']} "
                      f"t={result['time']:.1f} base={a['base_hp']:.0f}/{b['base_hp']:.0f} "
                      f"outpost={a['outpost_hp']:.0f}/{b['outpost_hp']:.0f} "
                      f"errors={len(result['diagnostics'])} max_ms={result['decision_ms']['max']:.1f}", flush=True)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
        print({key: sum(r["outcome"] == key for r in report["matches"]) for key in ("win", "loss", "draw")})
        print("Valid matches:", sum(r["valid"] for r in report["matches"]), "/", len(report["matches"]))


if __name__ == "__main__":
    main()
