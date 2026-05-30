"""Item embedding extraction using OutfitTransformer-labse.

The production encoder is expected to be an adapter around the HF checkpoint in
``outfitmatch.kb.outfit_transformer`` plus image/text feature extractors. This module
only depends on a tiny protocol so tests and experiments can use fake encoders:

* ``encoder.encode_items(items, batch_size=...) -> list[list[float]]``; or
* ``encoder.encode_item(item) -> list[float]``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from outfitmatch.kb.schema import ItemRecord


def _as_float_list(values: Iterable[Any], *, item_id: str) -> list[float]:
    try:
        out = [float(v) for v in values]
    except TypeError as exc:
        raise ValueError(f"Encoder returned a non-iterable embedding for {item_id}") from exc
    if not out:
        raise ValueError(f"Encoder returned an empty embedding for {item_id}")
    return out


def extract_item_embeddings(
    items: list[ItemRecord],
    encoder: Any,
    batch_size: int = 32,
) -> list[ItemRecord]:
    """Extract embeddings for each item using an OutfitTransformer-compatible encoder.

    Args:
        items: ItemRecords with image_path set; item_embedding will be populated.
        encoder: Adapter exposing either ``encode_items`` or ``encode_item``.
        batch_size: Batch size passed to ``encode_items`` when available.

    Returns:
        The same list with ``item_embedding`` populated in-place.
    """
    if not items:
        return items

    if hasattr(encoder, "encode_items"):
        embeddings = encoder.encode_items(items, batch_size=batch_size)
        if len(embeddings) != len(items):
            raise ValueError(
                f"encoder returned {len(embeddings)} embeddings for {len(items)} items"
            )
        for item, embedding in zip(items, embeddings, strict=True):
            item.item_embedding = _as_float_list(embedding, item_id=item.item_id)
        return items

    if hasattr(encoder, "encode_item"):
        for item in items:
            item.item_embedding = _as_float_list(encoder.encode_item(item), item_id=item.item_id)
        return items

    raise TypeError("encoder must provide encode_items(items, batch_size) or encode_item(item)")
