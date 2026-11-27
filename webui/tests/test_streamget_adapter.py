from __future__ import annotations

from types import SimpleNamespace

import pytest

from webui.backend.workers import stream_resolver
from webui.backend.workers import streamget_resolver as sg


def test_quality_mapping():
    assert sg.QUALITY_MAP["原画"] == "OD"
    assert sg.QUALITY_MAP["蓝光"] == "UHD"
    assert sg.QUALITY_MAP["高清"] == "HD"
    assert sg.QUALITY_MAP["流畅"] == "LD"


def test_normalize_offline_and_online():
    room = {"quality": "高清", "name": "fallback"}
    offline = sg._normalize(room, "douyin", {"is_live": False, "anchor_name": "主播"}, {})
    assert offline["is_live"] is False
    assert offline["anchor_name"] == "主播"

    online = sg._normalize(
        room,
        "douyin",
        {"is_live": True, "anchor_name": "主播", "title": "标题"},
        {"flv_url": "https://example.com/live.flv", "new_cookies": "a=b"},
    )
    assert online["record_url"] == "https://example.com/live.flv"
    assert online["quality"] == "高清"
    assert online["new_cookies"] == "a=b"


def test_normalize_live_without_url_fails():
    with pytest.raises(sg.StreamgetError) as exc:
        sg._normalize({"quality": "原画"}, "douyin", {"is_live": True}, {})
    assert exc.value.code == "no_stream_url"


def test_invalid_url_and_proxy():
    with pytest.raises(sg.StreamgetError) as exc:
        sg._validate_url("file:///etc/passwd")
    assert exc.value.code == "invalid_url"

    with pytest.raises(sg.StreamgetError) as exc:
        sg._validate_proxy("socks5://127.0.0.1:1080")
    assert exc.value.code == "proxy_unsupported"


def test_enabled_and_platforms(monkeypatch):
    monkeypatch.delenv("DLR_STREAMGET_ENABLED", raising=False)
    assert sg.enabled({})
    assert not sg.enabled({"启用streamget解析(是/否)": "否"})
    assert sg.enabled({"启用streamget解析(是/否)": "是"})

    monkeypatch.setenv("DLR_STREAMGET_ENABLED", "0")
    assert not sg.enabled({"启用streamget解析(是/否)": "是"})

    monkeypatch.delenv("DLR_STREAMGET_PLATFORMS", raising=False)
    assert sg.platforms({}) == set(sg.PLATFORM_CLASSES)
    assert sg.platforms({"streamget解析平台(逗号分隔)": "*"}) == set(sg.PLATFORM_CLASSES)
    assert sg.platforms({"streamget解析平台(逗号分隔)": "douyin, TikTok"}) == {"douyin", "tiktok"}


def test_build_client_accepts_proxy_addr_and_cookies():
    class FakeLive:
        def __init__(self, proxy_addr=None, cookies=None):
            self.proxy_addr = proxy_addr
            self.cookies = cookies

    module = SimpleNamespace(DouyinLiveStream=FakeLive)
    client = sg._build_client(module, "douyin", "http://127.0.0.1:7890", "a=b")
    assert client.proxy_addr == "http://127.0.0.1:7890"
    assert client.cookies == "a=b"


def test_fetch_info_prefers_app_for_douyin_short_url():
    class FakeLive:
        def __init__(self):
            self.calls = []

        async def fetch_app_stream_data(self, url):
            self.calls.append("app")
            return {"is_live": True, "anchor_name": "a"}

        async def fetch_web_stream_data(self, url):
            self.calls.append("web")
            return {"is_live": True, "anchor_name": "a"}

    live = FakeLive()
    info = sg._fetch_info(live, "douyin", "https://v.douyin.com/abc")
    assert info["is_live"] is True
    assert live.calls == ["app"]


def test_run_async_timeout():
    async def slow():
        import asyncio

        await asyncio.sleep(0.2)
        return {"is_live": True}

    with pytest.raises(sg.StreamgetError) as exc:
        sg._run_async(slow, 0.01)
    assert exc.value.code == "timeout"


def test_classify_node_missing():
    class ProgramError(Exception):
        pass

    error = sg._classify(ProgramError("Cannot find module 'x-bogus'"))
    assert error.code == "node_missing"


def test_try_resolve_never_raises(monkeypatch):
    def boom(*args, **kwargs):
        raise sg.StreamgetError("timeout", "slow")

    monkeypatch.setattr(sg, "resolve", boom)
    sg._FAILURES.clear()
    result, error = sg.try_resolve(
        {"platform_code": "douyin", "url": "https://live.douyin.com/1"},
        {},
        force=True,
    )
    assert result is None
    assert error is not None and error.code == "timeout"


def test_cooldown_after_failure(monkeypatch):
    monkeypatch.setenv("DLR_STREAMGET_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("DLR_STREAMGET_COOLDOWN", "60")

    def boom(*args, **kwargs):
        raise sg.StreamgetError("network", "down")

    monkeypatch.setattr(sg, "resolve", boom)
    sg._FAILURES.clear()
    sg.try_resolve(
        {"platform_code": "douyin", "url": "https://live.douyin.com/1"},
        {},
        force=True,
    )
    assert not sg.should_attempt("douyin", {}, force=False)
    assert sg.should_attempt("douyin", {}, force=True)


def test_normalize_infers_live_from_stream_url():
    result = sg._normalize(
        {"quality": "原画"},
        "douyin",
        {"anchor_name": "主播"},
        {"flv_url": "https://example.com/live.flv"},
    )
    assert result["is_live"] is True
    assert result["record_url"] == "https://example.com/live.flv"


def test_classify_http_status():
    class Response:
        status_code = 429

    class Error(Exception):
        response = Response()

    assert sg._classify(Error("too many")).code == "rate_limited"


def test_credentials_from_settings(monkeypatch):
    monkeypatch.delenv("DLR_STREAMGET_ORIENTATION", raising=False)
    monkeypatch.delenv("DLR_STREAMGET_HEVC", raising=False)
    credentials = sg.credentials_from_settings(
        "sooplive",
        {"sooplive账号": "user", "sooplive密码": "pass"},
    )
    assert credentials == {"username": "user", "password": "pass"}


def test_try_resolve_skips_unsupported(monkeypatch):
    monkeypatch.setattr(sg, "resolve", lambda *args, **kwargs: pytest.fail("must not run"))
    assert sg.try_resolve(
        {"platform_code": "custom", "url": "https://example.com/a.m3u8"},
        {},
    ) == (None, None)


def test_streamget_settings_meta():
    from webui.backend import settings_meta

    enabled = settings_meta.build_meta("录制设置", "启用streamget解析(是/否)", "否", 0)
    assert enabled["label"] == "启用 streamget 解析"
    assert enabled["value_type"] == "bool"
    platforms = settings_meta.build_meta(
        "录制设置", "streamget解析平台(逗号分隔)", "douyin", 1
    )
    assert platforms["label"] == "streamget 解析平台"


def test_resolve_stream_auto_uses_streamget(monkeypatch):
    monkeypatch.setattr(sg, "enabled", lambda settings: True)
    monkeypatch.setattr(
        sg,
        "try_resolve",
        lambda *args, **kwargs: (
            {"is_live": False, "anchor_name": "streamget", "quality": "原画"},
            None,
        ),
    )
    room = {
        "platform_code": "douyin",
        "url": "https://live.douyin.com/1",
        "quality": "原画",
        "name": "test",
    }
    result = stream_resolver.resolve_stream(room, {"启用streamget解析(是/否)": "是"})
    assert result["anchor_name"] == "streamget"
    assert result["is_live"] is False


def test_resolve_stream_streamget_backend_reports_error(monkeypatch):
    monkeypatch.setattr(
        sg,
        "try_resolve",
        lambda *args, **kwargs: (None, sg.StreamgetError("timeout", "slow")),
    )
    room = {
        "platform_code": "douyin",
        "url": "https://live.douyin.com/1",
        "quality": "原画",
        "name": "test",
    }
    with pytest.raises(RuntimeError) as exc:
        stream_resolver.resolve_stream(room, {}, backend="streamget")
    assert "timeout" in str(exc.value)
