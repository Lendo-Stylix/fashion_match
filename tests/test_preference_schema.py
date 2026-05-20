from outfitmatch.preference.schema import (
    HardConstraint, SoftPreference, StructuredPreference, apply_body_fallback,
)


def test_active_soft_groups_filters_empty():
    p = StructuredPreference(
        soft=SoftPreference(style="minimalist korean", color="earth tones", fit=""))
    assert p.active_soft_groups() == {
        "style": "minimalist korean", "color": "earth tones"}


def test_body_fallback_applied_when_no_user_hard():
    p = StructuredPreference()
    p = apply_body_fallback(p, "pear")
    assert p.hard.source == "body_fallback"
    assert p.hard.fit_bias == "structured_top"


def test_body_fallback_skipped_when_user_hard_present():
    p = StructuredPreference(hard=HardConstraint(colors_avoid=["bright"]))
    p = apply_body_fallback(p, "pear")
    assert p.hard.source == "user"
    assert p.hard.fit_bias is None
