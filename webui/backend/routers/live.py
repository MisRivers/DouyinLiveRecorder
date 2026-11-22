from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from .. import security
from ..responses import ok
from ..services import live_service

router = APIRouter(prefix="/api/live", tags=["live"])


@router.get("/summary")
def summary(request: Request, session: dict = Depends(security.require_user)):
    return ok(live_service.summary(), request)


@router.get("/recordings")
def recordings(request: Request, session: dict = Depends(security.require_user)):
    return ok({"items": live_service.recordings()}, request)


@router.get("/waiting")
def waiting(request: Request, query: str = "", page: int = Query(1, ge=1),
            page_size: int = Query(100, ge=1, le=500),
            session: dict = Depends(security.require_user)):
    return ok(live_service.waiting(query, page, page_size), request)
