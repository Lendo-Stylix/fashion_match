"""Quiz-based cold-start preference collection (v3.1-lite Tầng 4).

5-question onboarding quiz captures style, occasion, color, budget, and body info.
Answers are mapped to a PreferenceProfile used by rerank.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QuizAnswers:
    """Raw answers from the 5-question onboarding quiz."""

    style: list[str]          # STYLE enum values, up to 2  (Q1: phong cách yêu thích)
    occasions: list[str]      # OCCASION enum values, up to 2 (Q2: dịp mặc thường xuyên)
    favorite_colors: list[str]  # free-form, up to 3 (Q3: màu ưa thích)
    price_tier: str           # PRICE_TIER enum value (Q4: ngân sách)
    height_cm: int | None = None   # Q5: chiều cao
    weight_kg: int | None = None   # Q5: cân nặng


@dataclass
class PreferenceProfile:
    """Normalised preference profile derived from quiz answers.

    Used by rerank.py as the scoring basis.
    """

    style_priority: list[str]
    occasion_priority: list[str]
    color_priority: list[str]
    price_tier: str
    body_shape: str | None = None   # derived from height/weight if both provided


def quiz_to_profile(answers: QuizAnswers) -> PreferenceProfile:
    """Convert raw QuizAnswers to a PreferenceProfile.

    Body shape derivation from height/weight is intentionally simple for MVP:
    use the existing src/outfitmatch/body/shape_rules.py classifier if a full-body
    image is later provided; here we just carry through height/weight for future use.
    """
    return PreferenceProfile(
        style_priority=list(answers.style),
        occasion_priority=list(answers.occasions),
        color_priority=list(answers.favorite_colors),
        price_tier=answers.price_tier,
        body_shape=None,  # populated later via body module if full-body image provided
    )
