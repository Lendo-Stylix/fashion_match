"""Outfit compatibility graph — node = ItemRecord, edge = wearable-together.

An edge exists between two items only when all three hard constraints hold:
  1. co-wearable categories;
  2. consistent gender (``_combo_gender`` is not ``None``);
  3. coherent formality (bags/accessories are style-neutral).

Each anchor keeps its top-K strongest neighbours per partner category so the
graph stays sparse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from outfitmatch.kb.generation import _combo_gender
from outfitmatch.vocab import FORMALITY_RELEVANT_CATEGORIES, formality_span_ok

if TYPE_CHECKING:
    from outfitmatch.kb.pair_scoring import PairScorer
    from outfitmatch.kb.schema import ItemRecord


COMPLEMENTARY_CATEGORIES: dict[str, frozenset[str]] = {
    "top": frozenset({"bottom", "shoes", "outerwear", "bag", "accessory"}),
    "bottom": frozenset({"top", "shoes", "outerwear", "bag", "accessory"}),
    "dress": frozenset({"shoes", "outerwear", "bag", "accessory"}),
    "shoes": frozenset({"top", "bottom", "dress", "outerwear", "bag", "accessory"}),
    "outerwear": frozenset({"top", "bottom", "dress", "shoes", "bag", "accessory"}),
    "bag": frozenset({"top", "bottom", "dress", "shoes", "outerwear", "accessory"}),
    "accessory": frozenset({"top", "bottom", "dress", "shoes", "outerwear", "bag"}),
}


@dataclass(frozen=True)
class Edge:
    src_id: str
    dst_id: str
    src_category: str
    dst_category: str
    weight: float


def edge_allowed_categories(cat_a: str, cat_b: str) -> bool:
    """Return whether two categories can co-occur in one outfit."""
    return cat_b in COMPLEMENTARY_CATEGORIES.get(cat_a, frozenset())


def edge_allowed(a: ItemRecord, b: ItemRecord) -> bool:
    """Return whether an edge may exist between two item nodes."""
    if a.item_id == b.item_id:
        return False
    if not edge_allowed_categories(a.category, b.category):
        return False
    if _combo_gender([a, b]) is None:
        return False
    relevant_formalities = [
        item.formality for item in (a, b) if item.category in FORMALITY_RELEVANT_CATEGORIES
    ]
    return formality_span_ok(relevant_formalities)


def _canonical_edge(a: ItemRecord, b: ItemRecord, weight: float) -> Edge:
    if a.item_id < b.item_id:
        src, dst = a, b
    else:
        src, dst = b, a
    return Edge(
        src_id=src.item_id,
        dst_id=dst.item_id,
        src_category=src.category,
        dst_category=dst.category,
        weight=float(weight),
    )


def build_edges(
    items: list[ItemRecord],
    scorer: PairScorer,
    k: int = 15,
    *,
    anchors: list[ItemRecord] | None = None,
) -> list[Edge]:
    """Build sparse canonical edges for the compatibility graph.

    ``anchors=None`` means a full build: every item drives top-K neighbour
    selection. Passing a subset enables incremental builds: only new items anchor
    top-K selection while still being matched against all items.
    """
    if k <= 0 or not items:
        return []

    ordered_items = sorted(items, key=lambda item: item.item_id)
    by_category: dict[str, list[ItemRecord]] = {}
    for item in ordered_items:
        by_category.setdefault(item.category, []).append(item)

    anchor_items = sorted(
        anchors if anchors is not None else ordered_items,
        key=lambda item: item.item_id,
    )
    canonical: dict[tuple[str, str], Edge] = {}

    for anchor in anchor_items:
        for partner_category in sorted(COMPLEMENTARY_CATEGORIES.get(anchor.category, frozenset())):
            candidates: list[tuple[float, ItemRecord]] = []
            for candidate in by_category.get(partner_category, []):
                if not edge_allowed(anchor, candidate):
                    continue
                candidates.append((float(scorer.score_pair(anchor, candidate)), candidate))
            candidates.sort(key=lambda pair: (-pair[0], pair[1].item_id))
            for weight, candidate in candidates[:k]:
                edge = _canonical_edge(anchor, candidate, weight)
                key = (edge.src_id, edge.dst_id)
                previous = canonical.get(key)
                if previous is None or edge.weight > previous.weight:
                    canonical[key] = edge

    return sorted(canonical.values(), key=lambda edge: (edge.src_id, edge.dst_id))
