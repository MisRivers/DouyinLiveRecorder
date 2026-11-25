from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import db, security
from ..errors import ApiError
from ..responses import clear_session_cookie, ok, set_session_cookie

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def status(request: Request):
    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM admin_user").fetchone()["c"]
    session = security.get_session(security.session_token(request))
    return ok({
        "setup_required": count == 0,
        "authenticated": bool(session),
        "user": {"username": session["username"]} if session else None,
        "csrf_token": session["csrf_token"] if session else None,
    }, request)


@router.post("/setup")
def setup(request: Request, payload: dict):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    confirm = payload.get("password_confirm") or ""
    if not username or len(username) < 3 or len(username) > 32:
        raise ApiError(422, "VALIDATION_FAILED", "用户名长度需在 3 到 32 个字符之间")
    if len(password) < 10 or not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        raise ApiError(422, "WEAK_PASSWORD", "密码至少 10 位，且包含字母与数字")
    if password != confirm:
        raise ApiError(422, "PASSWORD_MISMATCH", "两次输入的密码不一致")
    with db.connect() as conn:
        if conn.execute("SELECT COUNT(*) AS c FROM admin_user").fetchone()["c"]:
            raise ApiError(409, "SETUP_ALREADY_DONE", "管理员已经初始化")
    now = db.now_iso()
    password_hash = security.hash_password(password)
    with db.connect() as conn:
        try:
            # 用写锁串行化首次初始化，避免并发请求各自创建管理员。
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute("SELECT COUNT(*) AS c FROM admin_user").fetchone()["c"]
            if count:
                conn.rollback()
                raise ApiError(409, "SETUP_ALREADY_DONE", "管理员已经初始化")
            cur = conn.execute(
                """
                INSERT INTO admin_user (username, password_hash, password_algo, created_at, updated_at)
                VALUES (?, ?, 'scrypt', ?, ?)
                """,
                (username, password_hash, now, now),
            )
            user_id = int(cur.lastrowid)
            db._set_meta(conn, "setup_completed", "1")
            conn.commit()
        except ApiError:
            raise
        except Exception:
            conn.rollback()
            raise
    token, csrf = security.create_session(user_id, request)
    db.audit(username, "auth.setup", "user", str(user_id), None, security.client_ip(request))
    response = ok({"user": {"username": username}, "csrf_token": csrf}, request, 201)
    set_session_cookie(response, token, secure=request.url.scheme == "https")
    return response


@router.post("/login")
def login(request: Request, payload: dict):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    key = f"{security.client_ip(request)}:{username}"
    security.check_login_attempt(key)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM admin_user WHERE username=?", (username,)).fetchone()
    if not row or not security.verify_password(password, row["password_hash"]):
        security.record_login_failure(key)
        raise ApiError(401, "INVALID_CREDENTIALS", "用户名或密码错误")
    security.clear_login_failures(key)
    with db.connect() as conn:
        conn.execute("UPDATE admin_user SET last_login_at=? WHERE id=?",
                     (db.now_iso(), row["id"]))
        conn.commit()
    token, csrf = security.create_session(row["id"], request)
    db.audit(username, "auth.login", "user", str(row["id"]), None, security.client_ip(request))
    response = ok({"user": {"username": row["username"]}, "csrf_token": csrf}, request)
    set_session_cookie(response, token, secure=request.url.scheme == "https")
    return response


@router.post("/logout")
def logout(request: Request, session: dict = Depends(security.require_user),
           _: None = Depends(security.require_csrf)):
    security.revoke_session(security.session_token(request))
    db.audit(session["username"], "auth.logout", "user", str(session["user_id"]), None,
             security.client_ip(request))
    response = ok({"ok": True}, request)
    clear_session_cookie(response)
    return response


@router.post("/password")
def change_password(request: Request, payload: dict,
                    session: dict = Depends(security.require_user),
                    _: None = Depends(security.require_csrf)):
    current = payload.get("current_password") or ""
    new = payload.get("new_password") or ""
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM admin_user WHERE id=?", (session["user_id"],)).fetchone()
    if not row or not security.verify_password(current, row["password_hash"]):
        raise ApiError(400, "WRONG_PASSWORD", "当前密码不正确")
    if len(new) < 10 or not any(ch.isalpha() for ch in new) or not any(ch.isdigit() for ch in new):
        raise ApiError(422, "WEAK_PASSWORD", "新密码至少 10 位，且包含字母与数字")
    with db.connect() as conn:
        conn.execute("UPDATE admin_user SET password_hash=?, updated_at=? WHERE id=?",
                     (security.hash_password(new), db.now_iso(), session["user_id"]))
        conn.commit()
    security.revoke_user_sessions(session["user_id"], keep_token=security.session_token(request))
    db.audit(session["username"], "auth.password", "user", str(session["user_id"]), None,
             security.client_ip(request))
    return ok({"ok": True}, request)
