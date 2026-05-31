"""Infer dress formality for a catalog item.

Why this exists:
    Outfit generation combines items by category + gender only. Without a
    formality signal it pairs a blazer with gym shorts. This assigns each item a
    coarse formality so generation can keep one outfit inside a sensible band.

Returns one of FORMALITY: ``athletic | casual | smart_casual | formal``.
``casual`` is the safe fallback. Keyword rules, same spirit as gender_map.py —
tune the marker lists as the catalog grows. Tested standalone — see
tests/data/scrape/test_formality_map.py.
"""

from __future__ import annotations

from outfitmatch.vocab import FORMALITY_SET

# Strong activewear signals (checked first — a sporty item is athletic even if a
# formal-sounding token also appears).
ATHLETIC_MARKERS: tuple[str, ...] = (
    "thể thao",
    "sport",
    "gym",
    "jogger",
    "training",
    "running",
    "legging",
    "tập luyện",
    "active",
    "yoga",
    "sneaker",
    "giày chạy",
)
# Strong formal / occasion-wear signals.
FORMAL_MARKERS: tuple[str, ...] = (
    "vest",
    "veston",
    "blazer",
    "suit",
    "tuxedo",
    "áo dài",
    "dạ hội",
    "dự tiệc",
    "công sở",
    "lễ phục",
    "giày tây",
)
# Smart-casual: between casual and formal.
SMART_CASUAL_MARKERS: tuple[str, ...] = (
    "polo",
    "sơ mi",
    "chinos",
    "chino",
    "cardigan",
    "blouse",
    "quần tây",
    "quần âu",
    "cao gót",
    "loafer",
)


def infer_formality(
    title: str,
    product_type: str = "",
    category: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Best-effort dress formality → one of FORMALITY. Default ``casual``."""
    text = f"{title} {product_type} {' '.join(tags or [])}".lower()
    if any(m in text for m in ATHLETIC_MARKERS):
        return "athletic"
    if any(m in text for m in FORMAL_MARKERS):
        return "formal"
    if any(m in text for m in SMART_CASUAL_MARKERS):
        return "smart_casual"
    result = "casual"
    assert result in FORMALITY_SET
    return result
