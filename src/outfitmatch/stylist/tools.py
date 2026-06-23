"""Qwen3-VL tool definitions for outfit search.

All enum parameters are populated directly from vocab.py to guarantee
consistency with Qdrant payload indexes.

This module is also the single source of truth for the tool-call wire format
used in fine-tuning data:

<tool_call>{"name":"search_outfits","arguments":{...}}</tool_call>
"""

from __future__ import annotations

import json
import re
from typing import Any

from outfitmatch.vocab import BODY_SHAPE, OCCASION, SKIN_TONE, STYLE

TOOL_CALL_OPEN = "<tool_call>"
TOOL_CALL_CLOSE = "</tool_call>"
TOOL_RESPONSE_OPEN = "<tool_response>"
TOOL_RESPONSE_CLOSE = "</tool_response>"
TOOL_CALL_PATTERN = re.compile(
    rf"{re.escape(TOOL_CALL_OPEN)}\s*(\{{.*?\}})\s*{re.escape(TOOL_CALL_CLOSE)}",
    re.DOTALL,
)

SEARCH_OUTFITS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_outfits",
        "description": "Tìm outfit phù hợp từ Knowledge Base dựa trên các bộ lọc",
        "parameters": {
            "type": "object",
            "properties": {
                "occasion": {
                    "type": "string",
                    "enum": list(OCCASION),
                    "description": "Dịp mặc (bắt buộc)",
                },
                "style": {
                    "type": "string",
                    "enum": list(STYLE),
                    "description": "Phong cách mong muốn",
                },
                "body_shape": {
                    "type": "string",
                    "enum": list(BODY_SHAPE),
                    "description": "Dáng người",
                },
                "skin_tone": {
                    "type": "string",
                    "enum": list(SKIN_TONE),
                    "description": "Tone da",
                },
                "price_max": {
                    "type": "integer",
                    "description": "Ngân sách tối đa (VND)",
                },
                "exclude_colors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Màu sắc cần tránh (vd: ['trắng', 'đỏ'])",
                },
            },
            "required": ["occasion"],
        },
    },
}

_SEARCH_OUTFITS_PARAMETERS = SEARCH_OUTFITS_TOOL["function"]["parameters"]
_SEARCH_OUTFITS_PROPERTIES = _SEARCH_OUTFITS_PARAMETERS["properties"]
ALLOWED_SEARCH_OUTFITS_ARGS: tuple[str, ...] = tuple(_SEARCH_OUTFITS_PROPERTIES)
REQUIRED_SEARCH_OUTFITS_ARGS: tuple[str, ...] = tuple(_SEARCH_OUTFITS_PARAMETERS["required"])
_ENUM_FIELDS: dict[str, frozenset[str]] = {
    name: frozenset(spec["enum"])
    for name, spec in _SEARCH_OUTFITS_PROPERTIES.items()
    if isinstance(spec, dict) and "enum" in spec
}


def validate_tool_call_payload(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate one parsed tool-call payload against the canonical schema."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["payload must be an object"]

    extra_top_level = sorted(set(payload) - {"name", "arguments"})
    if extra_top_level:
        errors.append(f"unsupported top-level keys: {', '.join(extra_top_level)}")

    name = payload.get("name")
    if name != SEARCH_OUTFITS_TOOL["function"]["name"]:
        errors.append("tool name must be search_outfits")

    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        errors.append("arguments must be an object")
        return len(errors) == 0, errors

    extra_args = sorted(set(arguments) - set(ALLOWED_SEARCH_OUTFITS_ARGS))
    if extra_args:
        errors.append(f"unsupported arguments: {', '.join(extra_args)}")

    missing_args = [arg for arg in REQUIRED_SEARCH_OUTFITS_ARGS if arg not in arguments]
    if missing_args:
        errors.append(f"missing required arguments: {', '.join(missing_args)}")

    for key, value in arguments.items():
        if key not in _SEARCH_OUTFITS_PROPERTIES:
            continue
        if key in _ENUM_FIELDS:
            if not isinstance(value, str):
                errors.append(f"{key} must be a string")
            elif value not in _ENUM_FIELDS[key]:
                errors.append(f"{key} must be one of: {', '.join(sorted(_ENUM_FIELDS[key]))}")
        elif key == "price_max":
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append("price_max must be an integer")
            elif value < 0:
                errors.append("price_max must be >= 0")
        elif key == "exclude_colors" and (
            not isinstance(value, list) or any(not isinstance(item, str) for item in value)
        ):
            errors.append("exclude_colors must be an array of strings")

    return len(errors) == 0, errors


def render_search_outfits_tool_call(arguments: dict[str, Any]) -> str:
    """Render the canonical tool-call text for training/inference prompts."""
    payload = {
        "name": SEARCH_OUTFITS_TOOL["function"]["name"],
        "arguments": arguments,
    }
    ok, errors = validate_tool_call_payload(payload)
    if not ok:
        raise ValueError("Invalid search_outfits tool call: " + "; ".join(errors))
    return (
        TOOL_CALL_OPEN
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + TOOL_CALL_CLOSE
    )


def parse_tool_call_text(text: str) -> dict[str, Any] | None:
    """Parse the first canonical tool-call payload found in ``text``."""
    match = TOOL_CALL_PATTERN.search(text)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
