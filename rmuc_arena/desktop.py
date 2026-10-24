"""Private desktop launcher protocol. Parent stdin owns the service lifetime."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import threading


def reconnect_workspaces(data_dir, url):
    """Keep existing practice clients usable when the app gets a new port."""
    from .submissions import locked_registry, sha, write_json
    registry = data_dir / ".arena_host/workspaces.json"
    if not registry.is_file():
        return
    workspace_root = (data_dir / "workspaces").resolve()
    with locked_registry(registry) as records:
        for directory, record in records.items():
            workspace = Path(directory).resolve()
            agent = workspace / "agent.json"
            training = record.get("training")
            if not workspace.is_relative_to(workspace_root) or not training or training.get("url") == url:
                continue
            # Never repair a tampered protected file or reset a development clock.
            if agent.is_symlink() or not agent.is_file() or sha(agent) != record.get("protected", {}).get("agent.json"):
                continue
            training["url"] = url
            write_json(agent, {key: value for key, value in record.items() if key != "protected"})
            record["protected"]["agent.json"] = sha(agent)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--sandbox", choices=("trusted-local", "docker"), default="trusted-local")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--lan", action="store_true", help="Open the LAN lobby on every interface")
    parser.add_argument("--lan-name", action="append", default=[])
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["RMUC_USER_DATA"] = str(args.data_dir.resolve())
    import uvicorn
    from .lan import local_urls
    from .server import create_app

    with socket.socket() as listener:
        listener.bind(("0.0.0.0" if args.lan else "127.0.0.1", args.port))
        port = listener.getsockname()[1]
        reconnect_workspaces(args.data_dir, f"http://127.0.0.1:{port}")
        urls = local_urls(port) if args.lan else []
        app = create_app(sandbox=args.sandbox, lan=args.lan, lan_urls=urls, lan_names=args.lan_name)
        config = uvicorn.Config(app, log_level="warning")
        server = uvicorn.Server(config)

        def parent_commands():
            for line in sys.stdin:
                if line.strip() == "shutdown":
                    break
            server.should_exit = True

        threading.Thread(target=parent_commands, daemon=True).start()
        ready = {"desktop_ready": True, "url": f"http://127.0.0.1:{port}", "lan": bool(args.lan),
                 "lan_urls": urls, "pin": app.state.arena.lan.pin if args.lan else None}
        print(json.dumps(ready), flush=True)
        server.run(sockets=[listener])


if __name__ == "__main__":
    main()
