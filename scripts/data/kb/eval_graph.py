"""Evaluate the compatibility graph KB: coverage, coherence, FITB recall, ablations.

Outputs structured CSV (--output-csv) for reproducible experiment tracking,
plus logger.info lines for human-readable stdout.

Example:
    uv run python -m scripts.data.kb.eval_graph --seeds 300
    uv run python -m scripts.data.kb.eval_graph --seeds 300 \\
        --output-csv docs/experiments/eval_graph.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import subprocess
from datetime import UTC, datetime
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
    from outfitmatch.kb.graph_eval import GraphReport
    from outfitmatch.kb.schema import ItemRecord


logger = logging.getLogger("kb.eval_graph")

# Columns written to the --output-csv CSV file.
CSV_COLUMNS = ("ablation", "metric", "value", "timestamp")


def _git_commit_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _current_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _collect_metrics(
    ablation: str,
    graph: OutfitGraph,
    seed_ids: list[str],
    config: AssemblyConfig,
    report: GraphReport,
    timestamp: str,
    commit_sha: str,
) -> list[dict[str, str]]:
    """Build a list of metric-row dicts for a single ablation run."""
    outfits = assemble_outfits(graph, seed_ids, config=config)
    fitb = fitb_recall_at_k(graph, outfits, k=5)
    return [
        {"ablation": ablation, "metric": "catalog_coverage", "value": str(report.catalog_coverage)},
        {"ablation": ablation, "metric": "n_assembled", "value": str(report.n_assembled)},
        {"ablation": ablation, "metric": "fitb_recall@5", "value": str(fitb)},
        {
            "ablation": ablation,
            "metric": "coherence_violations",
            "value": str(report.coherence_violations),
        },
    ]


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


def _run_ablation(
    graph: OutfitGraph,
    items: list[ItemRecord],
    edges: list,
    seed_ids: list[str],
    label: str,
    config: AssemblyConfig,
    timestamp: str,
    commit_sha: str,
    rows: list[dict[str, str]],
) -> GraphReport:
    """Evaluate one ablation, log, and collect metrics."""
    report = evaluate_graph(graph, items, edges, seed_ids, config=config)
    logger.info(
        "%s: coverage=%.4f, assembled=%d, violations=%d",
        label,
        report.catalog_coverage,
        report.n_assembled,
        report.coherence_violations,
    )
    rows.extend(_collect_metrics(label, graph, seed_ids, config, report, timestamp, commit_sha))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the OutfitMatch compatibility graph. "
        "Exits 1 if coherence_violations > 0 (graph regression).",
    )
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_metadata.parquet")
    parser.add_argument("--links", type=Path, default=CATALOG_DIR / "item_store_links.parquet")
    parser.add_argument("--edges", type=Path, default=EDGES_PARQUET)
    parser.add_argument(
        "--seeds",
        type=int,
        default=300,
        help="Max anchor seeds to sweep (0 = no cap / full sweep).",
    )
    parser.add_argument(
        "--occasion",
        type=str,
        default="office",
        help="Occasion used for occasion-ablation pivot (default: office).",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        dest="output_csv",
        help="Write structured metric rows to this CSV file.",
    )
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

    timestamp = _current_timestamp()
    commit_sha = _git_commit_sha()
    rows: list[dict[str, str]] = []

    # Ablation 1 — all seeds (baseline)
    all_seeds = _seed_ids(items, occasion=None, limit=args.seeds)
    baseline_report = _run_ablation(
        graph, items, edges, all_seeds, "all-seeds", beam3, timestamp, commit_sha, rows
    )
    logger.info("graph report:\n%s", summarize_graph_report(baseline_report))

    # Ablation 2 — occasion filter
    occasion_seeds = _seed_ids(items, occasion=args.occasion, limit=args.seeds)
    _run_ablation(
        graph,
        items,
        edges,
        occasion_seeds,
        f"occasion={args.occasion}",
        beam3,
        timestamp,
        commit_sha,
        rows,
    )

    # Ablation 3 — greedy (beam=1)
    _run_ablation(graph, items, edges, all_seeds, "beam=1", greedy, timestamp, commit_sha, rows)

    if args.output_csv:
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.output_csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        logger.info("Wrote %d metric rows to %s", len(rows), args.output_csv)

    if baseline_report.coherence_violations > 0:
        logger.error(
            "coherence_violations=%d — graph build regressed",
            baseline_report.coherence_violations,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
