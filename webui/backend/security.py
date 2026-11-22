from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import Request

from . import config, db
from .errors import ApiError

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1

_login_state: dict[str, dict] = {}


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
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
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


def check_login_attempt(key: str) -> None:
    state = _login_state.get(key)
    now = time.time()
    if not state:
        return
    if state.get("locked_until", 0) > now:
        remaining = int(state["locked_until"] - now)
        raise ApiError(423, "ACCOUNT_LOCKED", "登录失败次数过多", {"retry_after_seconds": remaining})


def record_login_failure(key: str) -> None:
    state = _login_state.setdefault(key, {"count": 0, "locked_until": 0})
    state["count"] += 1
    if state["count"] >= config.LOGIN_MAX_FAILURES:
        state["locked_until"] = time.time() + config.LOGIN_LOCK_SECONDS
        state["count"] = 0


def clear_login_failures(key: str) -> None:
    _login_state.pop(key, None)
