"""Cross-platform source setup and run commands (Python 3.10+)."""
import argparse
import os
import socket
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def run(*args):
    executable = shutil.which(args[0])
    if not executable:
        raise SystemExit(f"Missing {args[0]}; see https://rm-arena.github.io/Arena-1/guide/development")
    subprocess.run([executable, *args[1:]], cwd=ROOT, check=True)


def port_taken(port):
    """Whether 127.0.0.1:port cannot be bound right now.

    Windows answers a reserved or exclusively-bound port with WinError 10013 ("access denied") rather
    than 10048, which is what an input method holding the port (百度输入法 listens on 8765) or a
    Hyper-V/WinNAT port exclusion looks like from Python.
    """
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def free_port(start):
    return next((port for port in range(start + 1, start + 41) if not port_taken(port)), start + 1)


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
            run("docker", "build", "-t", "rmuc-arena-policy:0.5", "-f", "sandbox/Dockerfile", ".")
    elif args.command == "run":
        # A failed bind otherwise surfaces as a uvicorn stack trace from inside `uv run`, which says
        # nothing about the usual cause on Windows: another program already owns the port.
        if port_taken(args.port):
            raise SystemExit(
                f"端口 {args.port} 无法绑定：可能已被其他程序占用（Windows 上常见于输入法、Hyper-V 端口保留，"
                f"或本机已有一个服务在运行）。\n换一个端口：python scripts/project.py run --port {free_port(args.port)}"
            )
        run("uv", "run", "--locked", "python", "-X", "utf8", "-m", "rmuc_arena", "serve", "--port", str(args.port),
            *([] if args.docker else ["--trusted-local"]))
    elif args.command == "desktop":
        run("node", "desktop/launch.cjs")
    else:
        run("cargo", "test", "--locked", "--release", "--manifest-path", "simulation/Cargo.toml")
        run("uv", "run", "--locked", "python", "-X", "utf8", "-m", "unittest", "discover", "-s", "tests")
        run("bun", "run", "test:js")
        run("node", "--test", "desktop/backend.test.cjs")


def cli():
    """Run the requested command, turning Ctrl+C into a quiet exit."""
    try:
        main()
    except KeyboardInterrupt:
        # `run` and `desktop` stay in the foreground until the user stops them, and Ctrl+C is how a
        # desktop session ends. An unhandled KeyboardInterrupt made that normal exit print a
        # traceback that reads like a crash.
        print("\n已停止。", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
