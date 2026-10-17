"""Build a relocatable desktop runtime for the current OS and architecture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from notices import collect as collect_notices

ROOT = Path(__file__).resolve().parents[2]
PYTHON_VERSION = "3.12.12"


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    if not args.skip_build:
        run("cargo", "build", "--locked", "--release", "--manifest-path", "simulation/Cargo.toml")
        run("cargo", "build", "--locked", "--release", "--manifest-path", "legacy/v2/simulation/Cargo.toml")
        run("bun", "run", "build")
    stage = ROOT / "build/desktop-runtime"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    downloads = ROOT / "build/python-download"
    run("uv", "python", "install", PYTHON_VERSION, "--install-dir", downloads, "--no-bin")
    candidates = [p for p in downloads.glob(f"cpython-{PYTHON_VERSION}-*") if p.is_dir()]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one Python runtime, found {candidates}")
    shutil.copytree(candidates[0], stage / "python", symlinks=True)
    python = stage / "python" / ("python.exe" if os.name == "nt" else "bin/python3")
    requirements = ROOT / "build/desktop-requirements.txt"
    with requirements.open("w", encoding="utf-8") as output:
        run("uv", "export", "--locked", "--no-dev", "--no-emit-project", "--format", "requirements-txt", stdout=output)
    run("uv", "pip", "install", "--python", python, "--break-system-packages", "--require-hashes", "-r", requirements)
    app = stage / "app"
    app.mkdir()
    for directory in ("rmuc_arena", "config", "examples", "docs", "scripts", "legacy/v2/config"):
        # Package the publication set, never unrelated local experiments or
        # generated state that happens to sit beside a versioned example.
        versioned = subprocess.check_output(["git", "ls-files", "-z", directory], cwd=ROOT).decode().split("\0")
        for filename in filter(None, versioned):
            source = ROOT / filename
            if source.suffix == ".pyc" or "__pycache__" in source.parts or filename.endswith(".test.cjs"):
                continue
            target = app / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    shutil.copytree(ROOT / "frontend/dist", app / "frontend/dist")
    for filename in ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.md"):
        shutil.copyfile(ROOT / filename, app / filename)
    collect_notices(ROOT, app / "third_party_licenses")
    # Verify the bundled encoder, rather than accidentally relying on a system FFmpeg.
    run(python, "-B", "-X", "utf8", "-c",
        "import pathlib, subprocess, tempfile, imageio_ffmpeg\n"
        "encoder = imageio_ffmpeg.get_ffmpeg_exe()\n"
        "notices = pathlib.Path(__import__('sys').argv[1]); notices.mkdir(parents=True, exist_ok=True)\n"
        "for flag, name in [('-L', 'LICENSE.txt'), ('-buildconf', 'BUILD.txt')]:\n"
        " result = subprocess.run([encoder, flag], capture_output=True, check=True)\n"
        " (notices / name).write_bytes(result.stdout + result.stderr)\n"
        "with tempfile.TemporaryDirectory() as temporary:\n"
        " subprocess.run([encoder, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=s=16x16:r=30',\n"
        "  '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', '0.1', '-c:v', 'libx264', '-threads', '1',\n"
        "  '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(pathlib.Path(temporary)/'smoke.mp4')], check=True)\n"
        "print('Bundled H.264/AAC MP4 encoder OK')", app / "third_party_licenses/ffmpeg")
    executable = "rmuc-sim.exe" if os.name == "nt" else "rmuc-sim"
    for engine in ("simulation", "legacy/v2/simulation"):
        target = app / engine / "target/release" / executable
        target.parent.mkdir(parents=True)
        shutil.copy2(ROOT / engine / "target/release" / executable, target)
    # Includes the original frontend assets byte for byte; no desktop-specific
    # texture compression, model simplification or reduced renderer settings.
    manifest = {str(p.relative_to(app)).replace(os.sep, "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(app.rglob("*")) if p.is_file()}
    (stage / "resources.sha256.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Desktop runtime ready: {stage}", flush=True)
    run(python, "-B", "-X", "utf8", "-c", "import fastapi, uvicorn, httpx; print('Bundled Python dependencies OK')")
    subprocess.run([str(python), "-B", "-X", "utf8", "-c",
                    "import json\nfrom rmuc_arena.engine import Match\nfrom rmuc_arena.paths import ROOT\n"
                    "legacy_maps = json.loads((ROOT/'legacy/v2/config/rules.json').read_text(encoding='utf-8'))['maps']\n"
                    "for options in ({}, {'replay_version': 2, 'map_name': next(iter(legacy_maps))}):\n"
                    " with Match(duration=1, **options) as match:\n"
                    "  assert match.snapshot()['engine'] == 'rust'\n"
                    "print('Current and historical bundled engines OK')"],
                   cwd=app, env={**os.environ, "RMUC_RESOURCE_ROOT": str(app)}, check=True)


if __name__ == "__main__":
    main()
