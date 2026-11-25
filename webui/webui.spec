# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows one-folder build.

ffmpeg is intentionally NOT bundled. Place ffmpeg.exe and ffprobe.exe in a
sibling `ffmpeg` directory next to DouyinLiveRecorderUI.exe.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
ICON = ROOT / "webui" / "assets" / "logo.ico"

datas = [
    (str(ROOT / "webui" / "backend" / "static"), "webui/backend/static"),
    (str(ROOT / "webui" / "backend" / "schema.sql"), "webui/backend"),
    (str(ROOT / "src" / "javascript"), "src/javascript"),
    # config.ini is intentionally not bundled: it may contain cookies/tokens,
    # and the app generates defaults in the runtime config directory.
    (str(ROOT / "msg_push.py"), "."),
    (str(ROOT / "pyproject.toml"), "."),
]

hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("fastapi")
    + collect_submodules("src")
    + [
        "webui.backend.main",
        "webui.backend.desktop_launcher",
        "webui.backend.ffmpeg_setup",
        "webui.backend.version_service",
        "webui.backend.workers.recorder_worker",
        "webui.backend.workers.converter_worker",
        "tkinter",
        "tkinter.messagebox",
        "tkinter.ttk",
    ]
)

a = Analysis(
    [str(ROOT / "webui" / "backend" / "desktop_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[str(ROOT / "webui" / "runtime_hooks" / "streams.py")],
    excludes=["matplotlib", "numpy", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DouyinLiveRecorderUI",
    icon=str(ICON) if ICON.exists() else None,
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DouyinLiveRecorderUI",
)
