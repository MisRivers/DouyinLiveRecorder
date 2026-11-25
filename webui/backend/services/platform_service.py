from __future__ import annotations

from .. import db
from ..errors import ApiError


def list_platforms(include_disabled: bool = True, query: str = "") -> list[dict]:
    where = [] if include_disabled else ["p.enabled=1"]
    params: list = []
    if query:
        where.append("(p.name LIKE ? OR p.code LIKE ?)")
        like = f"%{query.strip()}%"
        params.extend([like, like])
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT p.*,
                   (SELECT COUNT(*) FROM room r WHERE r.platform_code=p.code) AS room_count
            FROM platform_template p
            {clause}
            ORDER BY p.name
            """,
            params,
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        item["needs_cookie"] = bool(item["needs_cookie"])
        item["proxy_recommended"] = bool(item["proxy_recommended"])
        item["room_count"] = int(item["room_count"])
        items.append(item)
    return items


def is_enabled(code: str) -> bool:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT enabled FROM platform_template WHERE code=?", (code,)
        ).fetchone()
    return bool(row and row["enabled"])


def require_enabled(code: str) -> None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT enabled FROM platform_template WHERE code=?", (code,)
        ).fetchone()
    if not row:
        raise ApiError(422, "PLATFORM_NOT_SUPPORTED", "平台不存在或未适配")
    if not row["enabled"]:
        raise ApiError(422, "PLATFORM_DISABLED", "该平台已禁用，请先在平台管理中启用")


def set_enabled(code: str, enabled: bool, actor: str, ip: str | None = None) -> dict:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT code, name, enabled FROM platform_template WHERE code=?", (code,)
        ).fetchone()
        if not row:
            raise ApiError(404, "PLATFORM_NOT_FOUND", "平台不存在")
        affected = conn.execute(
            "SELECT COUNT(*) AS c FROM room WHERE platform_code=? AND enabled=1", (code,)
        ).fetchone()["c"]
        if bool(row["enabled"]) != bool(enabled):
            conn.execute(
                "UPDATE platform_template SET enabled=?, updated_at=? WHERE code=?",
                (1 if enabled else 0, db.now_iso(), code),
            )
            conn.commit()
            db.enqueue_command("room.reload", {"reason": "platform", "code": code})
    db.audit(actor, "platform.toggle", "platform", code,
             {"enabled": bool(enabled), "affected_rooms": int(affected)}, ip)
    return {"code": code, "name": row["name"], "enabled": bool(enabled),
            "affected_rooms": int(affected)}
