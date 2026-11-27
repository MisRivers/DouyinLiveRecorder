"""Metadata overlay for upstream config.ini keys.

The upstream ini keeps Chinese keys. This module only adds presentation
metadata; values are always stored as the original strings.
"""
from __future__ import annotations

import json
import re

SECTION_GROUPS = {
    "录制设置": ("record", "录制设置"),
    "推送配置": ("push", "推送配置"),
    "Authorization": ("account", "账号与授权"),
    "账号密码": ("account", "账号与授权"),
    "Cookie": ("cookie", "Cookie 管理"),
}

GROUP_LABELS = {
    "record": "录制设置",
    "push": "推送配置",
    "account": "账号与授权",
    "cookie": "Cookie 管理",
}

LABELS = {
    "language(zh_cn/en)": "界面语言",
    "是否跳过代理检测(是/否)": "跳过代理检测",
    "直播保存路径(不填则默认)": "直播保存路径",
    "保存文件夹是否以作者区分": "按作者分文件夹",
    "保存文件夹是否以时间区分": "按时间分文件夹",
    "保存文件夹是否以标题区分": "按标题分文件夹",
    "保存文件名是否包含标题": "文件名包含标题",
    "是否去除名称中的表情符号": "去除名称中的表情符号",
    "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频": "视频保存格式",
    "原画|超清|高清|标清|流畅": "默认录制清晰度",
    "是否使用代理ip(是/否)": "使用代理 IP",
    "代理地址": "代理地址",
    "同一时间访问网络的线程数": "同时访问网络的线程数",
    "循环时间(秒)": "循环检测间隔",
    "排队读取网址时间(秒)": "排队读取网址间隔",
    "是否显示循环秒数": "显示循环倒计时",
    "是否显示直播源地址": "显示直播源地址",
    "分段录制是否开启": "开启分段录制",
    "是否强制启用https录制": "强制使用 HTTPS 录制",
    "录制空间剩余阈值(gb)": "磁盘剩余阈值",
    "视频分段时间(秒)": "视频分段时长",
    "录制完成后自动转为mp4格式": "录制完成后转为 MP4",
    "mp4格式重新编码为h264": "MP4 重新编码为 H.264",
    "追加格式后删除原文件": "转码后删除原文件",
    "生成时间字幕文件": "生成时间字幕文件",
    "是否录制完成后执行自定义脚本": "录制完成后执行脚本",
    "自定义脚本执行命令": "自定义脚本命令",
    "使用代理录制的平台(逗号分隔)": "使用代理的平台",
    "额外使用代理录制的平台(逗号分隔)": "额外使用代理的平台",
    "启用streamget解析(是/否)": "启用 streamget 解析",
    "streamget解析平台(逗号分隔)": "streamget 解析平台",
    "直播状态推送渠道": "直播状态推送渠道",
    "钉钉推送接口链接": "钉钉 Webhook",
    "微信推送接口链接": "微信推送接口",
    "bark推送接口链接": "Bark 推送地址",
    "bark推送中断级别": "Bark 中断级别",
    "bark推送铃声": "Bark 推送铃声",
    "钉钉通知@对象(填手机号)": "钉钉 @手机号",
    "钉钉通知@全体(是/否)": "钉钉 @全体",
    "tgapi令牌": "Telegram Bot Token",
    "tg聊天id(个人或者群组id)": "Telegram Chat ID",
    "SMTP邮件服务器": "SMTP 服务器",
    "是否使用SMTP服务SSL加密(是/否)": "SMTP SSL",
    "SMTP邮件服务器端口": "SMTP 端口",
    "邮箱登录账号": "邮箱登录账号",
    "发件人密码(授权码)": "发件人密码或授权码",
    "发件人邮箱": "发件人邮箱",
    "发件人显示昵称": "发件人显示昵称",
    "收件人邮箱": "收件人邮箱",
    "ntfy推送地址": "ntfy 推送地址",
    "ntfy推送标签": "ntfy 标签",
    "ntfy推送邮箱": "ntfy 邮箱",
    "pushplus推送token": "PushPlus Token",
    "自定义推送标题": "自定义推送标题",
    "自定义开播推送内容": "自定义开播推送内容",
    "自定义关播推送内容": "自定义关播推送内容",
    "只推送通知不录制(是/否)": "只推送不录制",
    "直播推送检测频率(秒)": "推送检测频率",
    "开播推送开启(是/否)": "开播推送开启",
    "关播推送开启(是/否)": "关播推送开启",
    "popkontv_token": "PopkonTV Token",
    "partner_code": "PopkonTV Partner Code",
    "sooplive账号": "SOOP 账号",
    "sooplive密码": "SOOP 密码",
    "flextv账号": "FlexTV 账号",
    "flextv密码": "FlexTV 密码",
    "popkontv账号": "PopkonTV 账号",
    "popkontv密码": "PopkonTV 密码",
    "twitcasting账号类型": "TwitCasting 账号类型",
    "twitcasting账号": "TwitCasting 账号",
    "twitcasting密码": "TwitCasting 密码",
}

DESCRIPTIONS = {
    "直播保存路径(不填则默认)": "留空时保存到应用目录下的 downloads。支持绝对路径。",
    "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频": "TS 便于断点续录与转码；音频格式仅保存声音。",
    "同一时间访问网络的线程数": "同时请求平台的并发上限，过高容易触发风控。",
    "循环时间(秒)": "未开播房间的检测间隔。",
    "录制空间剩余阈值(gb)": "剩余空间低于该值时停止新录制并暂停转码。",
    "直播状态推送渠道": "可多选，保存时自动合并为逗号分隔的渠道列表：微信、钉钉、邮箱、TG、BARK、NTFY、PUSHPLUS。",
    "只推送通知不录制(是/否)": "开启后只检测开播并推送，不启动 FFmpeg。",
    "启用streamget解析(是/否)": "默认开启：优先使用 streamget 解析直播源，失败时自动回退到 DLR 原有解析。",
    "streamget解析平台(逗号分隔)": "默认 *，表示全部 streamget 支持平台优先；streamget 不支持或解析失败的平台自动回退 DLR。",
}

ENUM_KEYS = {
    "language(zh_cn/en)": ["zh_cn", "en"],
    "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频": ["ts", "mkv", "flv", "mp4", "mp3音频", "m4a音频"],
    "原画|超清|高清|标清|流畅": ["原画", "超清", "高清", "标清", "流畅"],
    "twitcasting账号类型": ["normal", "cas"],
}

ADVANCED_KEYS = {
    "额外使用代理录制的平台(逗号分隔)",
    "自定义脚本执行命令",
    "排队读取网址时间(秒)",
    "录制空间剩余阈值(gb)",
    "mp4格式重新编码为h264",
    "twitcasting账号类型",
    "SMTP邮件服务器端口",
    "ntfy推送邮箱",
    "parse_extra",
}


def _clean_label(key: str) -> str:
    if key in LABELS:
        return LABELS[key]
    label = re.sub(r"[（(](是/否|填手机号|个人或者群组id|授权码|不填则默认|秒|gb)[）)]$", "", key)
    label = label.replace("cookie", " Cookie").replace("Cookie", " Cookie").strip()
    if label.endswith("cookie"):
        label = label[: -len("cookie")].strip() + " Cookie"
    return label or key


def _is_secret(section: str, key: str) -> bool:
    if section == "Cookie":
        return True
    lowered = key.lower()
    return any(word in lowered for word in ("cookie", "token", "密码", "password", "授权码", "secret"))


def _infer_type(section: str, key: str, value: str) -> tuple[str, list[str] | None]:
    if key in ENUM_KEYS:
        return "enum", ENUM_KEYS[key]
    if _is_secret(section, key):
        return "secret", None
    if key in ("自定义开播推送内容", "自定义关播推送内容", "自定义脚本执行命令"):
        return "multiline", None
    if value in ("是", "否") or key.endswith("(是/否)"):
        return "bool", ["是", "否"]
    if key in ("录制空间剩余阈值(gb)",):
        return "float", None
    if "(秒)" in key or "(gb)" in key or key in (
        "同一时间访问网络的线程数", "SMTP邮件服务器端口", "直播推送检测频率(秒)"
    ):
        return "int", None
    return "string", None


def build_meta(section: str, key: str, value: str, order: int, source: str = "upstream") -> dict:
    group_code = SECTION_GROUPS.get(section, ("record", "录制设置"))[0]
    value_type, options = _infer_type(section, key, value)
    return {
        "section": section,
        "key": key,
        "label": _clean_label(key),
        "description": DESCRIPTIONS.get(key),
        "value_type": value_type,
        "group_code": group_code,
        "options_json": json.dumps(options, ensure_ascii=False) if options else None,
        "sort_order": order,
        "is_secret": 1 if _is_secret(section, key) else 0,
        "is_advanced": 1 if key in ADVANCED_KEYS else 0,
        "source": source,
    }


def group_label(code: str) -> str:
    return GROUP_LABELS.get(code, "其他")
