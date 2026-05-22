"""Item embedding extraction using OutfitTransformer-labse.

Implemented in Sprint 1-2. See Kien_truc_v3.1.md §3.4 Bước 2.

Usage (once Sprint 1-2 is implemented):
    from outfitmatch.kb.embedding import extract_item_embeddings
    items_with_embs = extract_item_embeddings(items, encoder, batch_size=32)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from outfitmatch.kb.schema import ItemRecord


def extract_item_embeddings(
    items: list[ItemRecord],
    encoder: Any,
    batch_size: int = 32,
) -> list[ItemRecord]:
    """Extract embeddings for each item using the OT-labse Vision+Text encoder.

    Args:
        items: ItemRecords with image_path set; item_embedding will be populated.
        encoder: OutfitTransformer-labse encoder loaded with trust_remote_code=True.
                 Verify output dimension before creating the Qdrant collection.
        batch_size: GPU batch size.

    Returns:
        Same list with item_embedding populated in-place.
    """
    raise NotImplementedError("Implement in Sprint 1-2: Tầng 1 Item Embedding Extraction")
