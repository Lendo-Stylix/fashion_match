from __future__ import annotations

from outfitmatch.stylist.tools import (
    SEARCH_OUTFITS_TOOL,
    TOOL_CALL_CLOSE,
    TOOL_CALL_OPEN,
    parse_tool_call_text,
    render_search_outfits_tool_call,
    validate_tool_call_payload,
)
from outfitmatch.stylist.validation import extract_tool_calls, validate_tool_calls


def test_render_search_outfits_tool_call_uses_canonical_text_format() -> None:
    rendered = render_search_outfits_tool_call(
        {
            "occasion": "office",
            "style": "minimalist",
            "price_max": 900000,
        }
    )

    assert rendered == (
        '<tool_call>{"name":"search_outfits","arguments":'
        '{"occasion":"office","style":"minimalist","price_max":900000}}</tool_call>'
    )
    assert rendered.startswith(TOOL_CALL_OPEN)
    assert rendered.endswith(TOOL_CALL_CLOSE)


def test_parse_tool_call_text_accepts_trailing_natural_language() -> None:
    text = (
        '<tool_call>{"name":"search_outfits","arguments":'
        '{"occasion":"date","style":"elegant"}}</tool_call>'
        " Mình sẽ tìm outfit phù hợp trước."
    )

    assert parse_tool_call_text(text) == {
        "name": "search_outfits",
        "arguments": {"occasion": "date", "style": "elegant"},
    }


def test_validate_tool_call_payload_accepts_required_only() -> None:
    ok, errors = validate_tool_call_payload(
        {
            "name": "search_outfits",
            "arguments": {"occasion": "travel"},
        }
    )

    assert ok is True
    assert errors == []


def test_validate_tool_call_payload_rejects_extra_keys() -> None:
    ok, errors = validate_tool_call_payload(
        {
            "name": "search_outfits",
            "arguments": {"occasion": "office", "season": "summer"},
            "id": "tool_1",
        }
    )

    assert ok is False
    assert any("unsupported top-level keys" in error for error in errors)
    assert any("unsupported arguments" in error for error in errors)


def test_validate_tool_call_payload_rejects_missing_required_and_bad_enum() -> None:
    ok, errors = validate_tool_call_payload(
        {
            "name": "search_outfits",
            "arguments": {"style": "not_in_vocab"},
        }
    )

    assert ok is False
    assert any(error == "missing required arguments: occasion" for error in errors)
    assert any(error.startswith("style must be one of:") for error in errors)


def test_validate_tool_call_payload_rejects_non_integer_price_and_bad_colors() -> None:
    ok, errors = validate_tool_call_payload(
        {
            "name": "search_outfits",
            "arguments": {
                "occasion": "party",
                "price_max": "900000",
                "exclude_colors": ["đỏ", 7],
            },
        }
    )

    assert ok is False
    assert "price_max must be an integer" in errors
    assert "exclude_colors must be an array of strings" in errors


def test_validate_tool_calls_reports_invalid_json() -> None:
    ok, errors = validate_tool_calls(
        '<tool_call>{"name":"search_outfits","arguments":{"occasion":"office",}}</tool_call>'
    )

    assert ok is False
    assert any("invalid JSON" in error for error in errors)


def test_extract_tool_calls_returns_all_valid_payloads() -> None:
    text = " ".join(
        [
            render_search_outfits_tool_call({"occasion": "office"}),
            render_search_outfits_tool_call({"occasion": "travel", "style": "casual"}),
        ]
    )

    assert extract_tool_calls(text) == [
        {"name": "search_outfits", "arguments": {"occasion": "office"}},
        {
            "name": "search_outfits",
            "arguments": {"occasion": "travel", "style": "casual"},
        },
    ]


def test_validate_tool_calls_accepts_existing_dataset_shape() -> None:
    assistant = (
        '<tool_call>{"name": "search_outfits", "arguments": '
        '{"occasion": "office", "style": "elegant", "price_max": 900000}}</tool_call>'
        " Tôi sẽ tìm outfit phù hợp trước."
    )

    ok, errors = validate_tool_calls(assistant)
    assert ok is True
    assert errors == []


def test_tool_contract_matches_schema_name() -> None:
    assert SEARCH_OUTFITS_TOOL["function"]["name"] == "search_outfits"
