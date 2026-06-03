"""Build the OutfitMatch compatibility graph from the validated VN catalog.

Examples:
    uv run python -m scripts.data.kb.build_graph --qdrant-url path://data/cache/qdrant
    uv run python -m scripts.data.kb.build_graph --no-qdrant --limit-per-category 80
    uv run python -m scripts.data.kb.build_graph --incremental --no-qdrant
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from outfitmatch.kb.catalog import group_items_by_category, load_catalog_items
from outfitmatch.kb.embedding import extract_item_embeddings
from outfitmatch.kb.graph import build_edges
from outfitmatch.kb.graph_store import EDGES_PARQUET, index_item_nodes, read_edges, write_edges
from outfitmatch.kb.pair_scoring import HeuristicPairScorer
from outfitmatch.kb.scoring import HeuristicOutfitScorer
from scripts.data.scrape.base import CATALOG_DIR

logger = logging.getLogger("kb.build_graph")


def _flatten_items(items_by_category: dict[str, list]) -> list:
    items: list = []
    for category in sorted(items_by_category):
        items.extend(items_by_category[category])
    return items


def _ensure_embeddings(items: list) -> None:
    missing = [item for item in items if not item.item_embedding]
    if not missing:
        return
    extract_item_embeddings(missing, HeuristicOutfitScorer())


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the OutfitMatch compatibility graph")
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_metadata.parquet")
    parser.add_argument("--links", type=Path, default=CATALOG_DIR / "item_store_links.parquet")
    parser.add_argument("--edges-out", type=Path, default=EDGES_PARQUET)
    parser.add_argument("--k", type=int, default=15, help="Top-K neighbours per partner-category")
    parser.add_argument(
        "--limit-per-category",
        type=int,
        default=0,
        help="Cap items/category for smoke runs (0 = no cap)",
    )
    parser.add_argument("--include-kid", action="store_true", help="Include kids' wear")
    parser.add_argument("--qdrant-url", type=str, default="path://data/cache/qdrant")
    parser.add_argument("--no-qdrant", action="store_true", help="Write parquet only")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only new item_ids anchor new edges; existing edges are preserved",
    )
    parser.add_argument("--rebuild", action="store_true", help="Force full rebuild")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    genders = None if args.include_kid else {"men", "women", "unisex"}
    items = load_catalog_items(args.catalog, args.links, genders=genders)
    if args.limit_per_category > 0:
        items = _flatten_items(
            group_items_by_category(items, limit_per_category=args.limit_per_category)
        )
    items = sorted(items, key=lambda item: item.item_id)
    _ensure_embeddings(items)
    logger.info("loaded %d items", len(items))

    scorer = HeuristicPairScorer()
    if args.incremental and not args.rebuild:
        existing_edges = read_edges(args.edges_out)
        known_ids = {edge.src_id for edge in existing_edges} | {
            edge.dst_id for edge in existing_edges
        }
        new_items = [item for item in items if item.item_id not in known_ids]
        logger.info(
            "incremental mode: %d new items, %d existing edges",
            len(new_items),
            len(existing_edges),
        )
        new_edges = build_edges(items, scorer, k=args.k, anchors=new_items) if new_items else []
        seen = {(edge.src_id, edge.dst_id) for edge in existing_edges}
        edges = [
            *existing_edges,
            *(edge for edge in new_edges if (edge.src_id, edge.dst_id) not in seen),
        ]
        edges.sort(key=lambda edge: (edge.src_id, edge.dst_id))
    else:
        edges = build_edges(items, scorer, k=args.k)

    write_edges(edges, args.edges_out)
    logger.info("wrote %d edges -> %s", len(edges), args.edges_out)

    if not args.no_qdrant:
        index_item_nodes(items, args.qdrant_url)
        logger.info("indexed %d item nodes -> %s", len(items), args.qdrant_url)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
