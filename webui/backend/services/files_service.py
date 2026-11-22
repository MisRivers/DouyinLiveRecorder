from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .. import config, db, platform_registry
from ..errors import ApiError

MEDIA_EXT = {".ts", ".mp4", ".mkv", ".flv", ".m4a", ".mp3"}
PLAYABLE_EXT = {".mp4", ".m4a", ".mp3", ".ts", ".flv"}
TYPE_RANK = {".mp4": 0, ".ts": 0, ".mkv": 0, ".flv": 0, ".m4a": 1, ".mp3": 1}


def _is_hidden(name: str) -> bool:
    return name.startswith(".") or name.endswith((".tmp", ".part"))


def natural_key(value: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def _root() -> Path:
    return config.save_path_from_settings(db.get_settings())


def root() -> Path:
    return _root()


def _relative(path: Path) -> str | None:
    try:
        return path.resolve().relative_to(_root().resolve()).as_posix()
    except (ValueError, OSError):
        return None


def _anchor_for(parts: list[str], folder_by_author: bool) -> tuple[str, str, str | None]:
    platform_dir = parts[0] if parts and parts[0] in platform_registry.DIR_TO_CODE else None
    platform_code = platform_registry.DIR_TO_CODE.get(platform_dir) if platform_dir else None
    if folder_by_author and platform_dir and len(parts) >= 2:
        anchor_name = parts[1]
        return f"{platform_dir}/{anchor_name}", anchor_name, platform_code
    if folder_by_author and not platform_dir and len(parts) >= 1:
        anchor_name = parts[0]
        return anchor_name, anchor_name, platform_code
    if platform_dir:
        return platform_dir, platform_dir, platform_code
    return "未分类", "未分类", platform_code


def scan_index() -> dict:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    root_resolved = root.resolve()
    folder_by_author = db.bool_setting("保存文件夹是否以作者区分", True)
    seen: set[str] = set()
    added = 0
    updated = 0
    skipped = 0
    now = db.now_iso()

    def rel_of(path: Path) -> str | None:
        try:
            return path.resolve().relative_to(root_resolved).as_posix()
        except (ValueError, OSError):
            return None

    with db.connect() as conn:
        for current, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not _is_hidden(d)]
            current_path = Path(current)
            for filename in files:
                if _is_hidden(filename):
                    skipped += 1
                    continue
                ext = Path(filename).suffix.lower()
                if ext not in MEDIA_EXT:
                    skipped += 1
                    continue
                file_path = current_path / filename
                try:
                    stat = file_path.stat()
                except OSError:
                    skipped += 1
                    continue
                rel = rel_of(file_path)
                if not rel:
                    continue
                parts = rel.split("/")
                if len(parts) < 2:
                    continue
                anchor_key, anchor_name, platform_code = _anchor_for(parts[:-1], folder_by_author)
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
                existed = conn.execute(
                    "SELECT id, size_bytes, mtime, anchor_key, anchor_name, platform_code "
                    "FROM media_file WHERE path=?",
                    (str(file_path.resolve()),),
                ).fetchone()
                if existed:
                    changed = (
                        existed["size_bytes"] != stat.st_size
                        or existed["mtime"] != mtime
                        or existed["anchor_key"] != anchor_key
                        or existed["anchor_name"] != anchor_name
                        or existed["platform_code"] != platform_code
                    )
                    if changed:
                        conn.execute(
                            """
                            UPDATE media_file SET anchor_key=?, anchor_name=?, platform_code=?,
                              filename=?, extension=?, size_bytes=?, mtime=?, duration_seconds=NULL,
                              playable=?, updated_at=?
                            WHERE id=?
                            """,
                            (anchor_key, anchor_name, platform_code, filename, ext, stat.st_size,
                             mtime, 1 if ext in PLAYABLE_EXT else 0, now, existed["id"]),
                        )
                        updated += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO media_file
                          (anchor_key, anchor_name, platform_code, path, filename, extension,
                           size_bytes, mtime, playable, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (anchor_key, anchor_name, platform_code, str(file_path.resolve()),
                         filename, ext, stat.st_size, mtime, 1 if ext in PLAYABLE_EXT else 0,
                         now, now),
                    )
                    added += 1
                seen.add(str(file_path.resolve()))
        if seen:
            placeholders = ",".join("?" for _ in seen)
            conn.execute(
                f"DELETE FROM media_file WHERE path LIKE ? AND path NOT IN ({placeholders})",
                [f"{root_resolved}%"] + list(seen),
            )
        else:
            conn.execute("DELETE FROM media_file WHERE path LIKE ?", (f"{root_resolved}%",))
        conn.commit()
    db.set_meta("last_scan_at", now)
    return {"added": added, "updated": updated, "skipped": skipped, "root": str(root)}


def _anchor_rows() -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT anchor_key,
                   MAX(anchor_name) AS anchor_name,
                   MAX(platform_code) AS platform_code,
                   COUNT(*) AS file_count,
                   SUM(size_bytes) AS total_bytes,
                   MAX(mtime) AS latest_mtime,
                   SUM(CASE WHEN extension='.ts' THEN 1 ELSE 0 END) AS ts_count
            FROM media_file
            GROUP BY anchor_key
            """
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["platform_name"] = platform_registry.CODE_TO_NAME.get(item["platform_code"] or "", "")
        item["has_unconverted_ts"] = bool(item["ts_count"])
        item.pop("ts_count", None)
        result.append(item)
    return result


def anchors(sort: str = "name", order: str = "asc", query: str = "",
            page: int = 1, page_size: int = 50) -> dict:
    rows = _anchor_rows()
    if query:
        needle = query.strip().lower()
        rows = [row for row in rows if needle in (row["anchor_name"] or "").lower()]
    reverse = str(order).lower() == "desc"
    if sort == "mtime":
        rows.sort(key=lambda item: item["latest_mtime"] or "", reverse=reverse)
    elif sort == "type":
        rows.sort(key=lambda item: (item["platform_name"] or "", natural_key(item["anchor_name"] or "")),
                  reverse=reverse)
    else:
        rows.sort(key=lambda item: natural_key(item["anchor_name"] or ""), reverse=reverse)
    total = len(rows)
    page = max(1, page)
    page_size = min(200, max(1, page_size))
    start = (page - 1) * page_size
    return {"items": rows[start:start + page_size], "total": total, "page": page, "page_size": page_size}


def _file_rows(anchor_key: str) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT m.*, j.status AS conversion_status, j.progress AS conversion_progress
            FROM media_file m
            LEFT JOIN conversion_job j ON j.src_path=m.path
            WHERE m.anchor_key=?
            """,
            (anchor_key,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        rel = _relative(Path(item["path"]))
        if rel is None:
            continue
        item["rel_path"] = rel
        item["size_bytes"] = item["size_bytes"] or 0
        item["playable"] = bool(item["playable"])
        item.pop("path", None)
        result.append(item)
    return result


def files(anchor_key: str, sort: str = "name", order: str = "asc",
          page: int = 1, page_size: int = 200) -> dict:
    rows = _file_rows(anchor_key)
    reverse = str(order).lower() == "desc"
    if sort == "mtime":
        rows.sort(key=lambda item: item["mtime"] or "", reverse=reverse)
    elif sort == "type":
        rows.sort(
            key=lambda item: (TYPE_RANK.get(item["extension"], 9), natural_key(item["filename"])),
            reverse=reverse,
        )
    else:
        rows.sort(key=lambda item: natural_key(item["filename"]), reverse=reverse)
    total = len(rows)
    page = max(1, page)
    page_size = min(500, max(1, page_size))
    start = (page - 1) * page_size
    return {"items": rows[start:start + page_size], "total": total, "page": page, "page_size": page_size}


def playlist(anchor_key: str) -> list[dict]:
    rows = _file_rows(anchor_key)
    rows.sort(key=lambda item: natural_key(item["filename"]))
    return rows


def resolve_media_path(rel_path: str) -> Path:
    root = _root().resolve()
    candidate = (root / rel_path).resolve()
    if not candidate.is_relative_to(root):
        raise ApiError(403, "PATH_FORBIDDEN", "文件路径不合法")
    if candidate.suffix.lower() not in MEDIA_EXT:
        raise ApiError(403, "PATH_FORBIDDEN", "不支持的文件类型")
    if not candidate.is_file():
        raise ApiError(404, "FILE_NOT_FOUND", "文件不存在")
    return candidate


def _active_recording_targets() -> list[tuple[Path, str]]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT file_path FROM recording_session WHERE status='recording'
            UNION
            SELECT file_path FROM live_state WHERE state='recording'
            """
        ).fetchall()
    targets: list[tuple[Path, str]] = []
    for row in rows:
        value = row["file_path"]
        if not value:
            continue
        path = Path(value)
        parent = path.parent
        try:
            parent = parent.resolve()
        except OSError:
            pass
        if "%03d" in path.name:
            targets.append((parent, path.name.split("%03d", 1)[0]))
        else:
            targets.append((parent, path.name))
    return targets


def _is_active(path: Path, targets: list[tuple[Path, str]]) -> bool:
    # 只有最近仍在写入的文件才算“录制中”。这样旧会话、崩溃残留和已完成分段
    # 即使路径前缀匹配，也不会被永久拦截转码。
    try:
        if time.time() - path.stat().st_mtime > 30:
            return False
    except OSError:
        return False
    for parent, prefix in targets:
        if path.parent != parent:
            continue
        if path.name == prefix or path.name.startswith(prefix):
            return True
    return False


def enqueue_conversion(paths: list[str] | None = None, anchor_key: str | None = None,
                       trigger: str = "manual") -> dict:
    if isinstance(paths, str):
        paths = [paths]
    if not paths and anchor_key:
        paths = [item["rel_path"] for item in _file_rows(anchor_key) if item["extension"] == ".ts"]
    queued = []
    skipped = []
    rejected = []
    active_targets = _active_recording_targets()
    for rel in paths or []:
        try:
            source = resolve_media_path(rel)
        except ApiError as exc:
            rejected.append({"path": rel, "reason": exc.message})
            continue
        if source.suffix.lower() != ".ts":
            skipped.append({"path": rel, "reason": "不是 TS 文件"})
            continue
        if _is_active(source, active_targets):
            skipped.append({"path": rel, "reason": "文件仍在录制中"})
            continue
        target = source.with_suffix(".mp4")
        if target.exists() and target.stat().st_size > 0:
            skipped.append({"path": rel, "reason": "MP4 已存在"})
            continue
        with db.connect() as conn:
            existing = conn.execute(
                "SELECT id, status, dst_path FROM conversion_job WHERE src_path=?", (str(source),)
            ).fetchone()
            if existing:
                dst = Path(existing["dst_path"] or "")
                stale = existing["status"] == "succeeded" and (
                    not dst.exists() or dst.stat().st_size <= 0
                )
                if existing["status"] in ("failed", "canceled", "skipped") or stale:
                    conn.execute(
                        """
                        UPDATE conversion_job
                        SET status='pending', progress=0, attempts=0, error_code=NULL,
                            error_message=NULL, trigger=?, finished_at=NULL
                        WHERE id=?
                        """,
                        (trigger, existing["id"]),
                    )
                    conn.commit()
                    queued.append(rel)
                else:
                    skipped.append({"path": rel, "reason": "已在转码队列中"})
                continue
            conn.execute(
                """
                INSERT INTO conversion_job
                  (src_path, dst_path, status, progress, attempts, trigger, created_at)
                VALUES (?, ?, 'pending', 0, 0, ?, ?)
                """,
                (str(source), str(target), trigger, db.now_iso()),
            )
            conn.commit()
            queued.append(rel)
    return {"queued": queued, "skipped": skipped, "rejected": rejected}


def conversions(status: str | None = None, page: int = 1, page_size: int = 50) -> dict:
    where = "WHERE status=?" if status else ""
    params = [status] if status else []
    with db.connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM conversion_job {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM conversion_job {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size],
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["src_rel"] = _relative(Path(item["src_path"]))
        item["dst_rel"] = _relative(Path(item["dst_path"]))
        items.append(item)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def cancel_conversion(job_id: int) -> None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM conversion_job WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise ApiError(404, "NOT_FOUND", "转码任务不存在")
        if row["status"] in ("running", "succeeded", "failed"):
            raise ApiError(409, "CONFLICT", "当前任务状态不能取消")
        conn.execute("UPDATE conversion_job SET status='canceled', finished_at=? WHERE id=?",
                     (db.now_iso(), job_id))
        conn.commit()


def media_duration(rel_path: str) -> dict:
    source = resolve_media_path(rel_path)
    with db.connect() as conn:
        row = conn.execute(
            "SELECT duration_seconds FROM media_file WHERE path=?", (str(source),)
        ).fetchone()
    if row and row["duration_seconds"] and row["duration_seconds"] > 0:
        return {"duration": float(row["duration_seconds"])}
    from .recorder_control import ffmpeg_path, ffprobe_path

    duration = 0.0
    probe = ffprobe_path()
    if probe:
        try:
            result = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration:stream=duration",
                 "-of", "json", str(source)],
                capture_output=True, text=True, timeout=30,
            )
            payload = json.loads(result.stdout or "{}")
            raw = (payload.get("format") or {}).get("duration")
            if not raw:
                values = [item.get("duration") for item in payload.get("streams") or []]
                raw = max((float(value) for value in values if value not in (None, "N/A")), default=0)
            duration = float(raw or 0)
        except Exception:
            duration = 0
    if duration <= 0:
        ffmpeg = ffmpeg_path()
        if not ffmpeg:
            return {"duration": None}
        try:
            result = subprocess.run(
                [ffmpeg, "-hide_banner", "-i", str(source)],
                capture_output=True, text=True, timeout=30,
            )
            match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr or "")
            if match:
                duration = (int(match.group(1)) * 3600 + int(match.group(2)) * 60
                            + float(match.group(3)))
        except Exception:
            duration = 0
    if duration > 0:
        with db.connect() as conn:
            conn.execute(
                "UPDATE media_file SET duration_seconds=?, updated_at=? WHERE path=?",
                (duration, db.now_iso(), str(source)),
            )
            conn.commit()
    return {"duration": duration or None}


def _running_conversion_paths() -> set[str]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT src_path, dst_path FROM conversion_job WHERE status='running'"
        ).fetchall()
    paths = set()
    for row in rows:
        if row["src_path"]:
            paths.add(str(Path(row["src_path"]).resolve()))
        if row["dst_path"]:
            paths.add(str(Path(row["dst_path"]).resolve()))
    return paths


def delete_media(paths: list[str] | None = None, anchor_key: str | None = None) -> dict:
    if isinstance(paths, str):
        paths = [paths]
    rels = list(paths or [])
    if not rels and anchor_key:
        rels = [item["rel_path"] for item in _file_rows(anchor_key)]
    rels = list(dict.fromkeys(rels))
    deleted: list[str] = []
    skipped: list[dict] = []
    rejected: list[dict] = []
    deleted_paths: list[Path] = []
    active_targets = _active_recording_targets()
    running = _running_conversion_paths()
    root = _root().resolve()

    for rel in rels:
        try:
            source = resolve_media_path(rel)
        except ApiError as exc:
            rejected.append({"path": rel, "reason": exc.message})
            continue
        if _is_active(source, active_targets):
            skipped.append({"path": rel, "reason": "文件仍在录制中"})
            continue
        if str(source) in running:
            skipped.append({"path": rel, "reason": "文件正在转码"})
            continue
        try:
            source.unlink()
        except OSError as exc:
            skipped.append({"path": rel, "reason": f"删除失败：{exc.strerror or exc}"})
            continue
        for sidecar in (source.with_suffix(".srt"), source.with_suffix(".vtt")):
            try:
                if sidecar.exists():
                    sidecar.unlink()
            except OSError:
                pass
        deleted.append(rel)
        deleted_paths.append(source)
        try:
            parent = source.parent
            while parent != root and parent.is_relative_to(root):
                parent.rmdir()
                parent = parent.parent
        except OSError:
            pass

    if deleted_paths:
        with db.connect() as conn:
            for path in deleted_paths:
                value = str(path)
                conn.execute(
                    "DELETE FROM conversion_job WHERE src_path=? OR dst_path=?", (value, value)
                )
                conn.execute("DELETE FROM media_file WHERE path=?", (value,))
            conn.commit()
    return {"deleted": deleted, "skipped": skipped, "rejected": rejected}


def orphan_ts(limit: int = 200) -> list[Path]:
    root = _root().resolve()
    if not root.exists():
        return []
    result = []
    cutoff = datetime.now(timezone.utc).timestamp() - 600
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not _is_hidden(d)]
        for filename in files:
            if not filename.lower().endswith(".ts") or _is_hidden(filename):
                continue
            path = Path(current) / filename
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_mtime > cutoff:
                continue
            result.append(path)
            if len(result) >= limit:
                return result
    return result
