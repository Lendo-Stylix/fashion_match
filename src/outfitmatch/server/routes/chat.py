"""POST /api/chat — SSE streaming."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from outfitmatch.server.schemas import ChatRequest

router = APIRouter()


@router.post("")
async def chat(req: ChatRequest) -> Any:
    """Chat endpoint: SSE stream of stylist events."""
    from outfitmatch.server.deps import get_stylist_service

    stylist = get_stylist_service()
    if stylist is None:
        raise HTTPException(status_code=503, detail="Stylist model not available")

    async def event_generator():
        try:
            for event in stylist.chat_stream(user_message=req.message):
                data = event.get("data", "")
                # sse_starlette str()s complex objects as a Python repr
                # (single-quoted, invalid JSON). Serialize list/dict payloads
                # explicitly so the Next.js client receives valid JSON.
                if isinstance(data, (list, dict)):
                    data = json.dumps(data, ensure_ascii=False)
                yield {
                    "event": event["type"],
                    "data": data,
                }
        except Exception as e:
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())
