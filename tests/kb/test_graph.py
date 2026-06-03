from __future__ import annotations

from outfitmatch.kb.graph import Edge, build_edges, edge_allowed, edge_allowed_categories
from outfitmatch.kb.pair_scoring import HeuristicPairScorer
from outfitmatch.kb.schema import ItemRecord


def _item(
    item_id: str,
    *,
    category: str,
    gender: str = "unisex",
    formality: str = "casual",
    price: int = 200_000,
) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path="",
        item_embedding=[],
        gender=gender,
        formality=formality,
        store={"price_vnd": price, "colors": [], "product_url": "x", "in_stock": True},
    )


def test_edge_allowed_categories():
    assert edge_allowed_categories("top", "bottom") is True
    assert edge_allowed_categories("top", "shoes") is True
    assert edge_allowed_categories("dress", "shoes") is True
    assert edge_allowed_categories("top", "top") is False
    assert edge_allowed_categories("top", "dress") is False
    assert edge_allowed_categories("bottom", "dress") is False


def test_edge_blocked_by_gender():
    top = _item("a", category="top", gender="men")
    bottom_women = _item("b", category="bottom", gender="women")
    assert edge_allowed(top, bottom_women) is False
    bottom_unisex = _item("c", category="bottom", gender="unisex")
    assert edge_allowed(top, bottom_unisex) is True


def test_edge_blocked_by_formality():
    athletic_top = _item("a", category="top", formality="athletic")
    formal_bottom = _item("b", category="bottom", formality="formal")
    assert edge_allowed(athletic_top, formal_bottom) is False
    casual_top = _item("a2", category="top", formality="casual")
    smart_bottom = _item("c", category="bottom", formality="smart_casual")
    assert edge_allowed(casual_top, smart_bottom) is True


def test_edge_ignores_formality_for_accessory():
    top = _item("a", category="top", formality="casual")
    bag = _item("bag", category="bag", formality="formal")
    assert edge_allowed(top, bag) is True


def test_build_edges_canonical_and_sparse():
    items = [
        _item("i1", category="top"),
        _item("i2", category="bottom"),
        _item("i3", category="bottom"),
        _item("i4", category="shoes"),
    ]
    edges = build_edges(items, HeuristicPairScorer(), k=15)
    assert all(edge.src_id < edge.dst_id for edge in edges)
    pairs = {(edge.src_id, edge.dst_id) for edge in edges}
    assert ("i2", "i3") not in pairs
    assert ("i1", "i2") in pairs
    assert ("i1", "i4") in pairs
    assert all(isinstance(edge, Edge) for edge in edges)


def test_build_edges_respects_top_k_per_partner_category():
    top = _item("a_top", category="top")
    bottoms = [_item(f"b{i:02d}", category="bottom", price=100_000 + i) for i in range(20)]
    edges = build_edges([top, *bottoms], HeuristicPairScorer(), k=5, anchors=[top])
    assert len(edges) == 5


def test_build_edges_deterministic():
    items = [
        _item("i1", category="top"),
        _item("i2", category="bottom"),
        _item("i3", category="shoes"),
    ]
    scorer = HeuristicPairScorer()
    assert build_edges(items, scorer) == build_edges(items, scorer)
