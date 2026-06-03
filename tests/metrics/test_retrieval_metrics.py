from __future__ import annotations

from outfitmatch.kb.graph import Edge
from outfitmatch.kb.graph_store import OutfitGraph
from outfitmatch.kb.schema import ItemRecord
from outfitmatch.kb.traversal import AssembledOutfit
from outfitmatch.metrics.retrieval import fitb_recall_at_k, recall_at_k


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


def test_recall_at_k_basic():
    assert recall_at_k(["a", "b", "c"], {"b"}, 2) == 1.0
    assert recall_at_k(["a", "b", "c"], {"z"}, 2) == 0.0
    assert recall_at_k(["a", "b"], set(), 2) == 0.0


def test_fitb_recall_recovers_held_out_shoe():
    items = [_item("t", "top"), _item("b", "bottom"), _item("s", "shoes"), _item("s2", "shoes")]
    graph = OutfitGraph(
        items,
        [
            Edge("b", "t", "bottom", "top", 0.9),
            Edge("s", "t", "shoes", "top", 0.95),
            Edge("b", "s", "bottom", "shoes", 0.9),
            Edge("s2", "t", "shoes", "top", 0.2),
            Edge("b", "s2", "bottom", "shoes", 0.2),
        ],
    )
    outfit = AssembledOutfit(items=[items[0], items[1], items[2]], score=0.9)
    assert fitb_recall_at_k(graph, [outfit], k=1, masked_category="shoes") == 1.0


def test_fitb_recall_zero_when_no_eligible_outfit():
    items = [_item("t", "top"), _item("b", "bottom")]
    graph = OutfitGraph(items, [Edge("b", "t", "bottom", "top", 0.9)])
    outfit = AssembledOutfit(items=items, score=0.9)
    assert fitb_recall_at_k(graph, [outfit], k=5, masked_category="shoes") == 0.0
