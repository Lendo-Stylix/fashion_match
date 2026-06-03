from __future__ import annotations

from pathlib import Path

from outfitmatch.kb.graph import Edge
from outfitmatch.kb.graph_store import OutfitGraph, index_item_nodes
from outfitmatch.kb.schema import ItemRecord
from outfitmatch.pipeline import RecommendRequest
from outfitmatch.retrieval import qdrant_filter_seed_ids, search_outfits


def _item(
    item_id: str,
    category: str,
    *,
    colors: list[str] | None = None,
    price: int = 300_000,
) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path="",
        item_embedding=[0.1],
        gender="men",
        formality="smart_casual",
        store={
            "store_id": "aristino_vn",
            "price_vnd": price,
            "colors": colors or [],
            "product_url": "https://x",
            "in_stock": True,
        },
    )


def _graph() -> OutfitGraph:
    items = [_item("t", "top"), _item("b", "bottom", colors=["đỏ"]), _item("s", "shoes")]
    edges = [
        Edge("b", "t", "bottom", "top", 0.9),
        Edge("s", "t", "shoes", "top", 0.8),
        Edge("b", "s", "bottom", "shoes", 0.7),
    ]
    return OutfitGraph(items, edges)


def test_search_outfits_with_injected_seeds_returns_records():
    graph = _graph()
    request = RecommendRequest(occasion="office")
    records = search_outfits(request, graph=graph, seed_ids=["t"])
    assert records
    assert records[0].gen_method == "graph_traversal"
    assert {item.category for item in records[0].items} >= {"top", "bottom"}


def test_search_outfits_exclude_colors_drops_matching():
    graph = _graph()
    request = RecommendRequest(occasion="office", exclude_colors=["đỏ"])
    assert search_outfits(request, graph=graph, seed_ids=["t"]) == []


def test_search_outfits_price_max_filters():
    graph = _graph()
    request = RecommendRequest(occasion="office", price_max=500_000)
    assert search_outfits(request, graph=graph, seed_ids=["t"]) == []


def test_search_outfits_falls_back_to_graph_scan(tmp_path: Path):
    graph = _graph()
    request = RecommendRequest(occasion="office")
    records = search_outfits(
        request,
        graph=graph,
        qdrant_url=f"path://{tmp_path.as_posix()}",
    )
    assert records
    assert records[0].outfit_id == "OF_00001"


def test_qdrant_filter_seed_ids_returns_anchor_items(tmp_path: Path):
    items = [
        _item("top_ok", "top"),
        _item("dress_ok", "dress"),
        _item("bottom_ignored", "bottom"),
        ItemRecord(
            item_id="top_casual",
            category="top",
            image_path="",
            item_embedding=[0.1],
            gender="men",
            formality="casual",
            store={
                "store_id": "aristino_vn",
                "price_vnd": 300_000,
                "colors": [],
                "product_url": "https://x",
                "in_stock": True,
            },
        ),
    ]
    qdrant_url = f"path://{tmp_path.as_posix()}"
    index_item_nodes(items, qdrant_url)

    seed_ids = set(qdrant_filter_seed_ids(qdrant_url, occasion="office"))
    assert seed_ids == {"top_ok", "dress_ok"}
