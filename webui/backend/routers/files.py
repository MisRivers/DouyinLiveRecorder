from __future__ import annotations

import mimetypes
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from .. import security
from ..errors import ApiError
from ..responses import ok
from ..services import files_service

router = APIRouter(prefix="/api/files", tags=["files"])

MIME = {
    ".mp4": "video/mp4",
    ".ts": "video/mp2t",
    ".flv": "video/x-flv",
    ".mkv": "video/x-matroska",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
}


def _stream(path, request: Request):
    size = path.stat().st_size
    range_header = request.headers.get("range")
    start, end = 0, size - 1
    status = 200
    if range_header and range_header.startswith("bytes="):
        raw = range_header[len("bytes="):].split(",")[0]
        left, _, right = raw.partition("-")
        try:
            if left:
                start = int(left)
            if right:
                end = int(right)
        except ValueError:
            raise ApiError(416, "RANGE_NOT_SATISFIABLE", "Range 格式不正确")
        if start < 0 or end < start or start >= size:
            raise ApiError(416, "RANGE_NOT_SATISFIABLE", "请求范围超出文件大小")
        end = min(end, size - 1)
        status = 206
    length = end - start + 1
    media_type = MIME.get(path.suffix.lower()) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(path.name)}",
        "Cache-Control": "private, max-age=0",
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    def iterator():
        with open(path, "rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(iterator(), status_code=status, media_type=media_type, headers=headers)


@router.get("/anchors")
def anchors(request: Request, sort: str = "name", order: str = "asc", query: str = "",
            page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
            session: dict = Depends(security.require_user)):
    return ok(files_service.anchors(sort, order, query, page, page_size), request)


@router.get("")
def files(request: Request, anchor: str, sort: str = "name", order: str = "asc",
          page: int = Query(1, ge=1), page_size: int = Query(200, ge=1, le=500),
          session: dict = Depends(security.require_user)):
    return ok(files_service.files(anchor, sort, order, page, page_size), request)


@router.get("/playlist")
def playlist(request: Request, anchor: str, session: dict = Depends(security.require_user)):
    return ok({"items": files_service.playlist(anchor)}, request)


@router.get("/stream")
def stream(request: Request, rel: str, session: dict = Depends(security.require_user)):
    path = files_service.resolve_media_path(rel)
    return _stream(path, request)


@router.get("/duration")
def duration(request: Request, rel: str, session: dict = Depends(security.require_user)):
    return ok(files_service.media_duration(rel), request)


@router.post("/delete")
def delete(request: Request, payload: dict,
           session: dict = Depends(security.require_user),
           _: None = Depends(security.require_csrf)):
    result = files_service.delete_media(
        paths=payload.get("paths"), anchor_key=payload.get("anchor_key")
    )
    return ok(result, request)


@router.post("/convert")
def convert(request: Request, payload: dict,
            session: dict = Depends(security.require_user),
            _: None = Depends(security.require_csrf)):
    result = files_service.enqueue_conversion(
        paths=payload.get("paths"), anchor_key=payload.get("anchor_key"), trigger="manual"
    )
    return ok(result, request, 202)


@router.get("/conversions")
def conversions(request: Request, status: str | None = None, page: int = Query(1, ge=1),
                page_size: int = Query(50, ge=1, le=200),
                session: dict = Depends(security.require_user)):
    return ok(files_service.conversions(status, page, page_size), request)


@router.post("/conversions/{job_id}/cancel")
def cancel(request: Request, job_id: int,
           session: dict = Depends(security.require_user),
           _: None = Depends(security.require_csrf)):
    files_service.cancel_conversion(job_id)
    return ok({"ok": True}, request)
