from __future__ import annotations

from outfitmatch.kb.assemble_record import to_outfit_record
from outfitmatch.kb.schema import ItemRecord


def _item(
    item_id: str,
    category: str,
    *,
    gender: str = "men",
    formality: str = "smart_casual",
    price: int = 300_000,
    store_id: str = "aristino_vn",
    colors: list[str] | None = None,
    body_shapes_fit: list[str] | None = None,
    season: list[str] | None = None,
) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path="",
        item_embedding=[0.1, 0.2],
        gender=gender,
        formality=formality,
        body_shapes_fit=body_shapes_fit or [],
        season=season or [],
        store={
            "store_id": store_id,
            "price_vnd": price,
            "colors": colors or [],
            "product_url": "https://x",
            "in_stock": True,
        },
    )


def test_to_outfit_record_derives_tags():
    items = [_item("t", "top"), _item("b", "bottom", colors=["đen"])]
    record = to_outfit_record(items, 0.82)
    assert record.compatibility_score == 0.82
    assert record.gender == "men"
    assert record.gen_method == "graph_traversal"
    assert record.price_total_vnd == 600_000
    assert "office" in record.occasion
    assert record.style
    assert "đen" in record.color_palette


def test_to_outfit_record_unisex_when_all_unisex():
    items = [_item("t", "top", gender="unisex"), _item("b", "bottom", gender="unisex")]
    record = to_outfit_record(items, 0.5)
    assert record.gender == "unisex"
    assert record.body_shapes_fit == []


def test_to_outfit_record_derives_item_semantic_tags_by_intersection():
    items = [
        _item(
            "t",
            "top",
            body_shapes_fit=["pear", "rectangle"],
            season=["summer", "transitional"],
        ),
        _item(
            "b",
            "bottom",
            body_shapes_fit=["pear", "hourglass"],
            season=["transitional"],
        ),
        _item("s", "shoes", body_shapes_fit=[], season=["transitional", "rainy"]),
    ]

    record = to_outfit_record(items, 0.9)

    assert record.body_shapes_fit == ["pear"]
    assert record.season == ["transitional"]
