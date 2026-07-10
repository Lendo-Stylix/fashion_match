"""Tests for scripts/data/kb/eval_graph.py CSV output (--output-csv flag)."""

from __future__ import annotations

import csv
from pathlib import Path

from scripts.data.kb.eval_graph import main as eval_graph_main

from outfitmatch.kb.graph_store import EDGES_PARQUET

CATALOG_DIR = Path("data/custom/catalog")


def test_output_csv_writes_all_ablation_metrics(tmp_path: Path) -> None:
    """Running eval_graph --output-csv produces a CSV with all ablation rows."""
    out_csv = tmp_path / "metrics.csv"
    rc = eval_graph_main(
        [
            "--catalog",
            str(CATALOG_DIR / "catalog_metadata.parquet"),
            "--links",
            str(CATALOG_DIR / "item_store_links.parquet"),
            "--edges",
            str(EDGES_PARQUET),
            "--seeds",
            "50",
            "--output-csv",
            str(out_csv),
        ]
    )
    assert rc == 0, "eval_graph should exit 0 (no coherence violations)"
    assert out_csv.exists(), "CSV file must be created"
    rows = list(csv.DictReader(out_csv.read_text(encoding="utf-8").splitlines()))
    assert len(rows) >= 4, f"Expected ≥4 ablation rows, got {len(rows)}: {rows}"
    # Must have at least one row per ablation type
    ablations = {r["ablation"] for r in rows}
    assert "all-seeds" in ablations, f"all-seeds ablation missing from {rows}"
    assert "occasion=office" in ablations, f"occasion=office ablation missing from {rows}"
    assert "beam=1" in ablations, f"beam=1 ablation missing from {rows}"


def test_csv_has_required_columns(tmp_path: Path) -> None:
    """CSV must contain the required structured columns."""
    out_csv = tmp_path / "cols.csv"
    eval_graph_main(
        [
            "--catalog",
            str(CATALOG_DIR / "catalog_metadata.parquet"),
            "--links",
            str(CATALOG_DIR / "item_store_links.parquet"),
            "--edges",
            str(EDGES_PARQUET),
            "--seeds",
            "30",
            "--output-csv",
            str(out_csv),
        ]
    )
    with out_csv.open(encoding="utf-8") as fh:
        headers = next(csv.reader(fh))
    REQUIRED = {"ablation", "metric", "value", "timestamp"}
    assert REQUIRED.issubset(headers), f"Missing columns. Got {headers}"


def test_csv_requires_output_flag(tmp_path: Path, capsys) -> None:
    """Without --output-csv, no CSV file is created."""
    out_csv = tmp_path / "should_not_exist.csv"
    rc = eval_graph_main(
        [
            "--catalog",
            str(CATALOG_DIR / "catalog_metadata.parquet"),
            "--links",
            str(CATALOG_DIR / "item_store_links.parquet"),
            "--edges",
            str(EDGES_PARQUET),
            "--seeds",
            "20",
        ]
    )
    assert not out_csv.exists(), "CSV must NOT be created without --output-csv flag"
    assert rc == 0, "Should still exit 0 without --output-csv"


def test_csv_rows_contain_expected_metrics(tmp_path: Path) -> None:
    """Each ablation should emit rows for catalog_coverage, n_assembled, fitb_recall@5."""
    out_csv = tmp_path / "metrics.csv"
    eval_graph_main(
        [
            "--catalog",
            str(CATALOG_DIR / "catalog_metadata.parquet"),
            "--links",
            str(CATALOG_DIR / "item_store_links.parquet"),
            "--edges",
            str(EDGES_PARQUET),
            "--seeds",
            "30",
            "--output-csv",
            str(out_csv),
        ]
    )
    rows = list(csv.DictReader(out_csv.read_text(encoding="utf-8").splitlines()))
    METRICS = {"catalog_coverage", "n_assembled", "fitb_recall@5"}
    row_metrics = {r["metric"] for r in rows}
    assert METRICS.issubset(row_metrics), f"Missing metrics. Have {row_metrics}, want {METRICS}"


def test_eval_graph_exits_1_on_coherence_violation(tmp_path: Path, monkeypatch) -> None:
    """If the graph has coherence violations, eval_graph should exit 1."""

    from outfitmatch.kb.graph_eval import GraphReport
    from outfitmatch.kb.graph_store import EDGES_PARQUET

    # Force a graph with violations by patching evaluate_graph
    def fake_evaluate(*args, **kwargs):
        return GraphReport(
            n_nodes=100,
            n_edges=200,
            degree_min=1,
            degree_median=2,
            degree_max=5,
            coherence_violations=1,  # violation!
            catalog_coverage=0.5,
            distinct_items_used=50,
            n_assembled=10,
            item_reuse_p95=3,
        )

    from scripts.data.kb import eval_graph

    monkeypatch.setattr(eval_graph, "evaluate_graph", fake_evaluate)
    monkeypatch.setattr(eval_graph, "_seed_ids", lambda *a, **k: ["item1", "item2"])
    out_csv = tmp_path / "violations.csv"
    rc = eval_graph_main(
        [
            "--catalog",
            str(CATALOG_DIR / "catalog_metadata.parquet"),
            "--links",
            str(CATALOG_DIR / "item_store_links.parquet"),
            "--edges",
            str(EDGES_PARQUET),
            "--seeds",
            "10",
            "--output-csv",
            str(out_csv),
        ]
    )
    assert rc == 1, "Should exit 1 when coherence_violations > 0"
