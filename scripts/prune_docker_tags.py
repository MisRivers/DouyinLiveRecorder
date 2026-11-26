#!/usr/bin/env python3
"""Prune Docker Hub tags after a release build.

Policy:
- keep ``latest`` permanently; keep ``beta`` while publishing beta builds;
- beta builds keep only the newest N beta version tags (``X.Y.Z-beta.N``);
- stable builds keep only the newest N stable version tags (``X.Y.Z``) and
  remove all beta version tags plus the ``beta`` alias;
- delete legacy ``sha-*``, ``feature-web-ui``, ``amd64`` and ``arm64`` tags.

The script never fails a release build: missing credentials, insufficient
Delete permission and network errors are reported but exit with status 0.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://hub.docker.com/v2"
BETA = re.compile(r"^(\d+)\.(\d+)\.(\d+)-beta\.(\d+)$")
STABLE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
SHA = re.compile(r"^sha-[0-9a-f]{7,40}$")
LEGACY = {"feature-web-ui", "amd64", "arm64"}


def request(
    method: str, url: str, token: str = "", payload: dict | None = None
) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json", "User-Agent": "DLR-Release/1.0"}
    if token:
        headers["Authorization"] = f"JWT {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read()
        return response.status, json.loads(raw) if raw else {}


def login(username: str, password: str) -> str:
    _, data = request(
        "POST",
        f"{API}/users/login/",
        payload={"username": username, "password": password},
    )
    return str(data.get("token") or "")


def list_tags(repo: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    page = 1
    while True:
        url = (
            f"{API}/repositories/{repo}/tags/"
            f"?page_size=100&page={page}&ordering=last_updated"
        )
        _, data = request("GET", url)
        for item in data.get("results") or []:
            tags[str(item.get("name") or "")] = str(item.get("last_updated") or "")
        if not data.get("next"):
            break
        page += 1
    tags.pop("", None)
    return tags


def beta_key(name: str) -> tuple[int, int, int, int]:
    match = BETA.match(name)
    assert match
    return tuple(int(match.group(i)) for i in (1, 2, 3, 4))  # type: ignore[return-value]


def stable_key(name: str) -> tuple[int, int, int]:
    match = STABLE.match(name)
    assert match
    return tuple(int(match.group(i)) for i in (1, 2, 3))  # type: ignore[return-value]


def plan(tags: dict[str, str], keep: int, channel: str = "beta") -> list[str]:
    keep_tags = {"latest"} if channel == "release" else {"latest", "beta"}
    delete: list[str] = []
    for name in tags:
        if name in keep_tags:
            continue
        if channel == "release" and (name == "beta" or BETA.match(name)):
            delete.append(name)
            continue
        if SHA.match(name) or name in LEGACY:
            delete.append(name)
    for pattern, key in ((BETA, beta_key), (STABLE, stable_key)):
        if channel == "release" and pattern is BETA:
            continue
        versions = [name for name in tags if pattern.match(name)]
        versions.sort(key=key, reverse=True)
        delete.extend(versions[keep:])
    return sorted(set(delete))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="misrivers/dlr-webui")
    parser.add_argument("--keep", type=int, default=5)
    parser.add_argument("--channel", choices=("beta", "release"), default="beta")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    username = os.environ.get("DOCKERHUB_USERNAME", "").strip()
    password = (
        os.environ.get("DOCKERHUB_TOKEN", "").strip()
        or os.environ.get("DOCKERHUB_PASSWORD", "").strip()
    )
    if not username or not password:
        print("skip prune: DOCKERHUB_USERNAME / DOCKERHUB_TOKEN not configured")
        return 0

    try:
        tags = list_tags(args.repo)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"skip prune: cannot list tags: {exc}")
        return 0

    targets = plan(tags, max(1, args.keep), args.channel)
    print(f"docker tags: {len(tags)} total, {len(targets)} to delete")
    for name in targets:
        print(f"  delete {name}")
    if args.dry_run:
        return 0
    if not targets:
        return 0

    try:
        token = login(username, password)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"skip prune: login failed: {exc}")
        return 0
    if not token:
        print("skip prune: login returned no token")
        return 0

    deleted = 0
    forbidden = 0
    for name in targets:
        url = f"{API}/repositories/{args.repo}/tags/{urllib.parse.quote(name)}/"
        try:
            status, _ = request("DELETE", url, token)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            if exc.code in (401, 403):
                forbidden += 1
                continue
            print(f"  warning: delete {name} failed: HTTP {exc.code}")
            continue
        except (urllib.error.URLError, OSError) as exc:
            print(f"  warning: delete {name} failed: {exc}")
            continue
        if status in (200, 202, 204):
            deleted += 1

    print(f"prune done: deleted {deleted}, permission denied {forbidden}")
    if forbidden:
        print(
            "warning: Docker Hub token needs the Delete scope to remove old tags; "
            "grant Read, Write, Delete and rerun."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
