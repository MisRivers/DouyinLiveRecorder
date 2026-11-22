from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import security
from ..responses import ok
from ..services import recorder_control

router = APIRouter(prefix="/api/recorder", tags=["recorder"])


@router.get("/status")
def status(request: Request, session: dict = Depends(security.require_user)):
    return ok(recorder_control.status(), request)


@router.post("/start")
def start(request: Request, session: dict = Depends(security.require_user),
          _: None = Depends(security.require_csrf)):
    return ok(recorder_control.start(session["username"], security.client_ip(request)), request, 202)


@router.post("/stop")
def stop(request: Request, payload: dict | None = None,
         session: dict = Depends(security.require_user),
         _: None = Depends(security.require_csrf)):
    mode = (payload or {}).get("mode", "graceful")
    return ok(recorder_control.stop(mode, session["username"], security.client_ip(request)), request, 202)


@router.post("/restart")
def restart(request: Request, session: dict = Depends(security.require_user),
            _: None = Depends(security.require_csrf)):
    return ok(recorder_control.restart(session["username"], security.client_ip(request)), request, 202)
