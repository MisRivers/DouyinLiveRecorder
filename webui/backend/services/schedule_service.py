from __future__ import annotations

from datetime import datetime, time, timedelta

from .. import db
from ..errors import ApiError

MAX_WINDOWS = 20
WEEKDAY_LABELS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def _parse_clock(value: str, field: str) -> int:
    raw = (value or "").strip()
    try:
        hour_text, minute_text = raw.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (ValueError, AttributeError):
        raise ApiError(422, "INVALID_SCHEDULE", f"{field}时间格式应为 HH:mm") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ApiError(422, "INVALID_SCHEDULE", f"{field}时间超出范围")
    return hour * 60 + minute


def _clock_text(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _normalize_windows(windows: list[dict]) -> list[dict]:
    if not isinstance(windows, list):
        raise ApiError(422, "INVALID_SCHEDULE", "计划格式不正确")
    if len(windows) > MAX_WINDOWS:
        raise ApiError(422, "INVALID_SCHEDULE", f"单个直播间最多 {MAX_WINDOWS} 个时间段")
    result = []
    for item in windows:
        if not isinstance(item, dict):
            raise ApiError(422, "INVALID_SCHEDULE", "计划格式不正确")
        days = sorted({int(day) for day in item.get("weekdays", []) if str(day).isdigit()})
        if not days:
            raise ApiError(422, "INVALID_SCHEDULE", "请至少选择一个星期")
        if any(day < 0 or day > 6 for day in days):
            raise ApiError(422, "INVALID_SCHEDULE", "星期取值不合法")
        start = _parse_clock(item.get("start", ""), "开始")
        end = _parse_clock(item.get("end", ""), "结束")
        if start == end:
            raise ApiError(422, "INVALID_SCHEDULE", "开始时间与结束时间不能相同")
        result.append({"weekdays": days, "start": start, "end": end})
    _ensure_no_overlap(result)
    return result


def _segments(windows: list[dict]) -> list[tuple[int, int, int]]:
    segments = []
    for window in windows:
        start, end = window["start"], window["end"]
        for day in window["weekdays"]:
            if start < end:
                segments.append((day, start, end))
            else:
                segments.append((day, start, 1440))
                segments.append(((day + 1) % 7, 0, end))
    return segments


def _ensure_no_overlap(windows: list[dict]) -> None:
    by_day: dict[int, list[tuple[int, int, str]]] = {}
    for window in windows:
        label = f"{'/'.join(WEEKDAY_LABELS[d] for d in window['weekdays'])} " \
                f"{_clock_text(window['start'])}-{_clock_text(window['end'])}"
        for day, start, end in _segments([window]):
            by_day.setdefault(day, []).append((start, end, label))
    for day, items in by_day.items():
        items.sort()
        for previous, current in zip(items, items[1:]):
            if current[0] < previous[1]:
                raise ApiError(
                    422, "SCHEDULE_OVERLAP",
                    f"{WEEKDAY_LABELS[day]}存在重叠时间段：{previous[2]} 与 {current[2]}",
                )


def _rows(room_id: int) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, weekdays, start_minute, end_minute FROM room_schedule WHERE room_id=? ORDER BY id",
            (room_id,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "weekdays": [int(day) for day in str(row["weekdays"]).split(",") if day != ""],
            "start": int(row["start_minute"]),
            "end": int(row["end_minute"]),
        }
        for row in rows
    ]


def _display(rows: list[dict]) -> list[dict]:
    return [
        {
            "id": row["id"],
            "weekdays": row["weekdays"],
            "start": _clock_text(row["start"]),
            "end": _clock_text(row["end"]),
        }
        for row in rows
    ]


def windows_for_room(room_id: int) -> list[dict]:
    return _rows(room_id)


def _weekday_text(days: list[int]) -> str:
    days = sorted(set(days))
    if len(days) == 7:
        return "每天"
    parts, start, previous = [], days[0], days[0]
    for day in days[1:]:
        if day == previous + 1:
            previous = day
            continue
        parts.append((start, previous))
        start = previous = day
    parts.append((start, previous))
    labels = []
    for begin, end in parts:
        if begin == end:
            labels.append(WEEKDAY_LABELS[begin])
        elif end == begin + 1:
            labels.append(f"{WEEKDAY_LABELS[begin]}、{WEEKDAY_LABELS[end]}")
        else:
            labels.append(f"{WEEKDAY_LABELS[begin]}至{WEEKDAY_LABELS[end]}")
    return "、".join(labels)


def summary_text(windows: list[dict]) -> str:
    if not windows:
        return "全天"
    first = f"{_weekday_text(windows[0]['weekdays'])} " \
            f"{_clock_text(windows[0]['start'])}-{_clock_text(windows[0]['end'])}"
    if len(windows) == 1:
        return first
    return f"{first} 等 {len(windows)} 段"


def summaries(room_ids: list[int]) -> dict[int, dict]:
    if not room_ids:
        return {}
    marks = ",".join("?" for _ in room_ids)
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT room_id, weekdays, start_minute, end_minute FROM room_schedule "
            f"WHERE room_id IN ({marks}) ORDER BY id",
            room_ids,
        ).fetchall()
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["room_id"], []).append({
            "weekdays": [int(day) for day in str(row["weekdays"]).split(",") if day != ""],
            "start": int(row["start_minute"]),
            "end": int(row["end_minute"]),
        })
    return {
        room_id: {"count": len(windows), "summary": summary_text(windows)}
        for room_id, windows in grouped.items()
    }


def get(room_id: int) -> dict:
    return {"windows": _display(_rows(room_id))}


def replace(room_id: int, windows: list[dict], actor: str, ip: str | None = None) -> dict:
    normalized = _normalize_windows(windows)
    now = db.now_iso()
    with db.connect() as conn:
        room = conn.execute("SELECT id FROM room WHERE id=?", (room_id,)).fetchone()
        if not room:
            raise ApiError(404, "ROOM_NOT_FOUND", "直播间不存在")
        conn.execute("DELETE FROM room_schedule WHERE room_id=?", (room_id,))
        for window in normalized:
            conn.execute(
                """
                INSERT INTO room_schedule (room_id, weekdays, start_minute, end_minute, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    room_id,
                    ",".join(str(day) for day in window["weekdays"]),
                    window["start"], window["end"], now,
                ),
            )
        conn.commit()
    db.audit(actor, "room.schedule.update", "room", str(room_id),
             {"windows": len(normalized)}, ip)
    return get(room_id)


def _active_at(windows: list[dict], moment: datetime) -> bool:
    if not windows:
        return True
    minute = moment.hour * 60 + moment.minute
    today = moment.weekday()
    yesterday = (today - 1) % 7
    for window in windows:
        start, end = window["start"], window["end"]
        if start < end:
            if today in window["weekdays"] and start <= minute < end:
                return True
        else:
            if today in window["weekdays"] and minute >= start:
                return True
            if yesterday in window["weekdays"] and minute < end:
                return True
    return False


def is_active(room_id: int, windows: list[dict] | None = None,
              now: datetime | None = None) -> bool:
    rows = windows if windows is not None else _rows(room_id)
    return _active_at(rows, now or datetime.now())


def next_boundary_seconds(room_id: int, windows: list[dict] | None = None,
                          now: datetime | None = None) -> int:
    rows = windows if windows is not None else _rows(room_id)
    if not rows:
        return 3600
    moment = now or datetime.now()
    current = _active_at(rows, moment)
    candidates: list[float] = []
    for offset in range(0, 9):
        day = (moment + timedelta(days=offset)).date()
        weekday = day.weekday()
        for window in rows:
            if weekday not in window["weekdays"]:
                continue
            start_dt = datetime.combine(day, time(window["start"] // 60, window["start"] % 60))
            if window["start"] < window["end"]:
                end_day = day
            else:
                end_day = day + timedelta(days=1)
            end_dt = datetime.combine(end_day, time(window["end"] // 60, window["end"] % 60))
            for edge in (start_dt, end_dt):
                seconds = (edge - moment).total_seconds()
                if seconds > 0:
                    candidates.append(seconds)
    if not candidates:
        return 3600
    nearest = int(min(candidates)) + 1
    # 只保留真正会发生状态切换的边界，避免休眠过短空转。
    for seconds in sorted({int(item) for item in candidates}):
        if _active_at(rows, moment + timedelta(seconds=seconds)) != current:
            return max(1, seconds + 1)
    return max(60, nearest)
