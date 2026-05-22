from __future__ import annotations

from outfitmatch.vocab import (
    BODY_SHAPE,
    BODY_SHAPE_LABELS_VI,
    BODY_SHAPE_SET,
    OCCASION,
    OCCASION_LABELS_VI,
    OCCASION_SET,
    PRICE_TIER,
    PRICE_TIER_SET,
    SEASON,
    SEASON_SET,
    SKIN_TONE,
    SKIN_TONE_SET,
    STYLE,
    STYLE_LABELS_VI,
    STYLE_SET,
    ITEM_CATEGORY,
    ITEM_CATEGORY_SET,
    validate_enum_values,
)
from outfitmatch.preference.schema import BODY_FALLBACK


def test_all_enum_values_are_english_snake_case():
    all_enums = list(OCCASION) + list(STYLE) + list(BODY_SHAPE) + list(SEASON) + list(PRICE_TIER) + list(ITEM_CATEGORY) + list(SKIN_TONE)
    for v in all_enums:
        assert v == v.lower() and " " not in v, f"Bad enum value: {v!r}"


def test_sets_match_tuples():
    assert OCCASION_SET == frozenset(OCCASION)
    assert STYLE_SET == frozenset(STYLE)
    assert BODY_SHAPE_SET == frozenset(BODY_SHAPE)
    assert SEASON_SET == frozenset(SEASON)
    assert PRICE_TIER_SET == frozenset(PRICE_TIER)
    assert ITEM_CATEGORY_SET == frozenset(ITEM_CATEGORY)
    assert SKIN_TONE_SET == frozenset(SKIN_TONE)


def test_validate_enum_splits_valid_and_invalid():
    valid, invalid = validate_enum_values(["office", "bogus_value", "date"], OCCASION_SET)
    assert valid == ["office", "date"]
    assert invalid == ["bogus_value"]


def test_validate_enum_empty_input():
    valid, invalid = validate_enum_values([], OCCASION_SET)
    assert valid == []
    assert invalid == []


def test_all_occasions_have_vi_label():
    for v in OCCASION:
        assert v in OCCASION_LABELS_VI, f"Missing VI label for occasion: {v!r}"


def test_all_styles_have_vi_label():
    for v in STYLE:
        assert v in STYLE_LABELS_VI, f"Missing VI label for style: {v!r}"


def test_body_shape_consistent_with_preference_schema():
    """Every shape in preference/schema.py BODY_FALLBACK must exist in vocab.BODY_SHAPE_SET."""
    for shape in BODY_FALLBACK:
        assert shape in BODY_SHAPE_SET, (
            f"Body shape {shape!r} is in preference/schema.py BODY_FALLBACK "
            "but not in vocab.BODY_SHAPE — add it or align schemas."
        )


def test_price_tier_values():
    assert set(PRICE_TIER) == {"budget", "mid", "premium"}
