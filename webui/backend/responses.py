from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from . import config


def ok(data=None, request: Request | None = None, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"data": data, "request_id": getattr(request.state, "request_id", "") if request else ""},
    )


def set_session_cookie(response: JSONResponse, token: str, secure: bool = False) -> None:
    response.set_cookie(
        config.SESSION_COOKIE,
        token,
        max_age=config.SESSION_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


def clear_session_cookie(response: JSONResponse) -> None:
    response.delete_cookie(config.SESSION_COOKIE, path="/")
