from __future__ import annotations

import multiprocessing
import os
import sys
import time
import webbrowser

import uvicorn

from webui.backend import config
from webui.backend.main import app


def main() -> None:
    multiprocessing.freeze_support()
    if "--no-browser" not in sys.argv:
        def open_browser() -> None:
            time.sleep(1.5)
            try:
                webbrowser.open(f"http://127.0.0.1:{config.PORT}")
            except Exception:
                pass

        import threading

        threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level=os.environ.get("DLR_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
