"""Infer wearer gender for a catalog item.

Why this exists:
    Outfit generation combines a top + bottom + shoes by category only. Without a
    gender signal it will pair a men's shirt with a women's skirt. Stores expose
    gender three ways, in decreasing reliability:

      1. Explicit token in the title / product_type  — "nam", "nữ", "bé trai",
         "unisex", "men", "women", "kid".
      2. Single-gender brand               — aristino (menswear), rubies &
         huelleyrose (womenswear), dirtycoins (unisex streetwear).
      3. Category prior                    — a ``dress`` is women's wear.

Returns one of GENDER: ``men | women | unisex | kid``. ``unisex`` is the safe
fallback — it is allowed to combine with both men's and women's outfits.

Tested standalone — see tests/data/scrape/test_gender_map.py.
"""

from __future__ import annotations

import re

from outfitmatch.vocab import GENDER_SET

_TOKEN_RE = re.compile(r"[\w\-]+", re.UNICODE)

# Single-gender brands: used only when the title has no explicit gender token.
STORE_GENDER_DEFAULT: dict[str, str] = {
    "aristino_vn": "men",
    "rubies": "women",
    "huelleyrose": "women",
    "dirtycoins": "unisex",
    # canifa_vn / yody_vn sell all genders → no default, rely on the title.
}

# Substring markers (Vietnamese phrases) and single-token markers.
KID_MARKERS: tuple[str, ...] = (
    "bé trai",
    "bé gái",
    "trẻ em",
    "thiếu nhi",
    "cho bé",
    "em bé",
    "nhi đồng",
    "baby",
    "trẻ nhỏ",
)
KID_TOKENS: frozenset[str] = frozenset({"kid", "kids", "boy", "boys", "girl", "girls"})
WOMEN_MARKERS: tuple[str, ...] = ("phụ nữ",)
WOMEN_TOKENS: frozenset[str] = frozenset(
    {"nữ", "women", "woman", "womens", "female", "ladies", "lady"}
)
MEN_TOKENS: frozenset[str] = frozenset({"nam", "men", "man", "mens", "male"})

# Strongly women's garments — inferred women even without an explicit "nữ" token
# (helps multi-gender stores like YODY/Canifa where a skirt/heel lacks a token).
WOMEN_LEANING_MARKERS: tuple[str, ...] = (
    "chân váy",
    "váy",
    "đầm",
    "cao gót",
    "cao got",
    "bikini",
    "yếm nữ",
    "crop top",
    "legging",
    "công chúa",
)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def infer_gender(
    title: str,
    product_type: str = "",
    store_id: str = "",
    category: str | None = None,
) -> str:
    """Best-effort wearer gender → one of GENDER (``men|women|unisex|kid``)."""
    text = f"{title} {product_type}".lower()
    toks = _tokens(text)

    if any(m in text for m in KID_MARKERS) or (toks & KID_TOKENS):
        return "kid"
    if "unisex" in text:
        return "unisex"

    has_women = bool(toks & WOMEN_TOKENS) or any(m in text for m in WOMEN_MARKERS)
    has_men = bool(toks & MEN_TOKENS)
    if has_men and not has_women:
        return "men"
    if has_women and not has_men:
        return "women"
    if has_men and has_women:
        return "unisex"  # genuinely ambiguous (e.g. "đôi nam nữ")

    if category == "dress" or any(m in text for m in WOMEN_LEANING_MARKERS):
        return "women"

    store_default = STORE_GENDER_DEFAULT.get(store_id)
    if store_default:
        return store_default

    result = "unisex"
    assert result in GENDER_SET
    return result
