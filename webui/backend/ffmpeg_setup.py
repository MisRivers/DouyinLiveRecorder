"""Download and install Windows FFmpeg binaries for the desktop EXE.

The desktop build intentionally does not bundle FFmpeg. This module downloads
an official Windows build archive over HTTPS, extracts only ffmpeg.exe and
ffprobe.exe into the application's ffmpeg directory, and validates the PE
header before replacing any existing file.
"""
from __future__ import annotations

import os
import shutil
import ssl
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

SOURCES = (
    ("gyan.dev", "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"),
    (
        "BtbN",
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
        "ffmpeg-master-latest-win64-gpl.zip",
    ),
)
MANUAL_URL = "https://www.gyan.dev/ffmpeg/builds/"
OFFICIAL_URL = "https://ffmpeg.org/download.html"
BINARIES = ("ffmpeg.exe", "ffprobe.exe")
MIN_BINARY_BYTES = 1024 * 1024

ProgressCallback = Callable[[int, int, str], None]


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def target_dir(root: str | Path) -> Path:
    return Path(root) / "ffmpeg"


def binary_path(root: str | Path, name: str) -> Path:
    return target_dir(root) / name


def is_installed(root: str | Path) -> bool:
    return all(binary_path(root, name).is_file() for name in BINARIES)


def install_from_zip(zip_path: str | Path, dest: str | Path) -> Path:
    dest_dir = Path(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    found: dict[str, zipfile.ZipInfo] = {}
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename.replace("\\", "/")).name.lower()
            if name in BINARIES and name not in found:
                found[name] = info
        missing = [name for name in BINARIES if name not in found]
        if missing:
            raise RuntimeError(f"压缩包中缺少 {', '.join(missing)}")
        for name, info in found.items():
            target = dest_dir / name
            temp = target.with_name(name + ".part")
            with archive.open(info) as source, open(temp, "wb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
            if not temp.is_file() or temp.stat().st_size < MIN_BINARY_BYTES:
                temp.unlink(missing_ok=True)
                raise RuntimeError(f"{name} 文件过小，下载可能不完整")
            with open(temp, "rb") as handle:
                if handle.read(2) != b"MZ":
                    temp.unlink(missing_ok=True)
                    raise RuntimeError(f"{name} 不是有效的 Windows 可执行文件")
            os.replace(temp, target)
    return dest_dir


def download_and_install(
    root: str | Path, progress: ProgressCallback | None = None
) -> Path:
    dest = target_dir(root)
    errors: list[str] = []
    for label, url in SOURCES:
        temp_path: Path | None = None
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "DLR-WebUI/1.0"}
            )
            with urllib.request.urlopen(
                request, timeout=60, context=_ssl_context()
            ) as response:
                total = int(response.headers.get("Content-Length") or 0)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temp:
                    temp_path = Path(temp.name)
                    downloaded = 0
                    while True:
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        temp.write(chunk)
                        downloaded += len(chunk)
                        if progress:
                            progress(downloaded, total, label)
            install_from_zip(temp_path, dest)
            return dest
        except Exception as exc:
            errors.append(f"{label}: {exc}")
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except OSError:
                    pass
    raise RuntimeError("自动下载失败；" + "；".join(errors))
