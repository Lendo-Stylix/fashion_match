"""GET /api/health."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def health():
    """Health check endpoint."""
    from outfitmatch.server.deps import _graph, _model, _stylist_service

    return {
        "status": "ok",
        "graph_loaded": _graph is not None,
        "stylist_available": _stylist_service is not None,
        "gpu_available": _model is not None,
    }
