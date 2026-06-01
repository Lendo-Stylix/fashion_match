"""Index Knowledge Base outfits into Qdrant (v3.1-lite Tầng 1 Bước 6).

Creates the `outfits` collection with the verified OT-labse vector dimension and
the payload indexes required by Tầng 3 filter-first retrieval (`occasion`, `style`,
`body_shapes_fit`, `price_tier`, `season`, `has_vn_store`).

Vector dim MUST be read from the OT-labse checkpoint config — never hardcoded
(see Kien_truc_v3.1.md §3.5).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse
from uuid import NAMESPACE_URL, uuid5

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

_POINT_ID_NAMESPACE = "outfitmatch:outfits"


def _import_qdrant() -> tuple[type[Any], Any]:
    try:
        from qdrant_client import QdrantClient, models
    except ImportError as exc:  # pragma: no cover - exercised only in missing-dep envs
        raise RuntimeError("qdrant-client is required for KB indexing; run `uv sync`.") from exc
    return QdrantClient, models


def _file_url_to_path(url: str) -> str:
    parsed = urlparse(url)
    path = unquote(parsed.path)
    if parsed.netloc:
        path = f"//{parsed.netloc}{path}"
    if len(path) >= 3 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return path


def _make_client(qdrant_url: str) -> Any:
    QdrantClient, _ = _import_qdrant()
    if qdrant_url in {":memory:", "memory://"}:
        return QdrantClient(location=":memory:")
    if qdrant_url.startswith("path://"):
        return QdrantClient(path=qdrant_url.removeprefix("path://"))
    if qdrant_url.startswith("file://"):
        return QdrantClient(path=_file_url_to_path(qdrant_url))
    return QdrantClient(url=qdrant_url, timeout=30)


def _close_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()


def _collection_exists(client: Any, collection_name: str) -> bool:
    exists = getattr(client, "collection_exists", None)
    if callable(exists):
        return bool(exists(collection_name))
    collections = client.get_collections().collections
    return collection_name in {collection.name for collection in collections}


def _collection_vector_dim(client: Any, collection_name: str) -> int:
    info = client.get_collection(collection_name)
    vectors = info.config.params.vectors
    if hasattr(vectors, "size"):
        return int(vectors.size)
    if isinstance(vectors, dict) and len(vectors) == 1:
        vector_params = next(iter(vectors.values()))
        if hasattr(vector_params, "size"):
            return int(vector_params.size)
    raise ValueError(
        f"Qdrant collection {collection_name!r} must use a single unnamed dense vector."
    )


def _is_existing_index_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "already exists" in message or "same" in message and "schema" in message


def _ensure_payload_indexes(client: Any, models: Any, collection_name: str) -> None:
    for field in PAYLOAD_INDEX_FIELDS:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception as exc:
            if not _is_existing_index_error(exc):
                raise


def _ensure_outfits_collection(
    client: Any,
    models: Any,
    *,
    vector_dim: int,
    collection_name: str,
) -> None:
    if vector_dim <= 0:
        raise ValueError("vector_dim must be a positive integer")

    if not _collection_exists(client, collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=vector_dim, distance=models.Distance.COSINE),
        )
    else:
        existing_dim = _collection_vector_dim(client, collection_name)
        if existing_dim != vector_dim:
            raise ValueError(
                f"Qdrant collection {collection_name!r} has vector dim {existing_dim}, "
                f"but KB outfits use dim {vector_dim}. Recreate the collection or pass "
                "the verified OT-labse dimension."
            )

    _ensure_payload_indexes(client, models, collection_name)


def _coerce_vector(outfit: OutfitRecord) -> list[float]:
    try:
        vector = [float(value) for value in outfit.outfit_embedding]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"outfit {outfit.outfit_id!r} has a non-numeric outfit_embedding") from exc
    if not vector:
        raise ValueError(f"outfit {outfit.outfit_id!r} has an empty outfit_embedding")
    return vector


def _infer_vector_dim(outfits: Sequence[OutfitRecord]) -> int:
    expected_dim: int | None = None
    for outfit in outfits:
        dim = len(_coerce_vector(outfit))
        if expected_dim is None:
            expected_dim = dim
        elif dim != expected_dim:
            raise ValueError(
                f"outfit {outfit.outfit_id!r} embedding dim {dim} does not match "
                f"expected dim {expected_dim}"
            )
    if expected_dim is None:
        raise ValueError("cannot infer vector dim from an empty outfit list")
    return expected_dim


def _stable_point_id(outfit_id: str) -> str:
    # Qdrant point IDs must be uint64 integers or UUIDs; `OF_00001` is kept in payload.
    return str(uuid5(NAMESPACE_URL, f"{_POINT_ID_NAMESPACE}:{outfit_id}"))


def _batched[T](items: Sequence[T], batch_size: int) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def create_outfits_collection(
    qdrant_url: str,
    vector_dim: int,
    collection_name: str = "outfits",
) -> None:
    """Create the `outfits` Qdrant collection + payload indexes.

    Args:
        qdrant_url: Qdrant endpoint, e.g. `http://localhost:6333`. For tests/local
            smoke runs, `:memory:`, `memory://`, `path://<dir>`, and `file://<dir>`
            are also supported by `qdrant-client`'s embedded store.
        vector_dim: Dimension read from OT-labse checkpoint config — do NOT hardcode.
        collection_name: Collection name (default `outfits`).

    Raises:
        ValueError: If `vector_dim` is invalid or an existing collection has a
            different vector dimension.
        RuntimeError: If `qdrant-client` is not installed.
    """
    _, models = _import_qdrant()
    client = _make_client(qdrant_url)
    try:
        _ensure_outfits_collection(
            client,
            models,
            vector_dim=vector_dim,
            collection_name=collection_name,
        )
    finally:
        _close_client(client)


def index_outfits(
    outfits: list[OutfitRecord],
    qdrant_url: str,
    collection_name: str = "outfits",
    batch_size: int = 256,
) -> None:
    """Upsert OutfitRecord list into Qdrant (one point per outfit).

    The collection is created on demand using the vector dimension inferred from
    `outfit.outfit_embedding`. Qdrant point IDs are deterministic UUID5 values
    derived from `outfit_id` because raw IDs like `OF_00001` are not valid Qdrant
    point IDs. The canonical `outfit_id` is always stored in the payload.

    Each point: `id=uuid5(outfit_id)`, `vector=outfit_embedding`,
    `payload=to_qdrant_payload()`.

    Args:
        outfits: Non-empty list of `OutfitRecord` objects with populated embeddings.
        qdrant_url: Qdrant endpoint or embedded-store URL accepted by
            `create_outfits_collection()`.
        collection_name: Collection name (default `outfits`).
        batch_size: Number of points per upsert request.

    Raises:
        ValueError: If embeddings are empty, non-numeric, inconsistent in length,
            or `batch_size` is invalid.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be a positive integer")
    if not outfits:
        return

    vector_dim = _infer_vector_dim(outfits)
    _, models = _import_qdrant()
    client = _make_client(qdrant_url)
    try:
        _ensure_outfits_collection(
            client,
            models,
            vector_dim=vector_dim,
            collection_name=collection_name,
        )
        for batch in _batched(outfits, batch_size):
            points = [
                models.PointStruct(
                    id=_stable_point_id(outfit.outfit_id),
                    vector=_coerce_vector(outfit),
                    payload=outfit.to_qdrant_payload(),
                )
                for outfit in batch
            ]
            client.upsert(collection_name=collection_name, points=points, wait=True)
    finally:
        _close_client(client)
