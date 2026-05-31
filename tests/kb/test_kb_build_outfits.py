from __future__ import annotations

import pandas as pd

from outfitmatch.kb.build_outfits import build_outfit_records, outfits_to_frame
from outfitmatch.kb.schema import ItemRecord
from outfitmatch.vocab import PRICE_TIER_SET


def _item(item_id: str, category: str, price: int) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path=f"data/custom/catalog/images/{item_id}.jpg",
        item_embedding=[],
        store={
            "price_vnd": price,
            "product_url": f"https://test.vn/{item_id}",
            "store_id": "test",
            "title_vi": item_id,
            "desc_vi": "",
            "colors": [],
        },
    )


def test_build_outfit_records_respects_fitb_random_mix_and_schema():
    items_by_category = {
        "top": [_item("top_1", "top", 100000)],
        "bottom": [_item("bottom_1", "bottom", 200000)],
        "dress": [_item("dress_1", "dress", 300000)],
        "shoes": [_item("shoes_1", "shoes", 400000), _item("shoes_2", "shoes", 450000)],
    }

    outfits = build_outfit_records(items_by_category, n_outfits=6, fitb_ratio=0.5)

    assert len(outfits) == 6
    assert [outfit.outfit_id for outfit in outfits] == [f"OF_{i:05d}" for i in range(1, 7)]
    assert {outfit.gen_method for outfit in outfits} == {"fitb_beam", "random_scored"}
    for outfit in outfits:
        assert outfit.schema_version == "3.1"
        assert 0.0 <= outfit.compatibility_score <= 1.0
        assert outfit.price_tier in PRICE_TIER_SET
        categories = {item.category for item in outfit.items}
        assert categories >= {"shoes"}
        assert categories >= {"dress"} or categories >= {"top", "bottom"}


def test_build_outfit_records_can_target_affordable_price_tiers():
    items_by_category = {
        "top": [_item(f"top_budget_{i}", "top", 50_000) for i in range(3)]
        + [_item(f"top_mid_{i}", "top", 150_000) for i in range(3)]
        + [_item(f"top_premium_{i}", "top", 500_000) for i in range(3)],
        "bottom": [_item(f"bottom_budget_{i}", "bottom", 50_000) for i in range(3)]
        + [_item(f"bottom_mid_{i}", "bottom", 200_000) for i in range(3)]
        + [_item(f"bottom_premium_{i}", "bottom", 600_000) for i in range(3)],
        "shoes": [_item(f"shoes_budget_{i}", "shoes", 50_000) for i in range(3)]
        + [_item(f"shoes_mid_{i}", "shoes", 300_000) for i in range(3)]
        + [_item(f"shoes_premium_{i}", "shoes", 700_000) for i in range(3)],
    }

    outfits = build_outfit_records(
        items_by_category,
        n_outfits=9,
        fitb_ratio=0.5,
        price_tier_targets={"budget": 0.22, "mid": 0.45, "premium": 0.33},
    )

    tier_counts = pd.Series([outfit.price_tier for outfit in outfits]).value_counts().to_dict()
    assert tier_counts == {"mid": 4, "premium": 3, "budget": 2}
    assert len({tuple(item.item_id for item in outfit.items) for outfit in outfits}) == 9


def test_price_balanced_build_preserves_fitb_random_ratio_when_feasible():
    top_prices = [50_000] * 5 + [150_000] * 5 + [500_000] * 5
    items_by_category = {
        "top": [_item(f"top_{i}", "top", price) for i, price in enumerate(top_prices)],
        "bottom": [
            _item(f"bottom_{i}", "bottom", price)
            for i, price in enumerate([50_000] * 5 + [200_000] * 5 + [600_000] * 5)
        ],
        "shoes": [
            _item(f"shoes_{i}", "shoes", price)
            for i, price in enumerate([50_000] * 5 + [300_000] * 5 + [700_000] * 5)
        ],
    }

    outfits = build_outfit_records(
        items_by_category,
        n_outfits=10,
        fitb_ratio=0.7,
        price_tier_targets={"budget": 0.2, "mid": 0.5, "premium": 0.3},
    )

    assert pd.Series([outfit.gen_method for outfit in outfits]).value_counts().to_dict() == {
        "fitb_beam": 7,
        "random_scored": 3,
    }


def test_outfits_to_frame_is_parquet_friendly():
    items_by_category = {
        "top": [_item("top_1", "top", 100000)],
        "bottom": [_item("bottom_1", "bottom", 200000)],
        "shoes": [_item("shoes_1", "shoes", 400000)],
    }
    outfits = build_outfit_records(items_by_category, n_outfits=2, fitb_ratio=0.5)

    frame = outfits_to_frame(outfits)

    assert list(frame.columns) == [
        "outfit_id",
        "schema_version",
        "gender",
        "item_ids",
        "categories",
        "compatibility_score",
        "price_total_vnd",
        "price_tier",
        "has_vn_store",
        "gen_method",
    ]
    assert frame.shape[0] == 2
    assert pd.api.types.is_numeric_dtype(frame["compatibility_score"])
    assert frame.loc[0, "item_ids"].startswith("[")
