"""Persist and load the outfit compatibility graph (edges parquet + Qdrant nodes)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

import pandas as pd
from scripts.data.scrape.base import CATALOG_DIR

from outfitmatch.kb.graph import Edge
from outfitmatch.kb.qdrant_index import (
    _batched,
    _close_client,
    _collection_exists,
    _collection_vector_dim,
    _import_qdrant,
    _is_existing_index_error,
    _make_client,
)

if TYPE_CHECKING:
    from outfitmatch.kb.schema import ItemRecord


GRAPH_DIR: Path = CATALOG_DIR.parent / "graph"
EDGES_PARQUET: Path = GRAPH_DIR / "item_edges.parquet"

_EDGE_COLUMNS = ("src_id", "dst_id", "src_category", "dst_category", "weight")
ITEM_PAYLOAD_INDEX_FIELDS: tuple[str, ...] = (
    "category",
    "gender",
    "formality",
    "price_tier",
    "has_vn_store",
    "in_stock",
    "store_id",
)

_ITEM_POINT_NAMESPACE = "outfitmatch:items"


def write_edges(edges: list[Edge], path: Path = EDGES_PARQUET) -> Path:
    """Write canonical graph edges to parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "src_id": edge.src_id,
                "dst_id": edge.dst_id,
                "src_category": edge.src_category,
                "dst_category": edge.dst_category,
                "weight": float(edge.weight),
            }
            for edge in edges
        ],
        columns=list(_EDGE_COLUMNS),
    )
    frame.to_parquet(path, index=False)
    return path


def read_edges(path: Path = EDGES_PARQUET) -> list[Edge]:
    """Read graph edges from parquet, or return an empty list when absent."""
    if not path.exists():
        return []
    frame = pd.read_parquet(path)
    missing = set(_EDGE_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"{path} missing edge columns {sorted(missing)}; rebuild with --rebuild")
    return [
        Edge(
            src_id=str(row.src_id),
            dst_id=str(row.dst_id),
            src_category=str(row.src_category),
            dst_category=str(row.dst_category),
            weight=float(row.weight),
        )
        for row in frame.itertuples(index=False)
    ]


class OutfitGraph:
    """In-memory adjacency for sparse compatibility traversal."""

    def __init__(self, items: list[ItemRecord], edges: list[Edge]) -> None:
        self._items: dict[str, ItemRecord] = {item.item_id: item for item in items}
        self._adj: dict[str, dict[str, list[tuple[str, float]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._weights: dict[tuple[str, str], float] = {}

        for edge in edges:
            self._adj[edge.src_id][edge.dst_category].append((edge.dst_id, edge.weight))
            self._adj[edge.dst_id][edge.src_category].append((edge.src_id, edge.weight))
            self._weights[(edge.src_id, edge.dst_id)] = edge.weight
            self._weights[(edge.dst_id, edge.src_id)] = edge.weight

        for partner_map in self._adj.values():
            for neighbors in partner_map.values():
                neighbors.sort(key=lambda pair: (-pair[1], pair[0]))

    def neighbors(self, item_id: str, partner_category: str) -> list[tuple[str, float]]:
        """Return ``(neighbor_id, weight)`` sorted by weight descending."""
        return list(self._adj.get(item_id, {}).get(partner_category, []))

    def edge_weight(self, a_id: str, b_id: str) -> float | None:
        """Return the edge weight for ``a``-``b``, or ``None`` when disconnected."""
        return self._weights.get((a_id, b_id))

    def item(self, item_id: str) -> ItemRecord:
        """Return the backing item node by id."""
        return self._items[item_id]


def load_graph(edges_path: Path = EDGES_PARQUET, *, items: list[ItemRecord]) -> OutfitGraph:
    """Load an ``OutfitGraph`` from edge parquet plus in-memory item records."""
    return OutfitGraph(items, read_edges(edges_path))


def _item_point_id(item_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{_ITEM_POINT_NAMESPACE}:{item_id}"))


def _item_price_tier(price_vnd: int) -> str:
    if price_vnd < 300_000:
        return "budget"
    if price_vnd <= 1_000_000:
        return "mid"
    return "premium"


def _item_payload(item: ItemRecord) -> dict[str, Any]:
    price = int(item.store.get("price_vnd") or 0)
    return {
        "item_id": item.item_id,
        "category": item.category,
        "gender": item.gender,
        "formality": item.formality,
        "price_vnd": price,
        "price_tier": _item_price_tier(price),
        "has_vn_store": bool(item.store.get("product_url")),
        "in_stock": bool(item.store.get("in_stock")),
        "store_id": str(item.store.get("store_id") or ""),
        "colors": [str(color) for color in list(item.store.get("colors", []) or []) if str(color)],
        "image_path": item.image_path,
        "product_url": str(item.store.get("product_url") or ""),
    }


def _coerce_item_vector(item: ItemRecord) -> list[float]:
    try:
        vector = [float(value) for value in item.item_embedding]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"item {item.item_id!r} has a non-numeric item_embedding") from exc
    if not vector:
        raise ValueError(f"item {item.item_id!r} has an empty item_embedding")
    return vector


def _infer_item_vector_dim(items: list[ItemRecord]) -> int:
    expected_dim: int | None = None
    for item in items:
        dim = len(_coerce_item_vector(item))
        if expected_dim is None:
            expected_dim = dim
        elif dim != expected_dim:
            raise ValueError(
                f"item {item.item_id!r} embedding dim {dim} does not match "
                f"expected dim {expected_dim}"
            )
    if expected_dim is None:
        raise ValueError("cannot infer vector dim from an empty item list")
    return expected_dim


def create_items_collection(
    qdrant_url: str,
    vector_dim: int,
    collection_name: str = "items",
) -> None:
    """Create the Qdrant ``items`` collection plus payload indexes."""
    if vector_dim <= 0:
        raise ValueError("vector_dim must be a positive integer")

    _, models = _import_qdrant()
    client = _make_client(qdrant_url)
    try:
        if not _collection_exists(client, collection_name):
            client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_dim,
                    distance=models.Distance.COSINE,
                ),
            )
        else:
            existing_dim = _collection_vector_dim(client, collection_name)
            if existing_dim != vector_dim:
                raise ValueError(
                    f"Qdrant collection {collection_name!r} has vector dim {existing_dim}, "
                    f"but item nodes use dim {vector_dim}. Recreate the collection first."
                )

        for field in ITEM_PAYLOAD_INDEX_FIELDS:
            try:
                client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception as exc:
                if not _is_existing_index_error(exc):
                    raise
    finally:
        _close_client(client)


def index_item_nodes(
    items: list[ItemRecord],
    qdrant_url: str,
    collection_name: str = "items",
    batch_size: int = 256,
) -> None:
    """Upsert item nodes into the Qdrant ``items`` collection."""
    if batch_size <= 0:
        raise ValueError("batch_size must be a positive integer")

    nodes = [item for item in items if item.item_embedding]
    if not nodes:
        return

    vector_dim = _infer_item_vector_dim(nodes)
    _, models = _import_qdrant()
    client = _make_client(qdrant_url)
    try:
        if not _collection_exists(client, collection_name):
            client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_dim,
                    distance=models.Distance.COSINE,
                ),
            )
        else:
            existing_dim = _collection_vector_dim(client, collection_name)
            if existing_dim != vector_dim:
                raise ValueError(
                    f"Qdrant collection {collection_name!r} has vector dim {existing_dim}, "
                    f"but item nodes use dim {vector_dim}. Recreate the collection first."
                )

        for field in ITEM_PAYLOAD_INDEX_FIELDS:
            try:
                client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception as exc:
                if not _is_existing_index_error(exc):
                    raise

        for batch in _batched(nodes, batch_size):
            points = [
                models.PointStruct(
                    id=_item_point_id(item.item_id),
                    vector=_coerce_item_vector(item),
                    payload=_item_payload(item),
                )
                for item in batch
            ]
            client.upsert(collection_name=collection_name, points=points, wait=True)
    finally:
        _close_client(client)
