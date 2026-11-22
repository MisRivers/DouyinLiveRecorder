from __future__ import annotations

import shutil
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request

from .. import config, db, security
from ..responses import ok
from ..services import files_service, recorder_control

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
def health():
    checks = {}
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
    try:
        free = shutil.disk_usage(config.DOWNLOAD_DIR).free / (1024 ** 3)
        checks["disk_free_gb"] = round(free, 2)
    except OSError as exc:
        checks["disk"] = f"error: {exc}"
    checks["ffmpeg"] = recorder_control.ffmpeg_path() or "missing"
    checks["recorder_heartbeat"] = db.get_meta("recorder_heartbeat")
    checks["converter_heartbeat"] = db.get_meta("converter_heartbeat")
    ok_all = checks["database"] == "ok" and checks["ffmpeg"] != "missing"
    return {"data": {"status": "ok" if ok_all else "degraded", "checks": checks}}


@router.get("/info")
def info(request: Request, session: dict = Depends(security.require_user)):
    return ok({
        "version": db.get_meta("schema_version", "1"),
        "upstream_version": recorder_control.upstream_version(),
        "root": str(config.ROOT_DIR),
        "data_dir": str(config.DATA_DIR),
        "config_dir": str(config.CONFIG_DIR),
        "download_dir": str(config.save_path_from_settings(db.get_settings())),
        "db_size": config.DB_PATH.stat().st_size if config.DB_PATH.exists() else 0,
        "setup_completed": db.get_meta("setup_completed", "0") == "1",
        "last_scan_at": db.get_meta("last_scan_at"),
    }, request)


@router.get("/logs")
def logs(request: Request, limit: int = Query(200, ge=1, le=2000),
         session: dict = Depends(security.require_user)):
    lines: list[str] = []
    sources = ["webui.log", "recorder.log", "converter.log"]
    per_file = max(20, limit // len(sources))
    found = []
    for name in sources:
        path = config.LOG_DIR / name
        if not path.exists():
            continue
        found.append(name)
        try:
            part = path.read_text(encoding="utf-8", errors="replace").splitlines()[-per_file:]
            lines.append(f"--- {name} ---")
            lines.extend(part)
        except OSError:
            continue
    return ok({"lines": lines[-limit:], "file": ", ".join(found) or None}, request)


@router.post("/scan-files")
def scan_files(request: Request, session: dict = Depends(security.require_user),
               _: None = Depends(security.require_csrf)):
    threading.Thread(target=files_service.scan_index, daemon=True).start()
    return ok({"started": True}, request, 202)
