"""Tầng 3 retrieval — Qdrant seed filtering plus graph traversal assembly."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from outfitmatch.kb.assemble_record import to_outfit_record
from outfitmatch.kb.traversal import AssemblyConfig, assemble_outfits
from outfitmatch.vocab import formalities_for_occasion

if TYPE_CHECKING:
    from outfitmatch.kb.graph_store import OutfitGraph
    from outfitmatch.kb.schema import ItemRecord, OutfitRecord
    from outfitmatch.pipeline import RecommendRequest

logger = logging.getLogger(__name__)


def qdrant_filter_seed_ids(
    qdrant_url: str,
    *,
    occasion: str,
    gender: str | None = None,
    collection_name: str = "items",
    limit: int = 500,
) -> list[str]:
    """Return anchor item_ids whose formality suits the requested occasion."""
    formalities = sorted(formalities_for_occasion(occasion))
    if not formalities:
        return []

    from outfitmatch.kb.qdrant_index import _close_client, _import_qdrant, _make_client

    _, models = _import_qdrant()
    client = _make_client(qdrant_url)
    try:
        must: list = [
            models.FieldCondition(key="category", match=models.MatchAny(any=["top", "dress"])),
            models.FieldCondition(key="in_stock", match=models.MatchValue(value=True)),
            models.FieldCondition(key="has_vn_store", match=models.MatchValue(value=True)),
            models.FieldCondition(key="formality", match=models.MatchAny(any=formalities)),
        ]
        if gender is not None:
            must.append(
                models.FieldCondition(key="gender", match=models.MatchAny(any=[gender, "unisex"]))
            )
        records, _ = client.scroll(
            collection_name,
            scroll_filter=models.Filter(must=must),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [str(record.payload.get("item_id")) for record in records if record.payload]
    finally:
        _close_client(client)


def _fallback_seed_ids(graph: OutfitGraph, request: RecommendRequest) -> list[str]:
    """Scan graph items directly when Qdrant seeds are unavailable."""
    formalities = formalities_for_occasion(request.occasion)
    seeds: list[str] = []
    for item in sorted(graph._items.values(), key=lambda item: item.item_id):  # noqa: SLF001
        if item.category not in {"top", "dress"}:
            continue
        if item.formality not in formalities:
            continue
        if not bool(item.store.get("in_stock")):
            continue
        if not bool(item.store.get("product_url")):
            continue
        seeds.append(item.item_id)
    return seeds


def _has_excluded_color(items: list[ItemRecord], exclude: set[str]) -> bool:
    """Whether any item color matches the lowercase exclusion set."""
    return any(
        str(color).lower() in exclude
        for item in items
        for color in item.store.get("colors", [])
        if str(color)
    )


def _request_gender(request: RecommendRequest) -> str | None:
    """Hook for a future explicit gender field on RecommendRequest."""
    return None


def search_outfits(
    request: RecommendRequest,
    *,
    graph: OutfitGraph,
    seed_ids: list[str] | None = None,
    qdrant_url: str | None = None,
    top_n: int = 40,
    config: AssemblyConfig = AssemblyConfig(),
) -> list[OutfitRecord]:
    """Assemble + filter graph outfits for a request."""
    if request.body_shape:
        logger.info("body_shape=%s ignored in graph MVP retrieval", request.body_shape)

    if seed_ids is None:
        if qdrant_url is None:
            seed_ids = _fallback_seed_ids(graph, request)
        else:
            try:
                seed_ids = qdrant_filter_seed_ids(
                    qdrant_url,
                    occasion=request.occasion,
                    gender=_request_gender(request),
                )
            except Exception:
                logger.exception("Qdrant seed filtering failed; falling back to graph scan")
                seed_ids = _fallback_seed_ids(graph, request)

    exclude = {color.lower() for color in request.exclude_colors}
    records: list[OutfitRecord] = []
    for outfit in assemble_outfits(graph, seed_ids, config=config):
        total_price = sum(int(item.store.get("price_vnd") or 0) for item in outfit.items)
        if request.price_max is not None and total_price > request.price_max:
            continue
        if exclude and _has_excluded_color(outfit.items, exclude):
            continue
        record = to_outfit_record(outfit.items, outfit.score, index=len(records) + 1)
        if request.style and request.style not in record.style:
            continue
        records.append(record)
        if len(records) >= top_n:
            break
    return records
