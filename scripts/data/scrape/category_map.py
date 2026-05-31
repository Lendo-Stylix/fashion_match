"""Token-based category mapper: product title → ITEM_CATEGORY enum.

Why not pure substring matching:
    Old version matched substrings anywhere in the title/product_type/tags blob,
    which mis-classified items because feature words ("phối túi", "in giày"),
    descriptive words ("Baggy", "Capri"), and polluted upstream product_type/tags
    ("VUCANI TOP" with product_type="Dresses") would beat the real noun.

Strategy:
    1. Tokenize the title (Unicode word characters, ``-`` kept for "t-shirt").
    2. Walk tokens left-to-right — Vietnamese fashion titles almost always lead
       with the category noun (``Áo``, ``Quần``, ``Đầm``, ``Giày``, ``Túi``…).
       At each position try, in order:
           a. Two-token COMPOUND  ("áo khoác" → outerwear, "chân váy" → bottom,
              "đôi tất" → accessory, "ba lô" → bag).
           b. Single-token PRIMARY (Vietnamese head noun).
           c. ENGLISH_TOKEN (boundary-safe English keyword).
       Return on first hit.
    3. Fall back to product_type tokens, then tags tokens.
    4. Return None — caller drops the item.

Tested standalone — see tests/data/scrape/test_category_map.py.
"""

from __future__ import annotations

import re

from outfitmatch.vocab import ITEM_CATEGORY_SET

# Matches Unicode words (Vietnamese diacritics included) and keeps hyphenated
# tokens like "t-shirt" intact.
_TOKEN_RE = re.compile(r"[\w\-]+", re.UNICODE)

# Two-token compound — checked BEFORE single-token PRIMARY so "áo khoác" beats
# the generic "áo" rule, etc.
COMPOUND_TOKEN: dict[tuple[str, str], str] = {
    ("áo", "khoác"): "outerwear",
    ("áo", "vest"): "outerwear",
    ("áo", "len"): "outerwear",
    ("áo", "nỉ"): "outerwear",
    ("áo", "hoodie"): "outerwear",
    ("áo", "cardigan"): "outerwear",
    ("áo", "blazer"): "outerwear",
    ("áo", "phao"): "outerwear",
    ("áo", "dạ"): "outerwear",
    ("chân", "váy"): "bottom",
    ("ba", "lô"): "bag",
    ("phụ", "kiện"): "accessory",
    ("thắt", "lưng"): "accessory",
    ("đôi", "tất"): "accessory",
    ("đôi", "vớ"): "accessory",
}

# Vietnamese head noun → category. First hit when scanning tokens left-to-right.
PRIMARY_TOKEN: dict[str, str] = {
    "áo": "top",
    "quần": "bottom",
    "đầm": "dress",
    "váy": "dress",
    "yếm": "dress",
    "jumpsuit": "dress",
    "giày": "shoes",
    "dép": "shoes",
    "guốc": "shoes",
    "túi": "bag",
    "balo": "bag",
    "ví": "bag",
    "mũ": "accessory",
    "nón": "accessory",
    "khăn": "accessory",
    "vớ": "accessory",
    "tất": "accessory",
    "kính": "accessory",
}

# Boundary-safe English keyword → category. Hit when an exact token matches.
# Note: "cap" is intentionally NOT here — too many false positives ("Capri",
# "Capricorn"). "Cap" only as accessory when the full token "cap" exists.
ENGLISH_TOKEN: dict[str, str] = {
    # dress
    "dress": "dress",
    "dresses": "dress",
    "gown": "dress",
    "robe": "dress",
    "minidress": "dress",
    "midi-dress": "dress",
    "maxidress": "dress",
    "playsuit": "dress",
    "romper": "dress",
    "sundress": "dress",
    # outerwear
    "jacket": "outerwear",
    "coat": "outerwear",
    "blazer": "outerwear",
    "cardigan": "outerwear",
    "hoodie": "outerwear",
    "sweater": "outerwear",
    "puffer": "outerwear",
    "windbreaker": "outerwear",
    "parka": "outerwear",
    "trench": "outerwear",
    # top
    "shirt": "top",
    "shirts": "top",
    "blouse": "top",
    "polo": "top",
    "tee": "top",
    "tees": "top",
    "t-shirt": "top",
    "tshirt": "top",
    "tank": "top",
    "tanktop": "top",
    "crop": "top",
    "top": "top",
    "tops": "top",
    "knit": "top",
    "corset": "top",
    "bikini": "top",
    "sleeve": "top",
    "sweatshirt": "top",
    "bodysuit": "top",
    "camisole": "top",
    # bottom
    "pant": "bottom",
    "pants": "bottom",
    "jean": "bottom",
    "jeans": "bottom",
    "trouser": "bottom",
    "trousers": "bottom",
    "short": "bottom",
    "shorts": "bottom",
    "skirt": "bottom",
    "skirts": "bottom",
    "miniskirt": "bottom",
    "midiskirt": "bottom",
    "maxiskirt": "bottom",
    "legging": "bottom",
    "leggings": "bottom",
    "chino": "bottom",
    "chinos": "bottom",
    "culottes": "bottom",
    "sweatpant": "bottom",
    "sweatpants": "bottom",
    "jogger": "bottom",
    "joggers": "bottom",
    "cargo": "bottom",
    "slacks": "bottom",
    "overalls": "bottom",
    # shoes
    "sneaker": "shoes",
    "sneakers": "shoes",
    "boot": "shoes",
    "boots": "shoes",
    "loafer": "shoes",
    "loafers": "shoes",
    "heel": "shoes",
    "heels": "shoes",
    "sandal": "shoes",
    "sandals": "shoes",
    "slipper": "shoes",
    "slippers": "shoes",
    "mule": "shoes",
    "oxford": "shoes",
    "shoe": "shoes",
    "shoes": "shoes",
    # bag
    "bag": "bag",
    "handbag": "bag",
    "tote": "bag",
    "backpack": "bag",
    "crossbody": "bag",
    "clutch": "bag",
    "wallet": "bag",
    "purse": "bag",
    # accessory
    "hat": "accessory",
    "cap": "accessory",
    "scarf": "accessory",
    "belt": "accessory",
    "sunglasses": "accessory",
    "watch": "accessory",
    "necklace": "accessory",
    "earring": "accessory",
    "earrings": "accessory",
    "ring": "accessory",
    "bracelet": "accessory",
    "sock": "accessory",
    "socks": "accessory",
    "beanie": "accessory",
}


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _category_from_tokens(tokens: list[str]) -> str | None:
    for i, tok in enumerate(tokens):
        if i + 1 < len(tokens):
            compound = COMPOUND_TOKEN.get((tok, tokens[i + 1]))
            if compound:
                return compound
        if tok in PRIMARY_TOKEN:
            return PRIMARY_TOKEN[tok]
        if tok in ENGLISH_TOKEN:
            return ENGLISH_TOKEN[tok]
    return None


def categorize(title: str, product_type: str = "", tags: list[str] | None = None) -> str | None:
    """Return an ITEM_CATEGORY value or None when nothing matched.

    Sources are evaluated in priority order: title → product_type → tags. This
    means a polluted upstream tag/product_type can never override a clean title
    classification.
    """
    sources = (title, product_type, " ".join(str(t) for t in tags or []))
    for src in sources:
        category = _category_from_tokens(_tokenize(src))
        if category:
            assert category in ITEM_CATEGORY_SET, f"Bad category constant: {category}"
            return category
    return None


def is_valid_category(value: str) -> bool:
    return value in ITEM_CATEGORY_SET
