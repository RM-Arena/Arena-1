"""Collect installer files without uploading unpacked runtimes or private data."""
import hashlib
import platform
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
output = ROOT / "dist/installers"
output.mkdir(parents=True, exist_ok=True)
for path in (ROOT / "dist/desktop").glob("*"):
    if path.is_file() and path.suffix in (".dmg", ".zip", ".exe", ".AppImage", ".deb"):
        shutil.copy2(path, output / path.name)
files = sorted(p for p in output.iterdir() if not p.name.startswith("SHA256SUMS"))
if not files:
    raise SystemExit("No desktop installers were produced")
checksums = f"SHA256SUMS-{platform.system().lower()}-{platform.machine().lower()}.txt"
(output / checksums).write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files), encoding="utf-8")
