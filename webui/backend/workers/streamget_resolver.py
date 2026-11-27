"""Optional streamget extraction backend with strict fallback semantics.

The adapter is intentionally defensive: every failure is converted into a
``StreamgetError`` with a stable code, logged without leaking cookies or query
strings, and surfaced to the caller so ``stream_resolver`` can fall back to the
existing DLR implementation.

Failure matrix handled here:
- streamget missing / too old / class or method missing;
- invalid room URL, quality, cookies or proxy scheme;
- constructor signature differences between streamget versions;
- async event-loop conflicts, timeouts and cancellation;
- DNS, TLS, connection, proxy, 401/403, 429 and 5xx errors;
- Node.js / PyExecJS missing for JS-signed platforms;
- empty/None/HTML/JSON-invalid responses and unexpected data shapes;
- live result without a usable http(s) record URL;
- repeated failures with a per-platform cooldown to avoid hammering.
"""
from __future__ import annotations

import asyncio
import dataclasses
import html
import inspect
import logging
import os
import re
import socket
import ssl
import threading
import time
from typing import Any, Callable
from urllib.parse import urlparse

LOGGER = logging.getLogger("dlr.streamget")

DEFAULT_PLATFORMS = "*"

# DLR platform code -> streamget class name. Platforms not listed here keep the
# DLR implementation; this is deliberate for custom / unsupported platforms.
PLATFORM_CLASSES: dict[str, str] = {
    "douyin": "DouyinLiveStream",
    "tiktok": "TikTokLiveStream",
    "kuaishou": "KwaiLiveStream",
    "huya": "HuyaLiveStream",
    "douyu": "DouyuLiveStream",
    "yy": "YYLiveStream",
    "bilibili": "BilibiliLiveStream",
    "xhs": "RedNoteLiveStream",
    "bigo": "BigoLiveStream",
    "blued": "BluedLiveStream",
    "sooplive": "SoopLiveStream",
    "netease": "NeteaseLiveStream",
    "qiandurebo": "QiandureboLiveStream",
    "pandatv": "PandaLiveStream",
    "maoerfm": "MaoerLiveStream",
    "winktv": "WinkTVLiveStream",
    "flextv": "FlexTVLiveStream",
    "looklive": "LookLiveStream",
    "popkontv": "PopkonTVLiveStream",
    "twitcasting": "TwitCastingLiveStream",
    "baidu": "BaiduLiveStream",
    "weibo": "WeiboLiveStream",
    "kugou": "KugouLiveStream",
    "twitch": "TwitchLiveStream",
    "liveme": "LiveMeLiveStream",
    "huajiao": "HuajiaoLiveStream",
    "showroom": "ShowRoomLiveStream",
    "acfun": "AcfunLiveStream",
    "changliao": "ChangliaoLiveStream",
    "yinbo": "YinboLiveStream",
    "yingke": "InkeLiveStream",
    "zhihu": "ZhihuLiveStream",
    "chzzk": "ChzzkLiveStream",
    "haixiu": "HaixiuLiveStream",
    "vvxqiu": "VVXQLiveStream",
    "langlive": "LangLiveStream",
    "6room": "SixRoomLiveStream",
    "lehai": "LehaiLiveStream",
    "huamao": "HuamaoLiveStream",
    "shopee": "ShopeeLiveStream",
    "youtube": "YoutubeLiveStream",
    "taobao": "TaobaoLiveStream",
    "jd": "JDLiveStream",
    "faceit": "FaceitLiveStream",
    "migu": "MiguLiveStream",
    "lianjie": "LianJieLiveStream",
    "laixiu": "LaixiuLiveStream",
    "picarto": "PicartoLiveStream",
}

QUALITY_MAP = {
    "原画": "OD",
    "蓝光": "UHD",
    "超清": "UHD",
    "高清": "HD",
    "标清": "SD",
    "流畅": "LD",
    "OD": "OD",
    "UHD": "UHD",
    "HD": "HD",
    "SD": "SD",
    "LD": "LD",
}

APP_METHOD_PLATFORMS = {
    "douyin": ("v.douyin.com", "www.douyin.com/user", "/user/"),
}

# streamget account parameters that exist in the DLR settings UI.
ACCOUNT_SETTINGS: dict[str, dict[str, str]] = {
    "sooplive": {"username": "sooplive账号", "password": "sooplive密码"},
    "flextv": {"username": "flextv账号", "password": "flextv密码"},
    "twitcasting": {
        "username": "twitcasting账号",
        "password": "twitcasting密码",
        "account_type": "twitcasting账号类型",
    },
    "popkontv": {
        "username": "popkontv账号",
        "password": "popkontv密码",
        "access_token": "popkontv_token",
        "partner_code": "partner_code",
    },
}

_COOLDOWN_LOCK = threading.Lock()
_FAILURES: dict[str, tuple[int, float]] = {}


class StreamgetError(RuntimeError):
    """A classified streamget failure that callers may fall back from."""

    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable

    def __str__(self) -> str:  # keep logs readable
        return f"{self.code}: {self.args[0]}"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "是"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else _as_bool(raw)


def enabled(settings: dict) -> bool:
    settings = settings or {}
    raw = os.environ.get("DLR_STREAMGET_ENABLED")
    if raw is not None:
        return _as_bool(raw)
    return _as_bool(settings.get("启用streamget解析(是/否)", "是"))


def platforms(settings: dict) -> set[str]:
    settings = settings or {}
    raw = os.environ.get("DLR_STREAMGET_PLATFORMS")
    if raw is None:
        raw = settings.get("streamget解析平台(逗号分隔)", "")
    text = str(raw or "").strip()
    if not text:
        text = DEFAULT_PLATFORMS
    if text == "*":
        return set(PLATFORM_CLASSES)
    values = {
        item.strip().lower()
        for item in re.split(r"[,，\s]+", text)
        if item.strip()
    }
    return values


def supports(code: str) -> bool:
    return str(code or "").lower() in PLATFORM_CLASSES


def credentials_from_settings(code: str, settings: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for field, key in ACCOUNT_SETTINGS.get(code.lower(), {}).items():
        value = str(settings.get(key, "") or "").strip()
        if value:
            result[field] = value
    orientation = os.environ.get("DLR_STREAMGET_ORIENTATION", "").strip()
    if orientation.isdigit():
        result["stream_orientation"] = int(orientation)
    if _env_bool("DLR_STREAMGET_HEVC", False):
        result["is_hevc"] = True
    return result


def _timeout_seconds() -> float:
    try:
        value = float(os.environ.get("DLR_STREAMGET_TIMEOUT", "25"))
    except (TypeError, ValueError):
        value = 25.0
    return min(max(value, 3.0), 120.0)


def _failure_threshold() -> int:
    try:
        value = int(os.environ.get("DLR_STREAMGET_FAILURE_THRESHOLD", "2"))
    except (TypeError, ValueError):
        value = 2
    return max(1, value)


def _cooldown_seconds() -> float:
    try:
        value = float(os.environ.get("DLR_STREAMGET_COOLDOWN", "300"))
    except (TypeError, ValueError):
        value = 300.0
    return max(0.0, value)


def _in_cooldown(code: str) -> bool:
    with _COOLDOWN_LOCK:
        count, until = _FAILURES.get(code, (0, 0.0))
        return until > time.monotonic()


def _record_failure(code: str) -> None:
    threshold = _failure_threshold()
    with _COOLDOWN_LOCK:
        count, _ = _FAILURES.get(code, (0, 0.0))
        count += 1
        until = time.monotonic() + _cooldown_seconds() if count >= threshold else 0.0
        _FAILURES[code] = (count, until)


def _record_success(code: str) -> None:
    with _COOLDOWN_LOCK:
        _FAILURES.pop(code, None)


def should_attempt(code: str, settings: dict, *, force: bool = False) -> bool:
    if force:
        return supports(code)
    if not supports(code):
        return False
    if code not in platforms(settings):
        return False
    if _in_cooldown(code):
        LOGGER.info("streamget skipped for %s: cooldown active", code)
        return False
    return True


def _sanitize_url(url: str) -> str:
    try:
        parsed = urlparse(str(url or ""))
        netloc = parsed.netloc.rsplit("@", 1)[-1]
        suffix = "?<redacted>" if parsed.query else ""
        return f"{parsed.scheme}://{netloc}{parsed.path}{suffix}"
    except Exception:
        return "<invalid-url>"


def _redact(text: str) -> str:
    value = re.sub(r"(https?://[^\s?]+)\?[^\s]*", r"\1?<redacted>", str(text))
    return value[:300]


def _load_module():
    if not _env_bool("DLR_STREAMGET_LOG_HTTP", False):
        # httpx logs the full signed URL at INFO, which may contain tokens.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        import streamget  # type: ignore
    except Exception as exc:  # ImportError, broken install, missing PyExecJS...
        raise StreamgetError(
            "not_installed",
            "未安装 streamget，请执行 pip install -r webui/requirements.txt",
            retryable=False,
        ) from exc
    version = str(getattr(streamget, "__version__", "") or "")
    if version:
        try:
            parsed = tuple(int(part) for part in re.findall(r"\d+", version)[:3])
            if parsed and parsed < (4, 0, 10):
                LOGGER.warning(
                    "streamget %s is older than 4.0.10; platform fixes may be missing",
                    version,
                )
        except (TypeError, ValueError):
            LOGGER.warning("cannot parse streamget version %s", version)
    return streamget


def _validate_proxy(proxy: str | None) -> str | None:
    value = (proxy or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme.lower() not in ("http", "https"):
        raise StreamgetError(
            "proxy_unsupported",
            f"streamget/httpx 不支持 {parsed.scheme or '未知'} 代理，请改用 http/https 代理",
        )
    if not parsed.netloc:
        raise StreamgetError("proxy_invalid", "代理地址格式不正确")
    return value


def _validate_cookies(cookies: str | None) -> str:
    value = str(cookies or "").replace("\r", "").replace("\n", "").strip()
    if len(value) > 32768:
        raise StreamgetError(
            "cookies_too_large",
            "Cookie 超过 32KB，streamget 无法安全发送，请精简 Cookie",
        )
    return value


def _validate_url(url: str) -> str:
    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise StreamgetError("invalid_url", "直播间地址必须是 http(s) URL")
    return value


def _quality(room: dict) -> str:
    value = str(room.get("quality") or "原画").strip()
    return QUALITY_MAP.get(value, "OD")


def _first_valid_url(*values: Any) -> str:
    for value in values:
        if isinstance(value, (list, tuple)):
            candidate = next((item for item in value if item), None)
        else:
            candidate = value
        if not candidate:
            continue
        text = html.unescape(str(candidate)).strip()
        if text.startswith("//"):
            text = "https:" + text
        parsed = urlparse(text)
        if parsed.scheme.lower() in ("http", "https") and parsed.netloc:
            return text
    return ""


def _as_dict(value: Any, what: str) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    raise StreamgetError("bad_response", f"{what} 返回了无法识别的数据类型: {type(value).__name__}")


def _run_async(factory: Callable[[], Any], timeout: float) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise StreamgetError(
            "event_loop_conflict",
            "streamget 适配层不能在没有退出事件循环的线程中同步调用",
        )

    async def runner():
        return await asyncio.wait_for(factory(), timeout=timeout)

    try:
        return asyncio.run(runner())
    except (asyncio.TimeoutError, TimeoutError) as exc:
        raise StreamgetError(
            "timeout",
            f"streamget 请求超过 {timeout:.0f} 秒未完成",
        ) from exc
    except asyncio.CancelledError as exc:
        raise StreamgetError("cancelled", "streamget 请求被取消") from exc
    except Exception as exc:
        raise _classify(exc) from exc


def _classify(exc: BaseException) -> StreamgetError:
    if isinstance(exc, StreamgetError):
        return exc
    name = type(exc).__name__
    text = str(exc)
    lowered = text.lower()
    status = getattr(getattr(exc, "response", None), "status_code", None)

    if isinstance(exc, (ModuleNotFoundError, ImportError)):
        return StreamgetError("import_error", f"streamget 依赖导入失败: {_redact(text)}")
    if status in (401, 403):
        return StreamgetError("auth", f"平台返回 {status}，Cookie/登录状态可能失效")
    if status == 429:
        return StreamgetError("rate_limited", "平台限流，请稍后重试")
    if isinstance(status, int) and status >= 500:
        return StreamgetError("server", f"平台服务端错误 {status}")
    if isinstance(exc, ssl.SSLError):
        return StreamgetError("tls", f"TLS 握手失败: {_redact(text)}")
    if isinstance(exc, socket.gaierror):
        return StreamgetError("dns", f"域名解析失败: {_redact(text)}")
    if isinstance(exc, (ConnectionError, OSError)) and "node" not in lowered:
        return StreamgetError("network", f"网络请求失败: {_redact(text)}")
    if "programerror" in name.lower() or "node" in lowered or "execjs" in lowered:
        return StreamgetError(
            "node_missing",
            "streamget 需要 Node.js 执行签名脚本，请安装 Node 或改用 DLR 回退",
        )
    if "timeout" in name.lower() or "timed out" in lowered:
        return StreamgetError("timeout", "streamget 请求超时")
    if "proxy" in lowered:
        return StreamgetError("proxy", f"代理请求失败: {_redact(text)}")
    if "ssl" in lowered or "certificate" in lowered:
        return StreamgetError("tls", f"TLS 校验失败: {_redact(text)}")
    if "json" in name.lower() or "json" in lowered:
        return StreamgetError("parse_error", f"返回内容不是有效 JSON: {_redact(text)}")
    if isinstance(exc, (KeyError, IndexError, AttributeError, TypeError, ValueError)):
        return StreamgetError("parse_error", f"streamget 返回结构异常: {_redact(text)}")
    return StreamgetError("unknown", f"streamget 未知错误: {_redact(text)}")


def _build_client(module, code: str, proxy: str | None, cookies: str,
                  credentials: dict | None = None):
    class_name = PLATFORM_CLASSES.get(code)
    if not class_name:
        raise StreamgetError("unsupported_platform", f"streamget 未适配平台: {code}", retryable=False)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise StreamgetError(
            "class_missing",
            f"streamget 版本中不存在 {class_name}，请升级到 4.0.10",
            retryable=False,
        )
    try:
        signature = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        signature = None
    kwargs: dict[str, Any] = {}
    if signature is not None:
        params = signature.parameters
        accepts_kwargs = any(p.kind == p.VAR_KEYWORD for p in params.values())
        if "proxy_addr" in params:
            kwargs["proxy_addr"] = proxy
        elif "proxy" in params:
            kwargs["proxy"] = proxy
        elif accepts_kwargs and proxy:
            kwargs["proxy_addr"] = proxy
        if "cookies" in params or accepts_kwargs:
            kwargs["cookies"] = cookies
        for key, value in (credentials or {}).items():
            if value in (None, ""):
                continue
            if key in params or accepts_kwargs:
                kwargs[key] = value
    else:
        kwargs = {"proxy_addr": proxy, "cookies": cookies, **(credentials or {})}
    try:
        return cls(**kwargs)
    except TypeError as exc:
        raise StreamgetError(
            "constructor",
            f"{class_name} 构造参数不兼容: {_redact(str(exc))}",
        ) from exc
    except Exception as exc:
        raise _classify(exc) from exc


def _call_method(target, name: str, *args):
    method = getattr(target, name, None)
    if method is None:
        return None
    timeout = _timeout_seconds()
    try:
        return _run_async(lambda: method(*args), timeout)
    except StreamgetError as exc:
        # Some streamget versions only accept keyword arguments. The
        # classifier preserves the original "positional arguments" text.
        if "positional" not in str(exc).lower():
            raise
        return _run_async(lambda: method(url=args[0]), timeout)


def _fetch_info(live, code: str, url: str) -> dict:
    if code in APP_METHOD_PLATFORMS and any(token in url for token in APP_METHOD_PLATFORMS[code]):
        methods = ("fetch_app_stream_data", "fetch_web_stream_data")
    else:
        methods = ("fetch_web_stream_data", "fetch_app_stream_data")
    last_error: Exception | None = None
    for name in methods:
        if not hasattr(live, name):
            continue
        try:
            value = _call_method(live, name, url)
            if value is None:
                raise StreamgetError("no_data", f"{name} 返回空数据")
            return _as_dict(value, name)
        except StreamgetError as exc:
            last_error = exc
            # Transport/auth/limit errors are unlikely to be fixed by trying
            # another endpoint; fail fast so the caller can fall back to DLR.
            if exc.code in ("timeout", "auth", "rate_limited", "proxy", "tls", "dns"):
                raise
        except Exception as exc:
            last_error = exc
            if name == methods[-1]:
                raise
    if last_error:
        raise last_error
    raise StreamgetError("method_missing", "streamget 对象没有可用的取流方法")


def _fetch_stream(live, info: dict, quality: str) -> dict:
    method = getattr(live, "fetch_stream_url", None)
    if method is None:
        raise StreamgetError("method_missing", "streamget 对象缺少 fetch_stream_url")
    timeout = _timeout_seconds()
    try:
        value = _run_async(lambda: method(info, quality), timeout)
    except StreamgetError as exc:
        if "positional" not in str(exc).lower():
            raise
        try:
            value = _run_async(lambda: method(info, video_quality=quality), timeout)
        except StreamgetError as inner:
            if "positional" not in str(inner).lower():
                raise
            value = _run_async(lambda: method(info), timeout)
    if value is None:
        raise StreamgetError("no_stream", "fetch_stream_url 返回空数据")
    return _as_dict(value, "fetch_stream_url")


def _normalize(room: dict, code: str, info: dict, stream: dict) -> dict:
    data = {**info, **stream}
    anchor = str(data.get("anchor_name") or room.get("name") or "").strip() or "未知主播"
    record_url = _first_valid_url(
        data.get("record_url"),
        data.get("flv_url"),
        data.get("m3u8_url"),
    )
    raw_live = data.get("is_live")
    is_live = True if raw_live is None and record_url else _as_bool(raw_live)
    if not is_live:
        return {
            "anchor_name": anchor,
            "is_live": False,
            "quality": room.get("quality") or "原画",
        }

    if not record_url:
        raise StreamgetError("no_stream_url", "streamget 返回直播中，但没有可用的 http(s) 流地址")

    result = {
        "anchor_name": anchor,
        "is_live": True,
        "title": str(data.get("title") or ""),
        "quality": room.get("quality") or "原画",
        "record_url": record_url,
        "flv_url": _first_valid_url(data.get("flv_url")),
        "m3u8_url": _first_valid_url(data.get("m3u8_url")),
        "platform": str(data.get("platform") or code),
    }
    new_cookies = data.get("new_cookies") or data.get("new_cookie")
    if isinstance(new_cookies, str) and new_cookies.strip():
        result["new_cookies"] = new_cookies.strip()
    new_token = data.get("new_token")
    if isinstance(new_token, str) and new_token.strip():
        result["new_token"] = new_token.strip()
    return result


def resolve(room: dict, settings: dict, *, cookies: str = "", proxy: str | None = None,
            credentials: dict | None = None) -> dict:
    """Resolve one room with streamget or raise a classified StreamgetError."""
    code = str(room.get("platform_code") or "").strip().lower()
    if not supports(code):
        raise StreamgetError("unsupported_platform", f"streamget 未适配平台: {code}", retryable=False)
    url = _validate_url(room.get("url"))
    proxy = _validate_proxy(proxy)
    cookies = _validate_cookies(cookies)
    module = _load_module()
    live = _build_client(module, code, proxy, cookies, credentials)
    info = _fetch_info(live, code, url)
    stream = _fetch_stream(live, info, _quality(room))
    return _normalize(room, code, info, stream)


def try_resolve(
    room: dict,
    settings: dict,
    *,
    cookies: str = "",
    proxy: str | None = None,
    credentials: dict | None = None,
    force: bool = False,
) -> tuple[dict | None, StreamgetError | None]:
    """Try streamget; return ``(result, None)`` or ``(None, error)``.

    ``force=True`` bypasses the enable flag, whitelist and cooldown, which is
    used by the diagnostic script. Automatic callers never see an exception.
    """
    code = str(room.get("platform_code") or "").strip().lower()
    if not force and not should_attempt(code, settings):
        return None, None
    if force and not supports(code):
        return None, StreamgetError(
            "unsupported_platform", f"streamget 未适配平台: {code}", retryable=False
        )
    try:
        result = resolve(
            room,
            settings,
            cookies=cookies,
            proxy=proxy,
            credentials=credentials,
        )
    except StreamgetError as exc:
        _record_failure(code)
        LOGGER.warning(
            "streamget failed for %s %s: %s",
            code,
            _sanitize_url(room.get("url", "")),
            exc,
        )
        return None, exc
    except Exception as exc:  # defensive: never break the recorder
        _record_failure(code)
        LOGGER.exception(
            "streamget unexpected failure for %s %s",
            code,
            _sanitize_url(room.get("url", "")),
        )
        return None, StreamgetError("unknown", _redact(str(exc)))
    _record_success(code)
    return result, None
