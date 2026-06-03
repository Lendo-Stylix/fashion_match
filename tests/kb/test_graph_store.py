from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from qdrant_client import QdrantClient

from outfitmatch.kb.graph import Edge, build_edges
from outfitmatch.kb.graph_store import (
    ITEM_PAYLOAD_INDEX_FIELDS,
    create_items_collection,
    index_item_nodes,
    load_graph,
    read_edges,
    write_edges,
)
from outfitmatch.kb.pair_scoring import HeuristicPairScorer
from outfitmatch.kb.schema import ItemRecord


def _item(item_id: str, category: str) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path="",
        item_embedding=[0.1, 0.2],
        gender="unisex",
        formality="casual",
        store={
            "price_vnd": 200_000,
            "colors": [],
            "product_url": "x",
            "in_stock": True,
            "store_id": "yody_vn",
        },
    )


def _edges() -> list[Edge]:
    return [Edge("i1", "i2", "top", "bottom", 0.9), Edge("i1", "i3", "top", "shoes", 0.7)]


def _qdrant_url(path: Path) -> str:
    return f"path://{path.as_posix()}"


def test_edges_round_trip(tmp_path: Path):
    path = tmp_path / "item_edges.parquet"
    write_edges(_edges(), path)
    loaded = read_edges(path)
    assert {(edge.src_id, edge.dst_id, edge.weight) for edge in loaded} == {
        ("i1", "i2", 0.9),
        ("i1", "i3", 0.7),
    }


def test_read_edges_missing_file_returns_empty(tmp_path: Path):
    assert read_edges(tmp_path / "nope.parquet") == []


def test_read_edges_rejects_bad_schema(tmp_path: Path):
    path = tmp_path / "item_edges.parquet"
    pd.DataFrame([{"src_id": "i1", "dst_id": "i2"}]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="missing edge columns"):
        read_edges(path)


def test_outfit_graph_neighbors_both_directions_sorted(tmp_path: Path):
    path = tmp_path / "item_edges.parquet"
    write_edges(_edges(), path)
    items = [_item("i1", "top"), _item("i2", "bottom"), _item("i3", "shoes")]
    graph = load_graph(path, items=items)
    assert graph.neighbors("i1", "bottom") == [("i2", 0.9)]
    assert graph.neighbors("i1", "shoes") == [("i3", 0.7)]
    assert graph.neighbors("i2", "top") == [("i1", 0.9)]


def test_outfit_graph_edge_weight_symmetric_and_none(tmp_path: Path):
    path = tmp_path / "item_edges.parquet"
    write_edges(_edges(), path)
    items = [_item("i1", "top"), _item("i2", "bottom"), _item("i3", "shoes")]
    graph = load_graph(path, items=items)
    assert graph.edge_weight("i1", "i2") == 0.9
    assert graph.edge_weight("i2", "i1") == 0.9
    assert graph.edge_weight("i2", "i3") is None


def test_create_items_collection_is_idempotent_and_validates_dim(tmp_path: Path):
    qdrant_path = tmp_path / "qdrant"
    url = _qdrant_url(qdrant_path)

    create_items_collection(url, vector_dim=2)
    create_items_collection(url, vector_dim=2)

    client = QdrantClient(path=str(qdrant_path))
    try:
        info = client.get_collection("items")
        assert info.config.params.vectors.size == 2
    finally:
        client.close()

    with pytest.raises(ValueError, match="vector dim 2"):
        create_items_collection(url, vector_dim=3)


def test_index_item_nodes_upserts_with_filterable_payload(tmp_path: Path):
    items = [
        ItemRecord(
            item_id="item_custom_00001",
            category="top",
            image_path="data/custom/catalog/images/item_custom_00001.jpg",
            item_embedding=[0.1, 0.2, 0.3],
            gender="men",
            formality="smart_casual",
            store={
                "store_id": "yody_vn",
                "product_url": "https://yody.vn/p1",
                "price_vnd": 250_000,
                "in_stock": True,
                "colors": [],
            },
        )
    ]
    qdrant_path = tmp_path / "qdrant"
    index_item_nodes(items, _qdrant_url(qdrant_path), batch_size=1)

    client = QdrantClient(path=str(qdrant_path))
    try:
        assert client.get_collection("items").points_count == 1
        records, _ = client.scroll("items", limit=10, with_vectors=True)
    finally:
        client.close()

    payload = records[0].payload
    assert payload["item_id"] == "item_custom_00001"
    assert payload["gender"] == "men"
    assert payload["formality"] == "smart_casual"
    assert payload["price_tier"] == "budget"
    assert records[0].id != "item_custom_00001"
    assert "gender" in ITEM_PAYLOAD_INDEX_FIELDS


def test_index_item_nodes_skips_items_without_embedding(tmp_path: Path):
    items = [
        ItemRecord(
            item_id="i1",
            category="top",
            image_path="",
            item_embedding=[],
            gender="unisex",
            formality="casual",
            store={"store_id": "x", "price_vnd": 1, "in_stock": True, "product_url": "x"},
        )
    ]
    index_item_nodes(items, _qdrant_url(tmp_path / "qdrant"))


def test_incremental_anchor_build_keeps_old_edges():
    def make_item(item_id: str, category: str) -> ItemRecord:
        return ItemRecord(
            item_id=item_id,
            category=category,
            image_path="",
            item_embedding=[0.1],
            gender="unisex",
            formality="casual",
            store={"price_vnd": 200_000, "colors": [], "product_url": "x", "in_stock": True},
        )

    old_items = [make_item("i1", "top"), make_item("i2", "bottom")]
    scorer = HeuristicPairScorer()
    old_edges = build_edges(old_items, scorer)
    assert {(edge.src_id, edge.dst_id) for edge in old_edges} == {("i1", "i2")}

    new_shoe = make_item("i3", "shoes")
    all_items = [*old_items, new_shoe]
    inc_edges = build_edges(all_items, scorer, anchors=[new_shoe])
    inc_pairs = {(edge.src_id, edge.dst_id) for edge in inc_edges}
    assert ("i1", "i3") in inc_pairs
    assert ("i2", "i3") in inc_pairs
    assert ("i1", "i2") not in inc_pairs

    union = {(edge.src_id, edge.dst_id) for edge in (*old_edges, *inc_edges)}
    assert union == {("i1", "i2"), ("i1", "i3"), ("i2", "i3")}
