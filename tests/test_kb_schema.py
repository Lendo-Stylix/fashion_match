from __future__ import annotations

from outfitmatch.kb.schema import ItemRecord, OutfitRecord
from outfitmatch.vocab import OCCASION_SET, STYLE_SET, BODY_SHAPE_SET


def _make_item(item_id: str = "item_custom_00001", category: str = "top") -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path=f"data/custom/catalog/images/{item_id}.jpg",
        item_embedding=[0.1, 0.2, 0.3],
        store={
            "store_id": "canifa_vn",
            "store_name": "Canifa",
            "product_url": "https://canifa.com/ao-thun",
            "price_vnd": 299000,
            "in_stock": True,
        },
    )


def _make_outfit() -> OutfitRecord:
    return OutfitRecord(
        outfit_id="OF_00001",
        schema_version="3.1",
        items=[_make_item("item_custom_00001", "top"), _make_item("item_custom_00002", "bottom")],
        outfit_embedding=[0.4, 0.5, 0.6],
        compatibility_score=0.87,
        occasion=["office", "cafe_hangout"],
        style=["minimalist"],
        body_shapes_fit=["pear", "hourglass"],
        season=["transitional"],
        color_palette=["beige", "navy"],
        price_total_vnd=598000,
        price_tier="mid",
        has_vn_store=True,
        stylist_explanation_vi="Bộ đồ minimalist.",
        gen_method="fitb_beam",
    )


def test_outfit_record_roundtrip_qdrant_payload():
    outfit = _make_outfit()
    payload = outfit.to_qdrant_payload()
    assert payload["outfit_id"] == "OF_00001"
    assert payload["compatibility_score"] == 0.87
    assert "office" in payload["occasion"]
    assert payload["has_vn_store"] is True
    # items are NOT in payload (stored separately as vectors)
    assert "items" not in payload


def test_outfit_occasion_values_must_be_valid():
    outfit = _make_outfit()
    for v in outfit.occasion:
        assert v in OCCASION_SET, f"Bad occasion value in outfit: {v!r}"


def test_outfit_style_values_must_be_valid():
    outfit = _make_outfit()
    for v in outfit.style:
        assert v in STYLE_SET


def test_outfit_body_shape_values_must_be_valid():
    outfit = _make_outfit()
    for v in outfit.body_shapes_fit:
        assert v in BODY_SHAPE_SET


def test_item_record_has_required_store_fields():
    item = _make_item()
    for key in ("store_id", "store_name", "product_url", "price_vnd", "in_stock"):
        assert key in item.store, f"Missing store field: {key}"
