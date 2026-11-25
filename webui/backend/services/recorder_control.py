from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from .. import config, db, platform_registry
from ..errors import ApiError

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def ffmpeg_path() -> str | None:
    candidates = [
        config.ROOT_DIR / "ffmpeg" / ("ffmpeg.exe" if config.os.name == "nt" else "ffmpeg"),
        Path(shutil.which("ffmpeg") or ""),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def ffprobe_path() -> str | None:
    candidates = [
        config.ROOT_DIR / "ffmpeg" / ("ffprobe.exe" if config.os.name == "nt" else "ffprobe"),
        Path(shutil.which("ffprobe") or ""),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


@lru_cache(maxsize=8)
def _version(binary: str | None) -> str | None:
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "-version"], capture_output=True, text=True, timeout=10,
            creationflags=_NO_WINDOW,
        )
        return (result.stdout.splitlines() or [""])[0]
    except Exception:
        return None


def upstream_version() -> str | None:
    try:
        import tomllib

        with open(config.ROOT_DIR / "pyproject.toml", "rb") as handle:
            data = tomllib.load(handle)
        return data.get("project", {}).get("version")
    except Exception:
        return None


def status() -> dict:
    state = db.recorder_state()
    with db.connect() as conn:
        counts = conn.execute(
            """
            SELECT
              SUM(CASE WHEN state='recording' THEN 1 ELSE 0 END) AS recording_count,
              SUM(CASE WHEN state IN ('waiting','checking','live','error','stopping') THEN 1 ELSE 0 END) AS waiting_count,
              COUNT(*) AS total_count
            FROM live_state
            """
        ).fetchone()
        enabled = conn.execute("SELECT COUNT(*) AS c FROM room WHERE enabled=1").fetchone()["c"]
        last_session = conn.execute(
            "SELECT * FROM recording_session ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return {
        "state": state["state"],
        "heartbeat_at": state["heartbeat_at"],
        "recording_count": counts["recording_count"] or 0,
        "waiting_count": counts["waiting_count"] or 0,
        "enabled_room_count": enabled,
        "total_room_count": counts["total_count"] or 0,
        "ffmpeg_path": ffmpeg_path(),
        "ffmpeg_version": _version(ffmpeg_path()),
        "node_available": bool(shutil.which("node")),
        "upstream_version": upstream_version(),
        "last_session": dict(last_session) if last_session else None,
    }


def _disk_free_gb() -> float:
    root = config.save_path_from_settings(db.get_settings())
    root.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(root).free / (1024 ** 3)


def start(actor: str, ip: str | None = None) -> dict:
    current = db.recorder_state()["state"]
    if current in ("starting", "running", "stopping"):
        raise ApiError(409, "ALREADY_RUNNING", "录制程序已经在运行或正在切换状态")
    if not ffmpeg_path():
        raise ApiError(412, "FFMPEG_MISSING", "未找到 ffmpeg，请检查 ffmpeg/ffmpeg.exe 或系统 PATH")
    with db.connect() as conn:
        enabled = conn.execute("SELECT COUNT(*) AS c FROM room WHERE enabled=1").fetchone()["c"]
    if enabled == 0:
        raise ApiError(422, "NO_ENABLED_ROOMS", "没有启用的直播间")
    threshold = float(db.get_setting("录制空间剩余阈值(gb)", "1.0") or 0)
    if _disk_free_gb() < threshold:
        raise ApiError(507, "DISK_LOW", "磁盘剩余空间低于设置阈值，无法启动录制")
    command_id = db.enqueue_command("recorder.start")
    db.set_meta("recorder_state", "starting")
    db.audit(actor, "recorder.start", "recorder", str(command_id), None, ip)
    return {"command_id": command_id, "state": "starting"}


def stop(mode: str = "graceful", actor: str = "", ip: str | None = None) -> dict:
    current = db.recorder_state()["state"]
    if current in ("stopped", "stopping"):
        raise ApiError(409, "NOT_RUNNING", "录制程序当前没有运行或正在停止")
    command_id = db.enqueue_command("recorder.stop", {"mode": mode})
    db.set_meta("recorder_state", "stopping")
    db.audit(actor, "recorder.stop", "recorder", str(command_id), {"mode": mode}, ip)
    return {"command_id": command_id, "state": "stopping", "will_convert": True}


def restart(actor: str, ip: str | None = None) -> dict:
    if not ffmpeg_path():
        raise ApiError(412, "FFMPEG_MISSING", "未找到 ffmpeg，请检查 ffmpeg/ffmpeg.exe 或系统 PATH")
    command_id = db.enqueue_command("recorder.restart")
    db.set_meta("recorder_state", "starting")
    db.audit(actor, "recorder.restart", "recorder", str(command_id), None, ip)
    return {"command_id": command_id, "state": "starting"}


def platforms_status() -> list[dict]:
    return [
        {"code": item["code"], "name": item["name"], "dir_name": item["dir_name"]}
        for item in platform_registry.PLATFORMS
    ]
