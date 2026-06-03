from __future__ import annotations

from outfitmatch.kb.graph import Edge
from outfitmatch.kb.graph_eval import evaluate_graph
from outfitmatch.kb.graph_store import OutfitGraph
from outfitmatch.kb.schema import ItemRecord


def _item(
    item_id: str,
    category: str,
    *,
    gender: str = "unisex",
    formality: str = "casual",
) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path="",
        item_embedding=[0.1],
        gender=gender,
        formality=formality,
        store={"price_vnd": 200_000, "colors": [], "product_url": "x", "in_stock": True},
    )


def test_evaluate_graph_coverage_and_clean_coherence():
    items = [_item("t", "top"), _item("b", "bottom"), _item("s", "shoes")]
    edges = [
        Edge("b", "t", "bottom", "top", 0.9),
        Edge("s", "t", "shoes", "top", 0.8),
        Edge("b", "s", "bottom", "shoes", 0.7),
    ]
    graph = OutfitGraph(items, edges)
    report = evaluate_graph(graph, items, edges, seed_ids=["t"])
    assert report.n_nodes == 3
    assert report.coherence_violations == 0
    assert report.catalog_coverage == 1.0
    assert report.n_assembled >= 1


def test_evaluate_graph_flags_bad_edge():
    items = [_item("m", "top", gender="men"), _item("w", "bottom", gender="women")]
    bad_edges = [Edge("m", "w", "top", "bottom", 0.9)]
    graph = OutfitGraph(items, bad_edges)
    report = evaluate_graph(graph, items, bad_edges, seed_ids=["m"])
    assert report.coherence_violations == 1
