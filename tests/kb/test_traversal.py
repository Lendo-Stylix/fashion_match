from __future__ import annotations

from outfitmatch.kb.graph import Edge
from outfitmatch.kb.graph_store import OutfitGraph
from outfitmatch.kb.schema import ItemRecord
from outfitmatch.kb.traversal import AssemblyConfig, assemble_from_seed, assemble_outfits


def _item(item_id: str, category: str) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path="",
        item_embedding=[0.1],
        gender="unisex",
        formality="casual",
        store={"price_vnd": 200_000, "colors": [], "product_url": "x", "in_stock": True},
    )


def _graph(items: list[ItemRecord], edges: list[Edge]) -> OutfitGraph:
    return OutfitGraph(items, edges)


def test_assemble_top_seed_adds_bottom_and_shoes_when_available():
    items = [_item("t", "top"), _item("b", "bottom"), _item("s", "shoes")]
    edges = [
        Edge("b", "t", "bottom", "top", 0.9),
        Edge("s", "t", "shoes", "top", 0.8),
        Edge("b", "s", "bottom", "shoes", 0.7),
    ]
    graph = _graph(items, edges)
    outfits = assemble_from_seed(graph, "t")
    assert outfits, "top seed should assemble at least one outfit"
    categories = {item.category for item in outfits[0].items}
    assert {"top", "bottom"} <= categories
    assert "shoes" in categories
    assert outfits[0].score > 0.0


def test_assemble_allows_shoeless_top_when_no_shoe_neighbor():
    items = [_item("t", "top"), _item("b", "bottom")]
    edges = [Edge("b", "t", "bottom", "top", 0.9)]
    outfits = assemble_from_seed(_graph(items, edges), "t")
    assert outfits
    assert {item.category for item in outfits[0].items} == {"top", "bottom"}


def test_assemble_allows_shoeless_dress_when_no_shoe_neighbor():
    items = [_item("d", "dress"), _item("o", "outerwear")]
    edges = [Edge("o", "d", "outerwear", "dress", 0.9)]
    outfits = assemble_from_seed(_graph(items, edges), "d")
    assert outfits
    assert {item.category for item in outfits[0].items} == {"dress", "outerwear"}


def test_assemble_skips_top_with_no_bottom():
    items = [_item("t", "top"), _item("s", "shoes")]
    edges = [Edge("s", "t", "shoes", "top", 0.8)]
    assert assemble_from_seed(_graph(items, edges), "t") == []


def test_assemble_ignores_shoe_when_not_clique_safe():
    items = [_item("t", "top"), _item("b", "bottom"), _item("s", "shoes")]
    edges = [Edge("b", "t", "bottom", "top", 0.9), Edge("s", "t", "shoes", "top", 0.8)]
    outfits = assemble_from_seed(_graph(items, edges), "t")
    assert outfits
    assert {item.category for item in outfits[0].items} == {"top", "bottom"}


def test_assemble_clique_blocks_unconnected_optional_after_core_outfit_is_valid():
    items = [_item("t", "top"), _item("b", "bottom"), _item("s", "shoes"), _item("a", "accessory")]
    edges = [
        Edge("b", "t", "bottom", "top", 0.9),
        Edge("s", "t", "shoes", "top", 0.8),
        Edge("b", "s", "bottom", "shoes", 0.7),
        Edge("a", "t", "accessory", "top", 0.6),
    ]
    outfits = assemble_from_seed(_graph(items, edges), "t")
    assert outfits
    assert {item.category for item in outfits[0].items} == {"top", "bottom", "shoes"}


def test_assemble_prefers_shoes_first_under_optional_budget():
    items = [
        _item("t", "top"),
        _item("b", "bottom"),
        _item("s", "shoes"),
        _item("o", "outerwear"),
        _item("g", "bag"),
    ]
    edges = [
        Edge("b", "t", "bottom", "top", 0.9),
        Edge("s", "t", "shoes", "top", 0.8),
        Edge("b", "s", "bottom", "shoes", 0.7),
        Edge("o", "t", "outerwear", "top", 0.6),
        Edge("b", "o", "bottom", "outerwear", 0.6),
        Edge("g", "t", "bag", "top", 0.6),
        Edge("b", "g", "bottom", "bag", 0.6),
    ]
    outfits = assemble_from_seed(_graph(items, edges), "t", config=AssemblyConfig(max_optional=1))
    assert outfits
    assert {item.category for item in outfits[0].items} == {"top", "bottom", "shoes"}


def test_assemble_outfits_dedup_and_sorted():
    items = [_item("t", "top"), _item("b1", "bottom"), _item("b2", "bottom")]
    edges = [
        Edge("b1", "t", "bottom", "top", 0.9),
        Edge("b2", "t", "bottom", "top", 0.6),
    ]
    graph = _graph(items, edges)
    outfits = assemble_outfits(graph, ["t", "t"])
    keys = [outfit.item_ids for outfit in outfits]
    assert len(keys) == len(set(keys))
    assert outfits == sorted(
        outfits,
        key=lambda outfit: (outfit.score, outfit.item_ids),
        reverse=True,
    )
