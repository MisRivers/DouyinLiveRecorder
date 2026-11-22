from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from .. import security
from ..responses import ok
from ..services import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/schema")
def schema(request: Request, session: dict = Depends(security.require_user)):
    return ok(settings_service.schema(), request)


@router.get("")
def values(request: Request, session: dict = Depends(security.require_user)):
    return ok(settings_service.values(), request)


@router.put("")
def update(request: Request, payload: dict,
           session: dict = Depends(security.require_user),
           _: None = Depends(security.require_csrf)):
    return ok(settings_service.update(payload.get("updates", []), session["username"],
                                      security.client_ip(request)), request)


@router.post("/test-push")
def test_push(request: Request, payload: dict,
              session: dict = Depends(security.require_user),
              _: None = Depends(security.require_csrf)):
    return ok(settings_service.test_push(payload.get("channel", ""), session["username"],
                                         security.client_ip(request)), request)


@router.get("/export-ini", response_class=PlainTextResponse)
def export_ini(request: Request, session: dict = Depends(security.require_user)):
    return PlainTextResponse(settings_service.export_ini(), media_type="text/plain; charset=utf-8")


@router.post("/import-ini")
def import_ini(request: Request, payload: dict,
               session: dict = Depends(security.require_user),
               _: None = Depends(security.require_csrf)):
    return ok(settings_service.import_ini(payload.get("content", ""), session["username"],
                                          security.client_ip(request)), request)
