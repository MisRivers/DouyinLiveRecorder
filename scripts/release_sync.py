#!/usr/bin/env python3
"""Create/update a GitHub Release for a Docker or Windows build.

Stable releases are created as drafts. A draft is published only after both
`docker-info.json` and `windows-info.json` are attached, so `release docker`
and `release windows` can run as two separate commands and still form one
complete release.

Beta Windows builds update one rolling pre-release per base version:
    tag: v<base>-beta
    asset: DouyinLiveRecorderUI-windows-x64-beta.zip
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG_PREFIX = "webui-v"


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    token = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN", "")
    if token:
        env["GH_TOKEN"] = token
    result = subprocess.run(
        ["gh", *args], cwd=ROOT, capture_output=True, text=True, env=env
    )
    if check and result.returncode != 0:
        raise SystemExit(f"gh {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result


def view(tag: str) -> dict | None:
    result = gh("release", "view", tag, "--json", "isDraft,assets,url", check=False)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def ensure(tag: str, title: str, notes: str, *, draft: bool, prerelease: bool) -> dict:
    existing = view(tag)
    if existing:
        edit = ["release", "edit", tag, "--notes", notes]
        if prerelease:
            edit.append("--prerelease")
        gh(*edit)
        return existing
    create = ["release", "create", tag, "--title", title, "--notes", notes]
    if draft:
        create.append("--draft")
    if prerelease:
        create.append("--prerelease")
    result = gh(*create, check=False)
    if result.returncode != 0:
        existing = view(tag)
        if existing:
            return existing
        raise SystemExit(result.stderr.strip())
    current = view(tag)
    if not current:
        raise SystemExit(f"release {tag} was created but cannot be read")
    return current


def upload(tag: str, path: Path, name: str | None = None) -> None:
    source = path
    temporary: tempfile.TemporaryDirectory | None = None
    if name and name != path.name:
        temporary = tempfile.TemporaryDirectory()
        source = Path(temporary.name) / name
        source.write_bytes(path.read_bytes())
    try:
        gh("release", "upload", tag, str(source), "--clobber")
    finally:
        if temporary:
            temporary.cleanup()


def publish_when_complete(tag: str) -> bool:
    current = view(tag)
    if not current:
        return False
    names = {str(item.get("name") or "") for item in current.get("assets", [])}
    if "docker-info.json" not in names or "windows-info.json" not in names:
        return False
    if current.get("isDraft"):
        gh("release", "edit", tag, "--draft=false")
        gh("release", "edit", tag, "--latest")
    return True


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", choices=("beta", "stable"), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--zip", default="")
    parser.add_argument("--digest", default="")
    parser.add_argument("--tags", default="")
    parser.add_argument("--commit", default="")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    commit = args.commit[:12] if args.commit else ""
    if args.channel == "beta":
        tag = f"{TAG_PREFIX}{args.base}-beta"
        title = f"v{args.base} Beta"
        notes = args.notes or (
            f"## v{args.version}\n\n"
            f"- Channel: beta\n"
            f"- Commit: `{commit}`\n"
            f"- Windows: `DouyinLiveRecorderUI-windows-x64-beta.zip`\n"
        )
        ensure(tag, title, notes, draft=False, prerelease=True)
        if args.zip:
            zip_path = Path(args.zip)
            upload(tag, zip_path, "DouyinLiveRecorderUI-windows-x64-beta.zip")
            info = {
                "version": args.version,
                "base": args.base,
                "channel": "beta",
                "commit": commit,
                "zip_sha256": sha256(zip_path),
                "built_at": now(),
            }
            with tempfile.TemporaryDirectory() as temp:
                info_path = Path(temp) / "beta-info.json"
                info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
                upload(tag, info_path)
                sums_path = Path(temp) / "sha256sums-beta.txt"
                sums_path.write_text(f"{sha256(zip_path)}  DouyinLiveRecorderUI-windows-x64-beta.zip\n",
                                     encoding="utf-8")
                upload(tag, sums_path)
        print(f"beta release: {tag}")
        return

    tag = f"{TAG_PREFIX}{args.version}"
    notes = args.notes or (
        f"## v{args.version}\n\n"
        f"- Channel: stable\n"
        f"- Commit: `{commit}`\n"
        f"- Docker: `misrivers/dlr-webui:{args.version}` and `latest`\n"
        f"- Windows: `DouyinLiveRecorderUI-{args.version}-windows-x64.zip`\n"
    )
    ensure(tag, f"v{args.version}", notes, draft=True, prerelease=False)

    if args.digest:
        with tempfile.TemporaryDirectory() as temp:
            info_path = Path(temp) / "docker-info.json"
            info = {
                "version": args.version,
                "channel": "stable",
                "commit": commit,
                "digest": args.digest,
                "tags": [tag.strip() for tag in args.tags.split(",") if tag.strip()],
                "built_at": now(),
            }
            info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
            upload(tag, info_path)

    if args.zip:
        zip_path = Path(args.zip)
        upload(tag, zip_path)
        with tempfile.TemporaryDirectory() as temp:
            info_path = Path(temp) / "windows-info.json"
            info = {
                "version": args.version,
                "channel": "stable",
                "commit": commit,
                "zip": zip_path.name,
                "zip_sha256": sha256(zip_path),
                "built_at": now(),
            }
            info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
            upload(tag, info_path)
            sums_path = Path(temp) / "sha256sums.txt"
            sums_path.write_text(f"{sha256(zip_path)}  {zip_path.name}\n", encoding="utf-8")
            upload(tag, sums_path)

    published = publish_when_complete(tag)
    print(f"stable release: {tag} ({'published' if published else 'draft, waiting for the other target'})")


if __name__ == "__main__":
    main()
