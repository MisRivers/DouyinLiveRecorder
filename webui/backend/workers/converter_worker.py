from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .. import config, db, platform_registry
from ..services import files_service, notification_service, recorder_control

log = logging.getLogger("dlr.converter")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _ffmpeg() -> str:
    path = recorder_control.ffmpeg_path()
    if not path:
        raise RuntimeError("ffmpeg 未安装")
    return path


def _ffprobe_duration(path: Path) -> float:
    probe = recorder_control.ffprobe_path()
    if not probe:
        return 0.0
    try:
        result = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30, creationflags=_NO_WINDOW,
        )
        return float((result.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _temp_path(dst: Path) -> Path:
    return dst.with_name(dst.stem + ".part" + dst.suffix)


def _convert(job: dict) -> tuple[bool, str | None]:
    src = Path(job["src_path"])
    dst = Path(job["dst_path"])
    if dst.exists() and dst.stat().st_size > 0:
        if db.bool_setting("追加格式后删除原文件", False):
            try:
                src.unlink()
            except OSError:
                pass
        return True, None
    if not src.exists() or src.stat().st_size <= 0:
        return False, "源文件不存在或为空"
    try:
        if shutil.disk_usage(dst.parent).free < 500 * 1024 * 1024:
            return False, "磁盘剩余空间不足 500 MB"
    except OSError:
        pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = _temp_path(dst)
    if tmp.exists():
        try:
            tmp.unlink()
        except OSError:
            pass
    duration = _ffprobe_duration(src)
    reencode = db.bool_setting("mp4格式重新编码为h264", False)
    ffmpeg = _ffmpeg()
    if reencode:
        args = [
            ffmpeg, "-y", "-i", str(src), "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "23", "-vf", "format=yuv420p", "-c:a", "copy", "-movflags", "+faststart",
            "-f", "mp4", "-progress", "pipe:1", "-nostats", str(tmp),
        ]
    else:
        args = [
            ffmpeg, "-y", "-i", str(src), "-c", "copy", "-movflags", "+faststart",
            "-f", "mp4", "-progress", "pipe:1", "-nostats", str(tmp),
        ]
    log_path = Path(config.LOG_DIR) / f"convert-{job['id']}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "wb") as log_file:
        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=log_file, text=True,
            creationflags=_NO_WINDOW,
        )
        last_update = 0.0
        while proc.poll() is None:
            line = proc.stdout.readline() if proc.stdout else ""
            if line.startswith("out_time_ms=") and duration > 0:
                try:
                    seconds = int(line.split("=", 1)[1].strip()) / 1_000_000
                    progress = min(0.99, max(0.0, seconds / duration))
                    now = time.time()
                    if now - last_update > 1:
                        with db.connect() as conn:
                            conn.execute("UPDATE conversion_job SET progress=? WHERE id=?",
                                         (progress, job["id"]))
                            conn.commit()
                        last_update = now
                except ValueError:
                    pass
            time.sleep(0.05)
        returncode = proc.wait()
    if returncode != 0:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False, f"ffmpeg 退出码 {returncode}，详见 {log_path.name}"
    if not tmp.exists() or tmp.stat().st_size <= 0:
        return False, "转码输出为空"
    os.replace(tmp, dst)
    if db.bool_setting("追加格式后删除原文件", False):
        try:
            src.unlink()
        except OSError:
            pass
    return True, None


def _claim() -> dict | None:
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM conversion_job WHERE status='pending' ORDER BY id LIMIT 1"
        ).fetchone()
        if not row:
            conn.execute("COMMIT")
            return None
        conn.execute(
            "UPDATE conversion_job SET status='running', started_at=?, progress=0 WHERE id=?",
            (db.now_iso(), row["id"]),
        )
        conn.execute("COMMIT")
        return dict(row)
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def _notify_context(job: dict) -> dict:
    src = Path(job["src_path"])
    anchor = src.parent.name
    platform = "-"
    for item in platform_registry.PLATFORMS:
        if item.get("dir_name") == src.parent.parent.name:
            platform = item.get("name") or item["code"]
            break
    return {
        "主播": anchor,
        "平台": platform,
        "时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "文件名": Path(job["dst_path"]).name,
    }


def _process(job: dict) -> None:
    log.info("converting %s", job["src_path"])
    try:
        ok, error = _convert(job)
    except Exception as exc:
        log.exception("conversion crashed for %s", job["src_path"])
        ok, error = False, f"{type(exc).__name__}: {exc}"
    with db.connect() as conn:
        if ok:
            conn.execute(
                "UPDATE conversion_job SET status='succeeded', progress=1, finished_at=?, "
                "error_code=NULL, error_message=NULL WHERE id=?",
                (db.now_iso(), job["id"]),
            )
        else:
            attempts = (job["attempts"] or 0) + 1
            status = "failed" if attempts >= 2 else "pending"
            conn.execute(
                "UPDATE conversion_job SET status=?, attempts=?, error_code='CONVERT_FAILED', "
                "error_message=?, finished_at=CASE WHEN ?='failed' THEN ? ELSE NULL END WHERE id=?",
                (status, attempts, (error or "")[:500], status, db.now_iso(), job["id"]),
            )
        conn.commit()
    if ok:
        log.info("converted %s", job["dst_path"])
        dst = Path(job["dst_path"])
        size = dst.stat().st_size if dst.exists() else 0
        duration = _ffprobe_duration(dst) if dst.exists() else 0
        notification_service.emit(
            "conversion_finished", None,
            **(_notify_context(job) | {
                "时长": notification_service.context_duration(duration),
                "文件大小": notification_service.context_size(size),
            }),
        )
    else:
        log.warning("conversion failed %s: %s", job["src_path"], error)
        if status == "failed":
            notification_service.emit(
                "recording_error", None,
                **(_notify_context(job) | {"错误原因": f"转码失败：{error}"}),
            )


def _startup() -> None:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM conversion_job WHERE status='running'").fetchall()
        conn.execute("UPDATE conversion_job SET status='pending', progress=0 WHERE status='running'")
        conn.commit()
    for row in rows:
        tmp = _temp_path(Path(row["dst_path"]))
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
    try:
        rels = []
        root = files_service.root()
        for path in files_service.orphan_ts(200):
            try:
                rels.append(path.relative_to(root).as_posix())
            except ValueError:
                continue
        if rels:
            files_service.enqueue_conversion(rels, trigger="startup")
            log.info("queued %s orphan TS files", len(rels))
    except Exception as exc:
        log.warning("orphan TS scan failed: %s", exc)


def run_converter_worker() -> None:
    config.ensure_dirs()
    if not log.handlers:
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        file_handler = RotatingFileHandler(
            config.LOG_DIR / "converter.log", maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        if sys.stderr is not None:
            stream = logging.StreamHandler()
            stream.setFormatter(formatter)
            root.addHandler(stream)
    db.init_db()
    _startup()
    log.info("converter worker started")
    last_heartbeat = 0.0
    while True:
        job = _claim()
        if job:
            _process(job)
            continue
        now = time.time()
        if now - last_heartbeat > 5:
            db.set_meta("converter_heartbeat", db.now_iso())
            last_heartbeat = now
        time.sleep(1)
