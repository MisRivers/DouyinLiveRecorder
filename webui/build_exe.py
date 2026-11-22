"""Build the Windows one-folder executable.

Usage (from the repository root, on Windows):
    python -m pip install pyinstaller
    python webui/build_exe.py

The frontend is rebuilt automatically when webui/frontend is present.
ffmpeg is not bundled; copy ffmpeg.exe/ffprobe.exe to
dist/DouyinLiveRecorderUI/ffmpeg/ before distributing.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "webui" / "frontend"
STATIC = ROOT / "webui" / "backend" / "static"


def build_frontend() -> None:
    if not (FRONTEND / "package.json").exists():
        return
    npm = shutil.which("npm")
    if not npm:
        print("npm not found; using existing static files")
        return
    install = ["ci"] if (FRONTEND / "package-lock.json").exists() else ["install"]
    subprocess.run([npm, *install], cwd=FRONTEND, check=True)
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)


def main() -> None:
    build_frontend()
    if not (STATIC / "index.html").exists():
        raise SystemExit("frontend build missing: webui/backend/static/index.html")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit("PyInstaller is not installed. Run: python -m pip install pyinstaller")
    subprocess.run([sys.executable, "-m", "PyInstaller", "webui/webui.spec", "--noconfirm"],
                   cwd=ROOT, check=True)
    ffmpeg_dir = ROOT / "dist" / "DouyinLiveRecorderUI" / "ffmpeg"
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)
    print("\nBuild finished.")
    print("Copy ffmpeg.exe and ffprobe.exe to:")
    print(f"  {ffmpeg_dir}")
    print("ffmpeg is intentionally not bundled in the executable.")


if __name__ == "__main__":
    main()
