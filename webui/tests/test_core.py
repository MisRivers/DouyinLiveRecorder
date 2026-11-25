from __future__ import annotations

from webui.backend import db, platform_registry, settings_meta
from webui.backend.services.files_service import natural_key


def test_match_platform_special_hosts():
    assert platform_registry.match_platform("https://live.douyin.com/123") == "douyin"
    assert platform_registry.match_platform("https://sg.shp.ee/GmpXeuf") == "shopee"
    assert platform_registry.match_platform("https://3.cn/28MLBy-E") == "jd"
    assert platform_registry.match_platform("https://m.tb.cn/h.TWp0HTd") == "taobao"
    assert platform_registry.match_platform("https://www.youtube.com/watch?v=abc") == "youtube"
    assert platform_registry.match_platform("https://example.com/a.m3u8") == "custom"


def test_quick_add_builds_url():
    assert platform_registry.build_url("douyin", "745964462470") == "https://live.douyin.com/745964462470"
    assert platform_registry.build_url("tiktok", "pearlgaga88") == "https://www.tiktok.com/@pearlgaga88/live"
    assert platform_registry.build_url("douyin", "bad id") is None
    assert platform_registry.build_url("xhs", "anything") is None


def test_parse_room_line_original_semantics():
    row = db.parse_room_line("https://live.douyin.com/745964462470", "原画")
    assert row["enabled"] == 1
    assert row["platform_code"] == "douyin"
    assert row["quality"] == "原画"

    row = db.parse_room_line("#超清,https://live.bilibili.com/21593109,主播: 测试", "原画")
    assert row["enabled"] == 0
    assert row["quality"] == "超清"
    assert row["custom_name"] == "测试"

    row = db.parse_room_line("https://www.huya.com/116", "高清")
    assert row["quality"] == "高清"

    assert db.parse_room_line("https://unknown.example.com/room/123456", "原画") is None


def test_settings_meta_groups_and_types():
    meta = settings_meta.build_meta("Cookie", "抖音cookie", "abc", 0)
    assert meta["group_code"] == "cookie"
    assert meta["is_secret"] == 1

    meta = settings_meta.build_meta("录制设置", "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频", "ts", 1)
    assert meta["label"] == "视频保存格式"
    assert meta["value_type"] == "enum"
    assert meta["options_json"] == '["ts", "mkv", "flv", "mp4", "mp3音频", "m4a音频"]'


def test_natural_sort():
    names = ["第10集.mp4", "第2集.mp4", "第1集.mp4"]
    assert sorted(names, key=natural_key) == ["第1集.mp4", "第2集.mp4", "第10集.mp4"]


def test_install_ffmpeg_from_zip(tmp_path):
    import zipfile

    from webui.backend import ffmpeg_setup

    archive = tmp_path / "ffmpeg.zip"
    payload = b"MZ" + b"\0" * (1024 * 1024)
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("build/bin/ffmpeg.exe", payload)
        handle.writestr("build/bin/ffprobe.exe", payload)

    dest = ffmpeg_setup.install_from_zip(archive, tmp_path / "ffmpeg")

    assert (dest / "ffmpeg.exe").read_bytes()[:2] == b"MZ"
    assert (dest / "ffprobe.exe").stat().st_size >= ffmpeg_setup.MIN_BINARY_BYTES


def test_version_compare():
    from webui.backend import version_service

    assert version_service.is_newer("v1.2.3", "1.2.2")
    assert not version_service.is_newer("1.2.2", "1.2.2")
    assert not version_service.is_newer(None, "1.2.2")
    assert version_service.is_newer("v2.0", "1.9.9")
