from __future__ import annotations

import re
import sqlite3

from .. import db, platform_registry
from ..errors import ApiError
from . import platform_service, schedule_service

SORT_FIELDS = {
    "sort_order": "r.sort_order",
    "custom_name": "COALESCE(NULLIF(r.custom_name,''), r.last_anchor_name, '')",
    "url": "r.url",
    "quality": "r.quality",
    "created_at": "r.created_at",
}

NAME_BAD = re.compile(r"[,，#\n\r]")


def _validate_name(name: str | None) -> str | None:
    if name is None:
        return None
    name = name.strip()
    if not name:
        return None
    if len(name) > 64:
        raise ApiError(422, "VALIDATION_FAILED", "自定义主播名不能超过 64 个字符")
    if NAME_BAD.search(name):
        raise ApiError(422, "VALIDATION_FAILED", "自定义主播名不能包含逗号、# 或换行")
    return name


def _validate_quality(quality: str) -> str:
    if quality not in platform_registry.QUALITY_OPTIONS:
        raise ApiError(422, "VALIDATION_FAILED", "画质取值不合法")
    return quality


def _room_row(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["enabled"] = bool(item["enabled"])
    if "platform_enabled" in item:
        item["platform_enabled"] = bool(item["platform_enabled"])
    return item


def list_rooms(query: str = "", enabled: bool | None = None, platform_code: str | None = None,
               page: int = 1, page_size: int = 50, sort: str = "sort_order",
               order: str = "asc") -> dict:
    page = max(1, page)
    page_size = min(200, max(1, page_size))
    where = []
    params: list = []
    if query:
        where.append("(r.url LIKE ? OR COALESCE(r.custom_name,'') LIKE ? OR COALESCE(r.last_anchor_name,'') LIKE ?)")
        like = f"%{query.strip()}%"
        params.extend([like, like, like])
    if enabled is not None:
        where.append("r.enabled=?")
        params.append(1 if enabled else 0)
    if platform_code:
        where.append("r.platform_code=?")
        params.append(platform_code)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    column = SORT_FIELDS.get(sort, SORT_FIELDS["sort_order"])
    direction = "DESC" if str(order).lower() == "desc" else "ASC"
    with db.connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM room r {clause}", params).fetchone()["c"]
        rows = conn.execute(
            f"""
            SELECT r.*, p.name AS platform_name, p.enabled AS platform_enabled,
                   COALESCE(l.state, CASE WHEN r.enabled=1 THEN 'checking' ELSE 'disabled' END) AS live_state
            FROM room r
            JOIN platform_template p ON p.code=r.platform_code
            LEFT JOIN live_state l ON l.room_id=r.id
            {clause}
            ORDER BY {column} {direction}, r.id ASC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, (page - 1) * page_size],
        ).fetchall()
    items = [_room_row(row) for row in rows]
    schedule_map = schedule_service.summaries([item["id"] for item in items])
    for item in items:
        info = schedule_map.get(item["id"], {"count": 0, "summary": "全天"})
        item["schedule_summary"] = info["summary"]
        item["schedule_count"] = info["count"]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _insert_room(payload: dict, actor: str, ip: str | None) -> dict:
    platform_code = (payload.get("platform_code") or "").strip()
    if not platform_registry.platform_by_code(platform_code):
        raise ApiError(422, "PLATFORM_NOT_SUPPORTED", "平台不存在或未适配")
    platform_service.require_enabled(platform_code)
    url = platform_registry.normalize_url(payload.get("url") or "")
    if not platform_registry.validate_platform_url(platform_code, url):
        raise ApiError(400, "INVALID_URL", "直播间地址与所选平台不匹配")
    quality = _validate_quality(payload.get("quality") or db.get_setting("原画|超清|高清|标清|流畅", "原画"))
    custom_name = _validate_name(payload.get("custom_name"))
    enabled = bool(payload.get("enabled", True))
    note = (payload.get("note") or "").strip() or None
    if note and len(note) > 500:
        raise ApiError(422, "VALIDATION_FAILED", "备注不能超过 500 个字符")
    with db.connect() as conn:
        duplicate = conn.execute("SELECT id FROM room WHERE url=?", (url,)).fetchone()
        if duplicate:
            raise ApiError(409, "DUPLICATE_URL", "该直播间地址已存在")
        order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM room").fetchone()["n"]
        cur = conn.execute(
            """
            INSERT INTO room
              (sort_order, enabled, custom_name, url, platform_code, quality, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (order, 1 if enabled else 0, custom_name, url, platform_code, quality, note,
             db.now_iso(), db.now_iso()),
        )
        room_id = int(cur.lastrowid)
        conn.execute(
            """
            INSERT INTO live_state (room_id, state, platform_code, quality, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (room_id, "checking" if enabled else "disabled", platform_code, quality, db.now_iso()),
        )
        conn.commit()
    db.render_url_config()
    db.audit(actor, "room.create", "room", str(room_id),
             {"url": url, "platform": platform_code}, ip)
    return get_room(room_id)


def get_room(room_id: int) -> dict:
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT r.*, p.name AS platform_name, p.enabled AS platform_enabled,
                   COALESCE(l.state, 'disabled') AS live_state
            FROM room r
            JOIN platform_template p ON p.code=r.platform_code
            LEFT JOIN live_state l ON l.room_id=r.id
            WHERE r.id=?
            """,
            (room_id,),
        ).fetchone()
    if not row:
        raise ApiError(404, "NOT_FOUND", "直播间不存在")
    return _room_row(row)


def create(payload: dict, actor: str, ip: str | None) -> dict:
    return _insert_room(payload, actor, ip)


def quick_add(payload: dict, actor: str, ip: str | None) -> dict:
    code = (payload.get("platform_code") or "").strip()
    platform = platform_registry.platform_by_code(code)
    if not platform:
        raise ApiError(422, "PLATFORM_NOT_SUPPORTED", "平台不存在或未适配")
    if platform.get("quick") != "id" or not platform.get("template"):
        raise ApiError(422, "FULL_URL_REQUIRED", "该平台需要填写完整直播间地址")
    url = platform_registry.build_url(code, payload.get("platform_id") or "")
    if not url:
        raise ApiError(400, "INVALID_URL", "平台 ID 格式不正确")
    data = dict(payload)
    data["url"] = url
    data.pop("platform_id", None)
    room = _insert_room(data, actor, ip)
    room["generated_url"] = url
    return room


def update(room_id: int, payload: dict, actor: str, ip: str | None) -> dict:
    room = get_room(room_id)
    fields = {}
    if "enabled" in payload:
        fields["enabled"] = 1 if bool(payload["enabled"]) else 0
    if "custom_name" in payload:
        fields["custom_name"] = _validate_name(payload["custom_name"])
    if "quality" in payload:
        fields["quality"] = _validate_quality(payload["quality"])
    if "note" in payload:
        fields["note"] = (payload.get("note") or "").strip()[:500] or None
    if "platform_code" in payload and payload["platform_code"] != room["platform_code"]:
        code = payload["platform_code"]
        if not platform_registry.platform_by_code(code):
            raise ApiError(422, "PLATFORM_NOT_SUPPORTED", "平台不存在或未适配")
        platform_service.require_enabled(code)
        if not platform_registry.validate_platform_url(code, room["url"]):
            raise ApiError(400, "INVALID_URL", "现有地址与新的平台不匹配")
        fields["platform_code"] = code
    if "url" in payload:
        url = platform_registry.normalize_url(payload["url"])
        code = fields.get("platform_code", room["platform_code"])
        if not platform_registry.validate_platform_url(code, url):
            raise ApiError(400, "INVALID_URL", "直播间地址与平台不匹配")
        fields["url"] = url
    if not fields:
        return room
    fields["updated_at"] = db.now_iso()
    columns = ", ".join(f'"{key}"=?' for key in fields)
    with db.connect() as conn:
        try:
            conn.execute(f"UPDATE room SET {columns} WHERE id=?", list(fields.values()) + [room_id])
        except sqlite3.IntegrityError as exc:
            raise ApiError(409, "DUPLICATE_URL", "该直播间地址已存在") from exc
        if "enabled" in fields:
            state = "checking" if fields["enabled"] else "disabled"
            conn.execute(
                "UPDATE live_state SET state=?, updated_at=? WHERE room_id=?",
                (state, db.now_iso(), room_id),
            )
        if "platform_code" in fields or "quality" in fields:
            conn.execute(
                "UPDATE live_state SET platform_code=?, quality=?, updated_at=? WHERE room_id=?",
                (
                    fields.get("platform_code", room["platform_code"]),
                    fields.get("quality", room["quality"]),
                    db.now_iso(), room_id,
                ),
            )
        conn.commit()
    db.render_url_config()
    db.audit(actor, "room.update", "room", str(room_id), fields, ip)
    return get_room(room_id)


def delete(room_id: int, actor: str, ip: str | None, force: bool = False) -> None:
    room = get_room(room_id)
    if room["live_state"] in ("recording", "live", "stopping") and not force:
        raise ApiError(409, "CONFLICT", "直播间正在录制，请先停用并等待录制结束")
    with db.connect() as conn:
        conn.execute("DELETE FROM room WHERE id=?", (room_id,))
        conn.commit()
    db.render_url_config()
    db.audit(actor, "room.delete", "room", str(room_id), {"force": force}, ip)


def reorder(ids: list[int], actor: str, ip: str | None) -> None:
    if not ids:
        return
    with db.connect() as conn:
        for index, room_id in enumerate(ids):
            conn.execute("UPDATE room SET sort_order=?, updated_at=? WHERE id=?",
                         (index, db.now_iso(), room_id))
        conn.commit()
    db.render_url_config()
    db.audit(actor, "room.reorder", "room", None, {"ids": ids}, ip)


def import_ini(content: str, actor: str, ip: str | None) -> dict:
    default_quality = db.get_setting("原画|超清|高清|标清|流畅", "原画")
    imported = 0
    skipped = 0
    skipped_disabled = 0
    errors = []
    with db.connect() as conn:
        enabled_codes = {
            row["code"] for row in conn.execute("SELECT code FROM platform_template WHERE enabled=1")
        }
        order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM room").fetchone()["n"]
        for line in content.splitlines():
            parsed = db.parse_room_line(line, default_quality)
            if not parsed:
                if line.strip():
                    skipped += 1
                    errors.append(line.strip()[:120])
                continue
            if parsed["platform_code"] not in enabled_codes:
                skipped_disabled += 1
                errors.append(f"{line.strip()[:100]}（平台已禁用）")
                continue
            try:
                conn.execute(
                    """
                    INSERT INTO room
                      (sort_order, enabled, custom_name, url, platform_code, quality, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (order, parsed["enabled"], parsed["custom_name"], parsed["url"],
                     parsed["platform_code"], parsed["quality"], db.now_iso(), db.now_iso()),
                )
                room_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
                conn.execute(
                    """
                    INSERT OR IGNORE INTO live_state
                      (room_id, state, platform_code, quality, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (room_id, "checking" if parsed["enabled"] else "disabled",
                     parsed["platform_code"], parsed["quality"], db.now_iso()),
                )
                order += 1
                imported += 1
            except sqlite3.IntegrityError:
                skipped += 1
        conn.commit()
    db.render_url_config()
    db.audit(actor, "room.import", "room", None,
             {"imported": imported, "skipped": skipped, "skipped_disabled": skipped_disabled}, ip)
    return {"imported": imported, "skipped": skipped + skipped_disabled,
            "skipped_disabled": skipped_disabled, "errors": errors[:20]}


def export_ini() -> str:
    path = db.render_url_config()
    return path.read_text(encoding="utf-8-sig")


def platforms() -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM platform_template WHERE enabled=1 ORDER BY name"
        ).fetchall()
    return [dict(row) for row in rows]
