"""Body→size suggestion (v3.1-lite Tầng 4).

Maps quiz height/weight to a recommended alpha clothing size, then intersects
with the item's actually-available sizes. Numeric/footwear sizing is out of
scope for the MVP; only alpha-sized garment categories get a body-derived
suggestion.
"""

from __future__ import annotations

from outfitmatch.kb.schema import ItemRecord

ALPHA_SIZE_CATEGORIES: frozenset[str] = frozenset({"top", "dress", "outerwear"})
_SIZE_LADDER: tuple[str, ...] = ("XS", "S", "M", "L", "XL", "XXL")

_WOMEN_WEIGHT_BANDS: tuple[tuple[int, int], ...] = (
    (43, 0),
    (50, 1),
    (58, 2),
    (67, 3),
    (76, 4),
)
_MEN_WEIGHT_BANDS: tuple[tuple[int, int], ...] = (
    (55, 1),
    (65, 2),
    (75, 3),
    (85, 4),
)


def _base_index(gender: str, weight_kg: int) -> int:
    bands = _MEN_WEIGHT_BANDS if gender == "men" else _WOMEN_WEIGHT_BANDS
    for upper, idx in bands:
        if weight_kg <= upper:
            return idx
    return len(_SIZE_LADDER) - 1


def _height_nudge(gender: str, height_cm: int) -> int:
    tall, short = (183, 160) if gender == "men" else (175, 150)
    if height_cm >= tall:
        return 1
    if height_cm <= short:
        return -1
    return 0


def suggest_size(
    category: str,
    gender: str,
    height_cm: int | None,
    weight_kg: int | None,
    available_sizes: list[str],
) -> str | None:
    """Return the best available alpha size for an item, or ``None``."""
    if category not in ALPHA_SIZE_CATEGORIES:
        return None
    if height_cm is None or weight_kg is None:
        return None
    avail = {s.upper() for s in available_sizes}
    if not avail:
        return None

    idx = _base_index(gender, weight_kg) + _height_nudge(gender, height_cm)
    idx = max(0, min(idx, len(_SIZE_LADDER) - 1))

    for dist in range(len(_SIZE_LADDER)):
        for cand in (idx - dist, idx + dist):
            if 0 <= cand < len(_SIZE_LADDER) and _SIZE_LADDER[cand] in avail:
                return _SIZE_LADDER[cand]
    return None


def suggest_sizes_for_outfit(
    items: list[ItemRecord],
    height_cm: int | None,
    weight_kg: int | None,
) -> dict[str, str]:
    """Return ``item_id → suggested size`` for items whose size can be resolved."""
    out: dict[str, str] = {}
    for item in items:
        avail = [
            str(s)
            for s in (item.store.get("sizes_in_stock") or item.store.get("available_sizes") or [])
        ]
        size = suggest_size(item.category, item.gender, height_cm, weight_kg, avail)
        if size is not None:
            out[item.item_id] = size
    return out
