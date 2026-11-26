from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import Request

from . import config, db
from .errors import ApiError

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1

_login_state: dict[str, dict] = {}
_login_lock = threading.Lock()
_last_login_prune = 0.0
LOGIN_STATE_MAX = 2000
LOGIN_STATE_TTL = max(config.LOGIN_LOCK_SECONDS * 2, 1800)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(actual, _unb64(digest))
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: int, request: Request | None = None) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    session_id = secrets.token_hex(16)
    expires = now + timedelta(hours=config.SESSION_HOURS)
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO admin_session
              (id, user_id, token_hash, csrf_token, created_at, expires_at,
               last_seen_at, ip, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, user_id, _token_hash(token), csrf,
                now.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds"),
                now.isoformat(timespec="seconds"),
                client_ip(request) if request else None,
                request.headers.get("user-agent") if request else None,
            ),
        )
        conn.commit()
    return token, csrf


def get_session(token: str | None) -> dict | None:
    if not token:
        return None
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT s.*, u.username FROM admin_session s
            JOIN admin_user u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.revoked=0 AND s.expires_at>?
            """,
            (_token_hash(token), now),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE admin_session SET last_seen_at=? WHERE id=?",
            (now, row["id"]),
        )
        conn.commit()
    return dict(row)


def revoke_session(token: str | None) -> None:
    if not token:
        return
    with db.connect() as conn:
        conn.execute("UPDATE admin_session SET revoked=1 WHERE token_hash=?", (_token_hash(token),))
        conn.commit()


def revoke_user_sessions(user_id: int, keep_token: str | None = None) -> None:
    with db.connect() as conn:
        if keep_token:
            conn.execute(
                "UPDATE admin_session SET revoked=1 WHERE user_id=? AND token_hash<>?",
                (user_id, _token_hash(keep_token)),
            )
        else:
            conn.execute("UPDATE admin_session SET revoked=1 WHERE user_id=?", (user_id,))
        conn.commit()


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    if config.TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            values = [value.strip() for value in forwarded.split(",") if value.strip()]
            if values:
                # 仅在明确配置可信代理时使用代理追加的最后一跳地址。
                return values[-1]
    return request.client.host if request.client else None


def session_token(request: Request) -> str | None:
    return request.cookies.get(config.SESSION_COOKIE)


def require_user(request: Request) -> dict:
    session = get_session(session_token(request))
    if not session:
        raise ApiError(401, "UNAUTHENTICATED", "请先登录")
    request.state.session = session
    return session


def require_csrf(request: Request) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    session = getattr(request.state, "session", None) or get_session(session_token(request))
    if not session:
        raise ApiError(401, "UNAUTHENTICATED", "请先登录")
    header = request.headers.get(config.CSRF_HEADER)
    if not header or not hmac.compare_digest(header, session["csrf_token"]):
        raise ApiError(403, "FORBIDDEN", "CSRF 校验失败，请刷新页面后重试")


def _prune_login_state(now: float, force: bool = False) -> None:
    global _last_login_prune
    if not force and now - _last_login_prune < 60:
        return
    _last_login_prune = now
    stale = [
        key for key, state in _login_state.items()
        if now - state.get("updated_at", 0) > LOGIN_STATE_TTL
    ]
    for key in stale:
        _login_state.pop(key, None)
    overflow = len(_login_state) - LOGIN_STATE_MAX
    if overflow > 0:
        oldest = sorted(
            _login_state.items(), key=lambda item: item[1].get("updated_at", 0)
        )[:overflow]
        for key, _ in oldest:
            _login_state.pop(key, None)


def check_login_attempt(key: str) -> None:
    now = time.time()
    with _login_lock:
        state = _login_state.get(key)
        if not state:
            return
        locked_until = state.get("locked_until", 0)
        if locked_until > now:
            remaining = int(locked_until - now)
            raise ApiError(423, "ACCOUNT_LOCKED", "登录失败次数过多",
                           {"retry_after_seconds": remaining})


def record_login_failure(key: str) -> None:
    now = time.time()
    with _login_lock:
        _prune_login_state(now, force=len(_login_state) >= LOGIN_STATE_MAX)
        state = _login_state.setdefault(
            key, {"count": 0, "locked_until": 0, "updated_at": now}
        )
        state["updated_at"] = now
        state["count"] += 1
        if state["count"] >= config.LOGIN_MAX_FAILURES:
            state["locked_until"] = now + config.LOGIN_LOCK_SECONDS
            state["count"] = 0
        if len(_login_state) > LOGIN_STATE_MAX:
            _prune_login_state(time.time(), force=True)


def clear_login_failures(key: str) -> None:
    with _login_lock:
        _login_state.pop(key, None)


PASSWORD_MIN_LENGTH = 10
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 32


def validate_username(username: str) -> None:
    if not username or len(username) < USERNAME_MIN_LENGTH or len(username) > USERNAME_MAX_LENGTH:
        raise ValueError(
            f"用户名长度需在 {USERNAME_MIN_LENGTH} 到 {USERNAME_MAX_LENGTH} 个字符之间"
        )


def validate_password(password: str) -> None:
    if (
        len(password) < PASSWORD_MIN_LENGTH
        or not any(ch.isalpha() for ch in password)
        or not any(ch.isdigit() for ch in password)
    ):
        raise ValueError(f"密码至少 {PASSWORD_MIN_LENGTH} 位，且包含字母与数字")


def reset_admin_credentials(new_username: str, new_password: str) -> str:
    """Replace the administrator username and password, revoking all sessions."""
    username = (new_username or "").strip()
    validate_username(username)
    validate_password(new_password)
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM admin_user ORDER BY id LIMIT 1").fetchone()
        if not row:
            raise ValueError("尚未初始化管理员账号")
        try:
            conn.execute(
                "UPDATE admin_user SET username=?, password_hash=?, updated_at=? WHERE id=?",
                (username, hash_password(new_password), db.now_iso(), row["id"]),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            raise ValueError("用户名已被占用")
    revoke_user_sessions(int(row["id"]))
    return username
