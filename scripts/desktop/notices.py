"""Retain complete dependency license texts alongside desktop binaries."""
import json
from pathlib import Path
import shutil
import subprocess


def collect(root, output):
    records = {}

    def package(kind, name, version, directory, license_value):
        key = f"{kind}/{name.replace('/', '__')}@{version}"
        if key in records:
            return
        target = output / key
        files = []
        for source in directory.iterdir():
            if source.name.lower().startswith(("license", "licence", "copying", "notice", "copyright")):
                target.mkdir(parents=True, exist_ok=True)
                if source.is_file():
                    shutil.copy2(source, target / source.name)
                elif source.is_dir():
                    shutil.copytree(source, target / source.name, dirs_exist_ok=True)
                files.append(source.name)
        records[key] = {"name": name, "version": version, "license": license_value, "notices": files}

    modules = root / "node_modules"
    for manifest in [*modules.glob("*/package.json"), *modules.glob("@*/*/package.json")]:
        info = json.loads(manifest.read_text(encoding="utf-8"))
        package("javascript", info["name"], info["version"], manifest.parent, info.get("license"))
    for manifest in ("simulation/Cargo.toml", "legacy/v2/simulation/Cargo.toml"):
        metadata = json.loads(subprocess.check_output(["cargo", "metadata", "--locked", "--format-version", "1", "--manifest-path", manifest], cwd=root))
        for info in metadata["packages"]:
            if info["source"] is not None:
                package("rust", info["name"], info["version"], Path(info["manifest_path"]).parent, info.get("license"))
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Dependency license records retained: {len(records)}", flush=True)
