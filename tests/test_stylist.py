from __future__ import annotations

from outfitmatch.stylist.tools import SEARCH_OUTFITS_TOOL
from outfitmatch.stylist.validation import extract_outfit_ids, validate_response
from outfitmatch.vocab import OCCASION, STYLE, BODY_SHAPE, SKIN_TONE


def test_search_outfits_tool_has_required_fields():
    fn = SEARCH_OUTFITS_TOOL["function"]
    assert fn["name"] == "search_outfits"
    params = fn["parameters"]["properties"]
    assert "occasion" in params
    assert "style" in params
    assert "body_shape" in params
    assert "price_max" in params
    assert "exclude_colors" in params
    assert fn["parameters"]["required"] == ["occasion"]


def test_search_outfits_tool_occasion_enum_matches_vocab():
    params = SEARCH_OUTFITS_TOOL["function"]["parameters"]["properties"]
    assert set(params["occasion"]["enum"]) == set(OCCASION)


def test_search_outfits_tool_style_enum_matches_vocab():
    params = SEARCH_OUTFITS_TOOL["function"]["parameters"]["properties"]
    assert set(params["style"]["enum"]) == set(STYLE)


def test_extract_outfit_ids_finds_valid_ids():
    text = "Gợi ý bộ OF_00001 và OF_12345 cho bạn."
    assert extract_outfit_ids(text) == ["OF_00001", "OF_12345"]


def test_extract_outfit_ids_empty_text():
    assert extract_outfit_ids("không có id nào") == []


def test_validate_response_all_valid():
    valid_ids = {"OF_00001", "OF_00002"}
    ok, invalid = validate_response("Đây là bộ OF_00001 và OF_00002.", valid_ids)
    assert ok is True
    assert invalid == []


def test_validate_response_detects_hallucination():
    valid_ids = {"OF_00001"}
    ok, invalid = validate_response("Đây là bộ OF_00001 và OF_99999.", valid_ids)
    assert ok is False
    assert "OF_99999" in invalid


def test_validate_response_no_ids_is_valid():
    ok, invalid = validate_response("Xin chào, bạn cần giúp gì?", {"OF_00001"})
    assert ok is True
    assert invalid == []
