from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from .. import security
from ..responses import ok
from ..services import platform_service, rooms_service, schedule_service

router = APIRouter(prefix="/api/rooms", tags=["rooms"])
platform_router = APIRouter(prefix="/api", tags=["rooms"])


@router.get("/platforms")
def platforms(request: Request, session: dict = Depends(security.require_user)):
    return ok(rooms_service.platforms(), request)


@platform_router.get("/platforms")
def platforms_alias(request: Request, include_disabled: bool = False, query: str = "",
                    session: dict = Depends(security.require_user)):
    return ok(platform_service.list_platforms(include_disabled, query), request)


@router.get("")
def list_rooms(
    request: Request,
    query: str = "",
    enabled: bool | None = None,
    platform_code: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: str = "sort_order",
    order: str = "asc",
    session: dict = Depends(security.require_user),
):
    return ok(rooms_service.list_rooms(query, enabled, platform_code, page, page_size, sort, order), request)


@router.post("")
def create(request: Request, payload: dict,
           session: dict = Depends(security.require_user),
           _: None = Depends(security.require_csrf)):
    return ok(rooms_service.create(payload, session["username"], security.client_ip(request)), request, 201)


@router.post("/quick-add")
def quick_add(request: Request, payload: dict,
              session: dict = Depends(security.require_user),
              _: None = Depends(security.require_csrf)):
    return ok(rooms_service.quick_add(payload, session["username"], security.client_ip(request)),
              request, 201)


@router.post("/reorder")
def reorder(request: Request, payload: dict,
            session: dict = Depends(security.require_user),
            _: None = Depends(security.require_csrf)):
    ids = [int(item) for item in payload.get("ids", [])]
    rooms_service.reorder(ids, session["username"], security.client_ip(request))
    return ok({"ok": True}, request)


@router.post("/import")
def import_rooms(request: Request, payload: dict,
                 session: dict = Depends(security.require_user),
                 _: None = Depends(security.require_csrf)):
    content = payload.get("content") or ""
    return ok(rooms_service.import_ini(content, session["username"], security.client_ip(request)), request)


@router.get("/export", response_class=PlainTextResponse)
def export_rooms(request: Request, session: dict = Depends(security.require_user)):
    return PlainTextResponse(rooms_service.export_ini(), media_type="text/plain; charset=utf-8")


@router.get("/{room_id}")
def get_room(request: Request, room_id: int, session: dict = Depends(security.require_user)):
    return ok(rooms_service.get_room(room_id), request)


@router.get("/{room_id}/schedule")
def get_schedule(request: Request, room_id: int, session: dict = Depends(security.require_user)):
    return ok(schedule_service.get(room_id), request)


@router.put("/{room_id}/schedule")
def save_schedule(request: Request, room_id: int, payload: dict,
                  session: dict = Depends(security.require_user),
                  _: None = Depends(security.require_csrf)):
    return ok(schedule_service.replace(room_id, payload.get("windows", []),
                                      session["username"], security.client_ip(request)), request)


@router.patch("/{room_id}")
def update_room(request: Request, room_id: int, payload: dict,
                session: dict = Depends(security.require_user),
                _: None = Depends(security.require_csrf)):
    return ok(rooms_service.update(room_id, payload, session["username"], security.client_ip(request)),
              request)


@router.delete("/{room_id}")
def delete_room(request: Request, room_id: int, force: bool = False,
                session: dict = Depends(security.require_user),
                _: None = Depends(security.require_csrf)):
    rooms_service.delete(room_id, session["username"], security.client_ip(request), force)
    return ok({"ok": True}, request)
