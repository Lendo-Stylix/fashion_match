from __future__ import annotations

from outfitmatch.kb.generation import generate_fitb_beam, generate_random_scored
from outfitmatch.kb.schema import ItemRecord


def _item(item_id: str, category: str, price: int, emb: list[float] | None = None) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path=f"data/custom/catalog/images/{item_id}.jpg",
        item_embedding=emb or [1.0, 0.0],
        store={
            "store_id": "test_store",
            "store_name": "Test Store",
            "product_url": f"https://test.vn/{item_id}",
            "price_vnd": price,
            "in_stock": True,
        },
    )


class ScoringEncoder:
    def score_outfit(self, items: list[ItemRecord]) -> float:
        ids = {item.item_id for item in items}
        return 0.9 if "shoes_good" in ids else 0.2


class FitbEncoder:
    def score_outfit(self, items: list[ItemRecord]) -> float:
        # Beam path should prefer the outfit with the better shoes.
        return 0.95 if any(item.item_id == "shoes_good" for item in items) else 0.1


def test_generate_random_scored_emits_valid_category_rules_and_prices():
    items_by_category = {
        "top": [_item("top_1", "top", 100_000)],
        "bottom": [_item("bottom_1", "bottom", 200_000)],
        "dress": [_item("dress_1", "dress", 300_000)],
        "shoes": [_item("shoes_good", "shoes", 400_000)],
    }

    outfits = generate_random_scored(items_by_category, ScoringEncoder(), n_candidates=4)

    assert outfits
    for outfit in outfits:
        categories = {item.category for item in outfit.items}
        assert categories >= {"shoes"}
        assert categories >= {"dress"} or categories >= {"top", "bottom"}
        assert outfit.schema_version == "3.1"
        assert outfit.gen_method == "random_scored"
        assert outfit.price_total_vnd == sum(item.store["price_vnd"] for item in outfit.items)
        assert outfit.outfit_embedding


def test_generate_fitb_beam_prefers_high_scoring_completion():
    items_by_category = {
        "top": [_item("top_1", "top", 100_000)],
        "bottom": [_item("bottom_1", "bottom", 200_000)],
        "shoes": [
            _item("shoes_bad", "shoes", 350_000, [0.0, 1.0]),
            _item("shoes_good", "shoes", 450_000, [1.0, 0.0]),
        ],
    }

    outfits = generate_fitb_beam(
        items_by_category, FitbEncoder(), n_outfits=1, beam_size=2, top_k=2
    )

    assert len(outfits) == 1
    assert [item.item_id for item in outfits[0].items] == ["top_1", "bottom_1", "shoes_good"]
    assert outfits[0].gen_method == "fitb_beam"
    assert outfits[0].compatibility_score == 0.0
