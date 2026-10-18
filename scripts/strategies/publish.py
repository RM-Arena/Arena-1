"""Build a deterministic strategy feed. Standard library only; also shipped in Arena-Strategies."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

FORMAT = "arena-strategy-library-v1"
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
SOURCE_LIMIT = 512 * 1024


def publish(source, output, min_client_version="0.6.0", tracked=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?", min_client_version):
        raise ValueError("Minimum client version must be major.minor.patch with an optional prerelease suffix")
    tracked_paths = None
    if tracked:
        names = subprocess.check_output(["git", "ls-files", "-z", "--", str(source)], cwd=source).decode().split("\0")
        tracked_paths = {(source / name).resolve() for name in names if name}
    payload = io.BytesIO()
    count, unpacked, file_count = 0, 0, 0
    keys = set()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for manifest_path in sorted(source.glob("*/manifest.json")):
            if tracked_paths is not None and manifest_path.resolve() not in tracked_paths:
                continue
            folder = manifest_path.parent
            if not KEY.fullmatch(folder.name) or folder.name.casefold() in keys or folder.is_symlink() or manifest_path.is_symlink():
                raise ValueError(f"Invalid strategy directory: {folder}")
            keys.add(folder.name.casefold())
            manifest = json.loads(manifest_path.read_bytes())
            if manifest.get("api_version") != 3 or manifest.get("mode") not in ("team", "squad", "distributed", "adaptive", "robot"):
                raise ValueError(f"Unsupported strategy: {folder}")
            body = {k: v for k, v in manifest.items() if k != "version"}
            if hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16] != manifest.get("version"):
                raise ValueError(f"Manifest version mismatch: {folder}")
            sources = set(manifest["entries"].values())
            if not sources or any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+\.py", name) for name in sources):
                raise ValueError(f"Invalid entry paths: {folder}")
            names = {"manifest.json", *sources}
            names.update(name for name in ("profile.json", "showcase.json") if (folder / name).exists())
            for name in sorted(names):
                file = folder / name
                if file.is_symlink() or not file.is_file() or file.stat().st_size > SOURCE_LIMIT:
                    raise ValueError(f"Invalid strategy file: {file}")
                if tracked_paths is not None and file.resolve() not in tracked_paths:
                    raise ValueError(f"Strategy file is not tracked: {file}")
                data = file.read_bytes()
                unpacked += len(data)
                file_count += 1
                if unpacked > 128 * 1024 * 1024 or file_count > 16000:
                    raise ValueError("Strategy library exceeds archive limits")
                if name in sources:
                    if hashlib.sha256(data).hexdigest() != manifest["hashes"].get(name):
                        raise ValueError(f"Strategy checksum mismatch: {file}")
                    compile(data, name, "exec")
                else:
                    json.loads(data)
                info = zipfile.ZipInfo(f"strategies/{folder.name}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
            count += 1
    data = payload.getvalue()
    if not 0 < count <= 2000 or len(data) > 32 * 1024 * 1024:
        raise ValueError("Empty or oversized strategy library")
    digest = hashlib.sha256(data).hexdigest()
    relative = f"bundles/{digest}.zip"
    (output / "bundles").mkdir(parents=True, exist_ok=True)
    (output / relative).write_bytes(data)
    catalog = {"format": FORMAT, "min_client_version": min_client_version,
               "archive": relative, "sha256": digest, "bytes": len(data), "count": count}
    # Publish the pointer last. Bundles are content addressed and remain available across revisions.
    temporary = output / "catalog.json.tmp"
    temporary.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output / "catalog.json")
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("strategies"))
    parser.add_argument("--output", type=Path, default=Path("."))
    parser.add_argument("--min-client-version")
    parser.add_argument("--tracked", action="store_true", help="Only publish files tracked by git")
    args = parser.parse_args()
    settings = args.output / "library.json"
    minimum = args.min_client_version or (json.loads(settings.read_bytes())["min_client_version"] if settings.exists() else "0.6.0")
    print(json.dumps(publish(args.source, args.output, minimum, args.tracked), indent=2))


if __name__ == "__main__":
    main()
