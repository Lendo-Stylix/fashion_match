"""Heuristic mapper: product title / type / tags → ITEM_CATEGORY enum.

The mapper combines title + product_type + tags into one lowercased keyword
blob and tries category-specific keyword groups (Vietnamese + English).
Returns None when no group hits — caller decides whether to drop or default.

Tested standalone (no network) — see tests/data/scrape/test_category_map.py.
"""

from __future__ import annotations

from outfitmatch.vocab import ITEM_CATEGORY_SET

# Ordered: first hit wins. Order matters — `dress` before `top` so "đầm" doesn't get
# mis-classified, `outerwear` before `top` so "áo khoác" doesn't fall into "top".
CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "dress",
        (
            "dress", "gown", "robe",
            "đầm", "dam ", "váy liền", "vay lien", "jumpsuit", "yếm",
        ),
    ),
    (
        "outerwear",
        (
            "outerwear", "jacket", "coat", "blazer", "cardigan", "trench",
            "hoodie", "sweater", "puffer", "windbreaker", "parka",
            "áo khoác", "ao khoac", "áo vest", "ao vest", "áo len", "ao len",
            "khoac",
        ),
    ),
    (
        "shoes",
        (
            "shoe", "shoes", "sneaker", "boot", "loafer", "heel", "heels",
            "sandal", "slipper", "mule", "oxford",
            "giày", "giay", "dép", "dep", "boots",
        ),
    ),
    (
        "bag",
        (
            "bag", "handbag", "tote", "backpack", "crossbody", "clutch", "wallet",
            "purse", "shoulder bag",
            "túi", "tui", "ví", "vi ", "balo", "ba lô",
        ),
    ),
    (
        "accessory",
        (
            "accessory", "hat", "cap", "scarf", "belt", "sunglasses", "glasses",
            "watch", "jewelry", "necklace", "earring", "ring", "bracelet",
            "phụ kiện", "phu kien", "mũ", "mu ", "nón", "non ", "thắt lưng",
            "that lung", "khăn", "khan", "vớ", "vo ", "tất", "tat ",
        ),
    ),
    (
        "bottom",
        (
            "pant", "pants", "jean", "jeans", "trouser", "trousers", "short",
            "shorts", "skirt", "legging", "leggings", "chino", "culottes",
            "quần", "quan ", "chân váy", "chan vay", "váy bút chì",
        ),
    ),
    (
        "top",
        (
            "top", "tee", "t-shirt", "tshirt", "shirt", "blouse", "polo",
            "tank", "crop", "knit", "tank top", "long sleeve", "short sleeve",
            "áo thun", "ao thun", "áo sơ mi", "ao so mi", "áo phông", "ao phong",
            "áo polo", "ao polo", "áo", "ao ",  # generic VN "áo" last in this group
        ),
    ),
)


def categorize(title: str, product_type: str = "", tags: list[str] | None = None) -> str | None:
    """Return an ITEM_CATEGORY value or None when nothing matched.

    Matching is purely substring; the order in CATEGORY_KEYWORDS dictates priority.
    """
    blob_parts = [title or "", product_type or ""]
    if tags:
        blob_parts.extend(str(t) for t in tags)
    blob = " ".join(blob_parts).lower()
    # Normalize a few VN diacritics-removed forms by collapsing whitespace
    blob = " " + " ".join(blob.split()) + " "
    for category, keywords in CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in blob:
                assert category in ITEM_CATEGORY_SET, f"Bad category constant: {category}"
                return category
    return None


def is_valid_category(value: str) -> bool:
    return value in ITEM_CATEGORY_SET
