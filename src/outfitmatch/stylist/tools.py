"""Qwen3-VL tool definitions for outfit search.

All enum parameters are populated directly from vocab.py to guarantee
consistency with Qdrant payload indexes.
"""
from __future__ import annotations

from outfitmatch.vocab import BODY_SHAPE, OCCASION, SKIN_TONE, STYLE

SEARCH_OUTFITS_TOOL: dict = {
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
