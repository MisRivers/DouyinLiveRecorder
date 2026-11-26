#!/usr/bin/env python3
"""Enforce one build-content standard for Docker and Windows artifacts.

Run locally and in CI before every release. It fails when runtime secrets or
state (config/data/downloads/logs) can leak into an image or EXE.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "VERSION",
    "run_webui.py",
    "reset_account.py",
    "requirements.txt",
    "webui/requirements.txt",
    "webui/Dockerfile",
    "webui/docker-entrypoint.sh",
    "webui/backend/main.py",
    "webui/backend/schema.sql",
    "webui/frontend/package.json",
    "webui/webui.spec",
    "webui/build_exe.py",
]

DOCKERIGNORE = {
    ".git",
    ".venv",
    "config",
    "data",
    "downloads",
    "logs",
    "docs",
    ".aoci",
    "ffmpeg",
    "dist",
    "node_modules",
    "webui/frontend/node_modules",
    "webui/frontend/dist",
}

GITIGNORE = {
    "config/",
    "data/",
    "downloads/",
    "logs/",
    "ffmpeg/",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def read(path: str) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"cannot read {path}: {exc}")


def dockerignore_entries() -> set[str]:
    entries = set()
    for line in read(".dockerignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            entries.add(line.rstrip("/"))
    return entries


def check_dockerfile() -> None:
    text = read("webui/Dockerfile")
    if re.search(r"^\s*COPY\s+\.\s+/app\s*$", text, re.M):
        fail("webui/Dockerfile must not COPY the whole repository into /app")
    if re.search(r"^\s*COPY\s+\.\s+\.\s*$", text, re.M):
        fail("webui/Dockerfile must not COPY the whole repository")
    if "ARG APP_VERSION" not in text or "/app/VERSION" not in text:
        fail("webui/Dockerfile must bake the release version into /app/VERSION")
    for needed in ("requirements.txt", "run_webui.py", "src"):
        if needed not in text:
            fail(f"webui/Dockerfile does not copy required runtime path: {needed}")
    for forbidden in ("config", "downloads", "logs", "data"):
        if re.search(rf"^\s*COPY\s+.*\b{forbidden}\b", text, re.M):
            fail(f"webui/Dockerfile copies runtime directory: {forbidden}")


def check_ignore_files() -> None:
    docker = dockerignore_entries()
    missing = sorted(DOCKERIGNORE - docker)
    if missing:
        fail(f".dockerignore is missing: {', '.join(missing)}")
    gitignore = read(".gitignore")
    for entry in GITIGNORE:
        if entry not in gitignore:
            fail(f".gitignore is missing runtime pattern: {entry}")


def check_spec() -> None:
    text = read("webui/webui.spec")
    for path in ("config", "data", "downloads", "logs"):
        if re.search(rf"ROOT\s*/\s*\"{path}\"", text):
            fail(f"webui/webui.spec bundles runtime directory: {path}")
    if re.search(r"ROOT\s*/\s*\"config\"\s*/\s*\"config\.ini\"", text):
        fail("webui/webui.spec bundles config/config.ini")


def check_version_plumbing() -> None:
    service = read("webui/backend/version_service.py")
    if '"VERSION"' not in service:
        fail("version_service.py does not read the VERSION file")
    builder = read("webui/build_exe.py")
    if "--version" not in builder or '"VERSION"' not in builder:
        fail("build_exe.py must accept --version and write VERSION into the bundle")


def check_git_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "config", "data", "downloads", "logs"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    tracked = [line for line in result.stdout.splitlines() if line.strip()]
    if tracked:
        fail(f"runtime files are tracked by git: {', '.join(tracked[:10])}")


def main() -> None:
    for path in REQUIRED:
        if not (ROOT / path).exists():
            fail(f"required build file is missing: {path}")
    check_dockerfile()
    check_ignore_files()
    check_spec()
    check_version_plumbing()
    if (ROOT / ".git").exists():
        check_git_tracked()
    print("build files check passed: Docker/Windows include only runtime files")


if __name__ == "__main__":
    main()
