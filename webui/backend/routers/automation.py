from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import security
from ..responses import ok
from ..services import notification_service, platform_service

router = APIRouter(prefix="/api", tags=["automation"])


@router.get("/notifications/templates")
def notification_templates(request: Request, session: dict = Depends(security.require_user)):
    return ok(notification_service.templates(), request)


@router.put("/notifications/templates")
def save_notification_templates(request: Request, payload: dict,
                                session: dict = Depends(security.require_user),
                                _: None = Depends(security.require_csrf)):
    return ok(notification_service.update(payload, session["username"],
                                          security.client_ip(request)), request)


@router.post("/notifications/preview")
def preview_notification(request: Request, payload: dict,
                         session: dict = Depends(security.require_user),
                         _: None = Depends(security.require_csrf)):
    return ok(notification_service.preview(payload), request)


@router.patch("/platforms/{code}")
def toggle_platform(request: Request, code: str, payload: dict,
                    session: dict = Depends(security.require_user),
                    _: None = Depends(security.require_csrf)):
    enabled = bool(payload.get("enabled"))
    return ok(platform_service.set_enabled(code, enabled, session["username"],
                                           security.client_ip(request)), request)
