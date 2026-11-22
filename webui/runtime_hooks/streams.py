"""Windowed frozen apps may have sys.stdout/sys.stderr set to None.

This hook runs in every PyInstaller process, including multiprocessing spawn
workers, before application imports. Upstream loguru logging writes to stderr,
so provide a safe fallback instead of crashing.
"""
import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
    sys._dlr_stream_fallback = True
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
    sys._dlr_stream_fallback = True
