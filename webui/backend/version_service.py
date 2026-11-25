"""Application version and GitHub release update checks."""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read_version() -> str:
    override = os.environ.get("DLR_APP_VERSION", "").strip()
    if override:
        return override
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "VERSION")
    candidates.append(Path(__file__).resolve().parents[2] / "VERSION")
    candidates.append(Path.cwd() / "VERSION")
    for path in candidates:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return "1.0.0"


APP_VERSION = _read_version()
REPOSITORY = "MisRivers/DouyinLiveRecorder"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
CACHE_SECONDS = 1800
RETRY_SECONDS = 60

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"at": 0.0, "data": None}


def current_version() -> str:
    return APP_VERSION


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _version_tuple(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(value or ""))
    return tuple(int(item) for item in numbers[:4]) or (0,)


def is_newer(latest: str | None, current: str = APP_VERSION) -> bool:
    if not latest:
        return False
    return _version_tuple(latest) > _version_tuple(current)


def _request_release() -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "DLR-WebUI/1.0",
    }
    token = os.environ.get("DLR_GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(LATEST_RELEASE_API, headers=headers)
    try:
        with urllib.request.urlopen(
            request, timeout=8, context=_ssl_context()
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {
                "latest": None,
                "release_url": RELEASES_URL,
                "published_at": None,
                "notes": "",
                "assets": [],
                "error": None,
                "message": "暂无 GitHub 发行版",
            }
        raise
    assets = [
        {
            "name": item.get("name") or "",
            "url": item.get("browser_download_url") or "",
            "size": item.get("size") or 0,
        }
        for item in payload.get("assets") or []
    ]
    latest = str(payload.get("tag_name") or "").removeprefix("webui-").lstrip("vV")
    return {
        "latest": latest or None,
        "release_url": payload.get("html_url") or RELEASES_URL,
        "published_at": payload.get("published_at"),
        "notes": str(payload.get("body") or "")[:4000],
        "assets": assets,
        "error": None,
        "message": "",
    }


def check(force: bool = False) -> dict[str, Any]:
    now = time.time()
    with _cache_lock:
        cached = _cache["data"]
        if not force and cached and now - _cache["at"] < CACHE_SECONDS:
            return dict(cached)
    try:
        data = _request_release()
        error = None
    except Exception as exc:
        data = {
            "latest": None,
            "release_url": RELEASES_URL,
            "published_at": None,
            "notes": "",
            "assets": [],
            "message": "",
        }
        error = str(exc)
    result = {
        "current": APP_VERSION,
        **data,
        "update_available": is_newer(data.get("latest")),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "error": error,
    }
    with _cache_lock:
        _cache["at"] = now if error is None else now - CACHE_SECONDS + RETRY_SECONDS
        _cache["data"] = result
    return dict(result)
