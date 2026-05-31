"""Store-native `product_type` → ITEM_CATEGORY mapping.

Each store ships its own product taxonomy. That taxonomy is usually MORE
reliable than parsing the free-text title, and it is the only thing that can:

  * distinguish "váy" (skirt → bottom) from "đầm" (dress) — e.g. rubies codes
    ``VQ`` (váy quần / skort), ``VD`` (váy dài), ``VN`` (váy ngắn) are all
    bottoms, while ``DD`` / ``DN`` (đầm) are dresses;
  * drop out-of-scope SKUs that a title heuristic wrongly keeps — underwear
    (``Quần Briefs``, ``INNERWEAR``, ``bra``), phone cases, perfume, gift
    vouchers, keychains and 2-piece sets (``Bộ Suits``, ``clothing set``).

Resolution priority used by ``resolve_category``:
    1. store-native ``product_type`` (this module)  ── authoritative
    2. title-token categoriser (``category_map.categorize``)  ── fallback

Tested standalone — see tests/data/scrape/test_store_category_map.py.
"""

from __future__ import annotations

import re

from outfitmatch.vocab import ITEM_CATEGORY_SET

from .category_map import categorize

# Sentinel: the store explicitly sells something we do NOT model → drop the item
# (vs. None which means "store has no usable opinion, fall back to the title").
DROP = "__drop__"

_WS_RE = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").strip().lower())


# ── Per-store overrides (highest priority) ───────────────────────────────────
# rubies (Haravan) ships 2-letter SKU codes as product_type. Decoded by
# cross-referencing the product name with the store's own taxonomy.
STORE_OVERRIDE: dict[str, dict[str, str]] = {
    "rubies": {
        "ak": "top",  # Áo Kiểu
        "at": "top",  # Áo Thun
        "as": "top",  # Áo Sơ Mi
        "dk": "top",  # Áo Dệt Kim
        "ad": "top",  # Áo
        "dd": "dress",  # Đầm Dài
        "dn": "dress",  # Đầm Ngắn
        "jn": "dress",  # Jumpsuit
        "qd": "bottom",  # Quần Dài
        "qj": "bottom",  # Quần Jeans
        "qn": "bottom",  # Quần Ngắn
        "vq": "bottom",  # Váy Quần (skort)
        "vd": "bottom",  # Váy Dài (skirt)
        "vn": "bottom",  # Váy Ngắn (skirt)
        "kb": "outerwear",  # Áo Khoác Blazer
        "kk": "outerwear",  # Áo Khoác Kiểu
        "pc": "accessory",  # Phụ Kiện
        "sq": DROP,  # Set Áo và Quần (2-piece)
    },
}

# ── Out-of-scope product types (drop the item) ───────────────────────────────
# Exact normalized values.
OUT_OF_SCOPE_EXACT: frozenset[str] = frozenset(
    {
        "bra",
        "set",
        "clothing set",
        "swimwear",
        "innerwear",
        "boxer",
        "briefs",
        "quần boxer",
        "quần briefs",
        "đồ lót nam",
        "bộ suits",
        "bộ đồ",
        "nước hoa",
        "quà tặng",
        "gift voucher tiền mặt",
        "móc treo chìa khóa",
    }
)
# Substring markers (unambiguous) for the long free-text taxonomies (aristino).
OUT_OF_SCOPE_MARKERS: tuple[str, ...] = (
    "phone case",
    "ốp lưng",
    "innerwear",
    "đồ lót",
    "briefs",
    "boxer",
    "swimwear",
    "nước hoa",
    "perfume",
    "voucher",
    "gift voucher",
    "móc treo",
    "keychain",
    "bộ suit",
)

# ── Generic product_type → category (exact normalized) ───────────────────────
GENERIC_TYPE_MAP: dict[str, str] = {
    # dress
    "dress": "dress",
    "dresses": "dress",
    "gown": "dress",
    "jumpsuit": "dress",
    "playsuit": "dress",
    "romper": "dress",
    "đầm": "dress",
    "đầm dài": "dress",
    "đầm ngắn": "dress",
    "váy liền": "dress",
    "áo dài": "dress",
    # top
    "top": "top",
    "tops": "top",
    "t-shirts": "top",
    "t-shirt": "top",
    "tshirt": "top",
    "tee": "top",
    "tees": "top",
    "polo": "top",
    "polos": "top",
    "tank top": "top",
    "tanktop": "top",
    "longsleeves": "top",
    "sweatshirt": "top",
    "sweatshirts": "top",
    "shirt": "top",
    "shirts": "top",
    "jersey": "top",
    "flannel": "top",
    "knit": "top",
    "blouse": "top",
    "corset": "top",
    "bodysuit": "top",
    "camisole": "top",
    "áo sơ mi dài tay": "top",
    "áo sơ mi ngắn tay": "top",
    "áo polo ngắn tay": "top",
    "áo polo dài tay": "top",
    "áo thun ngắn tay": "top",
    "áo thun dài tay": "top",
    "áo tanktop": "top",
    "áo kiểu": "top",
    "áo dệt kim": "top",
    "áo nỉ sweatshirt": "top",
    "áo halfzip": "top",
    "áo gile": "top",
    # bottom
    "pant": "bottom",
    "pants": "bottom",
    "jean": "bottom",
    "jeans": "bottom",
    "short": "bottom",
    "shorts": "bottom",
    "skirt": "bottom",
    "skirts": "bottom",
    "trousers": "bottom",
    "leggings": "bottom",
    "bottom": "bottom",
    "quần âu": "bottom",
    "quần short": "bottom",
    "quần kaki": "bottom",
    "quần jeans": "bottom",
    "quần dài": "bottom",
    "quần ngắn": "bottom",
    "quần rời dệt kim": "bottom",
    "quần thu đông": "bottom",
    "quần giữ nhiệt": "bottom",
    "váy quần": "bottom",
    "váy dài": "bottom",
    "váy ngắn": "bottom",
    "chân váy": "bottom",
    # outerwear
    "jacket": "outerwear",
    "jackets": "outerwear",
    "hoodie": "outerwear",
    "hoodies": "outerwear",
    "coat": "outerwear",
    "blazer": "outerwear",
    "cardigan": "outerwear",
    "cardigans": "outerwear",
    "sweater": "outerwear",
    "sweaters": "outerwear",
    "parka": "outerwear",
    "áo khoác": "outerwear",
    "áo blazer": "outerwear",
    "áo vest": "outerwear",
    "áo len": "outerwear",
    "áo nỉ": "outerwear",
    # shoes
    "slides": "shoes",
    "sandal": "shoes",
    "sandals": "shoes",
    "sneaker": "shoes",
    "sneakers": "shoes",
    "boot": "shoes",
    "boots": "shoes",
    "loafer": "shoes",
    "loafers": "shoes",
    "giày da": "shoes",
    "giày loafer": "shoes",
    "giày moca": "shoes",
    "giày sneaker": "shoes",
    "giày derby": "shoes",
    "giày oxford": "shoes",
    "giày monkstraps": "shoes",
    "giày sục mules": "shoes",
    "giày slip-on": "shoes",
    "giày chelsea boot": "shoes",
    "giày desert boot": "shoes",
    "dép quai chéo": "shoes",
    "dép hai quai ngang": "shoes",
    # bag
    "bowler bags": "bag",
    "backpacks": "bag",
    "crossbody bags": "bag",
    "mini pouch": "bag",
    "túi đeo chéo": "bag",
    "túi cầm tay": "bag",
    "túi tote": "bag",
    "túi du lịch": "bag",
    "túi đeo hông": "bag",
    "ví": "bag",
    "ví ngang": "bag",
    "ví đứng": "bag",
    "ví đựng thẻ": "bag",
    "ví đựng card": "bag",
    "ví đựng hộ chiếu": "bag",
    "bóp tay": "bag",
    "cặp da": "bag",
    "ba lô": "bag",
    "travel wallet": "bag",
    # accessory
    "accessory": "accessory",
    "accessories": "accessory",
    "cap": "accessory",
    "caps": "accessory",
    "beanie": "accessory",
    "beanies": "accessory",
    "jewelry": "accessory",
    "sock": "accessory",
    "socks": "accessory",
    "phụ kiện": "accessory",
    "cà vạt": "accessory",
    "kẹp cà vạt": "accessory",
    "dây lưng lẻ": "accessory",
    "mặt dây lưng": "accessory",
    "thắt lưng": "accessory",
    "tất nam": "accessory",
    "khăn lụa nam": "accessory",
    "khăn quàng cổ": "accessory",
    "mũ lưỡi trai": "accessory",
    "ghim cài áo": "accessory",
}

# ── Keyword fallback for long free-text taxonomies (aristino's 77 values) ─────
# Ordered: outerwear/shoes/bag/accessory head-nouns BEFORE the generic "áo"/"quần".
KEYWORD_FALLBACK: tuple[tuple[str, str], ...] = (
    ("áo khoác", "outerwear"),
    ("blazer", "outerwear"),
    ("áo vest", "outerwear"),
    ("áo len", "outerwear"),
    ("áo nỉ", "outerwear"),
    ("cardigan", "outerwear"),
    ("hoodie", "outerwear"),
    ("giày", "shoes"),
    ("dép", "shoes"),
    ("sandal", "shoes"),
    ("sneaker", "shoes"),
    ("boot", "shoes"),
    ("loafer", "shoes"),
    ("túi", "bag"),
    ("ví", "bag"),
    ("ba lô", "bag"),
    ("balo", "bag"),
    ("cặp", "bag"),
    ("bóp", "bag"),
    ("backpack", "bag"),
    ("pouch", "bag"),
    ("cà vạt", "accessory"),
    ("dây lưng", "accessory"),
    ("thắt lưng", "accessory"),
    ("phụ kiện", "accessory"),
    ("mũ", "accessory"),
    ("nón", "accessory"),
    ("khăn", "accessory"),
    ("tất", "accessory"),
    ("vớ", "accessory"),
    ("ghim cài", "accessory"),
    ("jewelry", "accessory"),
    ("watch", "accessory"),
    ("đầm", "dress"),
    ("jumpsuit", "dress"),
    ("váy", "bottom"),
    ("quần", "bottom"),
    ("skirt", "bottom"),
    ("pant", "bottom"),
    ("jean", "bottom"),
    ("short", "bottom"),
    ("áo", "top"),
    ("shirt", "top"),
    ("polo", "top"),
    ("tee", "top"),
)


def category_from_store_type(product_type: str, store_id: str = "") -> str | None:
    """Map a store-native product_type → category, ``DROP``, or None.

    Returns:
        * a valid ITEM_CATEGORY value — confident store classification;
        * ``DROP`` — store sells an out-of-scope SKU (caller should drop it);
        * ``None`` — store gave no usable signal (caller falls back to title).
    """
    norm = _norm(product_type)
    if not norm:
        return None

    override = STORE_OVERRIDE.get(store_id, {})
    if norm in override:
        return override[norm]

    if norm in OUT_OF_SCOPE_EXACT or any(m in norm for m in OUT_OF_SCOPE_MARKERS):
        return DROP

    if norm in GENERIC_TYPE_MAP:
        return GENERIC_TYPE_MAP[norm]

    for kw, category in KEYWORD_FALLBACK:
        if kw in norm:
            return category
    return None


def resolve_category(
    title: str,
    product_type: str = "",
    tags: list[str] | None = None,
    store_id: str = "",
) -> str | None:
    """Resolve final ITEM_CATEGORY: store product_type first, title as fallback.

    Returns None when the item is out-of-scope or nothing classifies it — the
    caller drops it.
    """
    store_cat = category_from_store_type(product_type, store_id)
    if store_cat == DROP:
        return None
    if store_cat is not None:
        assert store_cat in ITEM_CATEGORY_SET, f"Bad category constant: {store_cat}"
        return store_cat
    return categorize(title, product_type, tags)
