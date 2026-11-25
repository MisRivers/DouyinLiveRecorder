#!/usr/bin/env python3
"""Resolve the version for a beta or stable release.

Beta:  <VERSION>-beta.N, N auto-incremented from existing v<VERSION>-beta.* tags.
Stable: bump the latest stable vX.Y.Z tag, or reuse an existing draft release
        so a Docker-only and a Windows-only command can share one version.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
TAG_PREFIX = "webui-v"
SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


def read_base() -> str:
    try:
        value = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        value = "1.0.0"
    if not SEMVER.match(value):
        raise SystemExit(f"invalid VERSION file: {value!r}")
    return value.lstrip("v")


def git_tags() -> list[str]:
    result = subprocess.run(
        ["git", "tag", "--list", f"{TAG_PREFIX}*"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def tag_version(tag: str) -> str | None:
    if not tag.startswith(TAG_PREFIX):
        return None
    value = tag[len(TAG_PREFIX):]
    return value if SEMVER.match(value) else None


def latest_stable(tags: list[str]) -> str | None:
    versions: list[tuple[int, int, int]] = []
    for tag in tags:
        value = tag_version(tag)
        match = SEMVER.match(value) if value else None
        if match and not match.group(4):
            versions.append((int(match.group(1)), int(match.group(2)), int(match.group(3))))
    return ".".join(map(str, max(versions))) if versions else None


def bump(version: str, part: str) -> str:
    match = SEMVER.match(version)
    if not match:
        raise SystemExit(f"invalid version: {version}")
    major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def beta_number(base: str, tags: list[str]) -> int:
    prefix = f"{TAG_PREFIX}{base}-beta."
    numbers = [
        int(tag[len(prefix):])
        for tag in tags
        if tag.startswith(prefix) and tag[len(prefix):].isdigit()
    ]
    return max(numbers, default=0) + 1


def draft_version(repository: str, token: str) -> str | None:
    if not repository or not token:
        return None
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases?per_page=30",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "DLR-Release/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            releases = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError):
        return None
    for release in releases:
        tag = str(release.get("tag_name") or "")
        value = tag_version(tag)
        match = SEMVER.match(value) if value else None
        if release.get("draft") and match and not match.group(4):
            return value
    return None


def emit(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{key}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", choices=("beta", "release"), required=True)
    parser.add_argument("--bump", choices=("patch", "minor", "major"), default="patch")
    parser.add_argument("--version", default="")
    args = parser.parse_args()

    base = read_base()
    tags = git_tags()
    explicit = args.version.strip().lstrip("v")

    if explicit:
        if not SEMVER.match(explicit):
            raise SystemExit(f"invalid --version: {args.version}")
        version = explicit
        if args.channel == "beta":
            base = explicit.split("-")[0]
        prerelease = bool(SEMVER.match(explicit).group(4))
    elif args.channel == "beta":
        latest = latest_stable(tags)
        if latest and tuple(map(int, base.split(".")[:3])) <= tuple(map(int, latest.split(".")[:3])):
            base = bump(latest, "minor")
        version = f"{base}-beta.{beta_number(base, tags)}"
        prerelease = True
    else:
        existing = draft_version(
            os.environ.get("GITHUB_REPOSITORY", "MisRivers/DouyinLiveRecorder"),
            os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", ""),
        )
        if existing:
            version = existing
        else:
            latest = latest_stable(tags)
            version = bump(latest, args.bump) if latest else base
        base = version
        prerelease = False

    data = {
        "version": version,
        "base": base,
        "channel": args.channel,
        "prerelease": prerelease,
    }
    build_dir = ROOT / "build"
    build_dir.mkdir(exist_ok=True)
    (build_dir / "version.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    emit("version", version)
    emit("base", base)
    emit("prerelease", "true" if prerelease else "false")
    print(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()
