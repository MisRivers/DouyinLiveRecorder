from __future__ import annotations

from datetime import datetime, timezone

from .. import db


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def recordings() -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT l.*, r.custom_name, r.url, r.enabled, p.name AS platform_name
            FROM live_state l
            JOIN room r ON r.id=l.room_id
            JOIN platform_template p ON p.code=r.platform_code
            WHERE l.state='recording'
            ORDER BY l.started_at ASC
            """
        ).fetchall()
    now = datetime.now(timezone.utc)
    items = []
    for row in rows:
        item = dict(row)
        started = _parse_time(item.get("started_at"))
        item["elapsed_seconds"] = int((now - started).total_seconds()) if started else 0
        item["anchor_display"] = item.get("custom_name") or item.get("anchor_name") or ""
        items.append(item)
    return items


def waiting(query: str = "", page: int = 1, page_size: int = 100) -> dict:
    page = max(1, page)
    page_size = min(500, max(1, page_size))
    where = "WHERE l.state <> 'recording' AND r.enabled=1"
    params: list = []
    if query:
        where += " AND (COALESCE(r.custom_name,'') LIKE ? OR COALESCE(l.anchor_name,'') LIKE ? OR r.url LIKE ?)"
        like = f"%{query.strip()}%"
        params.extend([like, like, like])
    with db.connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM live_state l JOIN room r ON r.id=l.room_id {where}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"""
            SELECT l.*, r.custom_name, r.url, r.enabled, p.name AS platform_name
            FROM live_state l
            JOIN room r ON r.id=l.room_id
            JOIN platform_template p ON p.code=r.platform_code
            {where}
            ORDER BY r.sort_order ASC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, (page - 1) * page_size],
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["anchor_display"] = item.get("custom_name") or item.get("anchor_name") or ""
        items.append(item)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def summary() -> dict:
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT
              SUM(CASE WHEN state='recording' THEN 1 ELSE 0 END) AS recording,
              SUM(CASE WHEN state IN ('waiting','checking','live') THEN 1 ELSE 0 END) AS waiting,
              SUM(CASE WHEN state='error' THEN 1 ELSE 0 END) AS error,
              COUNT(*) AS total
            FROM live_state
            """
        ).fetchone()
        enabled = conn.execute("SELECT COUNT(*) AS c FROM room WHERE enabled=1").fetchone()["c"]
    from ..services.recorder_control import status

    return {
        "recording": row["recording"] or 0,
        "waiting": row["waiting"] or 0,
        "error": row["error"] or 0,
        "enabled": enabled,
        "total": row["total"] or 0,
        "recorder": status(),
    }
