"""Seed an independent feed from the tracked, playable examples in this checkout."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from rmuc_arena import seasons
from rmuc_arena.strategy_library import validate_snapshot
from rmuc_arena.submissions import load_submission
from scripts.strategies.publish import publish


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/strategy-repository")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Output exists; choose a new directory")
    tracked = set(subprocess.check_output(["git", "ls-files", "-z", "examples"], cwd=ROOT).decode().split("\0"))
    for name in sorted(tracked):
        if not name.endswith("/manifest.json"):
            continue
        folder = (ROOT / name).parent
        manifest = json.loads((ROOT / name).read_bytes())
        if manifest.get("api_version") != 3 or manifest.get("rules_profile") not in seasons.profiles():
            continue
        load_submission(folder)
        names = {"manifest.json", *manifest["entries"].values()}
        names.update(n for n in ("showcase.json", "profile.json") if (folder / n).exists())
        destination = output / "strategies" / folder.name
        destination.mkdir(parents=True)
        for file in sorted(names):
            source = folder / file
            if str(source.relative_to(ROOT)).replace("\\", "/") not in tracked or source.is_symlink():
                raise ValueError(f"Not a tracked regular strategy file: {source}")
            shutil.copyfile(source, destination / file)
    validate_snapshot(output / "strategies")
    for source, target in (("scripts/strategies/publish.py", "publish.py"),
                           ("scripts/strategies/publish.yml", ".github/workflows/publish.yml"),
                           ("scripts/strategies/README.md", "README.md"),
                           ("LICENSE", "LICENSE")):
        destination = output / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, destination)
    (output / "library.json").write_text('{"min_client_version": "0.7.0-beta.1"}\n', encoding="utf-8")
    (output / ".gitignore").write_text('__pycache__/\n*.pyc\n.DS_Store\n', encoding="utf-8")
    # Submission hashes cover the exact bytes; checkout must not rewrite line endings.
    (output / ".gitattributes").write_text('* text=auto eol=lf\nstrategies/** -text\nbundles/** binary\n', encoding="utf-8")
    print(json.dumps(publish(output / "strategies", output), indent=2))


if __name__ == "__main__":
    main()
