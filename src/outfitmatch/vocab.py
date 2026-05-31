"""Controlled vocabulary for v3.1-lite.

Single source of truth for all enum values used across:
  1. LLM-tagging when building the Knowledge Base
  2. Qwen3-VL tool-call parameters (search_outfits)
  3. Qdrant payload index field values

Rules:
  - Internal values are always English snake_case.
  - Vietnamese labels appear ONLY in *_LABELS_VI dicts and *_vi schema fields.
  - Never rename an existing enum value (it would invalidate the KB).
    Add new values; don't change old ones.
"""

from __future__ import annotations

OCCASION: tuple[str, ...] = (
    "office",
    "interview",
    "school",
    "date",
    "cafe_hangout",
    "party",
    "wedding",
    "home_casual",
    "travel",
)

STYLE: tuple[str, ...] = (
    "minimalist",
    "korean",
    "streetwear",
    "elegant",
    "casual",
    "vintage",
    "sporty",
    "feminine",
)

BODY_SHAPE: tuple[str, ...] = (
    "pear",
    "apple",
    "hourglass",
    "rectangle",
    "inverted_triangle",
)

SEASON: tuple[str, ...] = (
    "summer",
    "transitional",
    "winter",
    "rainy",
)

PRICE_TIER: tuple[str, ...] = (
    "budget",
    "mid",
    "premium",
)

ITEM_CATEGORY: tuple[str, ...] = (
    "top",
    "bottom",
    "dress",
    "outerwear",
    "shoes",
    "bag",
    "accessory",
)

GENDER: tuple[str, ...] = (
    "men",
    "women",
    "unisex",
    "kid",
)

SKIN_TONE: tuple[str, ...] = (
    "warm",
    "neutral",
    "cool",
)

# Frozen sets for O(1) membership checks
OCCASION_SET: frozenset[str] = frozenset(OCCASION)
STYLE_SET: frozenset[str] = frozenset(STYLE)
BODY_SHAPE_SET: frozenset[str] = frozenset(BODY_SHAPE)
SEASON_SET: frozenset[str] = frozenset(SEASON)
PRICE_TIER_SET: frozenset[str] = frozenset(PRICE_TIER)
ITEM_CATEGORY_SET: frozenset[str] = frozenset(ITEM_CATEGORY)
GENDER_SET: frozenset[str] = frozenset(GENDER)
SKIN_TONE_SET: frozenset[str] = frozenset(SKIN_TONE)

# Vietnamese display labels (UI only — never use for filtering or matching)
OCCASION_LABELS_VI: dict[str, str] = {
    "office": "đi làm",
    "interview": "phỏng vấn",
    "school": "đi học",
    "date": "hẹn hò",
    "cafe_hangout": "cafe / dạo phố",
    "party": "tiệc",
    "wedding": "đám cưới",
    "home_casual": "ở nhà / thường ngày",
    "travel": "du lịch",
}

STYLE_LABELS_VI: dict[str, str] = {
    "minimalist": "tối giản",
    "korean": "phong cách Hàn",
    "streetwear": "đường phố",
    "elegant": "thanh lịch",
    "casual": "thường ngày",
    "vintage": "cổ điển",
    "sporty": "thể thao",
    "feminine": "nữ tính",
}

BODY_SHAPE_LABELS_VI: dict[str, str] = {
    "pear": "dáng quả lê",
    "apple": "dáng quả táo",
    "hourglass": "dáng đồng hồ cát",
    "rectangle": "dáng chữ nhật",
    "inverted_triangle": "dáng tam giác ngược",
}

SEASON_LABELS_VI: dict[str, str] = {
    "summer": "mùa hè",
    "transitional": "giao mùa",
    "winter": "mùa đông",
    "rainy": "mùa mưa",
}

PRICE_TIER_LABELS_VI: dict[str, str] = {
    "budget": "bình dân (<300K)",
    "mid": "tầm trung (300K–800K)",
    "premium": "cao cấp (>800K)",
}

GENDER_LABELS_VI: dict[str, str] = {
    "men": "nam",
    "women": "nữ",
    "unisex": "unisex",
    "kid": "trẻ em",
}

SKIN_TONE_LABELS_VI: dict[str, str] = {
    "warm": "da ấm",
    "neutral": "da trung tính",
    "cool": "da lạnh",
}


def validate_enum_values(values: list[str], allowed: frozenset[str]) -> tuple[list[str], list[str]]:
    """Split values into (valid, invalid) based on membership in allowed set.

    Used by LLM-tagging pipeline to reject stray values before writing to KB.
    """
    valid = [v for v in values if v in allowed]
    invalid = [v for v in values if v not in allowed]
    return valid, invalid
