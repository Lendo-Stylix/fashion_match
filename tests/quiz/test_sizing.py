from __future__ import annotations

from outfitmatch.kb.schema import ItemRecord
from outfitmatch.quiz.sizing import suggest_size, suggest_sizes_for_outfit


def test_suggest_size_women_medium():
    assert suggest_size("top", "women", 160, 55, ["S", "M", "L"]) == "M"


def test_suggest_size_men_large():
    assert suggest_size("top", "men", 175, 72, ["S", "M", "L", "XL"]) == "L"


def test_suggest_size_falls_back_to_nearest_available():
    assert suggest_size("top", "women", 160, 55, ["S", "L"]) == "S"


def test_suggest_size_none_for_non_alpha_category():
    assert suggest_size("bottom", "men", 175, 70, ["29", "30", "31"]) is None
    assert suggest_size("shoes", "women", 160, 55, ["38", "39"]) is None


def test_suggest_size_none_when_no_body_info():
    assert suggest_size("top", "women", None, None, ["S", "M"]) is None


def test_suggest_size_none_when_no_available_sizes():
    assert suggest_size("dress", "women", 160, 55, []) is None


def _item(item_id: str, category: str, gender: str, store: dict) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path="",
        item_embedding=[],
        gender=gender,
        store=store,
    )


def test_suggest_sizes_for_outfit_skips_unresolved():
    top = _item("i1", "top", "women", {"sizes_in_stock": ["M", "L"]})
    shoe = _item("i2", "shoes", "women", {"available_sizes": ["38", "39"]})
    result = suggest_sizes_for_outfit([top, shoe], 160, 55)
    assert result == {"i1": "M"}
