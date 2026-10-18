"""Check the versioned publication set for private state and obvious secrets."""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = {".env", ".arena_data", ".arena_host", ".venv", "node_modules", "workspaces", "submissions", "replays", ".claude"}
PATTERNS = [re.compile(rb"gh[pousr]_[A-Za-z0-9_]{30,}"),
            re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
            re.compile(rb"AKIA[0-9A-Z]{16}")]


DEPRECATED = re.compile(("off" + "icial|\u5b98\u65b9").encode(), re.IGNORECASE)


def main():
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    errors = []
    for filename in filter(None, files):
        path = Path(filename)
        if PRIVATE.intersection(path.parts):
            errors.append(f"Private runtime path is tracked: {filename}")
        absolute = ROOT / path
        if absolute.is_file():
            if absolute.stat().st_size >= 100 * 1024 * 1024:
                errors.append(f"File exceeds GitHub's 100 MiB limit: {filename}")
            if absolute.suffix not in (".glb", ".blend", ".m4a", ".mp3", ".png", ".jpg", ".woff2"):
                if any(pattern.search(absolute.read_bytes()) for pattern in PATTERNS):
                    errors.append(f"Possible credential in {filename}; inspect locally")
                if "third_party" not in path.parts and path.name not in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
                    try:
                        text = absolute.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        text = ""
                    if DEPRECATED.search(filename.encode()) or DEPRECATED.search(text.encode()):
                        errors.append(f"Obsolete category in publication source: {filename}")
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    if package["license"] != "SEE LICENSE IN LICENSE":
        errors.append("Package must point to the non-commercial learning license")
    if errors:
        raise SystemExit("\n".join(errors))
    print("Publication checks passed: no tracked private runtime state, obvious credentials or oversized files.")


if __name__ == "__main__":
    main()
