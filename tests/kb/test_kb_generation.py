from __future__ import annotations

from outfitmatch.kb.generation import (
    _base_combinations,
    _is_coherent,
    generate_fitb_beam,
    generate_random_scored,
)
from outfitmatch.kb.schema import ItemRecord


def _item(
    item_id: str,
    category: str,
    price: int,
    emb: list[float] | None = None,
    gender: str = "unisex",
    formality: str = "casual",
) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path=f"data/custom/catalog/images/{item_id}.jpg",
        item_embedding=emb or [1.0, 0.0],
        gender=gender,
        formality=formality,
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


def _gendered_catalog() -> dict[str, list[ItemRecord]]:
    return {
        "top": [
            _item("top_men", "top", 100_000, gender="men"),
            _item("top_women", "top", 110_000, gender="women"),
            _item("top_uni", "top", 120_000, gender="unisex"),
        ],
        "bottom": [
            _item("bottom_men", "bottom", 200_000, gender="men"),
            _item("bottom_women", "bottom", 210_000, gender="women"),
        ],
        "shoes": [
            _item("shoes_men", "shoes", 300_000, gender="men"),
            _item("shoes_women", "shoes", 310_000, gender="women"),
            _item("shoes_uni", "shoes", 320_000, gender="unisex"),
        ],
        "dress": [_item("dress_women", "dress", 400_000, gender="women")],
        "accessory": [_item("acc_men", "accessory", 50_000, gender="men")],
    }


def _assert_no_mixed_gender(outfits: list) -> None:
    for outfit in outfits:
        genders = {item.gender for item in outfit.items} - {"unisex"}
        assert len(genders) <= 1, f"mixed-gender outfit: {[i.item_id for i in outfit.items]}"
        # the recorded outfit gender must match its items
        assert outfit.gender == (next(iter(genders)) if genders else "unisex")


def test_random_scored_never_mixes_gender():
    outfits = generate_random_scored(_gendered_catalog(), ScoringEncoder(), n_candidates=50)
    assert outfits
    _assert_no_mixed_gender(outfits)


def test_fitb_beam_never_mixes_gender():
    outfits = generate_fitb_beam(_gendered_catalog(), FitbEncoder(), n_outfits=50)
    assert outfits
    _assert_no_mixed_gender(outfits)


def test_unisex_items_pair_into_both_genders():
    # A unisex top can appear in both a men's and a women's outfit.
    outfits = generate_random_scored(_gendered_catalog(), ScoringEncoder(), n_candidates=50)
    genders = {o.gender for o in outfits}
    assert "men" in genders and "women" in genders


def test_is_coherent_blocks_formality_clash():
    blazer = _item("blz", "top", 100_000, formality="formal")
    gym = _item("gym", "bottom", 100_000, formality="athletic")
    shoe = _item("sh", "shoes", 100_000, formality="formal")
    assert _is_coherent([blazer, gym, shoe]) is False


def test_is_coherent_allows_adjacent_bands():
    polo = _item("p", "top", 100_000, formality="smart_casual")
    chino = _item("c", "bottom", 100_000, formality="casual")
    loafer = _item("l", "shoes", 100_000, formality="smart_casual")
    assert _is_coherent([polo, chino, loafer]) is True


def test_is_coherent_ignores_accessory_formality():
    top = _item("t", "top", 100_000, formality="casual")
    bottom = _item("b", "bottom", 100_000, formality="casual")
    shoe = _item("s", "shoes", 100_000, formality="casual")
    formal_bag = _item("bag", "bag", 100_000, formality="formal")  # not a relevant cat
    assert _is_coherent([top, bottom, shoe, formal_bag]) is True


def test_base_combinations_excludes_formality_clash():
    catalog = {
        "top": [_item("formal_top", "top", 100_000, formality="formal")],
        "bottom": [_item("athletic_bottom", "bottom", 100_000, formality="athletic")],
        "shoes": [_item("formal_shoe", "shoes", 100_000, formality="formal")],
    }
    assert _base_combinations(catalog) == []  # only clashing combo → nothing built
