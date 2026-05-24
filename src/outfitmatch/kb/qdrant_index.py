"""Index Knowledge Base outfits into Qdrant (v3.1-lite Tầng 1 Bước 6).

Creates the `outfits` collection with the verified OT-labse vector dimension and
the payload indexes required by Tầng 3 filter-first retrieval (`occasion`, `style`,
`body_shapes_fit`, `price_tier`, `season`, `has_vn_store`).

Vector dim MUST be read from the OT-labse checkpoint config — never hardcoded
(see Kien_truc_v3.1.md §3.5).

Implemented in Sprint 5.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from outfitmatch.kb.schema import OutfitRecord


PAYLOAD_INDEX_FIELDS: tuple[str, ...] = (
    "occasion",
    "style",
    "body_shapes_fit",
    "price_tier",
    "season",
    "has_vn_store",
)


def create_outfits_collection(
    qdrant_url: str,
    vector_dim: int,
    collection_name: str = "outfits",
) -> None:
    """Create the `outfits` Qdrant collection + payload indexes.

    Args:
        qdrant_url: Qdrant endpoint (default `http://localhost:6333`).
        vector_dim: Dimension read from OT-labse checkpoint config — do NOT hardcode.
        collection_name: Collection name (default `outfits`).
    """
    raise NotImplementedError("Implement in Sprint 5: Qdrant collection setup")


def index_outfits(
    outfits: list[OutfitRecord],
    qdrant_url: str,
    collection_name: str = "outfits",
    batch_size: int = 256,
) -> None:
    """Upsert OutfitRecord list into Qdrant (one point per outfit).

    Each point: id=outfit_id, vector=outfit_embedding, payload=to_qdrant_payload().
    """
    raise NotImplementedError("Implement in Sprint 5: outfit upsert")
