from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import threading
import time
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

import httpx

from src.utils import remove_emojis

from .. import config, db, platform_registry
from ..services import files_service, notification_service, schedule_service
from .stream_resolver import resolve_stream, select_source_url

log = logging.getLogger("dlr.recorder")

NAME_BAD = re.compile(r'[\\/:*?"<>|&#,，。~！·\s]+')
QUALITY_ZH = {"OD": "原画", "BD": "蓝光", "UHD": "超清", "HD": "高清", "SD": "标清", "LD": "流畅"}
AUDIO_ONLY = {"maoerfm", "looklive"}
DIRECT_FLV = {"shopee", "huajiao"}
RECONNECT_GRACE_SECONDS = 30
RECONNECT_INTERVAL_SECONDS = 3
OVERSEAS = {
    "tiktok", "sooplive", "pandatv", "winktv", "flextv", "popkontv", "twitch",
    "liveme", "showroom", "chzzk", "shopee", "youtube", "faceit",
}


def _clean_name(text: str, clean_emoji: bool) -> str:
    value = NAME_BAD.sub("_", (text or "").strip()).strip("_")
    value = value.replace("（", "(").replace("）", ")")
    if clean_emoji:
        value = remove_emojis(value, "_").strip("_")
    return value[:80] or "空白昵称"


def _platform_headers(code: str, url: str) -> str | None:
    live_domain = "/".join(url.split("/")[0:3])
    table = {
        "pandatv": "origin:https://www.pandalive.co.kr",
        "winktv": "origin:https://www.winktv.co.kr",
        "popkontv": "origin:https://www.popkontv.com",
        "flextv": "origin:https://www.flextv.co.kr",
        "qiandurebo": "referer:https://qiandurebo.com",
        "17live": "referer:https://17.live/en/live/6302408",
        "langlive": "referer:https://www.lang.live",
        "shopee": f"origin:{live_domain}",
        "blued": "referer:https://app.blued.cn",
    }
    return table.get(code)


def _run_script(command: str, record_name: str, save_file: str, save_type: str,
                split: bool, to_mp4: bool) -> None:
    try:
        tokens = shlex.split(command.strip(), posix=(os.name != "nt"))
        if os.name == "nt":
            tokens = [
                token[1:-1] if len(token) >= 2 and token[0] == token[-1] == '"' else token
                for token in tokens
            ]
        if not tokens:
            return
        if "python" in command:
            params = [
                "--record_name", str(record_name),
                "--save_file_path", str(save_file),
                "--save_type", str(save_type),
                "--split_video_by_time", str(split),
                "--converts_to_mp4", str(to_mp4),
            ]
        else:
            params = [
                str(record_name), str(save_file), str(save_type),
                f"split_video_by_time:{split}",
                f"converts_to_mp4:{to_mp4}",
            ]
        subprocess.Popen([*tokens, *params])
    except Exception as exc:
        log.warning("custom script failed: %s", exc)


class RecordingTask:
    def __init__(self, room: dict, settings: dict, info: dict, stop_event: threading.Event,
                 semaphore: threading.Semaphore | None = None):
        self.room = room
        self.settings = settings
        self.info = info
        self.stop_event = stop_event
        self.semaphore = semaphore
        self.platform_code = room["platform_code"]
        self.room_id = room["id"]
        self.anchor = _clean_name(
            room.get("custom_name") or info.get("anchor_name") or f"room_{room['id']}",
            settings.get("是否去除名称中的表情符号", "是") == "是",
        )
        self.title = _clean_name(
            info.get("title") or "", settings.get("是否去除名称中的表情符号", "是") == "是"
        )
        self.session_id: int | None = None
        self.target_pattern: Path | None = None
        self.outputs: list[Path] = []
        self.stop_reason = "ended"
        self.base_time = datetime.now()
        self.part = 0
        self.save_dir: Path | None = None

    def _context(self, **extra) -> dict:
        context = {
            "主播": self.anchor,
            "平台": self.room.get("platform_name") or self.platform_code,
            "房间地址": self.room.get("url") or "-",
            "画质": self.room.get("quality") or "-",
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        context.update(extra)
        return context

    def _format(self) -> str:
        if self.platform_code in DIRECT_FLV:
            return "flv"
        raw = (self.settings.get("视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频", "ts") or "ts").lower()
        if "m4a" in raw:
            return "m4a"
        if "mp3" in raw:
            return "mp3"
        if raw in ("mkv", "flv", "mp4"):
            return raw
        if self.platform_code in AUDIO_ONLY:
            return "m4a"
        return "ts"

    def _save_dir(self) -> Path:
        base = config.save_path_from_settings(self.settings)
        folder = base / platform_registry.CODE_TO_DIR.get(self.platform_code, self.platform_code)
        if self.settings.get("保存文件夹是否以作者区分", "是") == "是":
            folder /= self.anchor
        now = self.base_time
        if self.settings.get("保存文件夹是否以时间区分", "否") == "是":
            folder /= now.strftime("%Y-%m-%d")
        if self.settings.get("保存文件夹是否以标题区分", "否") == "是" and self.info.get("title"):
            if self.settings.get("保存文件夹是否以时间区分", "否") == "是":
                folder /= f"{self.title}_{self.anchor}"
            else:
                folder /= f"{now.strftime('%Y-%m-%d')}_{self.title}"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _target(self, ext: str, split: bool) -> Path:
        folder = self.save_dir or self._save_dir()
        stamp = self.base_time.strftime("%Y-%m-%d_%H-%M-%S")
        name = self.anchor
        if self.settings.get("保存文件名是否包含标题", "否") == "是" and self.info.get("title"):
            name += f"_{self.title}"
        name += f"_{stamp}"
        if self.part:
            name += f"_p{self.part + 1}"
        if split:
            name += "_%03d"
        return folder / f"{name}.{ext}"

    def _ffmpeg(self) -> str:
        from ..services.recorder_control import ffmpeg_path

        path = ffmpeg_path()
        if not path:
            raise RuntimeError("ffmpeg 未安装")
        return path

    def _build_args(self, url: str, target: Path, ext: str, split: bool, proxy: str | None) -> list[str]:
        code = self.platform_code
        user_agent = ("Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36")
        rw_timeout, analyzeduration, probesize = "15000000", "20000000", "10000000"
        bufsize, max_queue = "8000k", "1024"
        if code in OVERSEAS:
            rw_timeout, analyzeduration, probesize = "50000000", "40000000", "20000000"
            bufsize, max_queue = "15000k", "2048"
        args = [
            self._ffmpeg(), "-y", "-v", "verbose", "-rw_timeout", rw_timeout,
            "-loglevel", "error", "-hide_banner", "-user_agent", user_agent,
            "-protocol_whitelist", "rtmp,crypto,file,http,https,tcp,tls,udp,rtp,httpproxy",
            "-thread_queue_size", "1024", "-analyzeduration", analyzeduration,
            "-probesize", probesize, "-fflags", "+discardcorrupt", "-re", "-i", url,
            "-bufsize", bufsize, "-sn", "-dn", "-reconnect_delay_max", "60",
            "-reconnect_streamed", "-reconnect_at_eof", "-max_muxing_queue_size", max_queue,
            "-correct_ts_overflow", "1", "-avoid_negative_ts", "1",
        ]
        headers = _platform_headers(code, self.room["url"])
        if headers:
            index = args.index("-i")
            args[index:index] = ["-headers", headers]
        if proxy:
            args[1:1] = ["-http_proxy", proxy]
        if ext in ("mp3", "m4a"):
            args.extend(["-map", "0:a"])
            if ext == "mp3":
                args.extend(["-c:a", "libmp3lame", "-ab", "320k"])
            else:
                args.extend(["-c:a", "aac", "-bsf:a", "aac_adtstoasc", "-ab", "320k"])
            if split:
                args.extend(["-f", "segment", "-segment_time", str(self._split_time()),
                             "-reset_timestamps", "1"])
            elif ext == "m4a":
                args.extend(["-movflags", "+faststart"])
        elif ext == "flv":
            args.extend(["-map", "0", "-c:v", "copy", "-c:a", "copy", "-bsf:a", "aac_adtstoasc"])
            self._segment_args(args, split, "flv")
            if not split:
                args.extend(["-f", "flv"])
        elif ext == "mkv":
            args.extend(["-flags", "global_header", "-map", "0", "-c:v", "copy", "-c:a", "copy"])
            self._segment_args(args, split, "matroska")
            if not split:
                args.extend(["-f", "matroska"])
        elif ext == "mp4":
            args.extend(["-map", "0", "-c:v", "copy", "-c:a", "copy"])
            self._segment_args(args, split, "mp4")
            if split:
                args.extend(["-movflags", "+frag_keyframe+empty_moov"])
            else:
                args.extend(["-f", "mp4"])
        else:
            args.extend(["-c:v", "copy", "-c:a", "copy"])
            self._segment_args(args, split, "mpegts")
            if not split:
                args.extend(["-f", "mpegts"])
        args.append(str(target))
        return args

    def _segment_args(self, args: list[str], split: bool, fmt: str) -> None:
        if split:
            args.extend([
                "-f", "segment", "-segment_time", str(self._split_time()),
                "-segment_format", fmt, "-reset_timestamps", "1",
            ])

    def _split_time(self) -> str:
        return str(self.settings.get("视频分段时间(秒)", "1800") or "1800")

    def _update_bytes(self) -> int:
        total = 0
        paths = set(self.outputs)
        if self.target_pattern:
            paths.update(self.target_pattern.parent.glob(
                self.target_pattern.name.replace("%03d", "*")
            ))
        for path in paths:
            try:
                total += path.stat().st_size
            except OSError:
                pass
        if total:
            db.set_live_state(self.room_id, bytes_written=total)
            if self.session_id:
                with db.connect() as conn:
                    conn.execute("UPDATE recording_session SET bytes_written=? WHERE id=?",
                                 (total, self.session_id))
                    conn.commit()
        return total

    def _terminate(self, proc: subprocess.Popen) -> None:
        try:
            if os.name == "nt":
                if proc.stdin:
                    proc.stdin.write(b"q")
                    proc.stdin.close()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            proc.wait(timeout=10)
            return
        except Exception:
            pass
        try:
            if os.name == "nt":
                proc.terminate()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
            return
        except Exception:
            pass
        try:
            if os.name == "nt":
                proc.kill()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass

    def _download_flv(self, url: str, target: Path) -> Path:
        headers = {}
        header = _platform_headers(self.platform_code, self.room["url"])
        if header and ":" in header:
            key, value = header.split(":", 1)
            headers[key] = value
        target.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=None, follow_redirects=True) as client:
            with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                with open(target, "wb") as handle:
                    for chunk in response.iter_bytes(16 * 1024):
                        if self.stop_event.is_set():
                            break
                        handle.write(chunk)
        return target

    def _should_stop(self) -> str | None:
        if self.stop_event.is_set():
            return "stopped"
        with db.connect() as conn:
            row = conn.execute(
                """
                SELECT r.enabled, p.enabled AS platform_enabled
                FROM room r JOIN platform_template p ON p.code=r.platform_code
                WHERE r.id=?
                """,
                (self.room_id,),
            ).fetchone()
            if not row or not row["enabled"]:
                return "disabled"
            if not row["platform_enabled"]:
                return "platform_disabled"
        try:
            if not schedule_service.is_active(self.room_id):
                return "schedule_ended"
        except Exception:
            log.exception("schedule check failed room=%s", self.room_id)
        threshold = float(self.settings.get("录制空间剩余阈值(gb)", "1.0") or 0)
        try:
            root = config.save_path_from_settings(self.settings)
            free = shutil.disk_usage(root).free / (1024 ** 3)
            if free < threshold:
                return "disk_low"
        except OSError:
            pass
        return None

    def run(self) -> dict:
        ext = self._format()
        split = (self.settings.get("分段录制是否开启", "是") == "是"
                 and self.platform_code not in DIRECT_FLV)
        target = self._target(ext, split)
        self.save_dir = target.parent
        self.target_pattern = target
        target.parent.mkdir(parents=True, exist_ok=True)
        with db.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO recording_session
                  (room_id, anchor_name, title, platform_code, quality, file_path,
                   save_dir, status, start_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'recording', ?)
                """,
                (self.room_id, self.anchor, self.info.get("title"), self.platform_code,
                 self.room.get("quality"), str(target), str(target.parent), db.now_iso()),
            )
            self.session_id = int(cur.lastrowid)
            conn.commit()
        db.set_live_state(
            self.room_id, state="recording", anchor_name=self.anchor,
            title=self.info.get("title"), platform_code=self.platform_code,
            quality=self.room.get("quality"), session_id=self.session_id,
            file_path=str(target), bytes_written=0, error_code=None,
            error_message=None, started_at=db.now_iso(),
        )
        with db.connect() as conn:
            conn.execute("UPDATE room SET last_anchor_name=?, updated_at=? WHERE id=?",
                         (self.info.get("anchor_name") or self.anchor, db.now_iso(), self.room_id))
            conn.commit()
        notification_service.emit(
            "recording_started", self.room_id,
            **self._context(标题=self.info.get("title") or "无标题", 文件名=target.name),
        )

        while True:
            if self.part > 0:
                if not self._wait_for_reconnect():
                    break
                target = self._target(ext, split)
                self.target_pattern = target
                target.parent.mkdir(parents=True, exist_ok=True)
                db.set_live_state(
                    self.room_id, state="recording", file_path=str(target),
                    error_code=None, error_message=None,
                )
            self._record_attempt(target, ext, split)
            if not self._should_reconnect():
                break
            self.part += 1

        self._finalize(ext)
        return {"session_id": self.session_id, "reason": self.stop_reason, "files": [str(p) for p in self.outputs]}

    def _record_attempt(self, target: Path, ext: str, split: bool) -> None:
        sub_stop = threading.Event()
        if (self.settings.get("生成时间字幕文件", "否") == "是"
                and not split and ext not in ("mp3", "m4a")):
            threading.Thread(target=self._subtitle_loop, args=(target, sub_stop), daemon=True).start()
        try:
            url = select_source_url(self.room, self.info)
            if self.platform_code in DIRECT_FLV:
                flv_url = self.info.get("flv_url") or url
                self.outputs.append(self._download_flv(flv_url, target))
                self.stop_reason = self._should_stop() or "ended"
            else:
                proxy = self._proxy()
                args = self._build_args(url, target, ext, split, proxy)
                log_path = config.LOG_DIR / f"ffmpeg-{self.session_id}.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(log_path, "ab") as log_file:
                    kwargs = {"stdin": subprocess.PIPE, "stdout": subprocess.DEVNULL, "stderr": log_file}
                    if os.name == "nt":
                        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                        startup = subprocess.STARTUPINFO()
                        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        kwargs["startupinfo"] = startup
                    else:
                        kwargs["start_new_session"] = True
                    proc = subprocess.Popen(args, **kwargs)
                    with db.connect() as conn:
                        conn.execute("UPDATE recording_session SET ffmpeg_pid=? WHERE id=?",
                                     (proc.pid, self.session_id))
                        conn.commit()
                    exit_code = None
                    while proc.poll() is None:
                        reason = self._should_stop()
                        if reason:
                            self.stop_reason = reason
                            self._terminate(proc)
                            break
                        self._update_bytes()
                        time.sleep(1)
                    exit_code = proc.poll()
                    if exit_code is None:
                        exit_code = proc.wait()
                if exit_code not in (0, None) and self.stop_reason == "ended":
                    self.stop_reason = "error"
        except Exception as exc:
            log.exception("recording failed for room %s: %s", self.room_id, exc)
            self.stop_reason = "error"
            db.set_live_state(self.room_id, error_code="RECORD_FAILED", error_message=str(exc)[:500])
        finally:
            sub_stop.set()
            self._collect_outputs(target)

    def _collect_outputs(self, target: Path) -> None:
        known = {path.resolve() for path in self.outputs}
        for path in sorted(target.parent.glob(target.name.replace("%03d", "*"))):
            if path.resolve() not in known:
                self.outputs.append(path)
                known.add(path.resolve())

    def _should_reconnect(self) -> bool:
        return self.stop_reason in ("ended", "error") and not self.stop_event.is_set()

    def _wait_for_reconnect(self) -> bool:
        deadline = time.time() + RECONNECT_GRACE_SECONDS
        log.warning("room %s stream interrupted, waiting up to %ss for reconnect",
                    self.room_id, RECONNECT_GRACE_SECONDS)
        db.set_live_state(
            self.room_id, state="recording", error_code="RECONNECTING",
            error_message="直播信号中断，正在重连…",
        )
        while time.time() < deadline:
            if self.stop_event.is_set():
                self.stop_reason = "stopped"
                return False
            with db.connect() as conn:
                row = conn.execute("SELECT * FROM room WHERE id=?", (self.room_id,)).fetchone()
            if not row or not row["enabled"]:
                self.stop_reason = "disabled"
                return False
            self.room = dict(row)
            reason = self._should_stop()
            if reason:
                self.stop_reason = reason
                return False
            try:
                context = self.semaphore if self.semaphore is not None else nullcontext()
                with context:
                    info = resolve_stream(self.room, self.settings)
            except Exception as exc:
                log.warning("room %s reconnect probe failed: %s", self.room_id, exc)
                self.stop_event.wait(RECONNECT_INTERVAL_SECONDS)
                continue
            if info.get("is_live"):
                self.info = info
                self.title = _clean_name(
                    info.get("title") or "",
                    self.settings.get("是否去除名称中的表情符号", "是") == "是",
                )
                self.stop_reason = "ended"
                db.set_live_state(
                    self.room_id, state="recording", anchor_name=self.anchor,
                    title=info.get("title"), error_code=None, error_message=None,
                )
                log.info("room %s reconnected within %ss", self.room_id, RECONNECT_GRACE_SECONDS)
                return True
            self.stop_event.wait(RECONNECT_INTERVAL_SECONDS)
        self.stop_reason = "ended"
        return False

    def _proxy(self) -> str | None:
        from .stream_resolver import _proxy

        return _proxy(self.room, self.settings)

    def _subtitle_loop(self, target: Path, stop: threading.Event) -> None:
        path = target.with_suffix(".srt")
        index = 0

        def stamp(seconds: int) -> str:
            hours, rest = divmod(seconds, 3600)
            minutes, secs = divmod(rest, 60)
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"

        while not stop.is_set():
            index += 1
            start = index - 1
            text = (f"{index}\n{stamp(start)},000 --> {stamp(index)},000\n"
                    f"{datetime.now():%Y-%m-%d %H:%M:%S}\n\n")
            try:
                with open(path, "a", encoding="utf-8-sig") as handle:
                    handle.write(text)
            except OSError:
                return
            stop.wait(1)

    def _finalize(self, ext: str) -> None:
        self._update_bytes()
        completed_reasons = ("ended", "disabled", "stopped", "platform_disabled", "schedule_ended")
        status = "completed" if self.stop_reason in completed_reasons else "failed"
        if self.stop_reason == "error":
            status = "failed"
        end_at = db.now_iso()
        output_path = self.outputs[0] if self.outputs else self.target_pattern
        total_bytes = sum(p.stat().st_size for p in self.outputs if p.exists())
        with db.connect() as conn:
            conn.execute(
                """
                UPDATE recording_session
                SET status=?, stop_reason=?, end_at=?, file_path=?, bytes_written=?
                WHERE id=?
                """,
                (status, self.stop_reason, end_at,
                 str(output_path), total_bytes, self.session_id),
            )
            conn.commit()
        state = "checking"
        if self.stop_reason == "disabled":
            state = "disabled"
        elif self.stop_reason == "platform_disabled":
            state = "platform_disabled"
        elif self.stop_reason == "schedule_ended":
            state = "scheduled"
        db.set_live_state(
            self.room_id, state=state, session_id=None,
            file_path=str(self.outputs[0]) if self.outputs else None,
            error_code=None if status == "completed" else "RECORD_FAILED",
            error_message=None if status == "completed" else self.stop_reason,
        )
        reason_text = {
            "ended": "直播结束", "disabled": "房间已停用", "stopped": "手动停止",
            "error": "录制异常", "disk_low": "磁盘空间不足",
            "platform_disabled": "平台已禁用", "schedule_ended": "计划时段结束",
        }.get(self.stop_reason, self.stop_reason)
        duration_seconds = max(0, int((datetime.now() - self.base_time).total_seconds()))
        notification_service.emit(
            "recording_finished", self.room_id,
            **self._context(
                文件名=output_path.name if output_path else "-",
                时长=notification_service.context_duration(duration_seconds),
                文件大小=notification_service.context_size(total_bytes),
                结束原因=reason_text,
            ),
        )
        if status == "failed":
            notification_service.emit(
                "recording_error", self.room_id,
                **self._context(错误原因=f"录制失败：{reason_text}"),
            )
        if ext == "ts":
            root = config.save_path_from_settings(self.settings)
            rels = []
            for path in self.outputs:
                if path.suffix != ".ts":
                    continue
                try:
                    rels.append(path.relative_to(root).as_posix())
                except ValueError:
                    continue
            if rels:
                files_service.enqueue_conversion(rels, trigger=self.stop_reason)
        if (self.settings.get("是否录制完成后执行自定义脚本", "否") == "是"
                and self.settings.get("自定义脚本执行命令")):
            _run_script(
                self.settings.get("自定义脚本执行命令", ""), self.anchor,
                str(self.outputs[0]) if self.outputs else "",
                ext.upper(), self.settings.get("分段录制是否开启", "是") == "是",
                self.settings.get("录制完成后自动转为mp4格式", "是") == "是",
            )
