"""Turn graph-assembled items into a normal OutfitRecord with derived tags."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.data.scrape.config import STORES_BY_ID

from outfitmatch.kb.generation import _aggregate_embedding, _combo_gender, _price_tier
from outfitmatch.kb.schema import OutfitRecord
from outfitmatch.vocab import FORMALITY_RANK, FORMALITY_RELEVANT_CATEGORIES, occasions_for_formality

if TYPE_CHECKING:
    from outfitmatch.kb.schema import ItemRecord


def _outfit_occasions(items: list[ItemRecord]) -> list[str]:
    """Derive admissible occasions from the outfit's highest formality band."""
    bands = [item.formality for item in items if item.category in FORMALITY_RELEVANT_CATEGORIES]
    if not bands:
        return []
    top_band = max(bands, key=lambda band: FORMALITY_RANK.get(band, 0))
    return sorted(occasions_for_formality(top_band))


def _outfit_styles(items: list[ItemRecord]) -> list[str]:
    """Union store-level style tags across the outfit's items."""
    styles: set[str] = set()
    for item in items:
        store_id = str(item.store.get("store_id") or "")
        store = STORES_BY_ID.get(store_id)
        if store is not None:
            styles.update(store.style_tags)
    return sorted(styles)


def _outfit_colors(items: list[ItemRecord]) -> list[str]:
    """Union item colors, preserving a stable sorted palette."""
    return sorted(
        {str(color) for item in items for color in item.store.get("colors", []) if str(color)}
    )


def to_outfit_record(items: list[ItemRecord], score: float, *, index: int = 1) -> OutfitRecord:
    """Build an OutfitRecord from graph-assembled items."""
    price_total = sum(int(item.store.get("price_vnd") or 0) for item in items)
    return OutfitRecord(
        outfit_id=f"OF_{index:05d}",
        schema_version="3.1",
        items=items,
        outfit_embedding=_aggregate_embedding(items),
        compatibility_score=round(float(score), 6),
        occasion=_outfit_occasions(items),
        style=_outfit_styles(items),
        body_shapes_fit=[],
        season=[],
        color_palette=_outfit_colors(items),
        price_total_vnd=price_total,
        price_tier=_price_tier(price_total),
        has_vn_store=all(bool(item.store.get("product_url")) for item in items),
        stylist_explanation_vi="",
        gen_method="graph_traversal",
        gender=_combo_gender(items) or "unisex",
    )
