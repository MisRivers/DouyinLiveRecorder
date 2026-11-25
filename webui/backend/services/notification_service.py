from __future__ import annotations

import logging
import queue
import re
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from .. import db
from ..errors import ApiError

log = logging.getLogger("dlr.notify")

EVENT_ORDER = (
    "live_started",
    "live_ended",
    "recording_started",
    "recording_finished",
    "conversion_finished",
    "recording_error",
)

EVENT_LABELS = {
    "live_started": "开播",
    "live_ended": "关播",
    "recording_started": "开始录制",
    "recording_finished": "录制结束",
    "conversion_finished": "转码完成",
    "recording_error": "录制异常",
}

EVENT_VARIABLES = {
    "live_started": ["主播", "平台", "标题", "房间地址", "时间", "画质"],
    "live_ended": ["主播", "平台", "标题", "房间地址", "时间", "直播时长"],
    "recording_started": ["主播", "平台", "标题", "房间地址", "时间", "画质", "文件名"],
    "recording_finished": ["主播", "平台", "时间", "时长", "文件大小", "文件名", "结束原因"],
    "conversion_finished": ["主播", "平台", "时间", "文件名", "时长", "文件大小"],
    "recording_error": ["主播", "平台", "时间", "错误原因", "房间地址"],
}

DEDUP_SECONDS = 60
ERROR_DEDUP_SECONDS = 600

_queue: "queue.Queue[tuple[str, int | None, dict]]" = queue.Queue(maxsize=500)
_URL_RE = re.compile(r"https?://[^\s,;]+")
_worker_lock = threading.Lock()
_worker_started = False


def _human_size(value) -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return "-"


def _human_duration(value) -> str:
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return "-"
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分"
    if minutes:
        return f"{minutes} 分 {seconds} 秒"
    return f"{seconds} 秒"


def render(template: str, context: dict) -> str:
    text = template or ""
    for key, value in context.items():
        text = text.replace("{" + str(key) + "}", str(value))
    return text


def _channels(settings: dict) -> list[str]:
    raw = settings.get("直播状态推送渠道", "") or ""
    parts = raw.replace("，", ",").split(",")
    return [part.strip() for part in parts if part.strip()]


def templates() -> dict:
    with db.connect() as conn:
        rows = {row["event_code"]: dict(row) for row in conn.execute(
            "SELECT event_code, enabled, title_template, content_template FROM notification_template"
        )}
    defaults = {item[0]: item for item in db.DEFAULT_NOTIFICATION_TEMPLATES}
    events = []
    for code in EVENT_ORDER:
        row = rows.get(code)
        default_title, default_content = defaults[code][1], defaults[code][2]
        events.append({
            "event_code": code,
            "name": EVENT_LABELS[code],
            "enabled": bool(row["enabled"]) if row else False,
            "title_template": row["title_template"] if row else default_title,
            "content_template": row["content_template"] if row else default_content,
            "default_title": default_title,
            "default_content": default_content,
            "variables": EVENT_VARIABLES[code],
        })
    settings = db.get_settings()
    return {"channels": _channels(settings), "events": events}


def update(payload: dict, actor: str, ip: str | None = None) -> dict:
    events = payload.get("events")
    if not isinstance(events, list):
        raise ApiError(422, "INVALID_TEMPLATE", "模板格式不正确")
    known = set(EVENT_ORDER)
    updates = []
    for item in events:
        if not isinstance(item, dict):
            raise ApiError(422, "INVALID_TEMPLATE", "模板格式不正确")
        code = item.get("event_code")
        if code not in known:
            raise ApiError(422, "INVALID_TEMPLATE", "未知的通知事件")
        title = str(item.get("title_template") or "").strip()
        content = str(item.get("content_template") or "").strip()
        if len(title) > 100:
            raise ApiError(422, "INVALID_TEMPLATE", "通知标题不能超过 100 字")
        if len(content) > 1000:
            raise ApiError(422, "INVALID_TEMPLATE", "通知正文不能超过 1000 字")
        defaults = {entry[0]: entry for entry in db.DEFAULT_NOTIFICATION_TEMPLATES}[code]
        updates.append((
            code, 1 if item.get("enabled") else 0,
            title or defaults[1], content or defaults[2], db.now_iso(),
        ))
    if not updates:
        raise ApiError(422, "INVALID_TEMPLATE", "没有需要保存的模板")
    with db.connect() as conn:
        conn.executemany(
            """
            INSERT INTO notification_template
              (event_code, enabled, title_template, content_template, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(event_code) DO UPDATE SET
              enabled=excluded.enabled,
              title_template=excluded.title_template,
              content_template=excluded.content_template,
              updated_at=excluded.updated_at
            """,
            updates,
        )
        conn.commit()
    db.audit(actor, "notifications.update", "notifications", None,
             {"events": [item[0] for item in updates]}, ip)
    return templates()


def preview(payload: dict) -> dict:
    code = payload.get("event_code")
    if code not in EVENT_LABELS:
        raise ApiError(422, "INVALID_TEMPLATE", "未知的通知事件")
    sample = {
        "主播": "示例主播", "平台": "抖音", "标题": "今天的直播主题",
        "房间地址": "https://live.douyin.com/123456", "时间": "2026-11-25 20:00:00",
        "画质": "原画", "文件名": "示例主播_2026-11-25_20-00-00_000.ts",
        "时长": "1 小时 23 分", "文件大小": "1.2 GB", "结束原因": "直播结束",
        "直播时长": "1 小时 23 分", "错误原因": "拉流失败：连接超时",
    }
    title = render(str(payload.get("title_template") or ""), sample)
    content = render(str(payload.get("content_template") or ""), sample)
    return {"title": title, "content": content}


def is_enabled(event_code: str) -> bool:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT enabled FROM notification_template WHERE event_code=?", (event_code,)
        ).fetchone()
    return bool(row and row["enabled"])


def _mask_error_text(value) -> str:
    def replace_url(match: re.Match) -> str:
        try:
            parsed = urlparse(match.group(0))
            if parsed.hostname:
                return f"{parsed.scheme}://{parsed.hostname}/***"
        except ValueError:
            pass
        return "***"
    return _URL_RE.sub(replace_url, str(value))[:500]


def emit(event_code: str, room_id: int | None = None, **context) -> None:
    if event_code not in EVENT_LABELS:
        return
    _ensure_worker()
    try:
        _queue.put_nowait((event_code, room_id, context))
    except queue.Full:
        log.warning("notification queue full, dropping event=%s room=%s", event_code, room_id)


def _ensure_worker() -> None:
    global _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        worker = threading.Thread(target=_run, name="notification-worker", daemon=True)
        worker.start()
        _worker_started = True


def _run() -> None:
    while True:
        event_code, room_id, context = _queue.get()
        try:
            _dispatch(event_code, room_id, context)
        except Exception:
            log.exception("notification dispatch failed event=%s room=%s", event_code, room_id)
        finally:
            _queue.task_done()


def _recent(event_code: str, room_id: int | None, seconds: int) -> bool:
    if room_id is None:
        # 转码等无房间归属的事件按文件逐条通知，不能共用同一个去重键。
        return False
    since = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="seconds")
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM notification_log
            WHERE event_code=? AND room_id IS ? AND created_at>=?
            LIMIT 1
            """,
            (event_code, room_id, since),
        ).fetchone()
    return row is not None


def _dispatch(event_code: str, room_id: int | None, context: dict) -> None:
    with db.connect() as conn:
        template = conn.execute(
            "SELECT enabled, title_template, content_template FROM notification_template WHERE event_code=?",
            (event_code,),
        ).fetchone()
    if not template or not template["enabled"]:
        return
    settings = db.get_settings()
    channels = _channels(settings)
    if not channels:
        return
    window = ERROR_DEDUP_SECONDS if event_code == "recording_error" else DEDUP_SECONDS
    if _recent(event_code, room_id, window):
        return
    title = render(template["title_template"] or "", context) or EVENT_LABELS[event_code]
    content = render(template["content_template"] or "", context) or title
    for channel in channels:
        status, error = "sent", None
        try:
            result = send_to_channel(channel, title, content, settings)
            if not result.get("success"):
                status = "failed"
                errors = result.get("error") or []
                detail = "; ".join(str(item) for item in errors) or "发送失败"
                error = _mask_error_text(detail)
        except Exception as exc:
            status, error = "failed", _mask_error_text(exc)
            log.warning("notify channel failed event=%s channel=%s error=%s",
                        event_code, channel, error)
        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO notification_log
                  (event_code, room_id, channel, status, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_code, room_id, channel, status, error, db.now_iso()),
            )
            conn.commit()


def send_to_channel(channel: str, title: str, content: str, settings: dict) -> dict:
    from msg_push import bark, dingtalk, ntfy, pushplus, send_email, tg_bot, xizhi

    channel = (channel or "").upper()
    if channel == "微信":
        return xizhi(settings.get("微信推送接口链接", ""), title, content)
    if channel == "钉钉":
        return dingtalk(
            settings.get("钉钉推送接口链接", ""), content,
            settings.get("钉钉通知@对象(填手机号)", ""),
            settings.get("钉钉通知@全体(是/否)", "否") == "是",
        )
    if channel == "邮箱":
        return send_email(
            settings.get("SMTP邮件服务器", ""), settings.get("邮箱登录账号", ""),
            settings.get("发件人密码(授权码)", ""), settings.get("发件人邮箱", ""),
            settings.get("发件人显示昵称", ""), settings.get("收件人邮箱", ""),
            title, content, settings.get("SMTP邮件服务器端口", ""),
            settings.get("是否使用SMTP服务SSL加密(是/否)", "是") == "是",
        )
    if channel == "TG":
        return tg_bot(
            settings.get("tg聊天id(个人或者群组id)", ""),
            settings.get("tgapi令牌", ""), content,
        )
    if channel == "BARK":
        return bark(
            settings.get("bark推送接口链接", ""), title=title, content=content,
            level=settings.get("bark推送中断级别", "active"),
            sound=settings.get("bark推送铃声", ""),
        )
    if channel == "NTFY":
        return ntfy(
            settings.get("ntfy推送地址", ""), title=title, content=content,
            tags=settings.get("ntfy推送标签", "tada"),
        )
    if channel == "PUSHPLUS":
        return pushplus(settings.get("pushplus推送token", ""), title, content)
    raise ApiError(422, "VALIDATION_FAILED", f"不支持的推送渠道：{channel}")


def context_size(value) -> str:
    return _human_size(value)


def context_duration(value) -> str:
    return _human_duration(value)
