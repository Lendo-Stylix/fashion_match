"""Turn graph-assembled items into a normal OutfitRecord with derived tags."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.data.scrape.config import STORES_BY_ID

from outfitmatch.kb.generation import _aggregate_embedding, _combo_gender, _price_tier
from outfitmatch.kb.ids import stable_outfit_id  # FIX D: stable outfit id
from outfitmatch.kb.schema import OutfitRecord
from outfitmatch.vocab import (
    BODY_SHAPE,
    FORMALITY_RANK,
    FORMALITY_RELEVANT_CATEGORIES,
    SEASON,
    STYLE_SET,
    occasions_for_formality,
)

# Coarse formality band -> canonical STYLE enum values. Graph items carry no
# per-item style tag (only formality), so we derive an item-level style hint
# from its formality band and MERGE it with the store-level style_tags.
# This replaces the old behavior where every item of a store (e.g. YODY) was
# blindly tagged with the store's ('casual','sporty') regardless of formality.
FORMALITY_STYLE: dict[str, frozenset[str]] = {
    "formal": frozenset({"elegant", "classic"}),
    "smart_casual": frozenset({"minimalist", "korean"}),
    "casual": frozenset({"casual"}),
    "athletic": frozenset({"sporty"}),
}

_BODY_SHAPE_RELEVANT_CATEGORIES = frozenset({"top", "bottom", "dress", "outerwear"})
_SEASON_RELEVANT_CATEGORIES = frozenset({"top", "bottom", "dress", "outerwear"})
_PRIMARY_BODY_SHAPE_CATEGORIES = ("dress", "top", "bottom", "outerwear")
_PRIMARY_SEASON_CATEGORIES = ("dress", "top", "bottom", "outerwear")

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
    """Derive outfit style from item-level formality + store-level tags.

    FIX B: previously this only returned the store's style_tags, so every YODY
    item (even formal blazers) was tagged ('casual','sporty'). Now we first add
    the style hint implied by each item's formality band, then union the
    store-level tags, keeping only canonical STYLE enum values.
    """
    styles: set[str] = set()
    for item in items:
        # item-level hint from formality (the only per-item style signal)
        styles.update(FORMALITY_STYLE.get(item.formality, frozenset()))
        # store-level tags (kept as a secondary signal)
        store_id = str(item.store.get("store_id") or "")
        store = STORES_BY_ID.get(store_id)
        if store is not None:
            styles.update(store.style_tags)
    # keep only canonical STYLE enum values (defensive against bad config)
    return sorted(styles & STYLE_SET)


def _outfit_colors(items: list[ItemRecord]) -> list[str]:
    """Union item colors, preserving a stable sorted palette."""
    return sorted(
        {str(color) for item in items for color in item.store.get("colors", []) if str(color)}
    )


def _ordered_vocab_values(values: set[str], vocab: tuple[str, ...]) -> list[str]:
    """Return values in canonical vocab order, dropping unknowns."""
    return [value for value in vocab if value in values]


def _tag_sets(
    items: list[ItemRecord],
    attr: str,
    *,
    categories: frozenset[str],
) -> list[set[str]]:
    """Collect non-empty tag sets from items in relevant categories."""
    tag_sets: list[set[str]] = []
    for item in items:
        if item.category not in categories:
            continue
        values = {str(v) for v in getattr(item, attr, []) if str(v)}
        if values:
            tag_sets.append(values)
    return tag_sets


def _derive_outfit_body_shapes(items: list[ItemRecord]) -> list[str]:
    """Derive body-shape tags from primary garments, ignoring accessories/shoes."""
    dress_tag_sets = _tag_sets(
        [item for item in items if item.category == "dress"],
        "body_shapes_fit",
        categories=frozenset({"dress"}),
    )
    if dress_tag_sets:
        return _ordered_vocab_values(set.union(*dress_tag_sets), BODY_SHAPE)

    tag_sets = _tag_sets(items, "body_shapes_fit", categories=_BODY_SHAPE_RELEVANT_CATEGORIES)
    if not tag_sets:
        return []

    shared = set.intersection(*tag_sets)
    if shared:
        return _ordered_vocab_values(shared, BODY_SHAPE)
    return _ordered_vocab_values(set.union(*tag_sets), BODY_SHAPE)


def _derive_outfit_seasons(items: list[ItemRecord]) -> list[str]:
    """Prefer shared seasons for main garments, then fall back to their union."""
    dress_tag_sets = _tag_sets(
        [item for item in items if item.category == "dress"],
        "season",
        categories=frozenset({"dress"}),
    )
    if dress_tag_sets:
        return _ordered_vocab_values(set.union(*dress_tag_sets), SEASON)

    tag_sets = _tag_sets(items, "season", categories=_SEASON_RELEVANT_CATEGORIES)
    if not tag_sets:
        return []

    shared = set.intersection(*tag_sets)
    if shared:
        return _ordered_vocab_values(shared, SEASON)
    return _ordered_vocab_values(set.union(*tag_sets), SEASON)


def to_outfit_record(items: list[ItemRecord], score: float, *, index: int = 1) -> OutfitRecord:
    """Build an OutfitRecord from graph-assembled items.

    FIX D: outfit_id is derived from the item set (stable across runs), NOT the
    positional index. ``index`` is kept for API compatibility but unused for id.
    """
    price_total = sum(int(item.store.get("price_vnd") or 0) for item in items)
    return OutfitRecord(
        outfit_id=stable_outfit_id([it.item_id for it in items]),
        schema_version="3.1",
        items=items,
        outfit_embedding=_aggregate_embedding(items),
        compatibility_score=round(float(score), 6),
        occasion=_outfit_occasions(items),
        style=_outfit_styles(items),
        body_shapes_fit=_derive_outfit_body_shapes(items),
        season=_derive_outfit_seasons(items),
        color_palette=_outfit_colors(items),
        price_total_vnd=price_total,
        price_tier=_price_tier(price_total),
        has_vn_store=all(bool(item.store.get("product_url")) for item in items),
        stylist_explanation_vi="",
        gen_method="graph_traversal",
        gender=_combo_gender(items) or "unisex",
    )
