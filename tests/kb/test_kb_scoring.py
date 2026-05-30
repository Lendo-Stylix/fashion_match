from __future__ import annotations

from outfitmatch.kb.schema import ItemRecord, OutfitRecord
from outfitmatch.kb.scoring import HeuristicOutfitScorer, rescore_outfits


def _item(item_id: str, category: str, price: int, colors: list[str]) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path=f"data/custom/catalog/images/{item_id}.jpg",
        item_embedding=[1.0, 0.0],
        store={
            "price_vnd": price,
            "product_url": f"https://test.vn/{item_id}",
            "store_id": "test",
            "colors": colors,
        },
    )


def _outfit(items: list[ItemRecord]) -> OutfitRecord:
    return OutfitRecord(
        outfit_id="OF_00001",
        schema_version="3.1",
        items=items,
        outfit_embedding=[],
        compatibility_score=0.0,
        occasion=[],
        style=[],
        body_shapes_fit=[],
        season=[],
        color_palette=[],
        price_total_vnd=sum(item.store["price_vnd"] for item in items),
        price_tier="mid",
        has_vn_store=True,
        stylist_explanation_vi="",
        gen_method="unit",
    )


class FixedScorer:
    def score_outfit(self, items: list[ItemRecord]) -> float:
        return 0.7 if len(items) == 3 else 0.2


def test_rescore_outfits_updates_scores_and_filters_threshold():
    keep = _outfit(
        [
            _item("top", "top", 100000, ["Trắng"]),
            _item("bottom", "bottom", 200000, ["Đen"]),
            _item("shoes", "shoes", 300000, ["Đen"]),
        ]
    )
    drop = _outfit([_item("dress", "dress", 400000, ["Đỏ"]), _item("shoes", "shoes", 300000, [])])

    rescored = rescore_outfits([keep, drop], FixedScorer(), score_threshold=0.5)

    assert rescored == [keep]
    assert keep.compatibility_score == 0.7
    assert drop.compatibility_score == 0.2


def test_heuristic_outfit_scorer_is_deterministic_and_bounded():
    scorer = HeuristicOutfitScorer()
    items = [
        _item("top", "top", 100000, ["Trắng"]),
        _item("bottom", "bottom", 200000, ["Đen"]),
        _item("shoes", "shoes", 300000, ["Đen"]),
    ]

    score1 = scorer.score_outfit(items)
    score2 = scorer.score_outfit(items)

    assert score1 == score2
    assert 0.0 <= score1 <= 1.0
    assert score1 > scorer.score_outfit(items[:2])
