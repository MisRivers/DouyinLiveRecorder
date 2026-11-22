from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str,
                 details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"code": exc.code, "message": exc.message, "details": exc.details},
            "request_id": request_id(request),
        },
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    details = getattr(exc, "errors", lambda: None)()
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_FAILED",
                "message": "请求参数不符合要求",
                "details": details,
            },
            "request_id": request_id(request),
        },
    )
