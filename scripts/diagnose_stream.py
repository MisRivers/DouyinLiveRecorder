#!/usr/bin/env python3
"""Compare DLR and streamget stream resolution for one live room.

Examples:
    python scripts/diagnose_stream.py --url https://live.douyin.com/123
    python scripts/diagnose_stream.py --platform sooplive --url ... --proxy http://127.0.0.1:7890
    python scripts/diagnose_stream.py --url ... --json

The script never writes to the database; it only reads settings (unless
``--no-db`` is used) and runs the two resolvers in isolation. Cookies and query
strings are redacted from the output by default.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui.backend import config, db, platform_registry  # noqa: E402
from webui.backend.workers import stream_resolver, streamget_resolver  # noqa: E402

LOGGER = logging.getLogger("dlr.diagnose")


def _redact_url(url: str) -> str:
    try:
        parsed = urlparse(str(url or ""))
        netloc = parsed.netloc.rsplit("@", 1)[-1]
        suffix = "?<redacted>" if parsed.query else ""
        return f"{parsed.scheme}://{netloc}{parsed.path}{suffix}"
    except Exception:
        return "<invalid-url>"


def _redact_text(text: str) -> str:
    value = str(text)
    if "http" in value:
        # Avoid leaking signed query parameters from exception messages.
        parts = []
        for token in value.split():
            parts.append(_redact_url(token) if token.startswith(("http://", "https://")) else token)
        value = " ".join(parts)
    return value[:500]


def _load_settings(use_db: bool) -> dict[str, str]:
    defaults = {key: value for _, key, value in db.DEFAULT_SETTINGS}
    if use_db and config.DB_PATH.exists():
        try:
            return {**defaults, **db.get_settings()}
        except Exception as exc:
            LOGGER.warning("读取数据库设置失败，改用默认设置：%s", exc)
    return defaults


def _setting(settings: dict[str, str], section: str, key: str, default: str = "") -> str:
    return settings.get(f"{section}\0{key}", settings.get(key, default))


def _apply_overrides(
    settings: dict[str, str],
    code: str,
    cookie: str,
    proxy: str | None,
    no_proxy: bool,
) -> None:
    if cookie:
        key = stream_resolver.COOKIE_KEYS.get(code)
        if not key:
            raise SystemExit(f"平台 {code} 没有可用的 Cookie 配置项")
        settings[f"Cookie\0{key}"] = cookie
        settings[key] = cookie
    if no_proxy:
        settings["录制设置\0是否使用代理ip(是/否)"] = "否"
        settings["是否使用代理ip(是/否)"] = "否"
    elif proxy:
        settings["录制设置\0是否使用代理ip(是/否)"] = "是"
        settings["录制设置\0代理地址"] = proxy
        settings["是否使用代理ip(是/否)"] = "是"
        settings["代理地址"] = proxy
        key = "使用代理录制的平台(逗号分隔)"
        current = _setting(settings, "录制设置", key, "")
        tokens = [token.strip() for token in current.replace("，", ",").split(",") if token.strip()]
        if code not in tokens:
            tokens.append(code)
        value = ", ".join(tokens)
        settings[f"录制设置\0{key}"] = value
        settings[key] = value


def _sanitize_result(result: dict, show_url: bool) -> dict:
    sanitized = dict(result)
    for key in ("record_url", "flv_url", "m3u8_url"):
        value = sanitized.get(key)
        if isinstance(value, str) and value and not show_url:
            sanitized[key] = _redact_url(value)
    for key in ("new_cookies", "new_token"):
        if sanitized.get(key):
            sanitized[key] = "<redacted>"
    return sanitized


def _streamget_version() -> str | None:
    try:
        import streamget

        return str(getattr(streamget, "__version__", "") or "") or None
    except Exception:
        return None


def _run_backend(
    label: str,
    backend: str,
    room: dict,
    settings: dict,
    show_url: bool,
) -> dict:
    started = time.monotonic()
    try:
        result = stream_resolver.resolve_stream(room, settings, backend=backend)
        elapsed = int((time.monotonic() - started) * 1000)
        return {
            "backend": label,
            "ok": True,
            "elapsed_ms": elapsed,
            "result": _sanitize_result(result, show_url),
        }
    except Exception as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        return {
            "backend": label,
            "ok": False,
            "elapsed_ms": elapsed,
            "error_type": type(exc).__name__,
            "error": _redact_text(str(exc)),
        }


def _summary(rows: list[dict]) -> dict:
    if len(rows) != 2:
        return {}
    left, right = rows
    left_result = left.get("result") or {}
    right_result = right.get("result") or {}
    return {
        "both_ok": bool(left.get("ok") and right.get("ok")),
        "live_match": (
            left.get("ok") and right.get("ok")
            and bool(left_result.get("is_live")) == bool(right_result.get("is_live"))
        ),
        "anchor_match": (
            left.get("ok") and right.get("ok")
            and str(left_result.get("anchor_name") or "") == str(right_result.get("anchor_name") or "")
        ),
    }


def _print_human(code: str, room: dict, rows: list[dict], summary: dict) -> None:
    print(f"platform : {code}")
    print(f"url      : {_redact_url(room['url'])}")
    print(f"quality  : {room['quality']}")
    for row in rows:
        if row["ok"]:
            result = row["result"]
            host = _redact_url(result.get("record_url") or result.get("flv_url") or result.get("m3u8_url") or "")
            print(
                f"{row['backend']:<9}: OK   {row['elapsed_ms']:>5} ms  "
                f"live={result.get('is_live')}  anchor={result.get('anchor_name') or '-'}  "
                f"stream={host or '-'}"
            )
        else:
            print(
                f"{row['backend']:<9}: FAIL {row['elapsed_ms']:>5} ms  "
                f"{row['error_type']}: {row['error']}"
            )
    if summary:
        print(
            "verdict  : "
            f"both_ok={summary.get('both_ok')} "
            f"live_match={summary.get('live_match')} "
            f"anchor_match={summary.get('anchor_match')}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare DLR and streamget resolution")
    parser.add_argument("--url", required=True, help="live room URL")
    parser.add_argument("--platform", default="", help="DLR platform code; inferred from URL when omitted")
    parser.add_argument(
        "--quality",
        default="原画",
        choices=platform_registry.QUALITY_OPTIONS,
        help="recording quality",
    )
    parser.add_argument("--cookie", default="", help="override cookie for this run")
    parser.add_argument("--proxy", default="", help="override proxy, e.g. http://127.0.0.1:7890")
    parser.add_argument("--no-proxy", action="store_true", help="disable proxy for this run")
    parser.add_argument("--timeout", type=float, default=25.0, help="streamget timeout seconds")
    parser.add_argument("--use-db", action="store_true", help="merge settings from the existing app database")
    parser.add_argument("--show-url", action="store_true", help="print full stream URLs (may contain tokens)")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stderr,
    )
    if not args.verbose and not os.environ.get("DLR_STREAMGET_LOG_HTTP"):
        # httpx logs full signed URLs at INFO; hide them unless explicitly debugging.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
    os.environ["DLR_STREAMGET_TIMEOUT"] = str(max(3.0, min(args.timeout, 120.0)))

    url = (args.url or "").strip()
    if not url.startswith(("http://", "https://")):
        parser.error("--url 必须是 http(s) 地址")
    code = (args.platform or platform_registry.match_platform(url) or "").strip().lower()
    if not code:
        parser.error("无法从 URL 推断平台，请使用 --platform 指定")
    if not platform_registry.platform_by_code(code):
        parser.error(f"未知平台代码: {code}")

    settings = _load_settings(args.use_db)
    _apply_overrides(settings, code, args.cookie, args.proxy or None, args.no_proxy)
    room = {
        "platform_code": code,
        "url": url,
        "quality": args.quality,
        "name": "diagnostic",
    }

    rows = [
        _run_backend("DLR", "dlr", room, settings, args.show_url),
        _run_backend("streamget", "streamget", room, settings, args.show_url),
    ]
    summary = _summary(rows)
    payload = {
        "platform": code,
        "url": _redact_url(url),
        "quality": args.quality,
        "streamget_version": _streamget_version(),
        "results": rows,
        "summary": summary,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_human(code, room, rows, summary)

    successes = sum(1 for row in rows if row["ok"])
    if successes == 2:
        return 0
    if successes == 1:
        return 1
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("cancelled", file=sys.stderr)
        raise SystemExit(130)
