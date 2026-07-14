"""GET /api/quiz — return quiz questions + enum options."""

from __future__ import annotations

from fastapi import APIRouter

from outfitmatch.vocab import (
    OCCASION,
    OCCASION_LABELS_VI,
    PRICE_TIER,
    PRICE_TIER_LABELS_VI,
    STYLE,
    STYLE_LABELS_VI,
)

router = APIRouter()


@router.get("")
async def get_quiz() -> dict:
    """Return 5 quiz questions with enum options."""
    return {
        "questions": [
            {
                "key": "style",
                "label_vi": "Bạn thích phong cách nào?",
                "type": "multi_select",
                "max": 2,
                "options": [{"id": s, "label_vi": STYLE_LABELS_VI.get(s, s)} for s in STYLE],
            },
            {
                "key": "occasions",
                "label_vi": "Bạn thường mặc vào dịp nào?",
                "type": "multi_select",
                "max": 2,
                "options": [{"id": o, "label_vi": OCCASION_LABELS_VI.get(o, o)} for o in OCCASION],
            },
            {
                "key": "favorite_colors",
                "label_vi": "Bạn thích màu nào?",
                "type": "text_multi",
                "max": 3,
                "options": [],
            },
            {
                "key": "price_tier",
                "label_vi": "Ngân sách của bạn?",
                "type": "single_select",
                "options": [
                    {"id": p, "label_vi": PRICE_TIER_LABELS_VI.get(p, p)} for p in PRICE_TIER
                ],
            },
            {
                "key": "body",
                "label_vi": "Chiều cao và cân nặng (tùy chọn)",
                "type": "number_pair",
                "fields": ["height_cm", "weight_kg"],
            },
        ]
    }
