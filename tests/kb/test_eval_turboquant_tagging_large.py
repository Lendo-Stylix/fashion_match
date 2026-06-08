from __future__ import annotations

import pandas as pd
from scripts.data.kb import eval_turboquant_tagging_large as mod


def test_build_sample_includes_outfit_items_then_balanced_fill():
    catalog = pd.DataFrame(
        [
            {
                "item_id": "top_1",
                "category": "top",
                "body_shapes_fit": '["rectangle"]',
                "season": '["summer"]',
                "stylist_notes_vi": "ok",
            },
            {
                "item_id": "bottom_1",
                "category": "bottom",
                "body_shapes_fit": '["rectangle"]',
                "season": '["summer"]',
                "stylist_notes_vi": "ok",
            },
            {
                "item_id": "shoe_1",
                "category": "shoes",
                "body_shapes_fit": "[]",
                "season": '["summer"]',
                "stylist_notes_vi": "ok",
            },
            {
                "item_id": "dress_1",
                "category": "dress",
                "body_shapes_fit": '["pear"]',
                "season": '["winter"]',
                "stylist_notes_vi": "ok",
            },
            {
                "item_id": "bag_1",
                "category": "bag",
                "body_shapes_fit": "[]",
                "season": '["summer"]',
                "stylist_notes_vi": "ok",
            },
        ]
    )
    outfits = pd.DataFrame(
        [
            {"outfit_id": "OF_1", "item_ids": '["top_1", "bottom_1", "shoe_1"]'},
        ]
    )

    sample = mod.build_sample(catalog, outfits, item_count=5, outfit_count=1, seed=7)

    assert sample.outfit_ids == ["OF_1"]
    assert sample.item_ids[:3] == ["top_1", "bottom_1", "shoe_1"]
    assert len(sample.item_ids) == 5
    assert len(set(sample.item_ids)) == 5


def test_derive_outfit_tags_prefers_dress_union_and_ignores_accessories():
    tags = {
        "dress": {"body_shapes_fit": ["pear"], "season": ["winter"]},
        "bag": {"body_shapes_fit": ["rectangle"], "season": ["summer"]},
    }
    categories = {"dress": "dress", "bag": "bag"}

    assert mod.derive_outfit_tags(["dress", "bag"], tags, categories, attr="body_shapes_fit") == [
        "pear"
    ]
    assert mod.derive_outfit_tags(["dress", "bag"], tags, categories, attr="season") == ["winter"]


def test_summarize_outfits_uses_item_predictions_and_references():
    sample = mod.BenchmarkSample(
        item_ids=["top", "bottom", "shoe"],
        outfit_ids=["OF_1"],
        outfit_item_ids={"OF_1": ["top", "bottom", "shoe"]},
    )
    categories = {"top": "top", "bottom": "bottom", "shoe": "shoes"}
    records = [
        {
            "item_id": "top",
            "valid_json": True,
            "body_shapes_fit": ["rectangle"],
            "season": ["summer"],
            "reference_body_shapes_fit": ["rectangle"],
            "reference_season": ["summer"],
        },
        {
            "item_id": "bottom",
            "valid_json": True,
            "body_shapes_fit": ["pear", "rectangle"],
            "season": ["summer"],
            "reference_body_shapes_fit": ["pear"],
            "reference_season": ["summer"],
        },
        {
            "item_id": "shoe",
            "valid_json": True,
            "body_shapes_fit": [],
            "season": ["summer"],
            "reference_body_shapes_fit": [],
            "reference_season": ["summer"],
        },
    ]

    summary = mod.summarize_outfits(records, sample, categories)

    assert summary["sample_size"] == 1
    assert summary["complete_rate"] == 1.0
    assert summary["avg_body_jaccard_vs_current_catalog_tags"] == 0.5
    assert summary["avg_season_jaccard_vs_current_catalog_tags"] == 1.0


def test_summarize_outfits_does_not_skip_invalid_ignored_accessory():
    sample = mod.BenchmarkSample(
        item_ids=["dress", "bag"],
        outfit_ids=["OF_1"],
        outfit_item_ids={"OF_1": ["dress", "bag"]},
    )
    categories = {"dress": "dress", "bag": "bag"}
    records = [
        {
            "item_id": "dress",
            "valid_json": True,
            "body_shapes_fit": ["pear"],
            "season": ["winter"],
            "reference_body_shapes_fit": ["pear"],
            "reference_season": ["winter"],
        },
        {
            "item_id": "bag",
            "valid_json": False,
            "body_shapes_fit": [],
            "season": [],
            "reference_body_shapes_fit": [],
            "reference_season": ["summer"],
        },
    ]

    summary = mod.summarize_outfits(records, sample, categories)

    assert summary["sample_size"] == 1
    assert summary["complete_rate"] == 1.0
    assert summary["avg_body_jaccard_vs_current_catalog_tags"] == 1.0
    assert summary["avg_season_jaccard_vs_current_catalog_tags"] == 1.0
