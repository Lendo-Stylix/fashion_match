from __future__ import annotations

from outfitmatch.kb.graph import Edge
from outfitmatch.kb.graph_store import OutfitGraph
from outfitmatch.kb.schema import ItemRecord
from outfitmatch.kb.traversal import assemble_from_seed, assemble_outfits


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


def test_assemble_top_seed_adds_bottom_and_shoes():
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


def test_assemble_is_shoeless_when_no_shoe_neighbor():
    items = [_item("t", "top"), _item("b", "bottom")]
    edges = [Edge("b", "t", "bottom", "top", 0.9)]
    outfits = assemble_from_seed(_graph(items, edges), "t")
    assert outfits
    assert {item.category for item in outfits[0].items} == {"top", "bottom"}


def test_assemble_skips_top_with_no_bottom():
    items = [_item("t", "top"), _item("s", "shoes")]
    edges = [Edge("s", "t", "shoes", "top", 0.8)]
    assert assemble_from_seed(_graph(items, edges), "t") == []


def test_assemble_clique_blocks_unconnected_optional():
    items = [_item("t", "top"), _item("b", "bottom"), _item("s", "shoes")]
    edges = [Edge("b", "t", "bottom", "top", 0.9), Edge("s", "t", "shoes", "top", 0.8)]
    outfits = assemble_from_seed(_graph(items, edges), "t")
    assert outfits
    assert {item.category for item in outfits[0].items} == {"top", "bottom"}


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
