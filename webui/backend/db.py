from __future__ import annotations

import configparser
import hashlib
import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import config, platform_registry, settings_meta

_init_lock = threading.Lock()
_initialized = False

DEFAULT_SETTINGS = [
    ("录制设置", "language(zh_cn/en)", "zh_cn"),
    ("录制设置", "是否跳过代理检测(是/否)", "否"),
    ("录制设置", "直播保存路径(不填则默认)", ""),
    ("录制设置", "保存文件夹是否以作者区分", "是"),
    ("录制设置", "保存文件夹是否以时间区分", "否"),
    ("录制设置", "保存文件夹是否以标题区分", "否"),
    ("录制设置", "保存文件名是否包含标题", "否"),
    ("录制设置", "是否去除名称中的表情符号", "是"),
    ("录制设置", "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频", "ts"),
    ("录制设置", "原画|超清|高清|标清|流畅", "原画"),
    ("录制设置", "是否使用代理ip(是/否)", "是"),
    ("录制设置", "代理地址", ""),
    ("录制设置", "同一时间访问网络的线程数", "3"),
    ("录制设置", "循环时间(秒)", "300"),
    ("录制设置", "排队读取网址时间(秒)", "0"),
    ("录制设置", "是否显示循环秒数", "否"),
    ("录制设置", "是否显示直播源地址", "否"),
    ("录制设置", "分段录制是否开启", "是"),
    ("录制设置", "是否强制启用https录制", "否"),
    ("录制设置", "录制空间剩余阈值(gb)", "1.0"),
    ("录制设置", "视频分段时间(秒)", "1800"),
    ("录制设置", "录制完成后自动转为mp4格式", "是"),
    ("录制设置", "mp4格式重新编码为h264", "否"),
    ("录制设置", "追加格式后删除原文件", "是"),
    ("录制设置", "生成时间字幕文件", "否"),
    ("录制设置", "是否录制完成后执行自定义脚本", "否"),
    ("录制设置", "自定义脚本执行命令", ""),
    ("录制设置", "使用代理录制的平台(逗号分隔)", "tiktok, sooplive, pandalive, winktv, flextv, popkontv, twitch, liveme, showroom, chzzk, shopee, shp, youtube, faceit"),
    ("录制设置", "额外使用代理录制的平台(逗号分隔)", ""),
    ("推送配置", "直播状态推送渠道", ""),
    ("推送配置", "钉钉推送接口链接", ""),
    ("推送配置", "微信推送接口链接", ""),
    ("推送配置", "bark推送接口链接", ""),
    ("推送配置", "bark推送中断级别", "active"),
    ("推送配置", "bark推送铃声", ""),
    ("推送配置", "钉钉通知@对象(填手机号)", ""),
    ("推送配置", "钉钉通知@全体(是/否)", "否"),
    ("推送配置", "tgapi令牌", ""),
    ("推送配置", "tg聊天id(个人或者群组id)", ""),
    ("推送配置", "SMTP邮件服务器", ""),
    ("推送配置", "是否使用SMTP服务SSL加密(是/否)", ""),
    ("推送配置", "SMTP邮件服务器端口", ""),
    ("推送配置", "邮箱登录账号", ""),
    ("推送配置", "发件人密码(授权码)", ""),
    ("推送配置", "发件人邮箱", ""),
    ("推送配置", "发件人显示昵称", ""),
    ("推送配置", "收件人邮箱", ""),
    ("推送配置", "ntfy推送地址", "https://ntfy.sh/xxxx"),
    ("推送配置", "ntfy推送标签", "tada"),
    ("推送配置", "ntfy推送邮箱", ""),
    ("推送配置", "pushplus推送token", ""),
    ("推送配置", "自定义推送标题", "直播间状态更新通知"),
    ("推送配置", "自定义开播推送内容", ""),
    ("推送配置", "自定义关播推送内容", ""),
    ("推送配置", "只推送通知不录制(是/否)", "否"),
    ("推送配置", "直播推送检测频率(秒)", "1800"),
    ("推送配置", "开播推送开启(是/否)", "是"),
    ("推送配置", "关播推送开启(是/否)", "否"),
    ("Cookie", "抖音cookie", ""),
    ("Cookie", "快手cookie", ""),
    ("Cookie", "tiktok_cookie", ""),
    ("Cookie", "虎牙cookie", ""),
    ("Cookie", "斗鱼cookie", ""),
    ("Cookie", "yy_cookie", ""),
    ("Cookie", "b站cookie", ""),
    ("Cookie", "小红书cookie", ""),
    ("Cookie", "bigo_cookie", ""),
    ("Cookie", "blued_cookie", ""),
    ("Cookie", "sooplive_cookie", ""),
    ("Cookie", "netease_cookie", ""),
    ("Cookie", "千度热播_cookie", ""),
    ("Cookie", "pandatv_cookie", ""),
    ("Cookie", "猫耳fm_cookie", ""),
    ("Cookie", "winktv_cookie", ""),
    ("Cookie", "flextv_cookie", ""),
    ("Cookie", "look_cookie", ""),
    ("Cookie", "twitcasting_cookie", ""),
    ("Cookie", "baidu_cookie", ""),
    ("Cookie", "weibo_cookie", ""),
    ("Cookie", "kugou_cookie", ""),
    ("Cookie", "twitch_cookie", ""),
    ("Cookie", "liveme_cookie", ""),
    ("Cookie", "huajiao_cookie", ""),
    ("Cookie", "liuxing_cookie", ""),
    ("Cookie", "showroom_cookie", ""),
    ("Cookie", "acfun_cookie", ""),
    ("Cookie", "changliao_cookie", ""),
    ("Cookie", "yinbo_cookie", ""),
    ("Cookie", "yingke_cookie", ""),
    ("Cookie", "zhihu_cookie", ""),
    ("Cookie", "chzzk_cookie", ""),
    ("Cookie", "haixiu_cookie", ""),
    ("Cookie", "vvxqiu_cookie", ""),
    ("Cookie", "17live_cookie", ""),
    ("Cookie", "langlive_cookie", ""),
    ("Cookie", "pplive_cookie", ""),
    ("Cookie", "6room_cookie", ""),
    ("Cookie", "lehaitv_cookie", ""),
    ("Cookie", "huamao_cookie", ""),
    ("Cookie", "shopee_cookie", ""),
    ("Cookie", "youtube_cookie", ""),
    ("Cookie", "taobao_cookie", ""),
    ("Cookie", "jd_cookie", ""),
    ("Cookie", "faceit_cookie", ""),
    ("Cookie", "migu_cookie", ""),
    ("Cookie", "lianjie_cookie", ""),
    ("Cookie", "laixiu_cookie", ""),
    ("Cookie", "picarto_cookie", ""),
    ("Authorization", "popkontv_token", ""),
    ("账号密码", "sooplive账号", ""),
    ("账号密码", "sooplive密码", ""),
    ("账号密码", "flextv账号", ""),
    ("账号密码", "flextv密码", ""),
    ("账号密码", "popkontv账号", ""),
    ("账号密码", "partner_code", "P-00001"),
    ("账号密码", "popkontv密码", ""),
    ("账号密码", "twitcasting账号类型", "normal"),
    ("账号密码", "twitcasting账号", ""),
    ("账号密码", "twitcasting密码", ""),
]

DEFAULT_NOTIFICATION_TEMPLATES = [
    (
        "live_started", "开播通知",
        "「{平台}」{主播} 正在直播\n标题：{标题}\n地址：{房间地址}\n时间：{时间}",
    ),
    (
        "live_ended", "关播通知",
        "「{平台}」{主播} 已下播\n本次直播时长：{直播时长}\n时间：{时间}",
    ),
    (
        "recording_started", "开始录制",
        "「{平台}」{主播} 开始录制\n标题：{标题}\n画质：{画质}\n文件：{文件名}",
    ),
    (
        "recording_finished", "录制结束",
        "「{平台}」{主播} 录制结束\n时长：{时长}\n大小：{文件大小}\n原因：{结束原因}\n文件：{文件名}",
    ),
    (
        "conversion_finished", "转码完成",
        "「{平台}」{主播} 转码完成\n文件：{文件名}\n时长：{时长}\n大小：{文件大小}",
    ),
    (
        "recording_error", "录制异常",
        "「{平台}」{主播} 录制异常\n时间：{时间}\n原因：{错误原因}\n地址：{房间地址}",
    ),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def init_db() -> None:
    global _initialized
    with _init_lock:
        if _initialized:
            return
        config.ensure_dirs()
        schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
        with connect() as conn:
            conn.executescript(schema)
            _seed_platforms(conn)
            _seed_settings(conn)
            _seed_notification_templates(conn)
            _seed_rooms(conn)
            _migrate_notification_templates(conn)
            _set_meta(conn, "schema_version", "1")
            conn.commit()
        _initialized = True


def _seed_platforms(conn: sqlite3.Connection) -> None:
    for item in platform_registry.PLATFORMS:
        conn.execute(
            """
            INSERT INTO platform_template
              (code, name, host_patterns, url_template, id_pattern, example,
               quick_add_mode, quality_options, needs_cookie, proxy_recommended,
               enabled, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'seed', ?)
            ON CONFLICT(code) DO UPDATE SET
              name=excluded.name, host_patterns=excluded.host_patterns,
              url_template=excluded.url_template, id_pattern=excluded.id_pattern,
              example=excluded.example, quick_add_mode=excluded.quick_add_mode,
              quality_options=excluded.quality_options,
              needs_cookie=excluded.needs_cookie,
              proxy_recommended=excluded.proxy_recommended,
              updated_at=excluded.updated_at
            """,
            (
                item["code"], item["name"], ",".join(item["hosts"]), item["template"],
                item["id_pattern"], item["example"], item["quick"],
                ",".join(platform_registry.QUALITY_OPTIONS), 1 if item["cookie"] else 0,
                1 if item["proxy"] else 0, now_iso(),
            ),
        )


def _iter_ini(path: Path) -> Iterable[tuple[str, str, str]]:
    if not path.exists():
        return []
    parser = configparser.RawConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read(path, encoding="utf-8-sig")
    rows = []
    for section in parser.sections():
        for key in parser.options(section):
            rows.append((section, key, parser.get(section, key)))
    return rows


def _seed_settings(conn: sqlite3.Connection) -> None:
    rows = list(_iter_ini(config.CONFIG_DIR / "config.ini"))
    if not rows:
        rows = list(DEFAULT_SETTINGS)
    else:
        seen = {(section, key) for section, key, _ in rows}
        rows.extend(item for item in DEFAULT_SETTINGS if (item[0], item[1]) not in seen)
    order = 0
    for section, key, value in rows:
        meta = settings_meta.build_meta(section, key, value, order)
        conn.execute(
            """
            INSERT INTO setting_meta
              (section, "key", label, description, value_type, group_code,
               options_json, sort_order, is_secret, is_advanced, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(section, "key") DO NOTHING
            """,
            (
                meta["section"], meta["key"], meta["label"], meta["description"],
                meta["value_type"], meta["group_code"], meta["options_json"],
                meta["sort_order"], meta["is_secret"], meta["is_advanced"],
                meta["source"], now_iso(),
            ),
        )
        conn.execute(
            """
            INSERT INTO setting_value (section, "key", value, updated_at, updated_by)
            VALUES (?, ?, ?, ?, 'import')
            ON CONFLICT(section, "key") DO NOTHING
            """,
            (section, key, value, now_iso()),
        )
        order += 1
    _set_meta(conn, "config_import_hash", _hash_file(config.CONFIG_DIR / "config.ini") or "")


def parse_room_line(line: str, default_quality: str) -> dict | None:
    raw = line.strip()
    if not raw or len(raw) < 18:
        return None
    enabled = not raw.startswith("#")
    raw = raw.lstrip("#").strip()
    parts = re.split(r"[,，]", raw)
    quality = default_quality
    custom_name = None
    url = ""
    if len(parts) == 1:
        url = parts[0].strip()
    elif len(parts) == 2:
        first, second = parts[0].strip(), parts[1].strip()
        if first.startswith(("http://", "https://", "www.", "live.", "v.")) or "://" in first:
            url = first
            custom_name = second
        else:
            quality, url = first, second
    else:
        quality, url = parts[0].strip(), parts[1].strip()
        custom_name = ",".join(part.strip() for part in parts[2:])
    if quality not in platform_registry.QUALITY_OPTIONS:
        quality = default_quality
    if custom_name:
        custom_name = re.sub(r"^主播\s*[:：]\s*", "", custom_name).strip() or None
    url = platform_registry.normalize_url(url)
    if not url:
        return None
    code = platform_registry.match_platform(url)
    if not code:
        return None
    return {
        "enabled": 1 if enabled else 0,
        "url": url,
        "platform_code": code,
        "quality": quality,
        "custom_name": custom_name,
    }


def _seed_notification_templates(conn: sqlite3.Connection) -> None:
    for event_code, title, content in DEFAULT_NOTIFICATION_TEMPLATES:
        conn.execute(
            """
            INSERT INTO notification_template
              (event_code, enabled, title_template, content_template, updated_at)
            VALUES (?, 0, ?, ?, ?)
            ON CONFLICT(event_code) DO NOTHING
            """,
            (event_code, title, content, now_iso()),
        )


def _migrate_notification_templates(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM app_meta WHERE key='notifications_migrated'").fetchone():
        return
    admin_count = conn.execute("SELECT COUNT(*) AS c FROM admin_user").fetchone()["c"]
    rows = conn.execute("SELECT enabled FROM notification_template").fetchall()
    any_enabled = any(row["enabled"] for row in rows)
    if admin_count and not any_enabled:
        legacy = {
            row["key"]: row["value"]
            for row in conn.execute(
                "SELECT key, value FROM setting_value WHERE key IN "
                "('开播推送开启(是/否)', '关播推送开启(是/否)')"
            )
        }
        now = now_iso()
        if legacy.get("开播推送开启(是/否)") == "是":
            conn.execute(
                "UPDATE notification_template SET enabled=1, updated_at=? WHERE event_code='live_started'",
                (now,),
            )
        if legacy.get("关播推送开启(是/否)") == "是":
            conn.execute(
                "UPDATE notification_template SET enabled=1, updated_at=? WHERE event_code='live_ended'",
                (now,),
            )
    _set_meta(conn, "notifications_migrated", "1")


def _seed_rooms(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM room").fetchone()["c"]
    if count:
        return
    default_quality = "原画"
    for section, key, value in _iter_ini(config.CONFIG_DIR / "config.ini"):
        if key == "原画|超清|高清|标清|流畅":
            default_quality = value or default_quality
    path = config.CONFIG_DIR / "URL_config.ini"
    if not path.exists():
        return
    order = 0
    for line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        parsed = parse_room_line(line, default_quality)
        if not parsed:
            continue
        try:
            conn.execute(
                """
                INSERT INTO room
                  (sort_order, enabled, custom_name, url, platform_code, quality,
                   created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order, parsed["enabled"], parsed["custom_name"], parsed["url"],
                    parsed["platform_code"], parsed["quality"], now_iso(), now_iso(),
                ),
            )
            order += 1
        except sqlite3.IntegrityError:
            continue


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_meta ("key", value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT("key") DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, value, now_iso()),
    )


def set_meta(key: str, value: str) -> None:
    with connect() as conn:
        _set_meta(conn, key, value)
        conn.commit()


def get_meta(key: str, default: str | None = None) -> str | None:
    with connect() as conn:
        row = conn.execute('SELECT value FROM app_meta WHERE "key"=?', (key,)).fetchone()
    return row["value"] if row else default


def get_settings() -> dict[str, str]:
    with connect() as conn:
        rows = conn.execute('SELECT "key", value FROM setting_value').fetchall()
    return {row["key"]: row["value"] for row in rows}


def get_settings_by_section() -> dict[str, dict[str, str]]:
    with connect() as conn:
        rows = conn.execute(
            'SELECT section, "key", value FROM setting_value ORDER BY section, "key"'
        ).fetchall()
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        result.setdefault(row["section"], {})[row["key"]] = row["value"]
    return result


def get_setting(key: str, default: str = "") -> str:
    with connect() as conn:
        row = conn.execute(
            'SELECT value FROM setting_value WHERE "key"=? ORDER BY section LIMIT 1', (key,)
        ).fetchone()
    return row["value"] if row else default


def bool_setting(key: str, default: bool = False) -> bool:
    value = get_setting(key, "是" if default else "否")
    return value.strip() == "是"


def set_settings(updates: list[dict], updated_by: str = "ui") -> int:
    changed = 0
    with connect() as conn:
        for item in updates:
            section = item["section"]
            key = item["key"]
            value = str(item.get("value", ""))
            cur = conn.execute(
                'UPDATE setting_value SET value=?, updated_at=?, updated_by=? WHERE section=? AND "key"=?',
                (value, now_iso(), updated_by, section, key),
            )
            if cur.rowcount == 0:
                raise KeyError(f"{section}/{key}")
            changed += 1
        conn.commit()
    render_config_ini()
    return changed


def ordered_settings() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT m.section, m."key", m.label, m.description, m.value_type,
                   m.group_code, m.options_json, m.sort_order, m.is_secret,
                   m.is_advanced, m.source, v.value
            FROM setting_meta m
            JOIN setting_value v ON v.section=m.section AND v."key"=m."key"
            ORDER BY m.group_code, m.sort_order, m."key"
            """
        ).fetchall()
    return [dict(row) for row in rows]


def atomic_write(path: Path, text: str, encoding: str = "utf-8-sig") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    data = text.encode(encoding)
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
    import os

    os.replace(tmp, path)


def render_config_ini() -> Path:
    groups = get_settings_by_section()
    with connect() as conn:
        metas = conn.execute(
            'SELECT section, "key" FROM setting_meta ORDER BY sort_order'
        ).fetchall()
    section_order: list[str] = []
    key_order: dict[str, list[str]] = {}
    for row in metas:
        section_order.append(row["section"]) if row["section"] not in section_order else None
        key_order.setdefault(row["section"], []).append(row["key"])
    parser = configparser.RawConfigParser(interpolation=None)
    parser.optionxform = str
    for section in section_order:
        parser.add_section(section)
    for section, values in groups.items():
        if not parser.has_section(section):
            parser.add_section(section)
        for key in key_order.get(section, []):
            if key in values:
                parser.set(section, key, values[key])
        for key, value in values.items():
            if key not in key_order.get(section, []):
                parser.set(section, key, value)
    import io

    buffer = io.StringIO()
    parser.write(buffer)
    target = config.CONFIG_DIR / "config.ini"
    _backup_before_write(target)
    atomic_write(target, buffer.getvalue())
    set_meta("config_export_hash", _hash_file(target) or "")
    return target


def _backup_before_write(path: Path) -> None:
    if not path.exists():
        return
    try:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = config.CONFIG_DIR / "backup_export"
        backup_dir.mkdir(parents=True, exist_ok=True)
        target = backup_dir / f"{path.name}.{stamp}"
        if not target.exists():
            target.write_bytes(path.read_bytes())
    except OSError:
        pass


def render_url_config() -> Path:
    with connect() as conn:
        rows = conn.execute(
            "SELECT enabled, quality, url, custom_name FROM room ORDER BY sort_order, id"
        ).fetchall()
    lines = []
    for row in rows:
        line = f"{row['quality']},{row['url']}"
        if row["custom_name"]:
            line += f",主播: {row['custom_name']}"
        if not row["enabled"]:
            line = "#" + line
        lines.append(line)
    target = config.CONFIG_DIR / "URL_config.ini"
    _backup_before_write(target)
    atomic_write(target, "\n".join(lines) + ("\n" if lines else ""))
    return target


def audit(actor: str, action: str, target_type: str | None = None,
          target_id: str | None = None, detail: Any = None, ip: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (actor, action, target_type, target_id, detail_json, ip, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actor, action, target_type, target_id,
                json.dumps(detail, ensure_ascii=False) if detail is not None else None,
                ip, now_iso(),
            ),
        )
        conn.commit()


def enqueue_command(command: str, payload: dict | None = None,
                    request_id: str | None = None) -> int:
    request_id = request_id or uuid.uuid4().hex
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO control_command (request_id, command, payload_json, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (request_id, command, json.dumps(payload or {}, ensure_ascii=False), now_iso()),
        )
        conn.commit()
        return int(cur.lastrowid)


def claim_command() -> dict | None:
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM control_command WHERE status='pending' ORDER BY id LIMIT 1"
        ).fetchone()
        if not row:
            conn.execute("COMMIT")
            return None
        conn.execute(
            "UPDATE control_command SET status='running', claimed_at=? WHERE id=? AND status='pending'",
            (now_iso(), row["id"]),
        )
        conn.execute("COMMIT")
        return dict(row)
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def finish_command(command_id: int, error: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE control_command SET status=?, finished_at=?, error=? WHERE id=?",
            ("failed" if error else "done", now_iso(), error, command_id),
        )
        conn.commit()


def fail_orphan_commands() -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE control_command SET status='failed', finished_at=?, error='worker restarted' "
            "WHERE status='running'",
            (now_iso(),),
        )
        conn.commit()


def set_live_state(room_id: int, **fields) -> None:
    allowed = {
        "state", "anchor_name", "title", "platform_code", "quality", "session_id",
        "file_path", "bytes_written", "error_code", "error_message", "started_at",
    }
    payload = {k: v for k, v in fields.items() if k in allowed}
    if not payload:
        return
    payload["updated_at"] = now_iso()
    columns = ", ".join(f'"{key}"=?' for key in payload)
    values = list(payload.values()) + [room_id]
    with connect() as conn:
        conn.execute(f"UPDATE live_state SET {columns} WHERE room_id=?", values)
        conn.commit()


def ensure_live_rows() -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO live_state (room_id, state, platform_code, quality, updated_at)
            SELECT id, CASE WHEN enabled=1 THEN 'checking' ELSE 'disabled' END,
                   platform_code, quality, ?
            FROM room
            WHERE id NOT IN (SELECT room_id FROM live_state)
            """,
            (now_iso(),),
        )
        conn.commit()


def recorder_state() -> dict:
    with connect() as conn:
        state = conn.execute('SELECT value FROM app_meta WHERE "key"=\'recorder_state\'').fetchone()
        heartbeat = conn.execute('SELECT value FROM app_meta WHERE "key"=\'recorder_heartbeat\'').fetchone()
    return {
        "state": state["value"] if state else "stopped",
        "heartbeat_at": heartbeat["value"] if heartbeat else None,
    }


def set_recorder_state(state: str) -> None:
    set_meta("recorder_state", state)
    set_meta("recorder_heartbeat", now_iso())


def heartbeat() -> None:
    set_meta("recorder_heartbeat", now_iso())
