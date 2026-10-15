"""Standalone, standard-library practice client copied into author workspaces."""
import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request


def main():
    workspace = Path(__file__).resolve().parent
    config = json.loads((workspace / "agent.json").read_text(encoding="utf-8"))
    training = config["training"]
    base = training["url"].rstrip("/") + "/api/training/" + training["session_id"]

    def request(path, data=None):
        req = urllib.request.Request(base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Authorization": "Bearer " + training["token"], "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read()).get("detail", "Request failed")
            except (ValueError, AttributeError):
                detail = "Request failed"
            raise ValueError(str(detail)) from error

    parser = argparse.ArgumentParser(description="Strategy development and practice")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show development time, submissions and practice jobs")
    test = commands.add_parser("test", help="Capture current strategy and run practice games")
    test.add_argument("--opponent", default="baseline", help="baseline, self, or an own submission version")
    test.add_argument("--duration", type=int, default=30)
    test.add_argument("--games", type=int, default=1)
    test.add_argument("--seed", type=int, default=42)
    test.add_argument("--swap-sides", action="store_true")
    results = commands.add_parser("results", help="Read progress, results and policy diagnostics")
    results.add_argument("job")
    replay = commands.add_parser("replay", help="Download an own practice replay")
    replay.add_argument("job")
    replay.add_argument("--game", type=int, default=0)
    replay.add_argument("--output")
    commands.add_parser("submit", help="Save an immutable final-candidate version")
    args = parser.parse_args()
    try:
        if args.command == "status":
            value = json.loads(request(""))
        elif args.command == "test":
            value = json.loads(request("/tests", {"opponent": args.opponent, "duration": args.duration,
                "games": args.games, "seed": args.seed, "swap_sides": args.swap_sides}))
        elif args.command == "results":
            value = json.loads(request("/tests/" + args.job))
        elif args.command == "submit":
            value = json.loads(request("/submit", {}))
        else:
            output = workspace / (args.output or f"practice/{args.job}-{args.game}.json")
            practice = workspace / "practice"
            if practice.is_symlink() or not output.resolve().is_relative_to(practice.resolve()):
                raise ValueError("Replay output must stay inside practice/")
            raw = request(f"/tests/{args.job}/replays/{args.game}")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(raw)
            value = {"replay": str(output), "bytes": len(raw)}
        print(json.dumps(value, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError, urllib.error.URLError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
