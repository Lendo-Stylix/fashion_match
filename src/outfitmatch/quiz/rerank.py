"""Preference-based outfit re-ranking for v3.1-lite Tầng 4.

Applies a simple additive scoring on top of compatibility_score
based on the user's PreferenceProfile from the onboarding quiz.
"""

from __future__ import annotations

from outfitmatch.kb.schema import OutfitRecord
from outfitmatch.quiz.schema import PreferenceProfile

# Scoring weights — tune during Sprint 8 if needed
_STYLE_BOOST = 0.10
_OCCASION_BOOST = 0.10
_COLOR_BOOST = 0.05
_PRICE_TIER_PENALTY = 0.10


def score_outfit_for_preference(outfit: OutfitRecord, pref: PreferenceProfile) -> float:
    """Score an outfit against a user preference profile.

    Base: outfit.compatibility_score (from OutfitTransformer).
    Boosts for style/occasion/color matches; penalty for wrong price tier.
    """
    score = outfit.compatibility_score

    style_matches = sum(1 for s in pref.style_priority if s in outfit.style)
    score += _STYLE_BOOST * style_matches

    occ_matches = sum(1 for o in pref.occasion_priority if o in outfit.occasion)
    score += _OCCASION_BOOST * occ_matches

    if pref.color_priority:
        color_matches = sum(
            1
            for c in pref.color_priority
            if any(c.lower() in pc.lower() for pc in outfit.color_palette)
        )
        score += _COLOR_BOOST * color_matches

    if pref.price_tier and outfit.price_tier != pref.price_tier:
        score -= _PRICE_TIER_PENALTY

    return score


def rerank_by_preference(
    outfits: list[OutfitRecord],
    pref: PreferenceProfile,
    top_k: int = 5,
) -> list[OutfitRecord]:
    """Re-rank a list of candidate outfits by preference score and return top_k.

    Call after Tầng 3 returns 30–50 Qdrant results.
    """
    scored = [(o, score_outfit_for_preference(o, pref)) for o in outfits]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [o for o, _ in scored[:top_k]]
