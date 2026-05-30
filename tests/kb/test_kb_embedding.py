from __future__ import annotations

import pytest

from outfitmatch.kb.embedding import extract_item_embeddings
from outfitmatch.kb.schema import ItemRecord


def _item(item_id: str = "item_custom_00001") -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category="top",
        image_path=f"data/custom/catalog/images/{item_id}.jpg",
        item_embedding=[],
        store={"price_vnd": 199000, "store_id": "test", "product_url": "https://x.test/p"},
    )


class BatchEncoder:
    def encode_items(self, items: list[ItemRecord], batch_size: int) -> list[list[float]]:
        assert batch_size == 2
        return [[float(i), float(i + 1)] for i, _ in enumerate(items)]


class SingleEncoder:
    def encode_item(self, item: ItemRecord) -> list[float]:
        return [float(len(item.item_id)), 1.0]


def test_extract_item_embeddings_uses_batch_encoder_and_mutates_items():
    items = [_item("a"), _item("b")]

    out = extract_item_embeddings(items, BatchEncoder(), batch_size=2)

    assert out is items
    assert [item.item_embedding for item in out] == [[0.0, 1.0], [1.0, 2.0]]


def test_extract_item_embeddings_falls_back_to_single_item_encoder():
    items = [_item("abc")]

    out = extract_item_embeddings(items, SingleEncoder())

    assert out[0].item_embedding == [3.0, 1.0]


def test_extract_item_embeddings_rejects_wrong_batch_size():
    class BadEncoder:
        def encode_items(self, items: list[ItemRecord], batch_size: int) -> list[list[float]]:
            return [[1.0]]

    with pytest.raises(ValueError, match="returned 1 embeddings for 2 items"):
        extract_item_embeddings([_item("a"), _item("b")], BadEncoder())
