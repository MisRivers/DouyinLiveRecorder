from __future__ import annotations

import asyncio
import logging
import multiprocessing
import os
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, version_service
from .errors import ApiError, api_error_handler, validation_error_handler
from .routers import auth, automation, files, live, recorder, rooms, settings, system, ws
from .services import files_service

log = logging.getLogger("dlr.api")


def _configure_logging() -> None:
    if log.handlers:
        return
    config.ensure_dirs()
    handler = RotatingFileHandler(
        config.LOG_DIR / "webui.log", maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)
    if sys.stderr is not None and not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in root.handlers
    ):
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        root.addHandler(stream)


def _start_workers() -> list[multiprocessing.Process]:
    if os.environ.get("DLR_DISABLE_WORKERS") == "1":
        return []
    from .workers.converter_worker import run_converter_worker
    from .workers.recorder_worker import run_recorder_worker

    context = multiprocessing.get_context("spawn")
    processes = []
    for target, name in ((run_recorder_worker, "recorder"), (run_converter_worker, "converter")):
        process = context.Process(target=target, name=name, daemon=True)
        process.start()
        log.info("started %s worker pid=%s", name, process.pid)
        processes.append(process)
    return processes


def _supervise(processes: list[multiprocessing.Process], stop: threading.Event) -> None:
    from .workers.converter_worker import run_converter_worker
    from .workers.recorder_worker import run_recorder_worker

    targets = {"recorder": run_recorder_worker, "converter": run_converter_worker}
    context = multiprocessing.get_context("spawn")
    while not stop.wait(5):
        for process in list(processes):
            if process.is_alive():
                continue
            name = process.name or "worker"
            if name not in targets:
                continue
            replacement = context.Process(target=targets[name], name=name, daemon=True)
            replacement.start()
            processes.remove(process)
            processes.append(replacement)
            log.warning("restarted %s worker pid=%s", name, replacement.pid)


def _index_loop(stop: threading.Event) -> None:
    try:
        files_service.scan_index()
    except Exception as exc:
        log.warning("initial file scan failed: %s", exc)
    while not stop.wait(30):
        try:
            files_service.scan_index()
        except Exception as exc:
            log.warning("file scan failed: %s", exc)


def _graceful_stop() -> None:
    """通知录制 Worker 优雅停止，给 FFmpeg 留出封装收尾时间。"""
    try:
        if db.recorder_state()["state"] != "stopped":
            db.enqueue_command("recorder.stop", {"mode": "graceful"})
            deadline = time.time() + 25
            while time.time() < deadline:
                if db.recorder_state()["state"] == "stopped":
                    break
                time.sleep(0.5)
    except Exception as exc:
        log.warning("graceful recorder stop failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    db.init_db()
    stop = threading.Event()
    scan_thread = threading.Thread(target=_index_loop, args=(stop,), name="file-indexer", daemon=True)
    scan_thread.start()
    processes = _start_workers()
    supervisor = threading.Thread(target=_supervise, args=(processes, stop), name="worker-supervisor",
                                  daemon=True)
    if processes:
        supervisor.start()
    log.info("DouyinLiveRecorder Web UI started")
    try:
        yield
    finally:
        stop.set()
        if processes:
            _graceful_stop()
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
        log.info("DouyinLiveRecorder Web UI stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="DouyinLiveRecorder Web UI",
        version=version_service.current_version(),
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:16]
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(auth.router)
    app.include_router(recorder.router)
    app.include_router(rooms.router)
    app.include_router(rooms.platform_router)
    app.include_router(settings.router)
    app.include_router(automation.router)
    app.include_router(live.router)
    app.include_router(files.router)
    app.include_router(system.router)
    app.include_router(ws.router)

    dist = config.FRONTEND_DIST
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND",
                                                                    "message": "接口不存在"}})
        index = dist / "index.html"
        if index.exists():
            response = FileResponse(index)
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return response
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "FRONTEND_NOT_BUILT",
                               "message": "前端尚未构建，请先执行 npm run build"}},
        )

    return app


app = create_app()
