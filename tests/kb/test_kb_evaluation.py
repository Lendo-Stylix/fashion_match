from __future__ import annotations

import pandas as pd

from outfitmatch.kb.evaluation import evaluate_outfit_frame, summarize_outfit_report


def test_evaluate_outfit_frame_reports_price_bias_and_rule_validity():
    frame = pd.DataFrame(
        [
            {
                "item_ids": '["a", "b", "c"]',
                "categories": '["top", "bottom", "shoes"]',
                "price_tier": "mid",
                "gen_method": "fitb_beam",
                "compatibility_score": 0.8,
            },
            {
                "item_ids": '["d", "e"]',
                "categories": '["dress", "shoes"]',
                "price_tier": "budget",
                "gen_method": "random_scored",
                "compatibility_score": 0.7,
            },
            {
                "item_ids": '["x"]',
                "categories": '["top"]',
                "price_tier": "premium",
                "gen_method": "fitb_beam",
                "compatibility_score": 0.4,
            },
        ]
    )

    report = evaluate_outfit_frame(
        frame, price_tier_targets={"budget": 1 / 3, "mid": 1 / 3, "premium": 1 / 3}
    )

    assert report.total_outfits == 3
    assert report.price_tier_counts == {"budget": 1, "mid": 1, "premium": 1}
    assert report.invalid_rule_count == 1
    assert report.unique_combo_count == 3
    assert report.max_price_tier_deviation == 0.0
    assert "invalid_rules: 1" in summarize_outfit_report(report)


def test_formality_clash_counted():
    frame = pd.DataFrame(
        [
            {
                "item_ids": '["a", "b", "c"]',
                "categories": '["top", "bottom", "shoes"]',
                "price_tier": "mid",
                "gen_method": "random_scored",
                "compatibility_score": 0.5,
            }
        ]
    )

    clash = {"a": "formal", "b": "athletic", "c": "formal"}
    rep = evaluate_outfit_frame(frame, price_tier_targets={"mid": 1.0}, item_formality=clash)
    assert rep.formality_clash_count == 1
    assert "formality_clash_outfits: 1" in summarize_outfit_report(rep)

    ok = {"a": "casual", "b": "casual", "c": "casual"}
    rep2 = evaluate_outfit_frame(frame, price_tier_targets={"mid": 1.0}, item_formality=ok)
    assert rep2.formality_clash_count == 0
