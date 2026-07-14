"""GET /api/outfits/{id} — outfit detail."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/{outfit_id}")
async def get_outfit(outfit_id: str) -> dict:
    """Return outfit detail by ID."""
    from outfitmatch.server.deps import get_graph

    graph = get_graph()
    # OutfitGraph has items, need to find outfit by id in items_to_outfits or similar
    # For now, scan the graph's items and check outfit references
    # The graph stores item->outfit mappings
    result = _find_outfit_in_graph(graph, outfit_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Outfit {outfit_id} not found")
    return result


def _find_outfit_in_graph(graph, outfit_id: str) -> dict | None:
    """Scan graph to find outfit record by ID."""
    # Graph stores items with outfit_id references
    # For MVP, we need to scan the graph's items and reconstruct the outfit
    # Since OutfitGraph doesn't directly index outfits, we scan items
    # Each item may reference outfit_id via item._outfit_ids
    # But this requires the graph to have outfit_id -> item mapping
    # For now, return None if not found
    # TODO: implement proper outfit lookup when outfit index is available
    return None
