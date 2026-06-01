from __future__ import annotations

from pathlib import Path

import pytest
from qdrant_client import QdrantClient

from outfitmatch.kb.qdrant_index import (
    PAYLOAD_INDEX_FIELDS,
    create_outfits_collection,
    index_outfits,
)
from outfitmatch.kb.schema import ItemRecord, OutfitRecord


def _qdrant_url(path: Path) -> str:
    return f"path://{path.as_posix()}"


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


def _make_outfit(
    outfit_id: str = "OF_00001",
    embedding: list[float] | None = None,
) -> OutfitRecord:
    return OutfitRecord(
        outfit_id=outfit_id,
        schema_version="3.1",
        items=[_make_item("item_custom_00001", "top"), _make_item("item_custom_00002", "bottom")],
        outfit_embedding=[0.4, 0.5, 0.6] if embedding is None else embedding,
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


def test_payload_index_fields_match_retrieval_filters():
    assert PAYLOAD_INDEX_FIELDS == (
        "occasion",
        "style",
        "body_shapes_fit",
        "price_tier",
        "season",
        "has_vn_store",
    )


def test_create_outfits_collection_is_idempotent_and_validates_dim(tmp_path: Path):
    qdrant_path = tmp_path / "qdrant"
    url = _qdrant_url(qdrant_path)

    create_outfits_collection(url, vector_dim=3)
    create_outfits_collection(url, vector_dim=3)

    client = QdrantClient(path=str(qdrant_path))
    try:
        info = client.get_collection("outfits")
        assert info.config.params.vectors.size == 3
    finally:
        client.close()

    with pytest.raises(ValueError, match="vector dim 3"):
        create_outfits_collection(url, vector_dim=4)


def test_index_outfits_creates_collection_and_upserts_payload(tmp_path: Path):
    qdrant_path = tmp_path / "qdrant"
    url = _qdrant_url(qdrant_path)
    outfit = _make_outfit()

    index_outfits([outfit], url, batch_size=1)

    client = QdrantClient(path=str(qdrant_path))
    try:
        assert client.get_collection("outfits").points_count == 1
        records, _ = client.scroll("outfits", limit=10, with_vectors=True)
    finally:
        client.close()

    assert len(records) == 1
    record = records[0]
    assert record.payload["outfit_id"] == "OF_00001"
    assert record.payload["occasion"] == ["office", "cafe_hangout"]
    assert record.payload["style"] == ["minimalist"]
    assert record.payload["has_vn_store"] is True
    assert record.payload["compatibility_score"] == 0.87
    assert record.vector == [0.4, 0.5, 0.6]
    assert record.id != "OF_00001"  # raw OF_* IDs are invalid Qdrant point IDs.


def test_index_outfits_rejects_empty_embedding(tmp_path: Path):
    with pytest.raises(ValueError, match="empty outfit_embedding"):
        index_outfits([_make_outfit(embedding=[])], _qdrant_url(tmp_path / "qdrant"))


def test_index_outfits_rejects_inconsistent_embedding_dims(tmp_path: Path):
    outfits = [
        _make_outfit("OF_00001", embedding=[0.1, 0.2, 0.3]),
        _make_outfit("OF_00002", embedding=[0.1, 0.2]),
    ]

    with pytest.raises(ValueError, match="embedding dim 2"):
        index_outfits(outfits, _qdrant_url(tmp_path / "qdrant"))


def test_index_outfits_validates_batch_size(tmp_path: Path):
    with pytest.raises(ValueError, match="batch_size"):
        index_outfits([_make_outfit()], _qdrant_url(tmp_path / "qdrant"), batch_size=0)
