"""Desktop launcher used by the Windows executable.

The window stays open while the service runs. Closing the window asks whether
to keep running in the background (minimize to taskbar) or shut down. A
graceful shutdown first stops active recordings and lets them finalize.
"""
from __future__ import annotations

import asyncio
import logging
import multiprocessing
import os
import queue
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from logging.handlers import RotatingFileHandler

from . import ffmpeg_setup


def _redirect_streams() -> None:
    from webui.backend import config

    config.ensure_dirs()
    fallback = getattr(sys, "_dlr_stream_fallback", False)
    if sys.stdout is None or fallback:
        sys.stdout = open(config.LOG_DIR / "desktop-stdout.log", "a", encoding="utf-8", buffering=1)
    if sys.stderr is None or fallback:
        sys.stderr = open(config.LOG_DIR / "desktop-stderr.log", "a", encoding="utf-8", buffering=1)


def _configure_logging() -> None:
    from webui.backend import config

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        handler = RotatingFileHandler(
            config.LOG_DIR / "webui.log", maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
    if sys.stderr is not None and not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in root.handlers
    ):
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)


def _lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class DesktopApp:
    def __init__(self, root, app, config, db, no_browser: bool = False) -> None:
        import tkinter as tk

        self.tk = tk
        self.root = root
        self.app = app
        self.config = config
        self.db = db
        self.no_browser = no_browser
        self.server = None
        self.server_thread = None
        self.shutting_down = False
        self.url = f"http://127.0.0.1:{config.PORT}"
        self._ffmpeg_dialog = None
        self._ffmpeg_queue: queue.Queue = queue.Queue()

        root.title("DouyinLiveRecorder UI")
        root.geometry("460x330")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build_ui()
        self._start_server()
        self._update_status()
        self.root.after(800, self._maybe_prompt_ffmpeg)
        if not no_browser:
            threading.Thread(target=self._open_browser_when_ready, daemon=True).start()

    def _build_ui(self) -> None:
        tk = self.tk
        frame = tk.Frame(self.root, padx=20, pady=18)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="DouyinLiveRecorder", font=("Microsoft YaHei UI", 16, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(frame, text="Web 管理端正在本机运行", fg="#64748b", anchor="w").pack(fill="x", pady=(2, 14))

        card = tk.Frame(frame, bg="#f1f5f9", padx=14, pady=12)
        card.pack(fill="x")
        self.status_var = tk.StringVar(value="正在启动服务…")
        tk.Label(card, textvariable=self.status_var, bg="#f1f5f9", fg="#0f172a",
                 font=("Microsoft YaHei UI", 11, "bold"), anchor="w").pack(fill="x")
        tk.Label(card, text=f"本机访问：{self.url}", bg="#f1f5f9", fg="#475569",
                 anchor="w").pack(fill="x", pady=(6, 0))
        tk.Label(card, text=f"局域网访问：http://{_lan_ip()}:{self.config.PORT}", bg="#f1f5f9",
                 fg="#475569", anchor="w").pack(fill="x")

        actions = tk.Frame(frame, pady=16)
        actions.pack(fill="x")
        tk.Button(actions, text="打开管理页面", bg="#2563eb", fg="white", relief="flat",
                  activebackground="#1d4ed8", activeforeground="white", padx=14, pady=6,
                  command=self.open_browser).pack(side="left")
        tk.Button(actions, text="最小化到后台", relief="flat", padx=12, pady=6,
                  command=self.background).pack(side="left", padx=(8, 0))
        tk.Button(actions, text="退出程序", relief="flat", padx=12, pady=6,
                  command=self.on_close).pack(side="right")

        tk.Label(frame, text="关闭窗口时会询问：后台继续运行，或停止录制并退出。",
                 fg="#94a3b8", anchor="w").pack(fill="x", pady=(4, 0))

    def _ffmpeg_ready(self) -> bool:
        from .services import recorder_control

        return (
            ffmpeg_setup.is_installed(self.config.ROOT_DIR)
            or bool(recorder_control.ffmpeg_path())
        )

    def _maybe_prompt_ffmpeg(self) -> None:
        if sys.platform != "win32":
            return
        if not self._ffmpeg_ready():
            self._show_ffmpeg_dialog()

    def _show_ffmpeg_dialog(self) -> None:
        from tkinter import messagebox, ttk

        if self._ffmpeg_dialog is not None and self._ffmpeg_dialog.winfo_exists():
            self._ffmpeg_dialog.lift()
            return
        if sys.platform != "win32":
            messagebox.showinfo(
                "安装 FFmpeg",
                "请安装 FFmpeg 并加入系统 PATH。\n" + ffmpeg_setup.OFFICIAL_URL,
            )
            return
        tk = self.tk
        win = tk.Toplevel(self.root)
        win.title("安装 FFmpeg")
        win.geometry("560x330")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        self._ffmpeg_dialog = win

        frame = tk.Frame(win, padx=22, pady=18)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="缺少 FFmpeg", font=("Microsoft YaHei UI", 14, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(
            frame,
            text="FFmpeg 用于拉流与转码，首次使用需要安装。\n"
                 "可自动下载 Windows 64 位版本（约 80 MB），或手动下载后放入 ffmpeg 文件夹。",
            fg="#475569", justify="left", anchor="w", wraplength=500,
        ).pack(fill="x", pady=(6, 10))
        status_var = tk.StringVar(value="尚未检测到 FFmpeg")
        tk.Label(frame, textvariable=status_var, fg="#2563eb", anchor="w").pack(fill="x")
        progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        progress.pack(fill="x", pady=(6, 12))

        actions = tk.Frame(frame)
        actions.pack(fill="x")
        start_btn = tk.Button(
            actions, text="自动下载并安装", bg="#2563eb", fg="white", relief="flat",
            activebackground="#1d4ed8", activeforeground="white", padx=14, pady=6,
            command=lambda: self._start_ffmpeg_download(
                win, start_btn, manual_btn, status_var, progress
            ),
        )
        start_btn.pack(side="left")
        manual_btn = tk.Button(
            actions, text="手动下载", relief="flat", padx=12, pady=6,
            command=lambda: self._open_ffmpeg_manual(status_var),
        )
        manual_btn.pack(side="left", padx=(8, 0))
        tk.Button(actions, text="稍后", relief="flat", padx=12, pady=6,
                  command=self._close_ffmpeg_dialog).pack(side="right")
        tk.Label(frame, text="下载源：gyan.dev / BtbN FFmpeg-Builds（HTTPS）",
                 fg="#94a3b8", anchor="w").pack(fill="x", pady=(12, 0))
        win.protocol("WM_DELETE_WINDOW", self._close_ffmpeg_dialog)

    def _start_ffmpeg_download(self, win, start_btn, manual_btn, status_var, progress) -> None:
        start_btn.config(state="disabled")
        manual_btn.config(state="disabled")
        progress.config(mode="determinate", value=0)
        status_var.set("正在下载 FFmpeg…")
        self._ffmpeg_queue = queue.Queue()
        threading.Thread(target=self._ffmpeg_worker, daemon=True).start()
        self.root.after(
            100,
            lambda: self._poll_ffmpeg_download(
                win, start_btn, manual_btn, status_var, progress
            ),
        )

    def _ffmpeg_worker(self) -> None:
        try:
            dest = ffmpeg_setup.download_and_install(
                self.config.ROOT_DIR, self._ffmpeg_progress
            )
            self._ffmpeg_queue.put(("done", str(dest)))
        except Exception as exc:
            self._ffmpeg_queue.put(("error", str(exc)))

    def _ffmpeg_progress(self, downloaded: int, total: int, label: str) -> None:
        self._ffmpeg_queue.put(("progress", downloaded, total, label))

    def _poll_ffmpeg_download(self, win, start_btn, manual_btn, status_var,
                              progress) -> None:
        from tkinter import messagebox

        finished = False
        error = None
        try:
            while True:
                item = self._ffmpeg_queue.get_nowait()
                if item[0] == "progress":
                    _, done, total, label = item
                    if total > 0:
                        progress.config(value=min(99, int(done * 100 / total)))
                        status_var.set(
                            f"正在从 {label} 下载… "
                            f"{done / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB"
                        )
                    else:
                        status_var.set(
                            f"正在从 {label} 下载… {done / 1024 / 1024:.1f} MB"
                        )
                elif item[0] == "done":
                    finished = True
                elif item[0] == "error":
                    error = item[1]
        except queue.Empty:
            pass
        if not win.winfo_exists():
            return
        if error:
            status_var.set(f"自动下载失败：{error}")
            start_btn.config(state="normal")
            manual_btn.config(state="normal")
            return
        if finished:
            progress.config(value=100)
            status_var.set("安装完成，FFmpeg 已就绪")
            self._update_status()
            self.root.after(
                600,
                lambda: (
                    self._close_ffmpeg_dialog(),
                    messagebox.showinfo(
                        "FFmpeg 安装完成",
                        "FFmpeg 已安装到程序目录的 ffmpeg 文件夹。",
                    ),
                ),
            )
            return
        self.root.after(
            150,
            lambda: self._poll_ffmpeg_download(
                win, start_btn, manual_btn, status_var, progress
            ),
        )

    def _open_ffmpeg_manual(self, status_var) -> None:
        try:
            webbrowser.open(ffmpeg_setup.MANUAL_URL)
        except Exception:
            pass
        status_var.set(
            "已打开下载页面；解压后把 bin 目录中的 ffmpeg.exe 与 ffprobe.exe "
            "放入程序目录的 ffmpeg 文件夹。"
        )

    def _close_ffmpeg_dialog(self) -> None:
        if self._ffmpeg_dialog is not None:
            try:
                self._ffmpeg_dialog.destroy()
            except Exception:
                pass
            self._ffmpeg_dialog = None

    def _start_server(self) -> None:
        import uvicorn

        config = uvicorn.Config(self.app, host=self.config.HOST, port=self.config.PORT,
                                log_config=None, access_log=False)
        self.server = uvicorn.Server(config)

        def run() -> None:
            try:
                asyncio.run(self.server.serve())
            except Exception:
                logging.getLogger("dlr.desktop").exception("web server failed")

        self.server_thread = threading.Thread(target=run, name="uvicorn", daemon=True)
        self.server_thread.start()

    def _open_browser_when_ready(self) -> None:
        for _ in range(40):
            try:
                urllib.request.urlopen(f"{self.url}/api/system/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        self.open_browser()

    def open_browser(self) -> None:
        try:
            webbrowser.open(self.url)
        except Exception:
            pass

    def _update_status(self) -> None:
        if self.shutting_down:
            return
        try:
            state = self.db.recorder_state()["state"]
            with self.db.connect() as conn:
                recording = conn.execute(
                    "SELECT COUNT(*) AS c FROM live_state WHERE state='recording'"
                ).fetchone()["c"]
                pending = conn.execute(
                    "SELECT COUNT(*) AS c FROM conversion_job WHERE status IN ('pending','running')"
                ).fetchone()["c"]
            labels = {
                "stopped": "录制未启动", "starting": "录制启动中", "running": "录制运行中",
                "stopping": "录制停止中", "error": "录制异常",
            }
            text = labels.get(state, state)
            text += f" · 正在录制 {recording} 个"
            if pending:
                text += f" · 转码队列 {pending} 个"
            self.status_var.set(text)
        except Exception:
            self.status_var.set("服务运行中")
        self.root.after(2000, self._update_status)

    def _ask_close_action(self) -> str:
        tk = self.tk
        dialog = tk.Toplevel(self.root)
        dialog.title("关闭 DouyinLiveRecorder")
        dialog.geometry("440x190")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        result = {"value": "cancel"}
        tk.Label(dialog, text="要如何处理正在运行的服务？", font=("Microsoft YaHei UI", 11, "bold"),
                 anchor="w").pack(fill="x", padx=20, pady=(18, 6))
        tk.Label(dialog, text="后台继续运行会最小化到任务栏；关闭程序会先停止录制并尽量完成收尾。",
                 fg="#64748b", wraplength=390, justify="left", anchor="w").pack(fill="x", padx=20)

        def choose(value: str) -> None:
            result["value"] = value
            dialog.destroy()

        buttons = tk.Frame(dialog, pady=18)
        buttons.pack(fill="x", padx=20)
        tk.Button(buttons, text="后台继续运行", bg="#2563eb", fg="white", relief="flat",
                  activebackground="#1d4ed8", activeforeground="white", padx=12, pady=6,
                  command=lambda: choose("background")).pack(side="left")
        tk.Button(buttons, text="关闭程序", fg="#dc2626", relief="flat", padx=12, pady=6,
                  command=lambda: choose("close")).pack(side="left", padx=(8, 0))
        tk.Button(buttons, text="取消", relief="flat", padx=12, pady=6,
                  command=lambda: choose("cancel")).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.root.wait_window(dialog)
        return result["value"]

    def background(self) -> None:
        self.status_var.set("已最小化到任务栏，服务继续运行")
        self.root.iconify()

    def on_close(self) -> None:
        if self.shutting_down:
            return
        action = self._ask_close_action()
        if action == "background":
            self.background()
        elif action == "close":
            self.shutdown()

    def shutdown(self) -> None:
        if self.shutting_down:
            return
        self.shutting_down = True
        self.status_var.set("正在停止录制并收尾…")
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        try:
            if self.db.recorder_state()["state"] != "stopped":
                self.db.enqueue_command("recorder.stop", {"mode": "graceful"})
                deadline = time.time() + 20
                while time.time() < deadline:
                    if self.db.recorder_state()["state"] == "stopped":
                        break
                    self.status_var.set("正在等待录制文件收尾…")
                    self.root.update()
                    time.sleep(0.3)
            deadline = time.time() + 10
            while time.time() < deadline:
                with self.db.connect() as conn:
                    pending = conn.execute(
                        "SELECT COUNT(*) AS c FROM conversion_job WHERE status IN ('pending','running')"
                    ).fetchone()["c"]
                if not pending:
                    break
                self.status_var.set("正在等待转码任务收尾…")
                self.root.update()
                time.sleep(0.3)
        except Exception:
            logging.getLogger("dlr.desktop").exception("graceful shutdown failed")
        if self.server:
            self.server.should_exit = True
        if self.server_thread:
            self.server_thread.join(timeout=5)
        try:
            self.root.destroy()
        except Exception:
            pass


def main() -> None:
    multiprocessing.freeze_support()
    _redirect_streams()
    _configure_logging()
    from webui.backend import config, db

    # 上游取流代码使用相对路径（config/、cookies 等），统一以程序目录为工作目录
    try:
        os.chdir(config.ROOT_DIR)
    except OSError:
        pass
    db.init_db()
    if "--headless" in sys.argv or os.environ.get("DLR_DESKTOP_HEADLESS") == "1":
        import uvicorn

        from webui.backend.main import app

        uvicorn.run(app, host=config.HOST, port=config.PORT,
                    log_level=os.environ.get("DLR_LOG_LEVEL", "info"))
        return
    try:
        import tkinter as tk

        root = tk.Tk()
    except Exception:
        import uvicorn
        from webui.backend.main import app

        uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
        return

    from webui.backend.main import app

    DesktopApp(root, app, config, db, no_browser="--no-browser" in sys.argv)
    root.mainloop()


if __name__ == "__main__":
    main()
