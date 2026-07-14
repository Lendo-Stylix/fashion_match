"""POST /api/chat — SSE streaming."""

from __future__ import annotations

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
                yield {
                    "event": event["type"],
                    "data": event["data"],
                }
        except Exception as e:
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())
