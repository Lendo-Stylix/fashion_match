from __future__ import annotations

from outfitmatch.kb.schema import OutfitRecord
from outfitmatch.quiz.rerank import rerank_by_preference, score_outfit_for_preference
from outfitmatch.quiz.schema import PreferenceProfile, QuizAnswers, quiz_to_profile


def _make_outfit(
    outfit_id: str,
    occasion: list[str],
    style: list[str],
    price_tier: str,
    compat_score: float,
    color_palette: list[str] | None = None,
) -> OutfitRecord:
    return OutfitRecord(
        outfit_id=outfit_id,
        schema_version="3.1",
        items=[],
        outfit_embedding=[],
        compatibility_score=compat_score,
        occasion=occasion,
        style=style,
        body_shapes_fit=[],
        season=[],
        color_palette=color_palette or [],
        price_total_vnd=500000,
        price_tier=price_tier,
        has_vn_store=True,
        stylist_explanation_vi="",
        gen_method="fitb_beam",
    )


def test_quiz_to_profile_maps_fields():
    answers = QuizAnswers(
        style=["minimalist", "korean"],
        occasions=["office"],
        favorite_colors=["beige", "white"],
        price_tier="mid",
        height_cm=160,
        weight_kg=55,
    )
    profile = quiz_to_profile(answers)
    assert profile.style_priority == ["minimalist", "korean"]
    assert profile.occasion_priority == ["office"]
    assert profile.price_tier == "mid"


def test_score_outfit_boosts_style_match():
    profile = PreferenceProfile(
        style_priority=["minimalist"],
        occasion_priority=["office"],
        color_priority=[],
        price_tier="mid",
    )
    outfit_match = _make_outfit("OF_00001", ["office"], ["minimalist"], "mid", 0.8)
    outfit_no_match = _make_outfit("OF_00002", ["party"], ["streetwear"], "mid", 0.8)
    score_match = score_outfit_for_preference(outfit_match, profile)
    score_no_match = score_outfit_for_preference(outfit_no_match, profile)
    assert score_match > score_no_match


def test_price_tier_mismatch_penalises_score():
    profile = PreferenceProfile(
        style_priority=[], occasion_priority=[], color_priority=[], price_tier="budget"
    )
    outfit_wrong_tier = _make_outfit("OF_00003", [], [], "premium", 0.8)
    outfit_right_tier = _make_outfit("OF_00004", [], [], "budget", 0.8)
    score_right = score_outfit_for_preference(outfit_right_tier, profile)
    score_wrong = score_outfit_for_preference(outfit_wrong_tier, profile)
    assert score_right > score_wrong


def test_rerank_returns_top_k():
    profile = PreferenceProfile(
        style_priority=["minimalist"],
        occasion_priority=["office"],
        color_priority=[],
        price_tier="mid",
    )
    outfits = [
        _make_outfit(f"OF_{i:05d}", ["office"], ["minimalist"], "mid", 0.5 + i * 0.01)
        for i in range(10)
    ]
    result = rerank_by_preference(outfits, profile, top_k=3)
    assert len(result) == 3


def test_rerank_preserves_order_by_score():
    profile = PreferenceProfile(
        style_priority=["korean"],
        occasion_priority=["date"],
        color_priority=[],
        price_tier="mid",
    )
    high = _make_outfit("OF_HIGH", ["date"], ["korean"], "mid", 0.9)
    low = _make_outfit("OF_LOW", ["party"], ["streetwear"], "mid", 0.3)
    result = rerank_by_preference([low, high], profile, top_k=2)
    assert result[0].outfit_id == "OF_HIGH"
