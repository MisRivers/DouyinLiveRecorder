"""Resolve a room into a normalized live-stream description.

The platform branches intentionally mirror the routing from upstream main.py.
Upstream spider/stream modules remain untouched; this module only adapts their
return values into the shape the recorder and UI expect.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from urllib.parse import urlparse

from src import spider, stream
from src.utils import handle_proxy_addr

from .. import db
from . import streamget_resolver

LOGGER = logging.getLogger("dlr.stream_resolver")

QUALITY_CODE = {
    "原画": "OD",
    "蓝光": "BD",
    "超清": "UHD",
    "高清": "HD",
    "标清": "SD",
    "流畅": "LD",
}

COOKIE_KEYS = {
    "douyin": "抖音cookie",
    "kuaishou": "快手cookie",
    "tiktok": "tiktok_cookie",
    "huya": "虎牙cookie",
    "douyu": "斗鱼cookie",
    "yy": "yy_cookie",
    "bilibili": "B站cookie",
    "xhs": "小红书cookie",
    "bigo": "bigo_cookie",
    "blued": "blued_cookie",
    "sooplive": "sooplive_cookie",
    "netease": "netease_cookie",
    "qiandurebo": "千度热播_cookie",
    "pandatv": "pandatv_cookie",
    "maoerfm": "猫耳fm_cookie",
    "winktv": "winktv_cookie",
    "flextv": "flextv_cookie",
    "looklive": "look_cookie",
    "twitcasting": "twitcasting_cookie",
    "baidu": "baidu_cookie",
    "weibo": "weibo_cookie",
    "kugou": "kugou_cookie",
    "twitch": "twitch_cookie",
    "liveme": "liveme_cookie",
    "huajiao": "huajiao_cookie",
    "liuxing": "liuxing_cookie",
    "showroom": "showroom_cookie",
    "acfun": "acfun_cookie",
    "changliao": "changliao_cookie",
    "yinbo": "yinbo_cookie",
    "yingke": "yingke_cookie",
    "zhihu": "zhihu_cookie",
    "chzzk": "chzzk_cookie",
    "haixiu": "haixiu_cookie",
    "vvxqiu": "vvxqiu_cookie",
    "17live": "17live_cookie",
    "langlive": "langlive_cookie",
    "pplive": "pplive_cookie",
    "6room": "6room_cookie",
    "lehai": "lehaitv_cookie",
    "huamao": "huamao_cookie",
    "shopee": "shopee_cookie",
    "youtube": "youtube_cookie",
    "taobao": "taobao_cookie",
    "jd": "jd_cookie",
    "faceit": "faceit_cookie",
    "migu": "migu_cookie",
    "lianjie": "lianjie_cookie",
    "laixiu": "laixiu_cookie",
    "picarto": "picarto_cookie",
}

PROXY_REQUIRED = {
    "tiktok", "sooplive", "pandatv", "winktv", "flextv", "popkontv",
    "twitch", "liveme", "showroom", "chzzk", "shopee", "youtube", "faceit",
}


def _run(coro):
    return asyncio.run(coro)


def _cookie(settings: dict, code: str) -> str:
    return settings.get(COOKIE_KEYS.get(code, ""), "") or ""


def _proxy(room: dict, settings: dict) -> str | None:
    if settings.get("是否使用代理ip(是/否)", "是") != "是":
        return None
    address = (settings.get("代理地址", "") or "").strip()
    if not address:
        return None
    url = (room.get("url") or "").lower()
    code = room.get("platform_code") or ""
    tokens = []
    for key in ("使用代理录制的平台(逗号分隔)", "额外使用代理录制的平台(逗号分隔)"):
        tokens.extend(
            token.strip().lower()
            for token in (settings.get(key, "") or "").replace("，", ",").split(",")
            if token.strip()
        )
    if not tokens:
        return None
    if any(token in url or token == code for token in tokens):
        return handle_proxy_addr(address)
    return None


def _update_setting(section: str, key: str, value: str) -> None:
    if not value:
        return
    try:
        db.set_settings([{"section": section, "key": key, "value": value}], updated_by="engine")
    except Exception:
        pass


def _normalize(info: Any, quality: str) -> dict:
    if not isinstance(info, dict):
        raise RuntimeError("平台返回数据格式异常")
    result = dict(info)
    result.setdefault("is_live", False)
    result.setdefault("anchor_name", "")
    result["quality"] = result.get("quality") or quality
    if result.get("is_live"):
        if not result.get("record_url"):
            result["record_url"] = result.get("flv_url") or result.get("m3u8_url")
        if not result.get("record_url"):
            raise RuntimeError("未获取到可录制的流地址")
    return result


def resolve_stream(room: dict, settings: dict, backend: str = "auto") -> dict:
    settings = settings or {}
    code = room["platform_code"]
    url = room["url"]
    quality = QUALITY_CODE.get(room.get("quality") or "原画", "OD")
    cookies = _cookie(settings, code)
    proxy = _proxy(room, settings)

    if code in PROXY_REQUIRED and not proxy:
        raise RuntimeError("该平台需要代理，请在设置中配置代理地址并启用对应平台")

    if code == "custom":
        if backend == "streamget":
            raise RuntimeError("streamget 不支持 custom 平台，请使用 DLR")
        lowered = url.lower()
        if ".flv" in lowered:
            return {"anchor_name": f"自定义直播_{abs(hash(url)) % 100000}", "is_live": True,
                    "flv_url": url, "record_url": url}
        return {"anchor_name": f"自定义直播_{abs(hash(url)) % 100000}", "is_live": True,
                "m3u8_url": url, "record_url": url}

    if backend in ("auto", "streamget"):
        if backend == "streamget" or streamget_resolver.enabled(settings):
            result, error = streamget_resolver.try_resolve(
                room,
                settings,
                cookies=cookies,
                proxy=proxy,
                credentials=streamget_resolver.credentials_from_settings(code, settings),
                force=backend == "streamget",
            )
            if result is not None:
                verify_offline = os.environ.get("DLR_STREAMGET_VERIFY_OFFLINE", "0") == "1"
                if result.get("is_live") or not verify_offline:
                    cookie_key = COOKIE_KEYS.get(code)
                    if result.get("new_cookies") and cookie_key:
                        _update_setting("Cookie", cookie_key, result["new_cookies"])
                    return result
                LOGGER.info("streamget 判定 %s 未开播，按配置再用 DLR 复核", code)
            elif backend == "streamget":
                detail = error or streamget_resolver.StreamgetError("unknown", "未知错误")
                raise RuntimeError(f"streamget 解析失败[{detail.code}]：{detail}") from detail
            elif error is not None:
                LOGGER.warning("streamget 解析失败，回退 DLR：%s", error)

    if code == "douyin":
        if "v.douyin.com" not in url and "/user/" not in url:
            data = _run(spider.get_douyin_web_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        else:
            data = _run(spider.get_douyin_app_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_douyin_stream_url(data, quality, proxy)), room["quality"])

    if code == "tiktok":
        data = _run(spider.get_tiktok_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_tiktok_stream_url(data, quality, proxy)), room["quality"])

    if code == "kuaishou":
        data = _run(spider.get_kuaishou_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_kuaishou_stream_url(data, quality)), room["quality"])

    if code == "huya":
        if quality not in ("OD", "BD", "UHD"):
            data = _run(spider.get_huya_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
            return _normalize(_run(stream.get_huya_stream_url(data, quality)), room["quality"])
        return _normalize(_run(spider.get_huya_app_stream_url(
            url=url, proxy_addr=proxy, cookies=cookies)), room["quality"])

    if code == "douyu":
        data = _run(spider.get_douyu_info_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_douyu_stream_url(
            data, video_quality=quality, cookies=cookies, proxy_addr=proxy)), room["quality"])

    if code == "yy":
        data = _run(spider.get_yy_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_yy_stream_url(data)), room["quality"])

    if code == "bilibili":
        data = _run(spider.get_bilibili_room_info(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_bilibili_stream_url(
            data, video_quality=quality, cookies=cookies, proxy_addr=proxy)), room["quality"])

    if code == "xhs":
        return _normalize(_run(spider.get_xhs_stream_url(url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "bigo":
        return _normalize(_run(spider.get_bigo_stream_url(url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "blued":
        return _normalize(_run(spider.get_blued_stream_url(url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])

    if code == "sooplive":
        data = _run(spider.get_sooplive_stream_data(
            url=url, proxy_addr=proxy, cookies=cookies,
            username=settings.get("sooplive账号", ""), password=settings.get("sooplive密码", ""),
        ))
        if data.get("new_cookies"):
            _update_setting("Cookie", "sooplive_cookie", data["new_cookies"])
        return _normalize(_run(stream.get_stream_url(data, quality, spec=True)), room["quality"])

    if code == "netease":
        data = _run(spider.get_netease_stream_data(url=url, cookies=cookies))
        return _normalize(_run(stream.get_netease_stream_url(data, quality)), room["quality"])

    if code == "qiandurebo":
        return _normalize(_run(spider.get_qiandurebo_stream_data(
            url=url, proxy_addr=proxy, cookies=cookies)), room["quality"])

    if code == "pandatv":
        data = _run(spider.get_pandatv_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_stream_url(data, quality, spec=True)), room["quality"])

    if code == "maoerfm":
        return _normalize(_run(spider.get_maoerfm_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])

    if code == "winktv":
        data = _run(spider.get_winktv_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_stream_url(data, quality, spec=True)), room["quality"])

    if code == "flextv":
        data = _run(spider.get_flextv_stream_data(
            url=url, proxy_addr=proxy, cookies=cookies,
            username=settings.get("flextv账号", ""), password=settings.get("flextv密码", ""),
        ))
        if data.get("new_cookies"):
            _update_setting("Cookie", "flextv_cookie", data["new_cookies"])
        if "play_url_list" in data:
            return _normalize(_run(stream.get_stream_url(data, quality, spec=True)), room["quality"])
        return _normalize(data, room["quality"])

    if code == "looklive":
        return _normalize(_run(spider.get_looklive_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])

    if code == "popkontv":
        data = _run(spider.get_popkontv_stream_url(
            url=url, proxy_addr=proxy,
            access_token=settings.get("popkontv_token", ""),
            username=settings.get("popkontv账号", ""),
            password=settings.get("popkontv密码", ""),
            partner_code=settings.get("partner_code", "P-00001"),
        ))
        if data.get("new_token"):
            _update_setting("Authorization", "popkontv_token", data["new_token"])
        return _normalize(data, room["quality"])

    if code == "twitcasting":
        data = _run(spider.get_twitcasting_stream_url(
            url=url, proxy_addr=proxy, cookies=cookies,
            account_type=settings.get("twitcasting账号类型", "normal"),
            username=settings.get("twitcasting账号", ""),
            password=settings.get("twitcasting密码", ""),
        ))
        if data.get("new_cookies"):
            _update_setting("Cookie", "twitcasting_cookie", data["new_cookies"])
        return _normalize(_run(stream.get_stream_url(data, quality, spec=False)), room["quality"])

    if code == "baidu":
        data = _run(spider.get_baidu_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_stream_url(data, quality)), room["quality"])

    if code == "weibo":
        data = _run(spider.get_weibo_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_stream_url(data, quality, hls_extra_key="m3u8_url")),
                          room["quality"])

    if code == "kugou":
        return _normalize(_run(spider.get_kugou_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])

    if code == "twitch":
        data = _run(spider.get_twitchtv_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_stream_url(data, quality, spec=True)), room["quality"])

    if code == "liveme":
        return _normalize(_run(spider.get_liveme_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])

    if code == "huajiao":
        return _normalize(_run(spider.get_huajiao_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])

    if code == "liuxing":
        return _normalize(_run(spider.get_liuxing_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])

    if code == "showroom":
        data = _run(spider.get_showroom_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_stream_url(data, quality, spec=True)), room["quality"])

    if code == "acfun":
        data = _run(spider.get_acfun_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_stream_url(
            data, quality, url_type="flv", flv_extra_key="url")), room["quality"])

    if code == "changliao":
        return _normalize(_run(spider.get_changliao_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "yinbo":
        return _normalize(_run(spider.get_yinbo_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "yingke":
        return _normalize(_run(spider.get_yingke_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "zhihu":
        return _normalize(_run(spider.get_zhihu_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])

    if code == "chzzk":
        data = _run(spider.get_chzzk_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_stream_url(data, quality, spec=True)), room["quality"])

    if code == "haixiu":
        return _normalize(_run(spider.get_haixiu_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "vvxqiu":
        return _normalize(_run(spider.get_vvxqiu_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "17live":
        return _normalize(_run(spider.get_17live_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "langlive":
        return _normalize(_run(spider.get_langlive_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "pplive":
        return _normalize(_run(spider.get_pplive_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "6room":
        return _normalize(_run(spider.get_6room_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "lehai":
        return _normalize(_run(spider.get_haixiu_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "huamao":
        return _normalize(_run(spider.get_pplive_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "shopee":
        return _normalize(_run(spider.get_shopee_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "youtube":
        data = _run(spider.get_youtube_stream_url(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_stream_url(data, quality, spec=True)), room["quality"])
    if code == "taobao":
        data = _run(spider.get_taobao_stream_url(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_stream_url(
            data, quality, url_type="all", hls_extra_key="hlsUrl", flv_extra_key="flvUrl")),
            room["quality"])
    if code == "jd":
        return _normalize(_run(spider.get_jd_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "faceit":
        data = _run(spider.get_faceit_stream_data(url=url, proxy_addr=proxy, cookies=cookies))
        return _normalize(_run(stream.get_stream_url(data, quality, spec=True)), room["quality"])
    if code == "migu":
        return _normalize(_run(spider.get_migu_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "lianjie":
        return _normalize(_run(spider.get_lianjie_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "laixiu":
        return _normalize(_run(spider.get_laixiu_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])
    if code == "picarto":
        return _normalize(_run(spider.get_picarto_stream_url(url=url, proxy_addr=proxy, cookies=cookies)),
                          room["quality"])

    raise RuntimeError(f"平台 {code} 尚未接入录制引擎")


def select_source_url(room: dict, info: dict) -> str:
    code = room["platform_code"]
    url = info.get("record_url") or info.get("m3u8_url") or info.get("flv_url")
    if not url:
        raise RuntimeError("未获取到录制地址")
    if code in ("douyin", "tiktok") and info.get("flv_url"):
        try:
            parsed = urlparse(info["flv_url"])
            query = dict(pair.split("=", 1) for pair in parsed.query.split("&") if "=" in pair)
            if (query.get("codec") or "").lower() != "h265":
                url = info["flv_url"]
        except Exception:
            url = info["flv_url"]
    return url
