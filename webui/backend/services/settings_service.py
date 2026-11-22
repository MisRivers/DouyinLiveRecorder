from __future__ import annotations

import configparser
import json
from typing import Any

from .. import db, settings_meta
from ..errors import ApiError

GROUP_ORDER = ["record", "push", "account", "cookie"]
BOOL_VALUES = {"是", "否"}


def _field(row: dict, secret: bool) -> dict:
    options = json.loads(row["options_json"]) if row.get("options_json") else None
    field = {
        "section": row["section"],
        "key": row["key"],
        "label": row["label"],
        "description": row.get("description"),
        "type": row["value_type"],
        "group_code": row["group_code"],
        "options": options,
        "sort_order": row["sort_order"],
        "secret": bool(row["is_secret"]),
        "advanced": bool(row["is_advanced"]),
        "source": row["source"],
    }
    if secret:
        field["has_value"] = bool(row.get("value"))
        field["value"] = ""
    else:
        field["value"] = row.get("value", "")
    return field


def schema() -> dict:
    rows = db.ordered_settings()
    groups = []
    for code in GROUP_ORDER:
        fields = [_field(row, bool(row["is_secret"])) for row in rows if row["group_code"] == code]
        if fields:
            groups.append({"code": code, "label": settings_meta.group_label(code), "fields": fields})
    known = {group["code"] for group in groups}
    for code in sorted({row["group_code"] for row in rows} - known):
        groups.append({
            "code": code,
            "label": settings_meta.group_label(code),
            "fields": [_field(row, bool(row["is_secret"])) for row in rows if row["group_code"] == code],
        })
    return {"groups": groups}


def values() -> dict:
    rows = db.ordered_settings()
    items = []
    for row in rows:
        item = {"section": row["section"], "key": row["key"]}
        if row["is_secret"]:
            item["value"] = ""
            item["has_value"] = bool(row["value"])
        else:
            item["value"] = row["value"]
        items.append(item)
    return {"items": items}


def _coerce(row: dict, value: Any) -> str:
    raw = "" if value is None else str(value)
    kind = row["value_type"]
    if kind == "bool":
        if raw in (True, "true", "True", "1"):
            raw = "是"
        elif raw in (False, "false", "False", "0"):
            raw = "否"
        if raw not in BOOL_VALUES:
            raise ApiError(422, "VALUE_OUT_OF_RANGE", f"{row['label']} 只能是“是”或“否”")
    elif kind == "int":
        try:
            number = int(float(raw or 0))
        except ValueError as exc:
            raise ApiError(422, "VALUE_OUT_OF_RANGE", f"{row['label']} 必须是整数") from exc
        if raw.strip() and number < 0:
            raise ApiError(422, "VALUE_OUT_OF_RANGE", f"{row['label']} 不能为负数")
        raw = str(number)
    elif kind == "float":
        try:
            number = float(raw or 0)
        except ValueError as exc:
            raise ApiError(422, "VALUE_OUT_OF_RANGE", f"{row['label']} 必须是数字") from exc
        if number < 0:
            raise ApiError(422, "VALUE_OUT_OF_RANGE", f"{row['label']} 不能为负数")
        raw = str(number)
    elif kind == "enum":
        options = json.loads(row["options_json"]) if row["options_json"] else []
        if raw not in options:
            raise ApiError(422, "VALUE_OUT_OF_RANGE", f"{row['label']} 取值不在允许范围")
    return raw


def update(updates: list[dict], actor: str, ip: str | None = None) -> dict:
    if not updates:
        return {"saved": 0, "restart_required": False, "ini_regenerated": True}
    rows = db.ordered_settings()
    index = {(row["section"], row["key"]): row for row in rows}
    cleaned = []
    for item in updates:
        key = (item.get("section"), item.get("key"))
        row = index.get(key)
        if not row:
            raise ApiError(422, "UNKNOWN_SETTING", f"未知配置项：{key[0]}/{key[1]}")
        cleaned.append({"section": key[0], "key": key[1], "value": _coerce(row, item.get("value"))})
    saved = db.set_settings(cleaned, updated_by="ui")
    db.render_url_config()
    db.audit(actor, "settings.update", "settings", None,
             {"count": saved, "keys": [f"{i['section']}/{i['key']}" for i in cleaned]}, ip)
    restart_required = any(
        item["key"] in ("language(zh_cn/en)",) for item in cleaned
    )
    return {
        "saved": saved,
        "restart_required": restart_required,
        "effective_hint": "已保存，将在下一轮调度或下一次请求生效",
        "ini_regenerated": True,
    }


def import_ini(content: str, actor: str, ip: str | None = None) -> dict:
    parser = configparser.RawConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read_string(content)
    except configparser.Error as exc:
        raise ApiError(422, "VALIDATION_FAILED", f"ini 解析失败：{exc}") from exc
    with db.connect() as conn:
        order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM setting_meta").fetchone()["n"]
        imported = 0
        new_keys = []
        for section in parser.sections():
            for key in parser.options(section):
                value = parser.get(section, key)
                exists = conn.execute(
                    'SELECT 1 FROM setting_meta WHERE section=? AND "key"=?', (section, key)
                ).fetchone()
                if not exists:
                    meta = settings_meta.build_meta(section, key, value, order, source="upstream_new")
                    conn.execute(
                        """
                        INSERT INTO setting_meta
                          (section, "key", label, description, value_type, group_code,
                           options_json, sort_order, is_secret, is_advanced, source, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            meta["section"], meta["key"], meta["label"], meta["description"],
                            meta["value_type"], meta["group_code"], meta["options_json"],
                            meta["sort_order"], meta["is_secret"], meta["is_advanced"],
                            "upstream_new", db.now_iso(),
                        ),
                    )
                    order += 1
                    new_keys.append(f"{section}/{key}")
                conn.execute(
                    """
                    INSERT INTO setting_value (section, "key", value, updated_at, updated_by)
                    VALUES (?, ?, ?, ?, 'import')
                    ON CONFLICT(section, "key") DO UPDATE SET
                      value=excluded.value, updated_at=excluded.updated_at, updated_by='import'
                    """,
                    (section, key, value, db.now_iso()),
                )
                imported += 1
        conn.commit()
    db.render_config_ini()
    db.audit(actor, "settings.import", "settings", None,
             {"imported": imported, "new_keys": new_keys}, ip)
    return {"imported": imported, "new_keys": new_keys}


def export_ini() -> str:
    path = db.render_config_ini()
    return path.read_text(encoding="utf-8-sig")


def test_push(channel: str, actor: str, ip: str | None = None) -> dict:
    from msg_push import bark, dingtalk, ntfy, pushplus, send_email, tg_bot, xizhi

    settings = db.get_settings()
    title = settings.get("自定义推送标题") or "直播间状态更新通知"
    content = "这是一条来自 Web 管理端的测试消息"
    channel = channel.upper()
    try:
        if channel == "微信":
            result = xizhi(settings.get("微信推送接口链接", ""), title, content)
        elif channel == "钉钉":
            result = dingtalk(
                settings.get("钉钉推送接口链接", ""), content,
                settings.get("钉钉通知@对象(填手机号)", ""),
                settings.get("钉钉通知@全体(是/否)", "否") == "是",
            )
        elif channel == "邮箱":
            result = send_email(
                settings.get("SMTP邮件服务器", ""), settings.get("邮箱登录账号", ""),
                settings.get("发件人密码(授权码)", ""), settings.get("发件人邮箱", ""),
                settings.get("发件人显示昵称", ""), settings.get("收件人邮箱", ""),
                title, content, settings.get("SMTP邮件服务器端口", ""),
                settings.get("是否使用SMTP服务SSL加密(是/否)", "是") == "是",
            )
        elif channel == "TG":
            result = tg_bot(
                settings.get("tg聊天id(个人或者群组id)", ""),
                settings.get("tgapi令牌", ""), content,
            )
        elif channel == "BARK":
            result = bark(
                settings.get("bark推送接口链接", ""), title=title, content=content,
                level=settings.get("bark推送中断级别", "active"),
                sound=settings.get("bark推送铃声", ""),
            )
        elif channel == "NTFY":
            result = ntfy(
                settings.get("ntfy推送地址", ""), title=title, content=content,
                tags=settings.get("ntfy推送标签", "tada"),
            )
        elif channel == "PUSHPLUS":
            result = pushplus(settings.get("pushplus推送token", ""), title, content)
        else:
            raise ApiError(422, "VALIDATION_FAILED", "不支持的推送渠道")
    except ApiError:
        raise
    except Exception as exc:
        db.audit(actor, "settings.test_push", "settings", channel, {"error": str(exc)}, ip)
        return {"ok": False, "message": str(exc)}
    ok = bool(result.get("success"))
    db.audit(actor, "settings.test_push", "settings", channel, {"ok": ok}, ip)
    return {"ok": ok, "success": result.get("success", []), "error": result.get("error", [])}
