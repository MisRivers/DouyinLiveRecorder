#!/usr/bin/env python3
"""Reset the WebUI administrator username and password inside Docker.

Usage:
    docker exec -it -u dlr dlr-webui python reset_account.py
    docker exec -it -u dlr dlr-webui python reset_account.py --username admin --password 'NewPass1234'
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui.backend import db, security


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset the LiveRecorder admin username and password"
    )
    parser.add_argument("--username", default="", help="new admin username")
    parser.add_argument("--password", default="", help="new admin password")
    args = parser.parse_args()

    if os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() == 0:
        print("请以 dlr 用户运行，避免改动数据库文件属主：", file=sys.stderr)
        print("  docker exec -it -u dlr <容器名> python reset_account.py", file=sys.stderr)
        return 1

    db.init_db()
    username = args.username.strip()
    if not username:
        username = input("新用户名: ").strip()
    if args.password:
        password = args.password
    else:
        password = getpass.getpass("新密码: ")
        confirm = getpass.getpass("确认新密码: ")
        if password != confirm:
            print("两次输入的密码不一致", file=sys.stderr)
            return 1

    try:
        username = security.reset_admin_credentials(username, password)
    except ValueError as exc:
        print(f"重置失败：{exc}", file=sys.stderr)
        return 1
    print(f"管理员账号已重置为 {username}，请使用新用户名和密码重新登录。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
