from __future__ import annotations

import logging
import random
import signal
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .. import config, db
from ..services import files_service
from .ffmpeg_recorder import RecordingTask
from .stream_resolver import resolve_stream

log = logging.getLogger("dlr.recorder.worker")


def _logging() -> None:
    if log.handlers:
        return
    config.ensure_dirs()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    file_handler = RotatingFileHandler(
        config.LOG_DIR / "recorder.log", maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    if sys.stderr is not None:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)


class RoomRunner(threading.Thread):
    def __init__(self, engine: "RecorderEngine", room_id: int):
        super().__init__(name=f"room-{room_id}", daemon=True)
        self.engine = engine
        self.room_id = room_id

    def _room(self) -> dict | None:
        with db.connect() as conn:
            row = conn.execute(
                """
                SELECT r.*, p.name AS platform_name
                FROM room r JOIN platform_template p ON p.code=r.platform_code
                WHERE r.id=?
                """,
                (self.room_id,),
            ).fetchone()
        return dict(row) if row else None

    def _sleep(self, seconds: int) -> None:
        if seconds > 0:
            self.engine.stop_event.wait(seconds)

    def run(self) -> None:
        while not self.engine.stop_event.is_set():
            room = self._room()
            if not room or not room["enabled"]:
                db.set_live_state(self.room_id, state="disabled", updated_at=db.now_iso())
                return
            settings = db.get_settings()
            db.set_live_state(
                self.room_id, state="checking", platform_code=room["platform_code"],
                quality=room["quality"], error_code=None, error_message=None,
            )
            try:
                with self.engine.semaphore:
                    info = resolve_stream(room, settings)
            except Exception as exc:
                log.exception("fetch failed room=%s", self.room_id)
                db.set_live_state(
                    self.room_id, state="error", error_code="FETCH_FAILED",
                    error_message=str(exc)[:500],
                )
                self._sleep(15)
                continue
            if not info.get("is_live"):
                db.set_live_state(
                    self.room_id, state="waiting",
                    anchor_name=info.get("anchor_name") or None,
                    title=info.get("title") or None,
                    error_code=None, error_message=None,
                )
                self._sleep(self._interval(settings))
                continue
            db.set_live_state(
                self.room_id, state="live",
                anchor_name=info.get("anchor_name") or None,
                title=info.get("title") or None,
                quality=room["quality"], error_code=None, error_message=None,
            )
            try:
                RecordingTask(room, settings, info, self.engine.stop_event,
                              semaphore=self.engine.semaphore).run()
            except Exception as exc:
                log.exception("record failed room=%s", self.room_id)
                db.set_live_state(
                    self.room_id, state="error", error_code="RECORD_FAILED",
                    error_message=str(exc)[:500],
                )
                self._sleep(15)
                continue
            self._sleep(5 if self.engine.stop_event.is_set() is False else 0)

    def _interval(self, settings: dict) -> int:
        try:
            base = int(settings.get("循环时间(秒)", "300") or 300)
        except ValueError:
            base = 300
        return max(5, base + random.randint(-5, 5))


class RecorderEngine:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.semaphore = threading.Semaphore(3)
        self.running = False
        self._shutdown = False
        self.runners: dict[int, RoomRunner] = {}
        self._lock = threading.Lock()
        self._last_tick = 0.0
        self._last_heartbeat = 0.0

    def start(self) -> None:
        if self.running:
            return
        db.set_meta("recorder_state", "starting")
        settings = db.get_settings()
        try:
            limit = max(1, min(50, int(settings.get("同一时间访问网络的线程数", "3") or 3)))
        except ValueError:
            limit = 3
        self.semaphore = threading.Semaphore(limit)
        self.stop_event = threading.Event()
        self.running = True
        db.ensure_live_rows()
        with db.connect() as conn:
            rooms = conn.execute("SELECT id FROM room WHERE enabled=1 ORDER BY sort_order").fetchall()
        for row in rooms:
            self._ensure_runner(row["id"])
        db.set_meta("recorder_state", "running")
        log.info("recorder started with %s rooms", len(rooms))

    def stop(self) -> None:
        if not self.running:
            db.set_meta("recorder_state", "stopped")
            return
        db.set_meta("recorder_state", "stopping")
        self.stop_event.set()
        with self._lock:
            runners = list(self.runners.values())
            self.runners.clear()
        deadline = time.time() + 25
        for runner in runners:
            runner.join(timeout=max(0.1, deadline - time.time()))
        self.running = False
        db.set_meta("recorder_state", "stopped")
        log.info("recorder stopped")

    def shutdown(self) -> None:
        self._shutdown = True
        try:
            if self.running:
                self.stop()
            else:
                db.set_meta("recorder_state", "stopped")
        except Exception:
            log.exception("recorder shutdown failed")

    def restart(self) -> None:
        self.stop()
        time.sleep(1)
        self.start()

    def _ensure_runner(self, room_id: int) -> None:
        with self._lock:
            runner = self.runners.get(room_id)
            if runner and runner.is_alive():
                return
            if runner:
                self.runners.pop(room_id, None)
            runner = RoomRunner(self, room_id)
            self.runners[room_id] = runner
            runner.start()

    def tick(self) -> None:
        now = time.time()
        if now - self._last_tick < 2:
            return
        self._last_tick = now
        with db.connect() as conn:
            rows = conn.execute("SELECT id FROM room WHERE enabled=1").fetchall()
        enabled_ids = {row["id"] for row in rows}
        for room_id in enabled_ids:
            self._ensure_runner(room_id)
        with self._lock:
            for room_id in list(self.runners):
                runner = self.runners[room_id]
                if not runner.is_alive():
                    self.runners.pop(room_id, None)

    def handle(self, command: dict) -> None:
        name = command["command"]
        log.info("command %s", name)
        try:
            if name == "recorder.start":
                self.start()
            elif name == "recorder.stop":
                self.stop()
            elif name == "recorder.restart":
                self.restart()
            elif name == "room.reload":
                if self.running:
                    self.restart()
            db.finish_command(command["id"])
        except Exception as exc:
            log.exception("command failed %s", name)
            db.finish_command(command["id"], str(exc)[:500])

    def run(self) -> None:
        _logging()
        db.init_db()
        db.fail_orphan_commands()
        self._recover()
        db.set_meta("recorder_state", "stopped")
        while not self._shutdown:
            command = db.claim_command()
            if command:
                self.handle(command)
            if self.running:
                self.tick()
            now = time.time()
            if now - self._last_heartbeat >= 2:
                db.heartbeat()
                self._last_heartbeat = now
            time.sleep(0.5)

    def _recover(self) -> None:
        with db.connect() as conn:
            interrupted = conn.execute(
                "SELECT file_path FROM recording_session "
                "WHERE status='recording' AND file_path LIKE '%.ts'"
            ).fetchall()
            conn.execute(
                "UPDATE recording_session SET status='interrupted', stop_reason='crash', end_at=? "
                "WHERE status='recording'",
                (db.now_iso(),),
            )
            conn.execute(
                "UPDATE live_state SET state=CASE WHEN room_id IN "
                "(SELECT id FROM room WHERE enabled=1) THEN 'checking' ELSE 'disabled' END, "
                "session_id=NULL, updated_at=? WHERE state='recording'",
                (db.now_iso(),),
            )
            conn.commit()
        root = files_service.root()
        rels = []
        for row in interrupted:
            path = row["file_path"]
            if not path:
                continue
            target = Path(path)
            candidates = (
                target.parent.glob(target.name.replace("%03d", "*"))
                if "%03d" in target.name else [target]
            )
            for candidate in candidates:
                if candidate.suffix != ".ts" or not candidate.exists():
                    continue
                try:
                    rels.append(candidate.relative_to(root).as_posix())
                except (ValueError, OSError):
                    continue
        if rels:
            files_service.enqueue_conversion(rels, trigger="recovery")


def run_recorder_worker() -> None:
    db.init_db()
    engine = RecorderEngine()

    def _handle_signal(_signum, _frame):
        engine.shutdown()
        sys.exit(0)

    try:
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)
    except (ValueError, OSError):
        pass
    engine.run()
