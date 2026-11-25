"""Build the Windows one-folder executable.

Usage (from the repository root, on Windows):
    python -m pip install pyinstaller
    python webui/build_exe.py

The frontend is rebuilt automatically when webui/frontend is present.
ffmpeg is not bundled; copy ffmpeg.exe/ffprobe.exe to
dist/DouyinLiveRecorderUI/ffmpeg/ before distributing.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="", help="version baked into the bundle")
    args = parser.parse_args()
    version = args.version.strip() or (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    build_frontend()
    if not (STATIC / "index.html").exists():
        raise SystemExit("frontend build missing: webui/backend/static/index.html")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit("PyInstaller is not installed. Run: python -m pip install pyinstaller")
    subprocess.run([sys.executable, "-m", "PyInstaller", "webui/webui.spec", "--noconfirm"],
                   cwd=ROOT, check=True)
    dist = ROOT / "dist" / "DouyinLiveRecorderUI"
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "VERSION").write_text(version + "\n", encoding="utf-8")
    build_info = {
        "version": version,
        "channel": os.environ.get("RELEASE_CHANNEL", "dev"),
        "commit": os.environ.get("GITHUB_SHA", ""),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (dist / "build-info.json").write_text(
        json.dumps(build_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ffmpeg_dir = dist / "ffmpeg"
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)
    print("\nBuild finished.")
    print(f"version: {version}")
    print("Copy ffmpeg.exe and ffprobe.exe to:")
    print(f"  {ffmpeg_dir}")
    print("ffmpeg is intentionally not bundled in the executable.")


if __name__ == "__main__":
    main()
