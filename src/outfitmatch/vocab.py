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

FORMALITY: tuple[str, ...] = (
    "athletic",
    "casual",
    "smart_casual",
    "formal",
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
FORMALITY_SET: frozenset[str] = frozenset(FORMALITY)

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

FORMALITY_LABELS_VI: dict[str, str] = {
    "athletic": "thể thao",
    "casual": "thường ngày",
    "smart_casual": "lịch sự nhẹ",
    "formal": "trang trọng",
}


def validate_enum_values(values: list[str], allowed: frozenset[str]) -> tuple[list[str], list[str]]:
    """Split values into (valid, invalid) based on membership in allowed set.

    Used by LLM-tagging pipeline to reject stray values before writing to KB.
    """
    valid = [v for v in values if v in allowed]
    invalid = [v for v in values if v not in allowed]
    return valid, invalid


# Formality ladder for outfit-coherence filtering. Items in one outfit must stay
# within FORMALITY_TOLERANCE steps on this ordinal ladder
# (athletic < casual < smart_casual < formal); otherwise the combo is incoherent
# (e.g. blazer + gym shorts). Only FORMALITY_RELEVANT_CATEGORIES participate;
# bags/accessories are style-neutral and ignored.
FORMALITY_RANK: dict[str, int] = {name: i for i, name in enumerate(FORMALITY)}
FORMALITY_RELEVANT_CATEGORIES: frozenset[str] = frozenset(
    {"top", "bottom", "dress", "shoes", "outerwear"}
)
FORMALITY_TOLERANCE: int = 1


def formality_span_ok(formalities: list[str], tolerance: int = FORMALITY_TOLERANCE) -> bool:
    """True if all formalities sit within ``tolerance`` steps on the ladder.

    Unknown values are ignored; an empty / all-unknown list is considered OK.
    """
    ranks = [FORMALITY_RANK[f] for f in formalities if f in FORMALITY_RANK]
    if not ranks:
        return True
    return max(ranks) - min(ranks) <= tolerance


# Coarse formality → admissible occasions. Graph nodes carry no per-item occasion
# tag, so retrieval derives occasion fit from an item's formality band. Keep every
# value inside OCCASION.
FORMALITY_OCCASIONS: dict[str, frozenset[str]] = {
    "athletic": frozenset({"home_casual", "travel", "school"}),
    "casual": frozenset({"school", "cafe_hangout", "home_casual", "travel", "date"}),
    "smart_casual": frozenset({"office", "interview", "school", "date", "cafe_hangout", "party"}),
    "formal": frozenset({"office", "interview", "wedding", "party", "date"}),
}


def occasions_for_formality(formality: str) -> frozenset[str]:
    """Occasions a given formality band is appropriate for (⊆ OCCASION)."""
    return FORMALITY_OCCASIONS.get(formality, frozenset())


def formalities_for_occasion(occasion: str) -> set[str]:
    """Inverse: formality bands whose items suit ``occasion`` (for seed filtering)."""
    return {
        formality for formality, occasions in FORMALITY_OCCASIONS.items() if occasion in occasions
    }
