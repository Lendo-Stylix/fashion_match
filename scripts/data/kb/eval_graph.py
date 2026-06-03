"""Evaluate the compatibility graph KB: coverage, coherence, FITB recall, ablations.

Example:
    uv run python -m scripts.data.kb.eval_graph --seeds 300
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from outfitmatch.kb.catalog import load_catalog_items
from outfitmatch.kb.graph_eval import evaluate_graph, summarize_graph_report
from outfitmatch.kb.graph_store import EDGES_PARQUET, OutfitGraph, read_edges
from outfitmatch.kb.traversal import AssemblyConfig, assemble_outfits
from outfitmatch.metrics.retrieval import fitb_recall_at_k
from outfitmatch.vocab import formalities_for_occasion
from scripts.data.scrape.base import CATALOG_DIR

if TYPE_CHECKING:
    from outfitmatch.kb.schema import ItemRecord


logger = logging.getLogger("kb.eval_graph")


def _seed_ids(items: list[ItemRecord], *, occasion: str | None, limit: int) -> list[str]:
    bands = formalities_for_occasion(occasion) if occasion else None
    seed_ids: list[str] = []
    for item in items:
        if item.category not in {"top", "dress"}:
            continue
        if bands is not None and item.formality not in bands:
            continue
        seed_ids.append(item.item_id)
        if limit and len(seed_ids) >= limit:
            break
    return seed_ids


def _log_fitb(label: str, graph: OutfitGraph, seed_ids: list[str], config: AssemblyConfig) -> None:
    outfits = assemble_outfits(graph, seed_ids, config=config)
    logger.info("%s fitb_recall@5(mask shoes): %.4f", label, fitb_recall_at_k(graph, outfits, k=5))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the OutfitMatch compatibility graph")
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_metadata.parquet")
    parser.add_argument("--links", type=Path, default=CATALOG_DIR / "item_store_links.parquet")
    parser.add_argument("--edges", type=Path, default=EDGES_PARQUET)
    parser.add_argument(
        "--seeds",
        type=int,
        default=300,
        help="Max anchor seeds to sweep (0 = no cap / full sweep).",
    )
    parser.add_argument("--occasion", type=str, default="office", help="Occasion ablation pivot")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    items = load_catalog_items(args.catalog, args.links, genders={"men", "women", "unisex"})
    edges = read_edges(args.edges)
    graph = OutfitGraph(items, edges)

    beam3 = AssemblyConfig(beam=3)
    greedy = AssemblyConfig(beam=1)

    all_seeds = _seed_ids(items, occasion=None, limit=args.seeds)
    report = evaluate_graph(graph, items, edges, all_seeds, config=beam3)
    logger.info("graph report:\n%s", summarize_graph_report(report))
    _log_fitb("all-seeds", graph, all_seeds, beam3)

    occasion_seeds = _seed_ids(items, occasion=args.occasion, limit=args.seeds)
    occasion_report = evaluate_graph(graph, items, edges, occasion_seeds, config=beam3)
    logger.info(
        "ablation occasion=%s: seeds %d→%d, coverage %.4f vs %.4f, assembled %d vs %d",
        args.occasion,
        len(all_seeds),
        len(occasion_seeds),
        occasion_report.catalog_coverage,
        report.catalog_coverage,
        occasion_report.n_assembled,
        report.n_assembled,
    )
    _log_fitb(f"occasion={args.occasion}", graph, occasion_seeds, beam3)

    greedy_report = evaluate_graph(graph, items, edges, all_seeds, config=greedy)
    logger.info(
        "ablation decoding beam=1 vs beam=3: coverage %.4f vs %.4f, assembled %d vs %d",
        greedy_report.catalog_coverage,
        report.catalog_coverage,
        greedy_report.n_assembled,
        report.n_assembled,
    )
    _log_fitb("beam=1", graph, all_seeds, greedy)

    if report.coherence_violations > 0:
        logger.error("coherence_violations=%d — graph build regressed", report.coherence_violations)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
