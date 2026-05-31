"""Outfit combination generation.

Two methods (see Kien_truc_v3.1.md §3.4 Bước 3):
  - fitb_beam:      Iterative FITB + Top-K sampling + Beam Search (beam=3). 70% of KB.
  - random_scored:  Random combos per category rule, pre-filtered by OT scoring. 30% of KB.

Category rule: (1 top + 1 bottom + 1 shoes) OR (1 dress + 1 shoes);
               outerwear / bag / accessory optional.
"""

from __future__ import annotations

import itertools
import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from outfitmatch.kb.schema import ItemRecord, OutfitRecord

from outfitmatch.kb.schema import OutfitRecord
from outfitmatch.vocab import FORMALITY_RELEVANT_CATEGORIES, formality_span_ok

OPTIONAL_CATEGORIES: tuple[str, ...] = ("outerwear", "bag", "accessory")


def _combo_gender(items: list[ItemRecord]) -> str | None:
    """Shared wearer gender of a combo, or None if it mixes incompatible genders.

    ``unisex`` items pair with anything. A combo is valid only when its
    non-unisex items all agree (all men, or all women, or all kid). The returned
    value is that shared gender, or ``unisex`` when every item is unisex.
    """
    non_unisex = {item.gender for item in items} - {"unisex"}
    if len(non_unisex) > 1:
        return None
    return next(iter(non_unisex)) if non_unisex else "unisex"


def _is_coherent(items: list[ItemRecord]) -> bool:
    """True if the outfit's core garments stay within one formality band.

    Only FORMALITY_RELEVANT_CATEGORIES (top/bottom/dress/shoes/outerwear) count;
    bags/accessories are style-neutral and ignored. Blocks combos like
    blazer + gym shorts.
    """
    formalities = [
        item.formality for item in items if item.category in FORMALITY_RELEVANT_CATEGORIES
    ]
    return formality_span_ok(formalities)


def _is_valid_combo(items: list[ItemRecord]) -> bool:
    """A combo is buildable only if gender-consistent AND formality-coherent."""
    return _combo_gender(items) is not None and _is_coherent(items)


def _price_tier(total: int) -> str:
    if total < 300_000:
        return "budget"
    if total <= 800_000:
        return "mid"
    return "premium"


def _item_price(item: ItemRecord) -> int:
    value = item.store.get("price_vnd", 0)
    return int(value or 0)


def _aggregate_embedding(items: list[ItemRecord]) -> list[float]:
    vectors = [item.item_embedding for item in items if item.item_embedding]
    if not vectors:
        return []
    dim = min(len(v) for v in vectors)
    return [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]


def _score(items: list[ItemRecord], encoder: Any) -> float:
    if hasattr(encoder, "score_outfit"):
        return float(encoder.score_outfit(items))
    return 0.0


def _make_outfit(
    items: list[ItemRecord], *, index: int, method: str, score: float = 0.0
) -> OutfitRecord:
    price_total = sum(_item_price(item) for item in items)
    return OutfitRecord(
        outfit_id=f"OF_{index:05d}",
        schema_version="3.1",
        items=items,
        outfit_embedding=_aggregate_embedding(items),
        compatibility_score=score,
        occasion=[],
        style=[],
        body_shapes_fit=[],
        season=[],
        color_palette=[],
        price_total_vnd=price_total,
        price_tier=_price_tier(price_total),
        has_vn_store=all(bool(item.store.get("product_url")) for item in items),
        stylist_explanation_vi="",
        gen_method=method,
        gender=_combo_gender(items) or "unisex",
    )


def _base_combinations(items_by_category: dict[str, list[ItemRecord]]) -> list[list[ItemRecord]]:
    """All valid (top+bottom+shoes) / (dress+shoes) combos with no gender clash."""
    combos: list[list[ItemRecord]] = []
    for top, bottom, shoes in itertools.product(
        items_by_category.get("top", []),
        items_by_category.get("bottom", []),
        items_by_category.get("shoes", []),
    ):
        if _is_valid_combo([top, bottom, shoes]):
            combos.append([top, bottom, shoes])
    for dress, shoes in itertools.product(
        items_by_category.get("dress", []),
        items_by_category.get("shoes", []),
    ):
        if _is_valid_combo([dress, shoes]):
            combos.append([dress, shoes])
    return combos


def _with_optional_items(
    base: list[ItemRecord],
    items_by_category: dict[str, list[ItemRecord]],
    rng: random.Random,
) -> list[ItemRecord]:
    items = list(base)
    used = {item.category for item in items}
    for category in OPTIONAL_CATEGORIES:
        candidates = items_by_category.get(category, [])
        if candidates and category not in used and rng.random() < 0.35:
            # Only add an optional item that keeps the outfit gender-consistent.
            choice = rng.choice(candidates)
            if _is_valid_combo([*items, choice]):
                items.append(choice)
    return items


def generate_fitb_beam(
    items_by_category: dict[str, list[ItemRecord]],
    encoder: Any,
    n_outfits: int = 1000,
    beam_size: int = 3,
    top_k: int = 5,
) -> list[OutfitRecord]:
    """Generate outfit candidates via a deterministic FITB-style beam approximation.

    This prototype enumerates valid category-rule completions, scores them with
    ``encoder.score_outfit`` when available, keeps the best ``beam_size * top_k``
    candidates, and returns at most ``n_outfits`` with placeholder
    ``compatibility_score=0.0``. Run ``scoring.rescore_outfits`` before indexing.
    """
    if n_outfits <= 0:
        return []
    limit = max(1, beam_size) * max(1, top_k)
    ranked = sorted(
        _base_combinations(items_by_category),
        key=lambda combo: (_score(combo, encoder), [item.item_id for item in combo]),
        reverse=True,
    )[:limit]
    return [
        _make_outfit(items, index=i + 1, method="fitb_beam", score=0.0)
        for i, items in enumerate(ranked[:n_outfits])
    ]


def generate_random_scored(
    items_by_category: dict[str, list[ItemRecord]],
    encoder: Any,
    n_candidates: int = 5000,
) -> list[OutfitRecord]:
    """Generate candidates via deterministic random sampling and OT pre-scoring.

    Uses ``encoder.score_outfit`` as the pre-filter score when present. The returned
    records keep that score as an audit hint; production KB build should still call
    ``scoring.rescore_outfits`` once the final OT scorer is selected.
    """
    if n_candidates <= 0:
        return []
    bases = _base_combinations(items_by_category)
    if not bases:
        return []

    rng = random.Random(31)
    seen: set[tuple[str, ...]] = set()
    candidates: list[tuple[float, list[ItemRecord]]] = []
    attempts = max(n_candidates * 4, len(bases))
    for _ in range(attempts):
        base = rng.choice(bases)
        items = _with_optional_items(base, items_by_category, rng)
        key = tuple(item.item_id for item in items)
        if key in seen:
            continue
        seen.add(key)
        candidates.append((_score(items, encoder), items))
        if len(candidates) >= n_candidates:
            break

    candidates.sort(key=lambda pair: (pair[0], [item.item_id for item in pair[1]]), reverse=True)
    return [
        _make_outfit(items, index=i + 1, method="random_scored", score=score)
        for i, (score, items) in enumerate(candidates[:n_candidates])
    ]
