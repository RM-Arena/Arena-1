"""Cross-platform source setup and run commands (Python 3.10+)."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def run(*args):
    executable = shutil.which(args[0])
    if not executable:
        raise SystemExit(f"Missing {args[0]}; see https://rm-arena.github.io/Arena-1/guide/development")
    subprocess.run([executable, *args[1:]], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("setup", "run", "desktop", "test"))
    parser.add_argument("--docker", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.command == "setup":
        run("uv", "sync", "--locked")
        run("bun", "install", "--frozen-lockfile")
        run("cargo", "build", "--locked", "--release", "--manifest-path", "simulation/Cargo.toml")
        run("cargo", "build", "--locked", "--release", "--manifest-path", "legacy/v2/simulation/Cargo.toml")
        run("bun", "run", "build")
        if args.docker:
            run("docker", "build", "-t", "rmuc-arena-policy:0.4", "-f", "sandbox/Dockerfile", ".")
    elif args.command == "run":
        run("uv", "run", "--locked", "python", "-X", "utf8", "-m", "rmuc_arena", "serve", "--port", str(args.port),
            *([] if args.docker else ["--trusted-local"]))
    elif args.command == "desktop":
        run("node", "desktop/launch.cjs")
    else:
        run("cargo", "test", "--locked", "--release", "--manifest-path", "simulation/Cargo.toml")
        run("uv", "run", "--locked", "python", "-X", "utf8", "-m", "unittest", "discover", "-s", "tests")
        run("bun", "run", "test:js")
        run("node", "--test", "desktop/backend.test.cjs")


if __name__ == "__main__":
    main()
