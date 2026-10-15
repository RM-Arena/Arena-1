import argparse
import json
from pathlib import Path
import sys

from .paths import data_path
from .engine import Match
from .runner import Battle
from .server import serve
from .submissions import ROOT, assemble, scaffold, submit, start_training, refresh_workspace


def verify_replay(path):
    replay = json.loads(Path(path).read_text(encoding="utf-8"))
    if replay.get("format") not in ("rmuc-replay-v1", "rmuc-replay-v2", "rmuc-replay-v3", "rmuc-replay-v4"):
        raise ValueError("Unsupported replay format")
    if replay["format"]=="rmuc-replay-v4":
        replay["frames"]=[{**replay["static"],**frame} for frame in replay["frames"]]
    meta = replay["metadata"]
    if replay["format"] == "rmuc-replay-v1":
        from .legacy_engine import Match as ReplayEngine
    else:
        ReplayEngine = Match
    options = {"replay_version":2} if replay["format"]=="rmuc-replay-v2" else {"lineups":meta["lineups"]} if meta.get("lineups") else {}
    match = ReplayEngine(meta["seed"], meta["duration"], meta["map"], **options)
    if replay["format"] in ("rmuc-replay-v2", "rmuc-replay-v3", "rmuc-replay-v4") and meta.get("engine_hash") != match.snapshot().get("engine_hash"):
        match.close()
        raise ValueError("Replay was recorded with a different Rust engine build")
    if len(replay["frames"]) != len(replay["actions"]) + 1:
        raise ValueError("Frame/action count mismatch")
    # Full state verification compares every recorded frame, excluding runtime errors.
    def canonical(frame):
        frame = dict(frame)
        frame["events"] = [e for e in frame["events"] if e["type"] != "policy_error"]
        # JSON consumers may serialize 0.0 as 0; compare numeric values.
        return frame
    if not replay["actions"] and replay["result"]["reason"] == "stopped":
        match.finish(None, "stopped")
    if canonical(match.snapshot()) != canonical(replay["frames"][0]):
        raise ValueError("Initial frame mismatch")
    for i, commands in enumerate(replay["actions"], 1):
        frame = match.step(commands)
        if i == len(replay["actions"]) and replay["result"]["reason"] == "stopped":
            match.finish(None, "stopped")
            frame = match.snapshot()
        if canonical(frame) != canonical(replay["frames"][i]):
            raise ValueError(f"Replay diverges at tick {i}")
    if match.digest() != replay["result"]["digest"]:
        raise ValueError("Final digest mismatch")
    result = {"verified_ticks": len(replay["actions"]), "digest": match.digest(), "winner": match.winner}
    if hasattr(match, "close"):
        match.close()
    return result


def main():
    parser = argparse.ArgumentParser(description="RMUC Arena · RMUC 2026 V1.0.0 6v6 strategy game")
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("serve", help="Start the local 3D spectator")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--submissions", default=str(data_path("submissions")))
    server.add_argument("--trusted-local", action="store_true", help="Run trusted developer strategies without container isolation")
    for name in ("match", "batch"):
        p = sub.add_parser(name)
        p.add_argument("--red", default=str(ROOT / "examples" / "official_team"))
        p.add_argument("--blue", default=str(ROOT / "examples" / "official_hold"))
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--duration", type=int, default=420, help="Official matches are 420s; shorter runs are unranked test matches")
        p.add_argument("--map", choices=["rmuc2026"], default="rmuc2026")
        p.add_argument("--trusted-local", action="store_true")
        p.add_argument("--timeout", type=float, default=0.2)
        p.add_argument("--output", default="replays/match.json" if name == "match" else "replays/batch")
        if name == "batch":
            p.add_argument("--games", type=int, default=4)
            p.add_argument("--swap-sides", action="store_true", help="Play each seed twice, swapping sides")
    p = sub.add_parser("new-agent")
    p.add_argument("output")
    p.add_argument("--mode", choices=["team", "robot", "distributed", "adaptive"], default="team")
    p.add_argument("--robot", type=int)
    p.add_argument("--lineup",help="Team slot-to-model JSON, fixed before development")
    p.add_argument("--minutes",type=int,default=90,help="Total development time, started separately by the organizer")
    p.add_argument("--training-url",default="http://127.0.0.1:8765")
    p = sub.add_parser("start-training",help="Start the host-controlled development clock once")
    p.add_argument("workspace")
    p = sub.add_parser("refresh-agent",help="Refresh protected references while preserving strategy source files")
    p.add_argument("workspace")
    p = sub.add_parser("submit")
    p.add_argument("workspace")
    p.add_argument("output")
    p = sub.add_parser("assemble")
    p.add_argument("output")
    p.add_argument("robots", nargs=6, help="Robot submissions in order 1,2,3,4,6,7")
    p = sub.add_parser("verify-replay")
    p.add_argument("replay")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            serve(args.port, "trusted-local" if args.trusted_local else "docker", args.submissions)
        elif args.command == "new-agent":
            print(scaffold(args.output,args.mode,args.robot,minutes=args.minutes,training_url=args.training_url,team_lineup=json.loads(args.lineup) if args.lineup else None))
        elif args.command == "start-training":
            print(json.dumps(start_training(args.workspace),ensure_ascii=False,indent=2))
        elif args.command == "refresh-agent":
            print(refresh_workspace(args.workspace))
        elif args.command == "submit":
            print(json.dumps(submit(args.workspace, args.output), indent=2))
        elif args.command == "assemble":
            print(json.dumps(assemble(args.robots, args.output), indent=2))
        elif args.command == "verify-replay":
            print(json.dumps(verify_replay(args.replay), indent=2))
        elif args.command in ("match", "batch"):
            if not 0.01 <= args.timeout <= 5:
                raise ValueError("timeout must be in [0.01, 5]")
            games = args.games if args.command == "batch" else 1
            if not 1 <= games <= 1000:
                raise ValueError("games must be in [1, 1000]")
            results = []
            for i in range(games):
                orientations = (False, True) if args.command == "batch" and args.swap_sides else (False,)
                for swapped in orientations:
                    red, blue = (args.blue, args.red) if swapped else (args.red, args.blue)
                    with Battle(red, blue, args.seed + i, args.duration, args.map,
                                "trusted-local" if args.trusted_local else "docker", args.timeout) as battle:
                        result = battle.run()
                        output = args.output if args.command == "match" else str(Path(args.output) / f"{i}-{'swap' if swapped else 'normal'}.json")
                        battle.save(output)
                        result.update({"seed": args.seed + i, "swapped": swapped, "replay": output})
                        results.append(result)
                        print(json.dumps(result, ensure_ascii=False), flush=True)
            if args.command == "batch":
                summary = {"games": len(results), "strategy_a_wins": 0, "strategy_b_wins": 0, "draws": 0,
                           "policy_errors": sum(r["policy_errors"] for r in results)}
                for r in results:
                    if r["winner"] is None:
                        summary["draws"] += 1
                    else:
                        a_won = r["winner"] == ("blue" if r["swapped"] else "red")
                        summary["strategy_a_wins" if a_won else "strategy_b_wins"] += 1
                Path(args.output, "summary.json").write_text(json.dumps(summary, indent=2))
                print(json.dumps(summary), flush=True)
    except (RuntimeError, ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
