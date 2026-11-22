from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import config, security
from ..services import files_service, live_service, recorder_control

router = APIRouter(tags=["ws"])


def snapshot() -> dict:
    return {
        "recorder": recorder_control.status(),
        "summary": live_service.summary(),
        "recordings": live_service.recordings(),
        "waiting": live_service.waiting(page_size=200),
        "conversions": files_service.conversions(page_size=20),
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@router.websocket("/api/ws/events")
async def events(websocket: WebSocket):
    token = websocket.cookies.get(config.SESSION_COOKIE)
    session = security.get_session(token)
    if not session:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        data = await asyncio.to_thread(snapshot)
        await websocket.send_text(json.dumps({"type": "snapshot", "data": data}, ensure_ascii=False))
        last = json.dumps(data, ensure_ascii=False, sort_keys=True)
        while True:
            await asyncio.sleep(1)
            data = await asyncio.to_thread(snapshot)
            serialized = json.dumps(data, ensure_ascii=False, sort_keys=True)
            if serialized != last:
                await websocket.send_text(json.dumps({"type": "tick", "data": data}, ensure_ascii=False))
                last = serialized
    except (WebSocketDisconnect, RuntimeError):
        return
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
