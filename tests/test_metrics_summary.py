"""Tests for scripts/metrics_summary.py aggregation logic."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.metrics_summary import (
    aggregate_csv_files,
    build_json_report,
    build_markdown_table,
    read_csv_metrics,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    path = tmp_path / "eval_graph.csv"
    path.write_text(
        "ablation,metric,value,timestamp\n"
        "all-seeds,catalog_coverage,0.72,2026-07-10T10:00:00+00:00\n"
        "all-seeds,n_assembled,142,2026-07-10T10:00:00+00:00\n"
        "all-seeds,fitb_recall@5,0.95,2026-07-10T10:00:00+00:00\n"
        "occasion=office,catalog_coverage,0.65,2026-07-10T10:00:00+00:00\n"
        "occasion=office,fitb_recall@5,0.91,2026-07-10T10:00:00+00:00\n"
        "beam=1,catalog_coverage,0.70,2026-07-10T10:00:00+00:00\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def csv_dir(tmp_path: Path) -> Path:
    (tmp_path / "eval_graph.csv").write_text(
        "ablation,metric,value,timestamp\n"
        "all-seeds,catalog_coverage,0.72,2026-07-10T10:00:00+00:00\n",
        encoding="utf-8",
    )
    (tmp_path / "fashion_eval.csv").write_text(
        "ablation,metric,value,timestamp\nask_back,accuracy,0.95,2026-07-10T11:00:00+00:00\n",
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# read_csv_metrics
# ---------------------------------------------------------------------------


def test_read_csv_metrics_returns_dict_rows(sample_csv: Path) -> None:
    rows = read_csv_metrics(sample_csv)
    assert len(rows) == 6
    assert rows[0]["ablation"] == "all-seeds"
    assert rows[0]["metric"] == "catalog_coverage"
    assert rows[0]["value"] == "0.72"


def test_read_csv_metrics_preserves_timestamp(sample_csv: Path) -> None:
    rows = read_csv_metrics(sample_csv)
    ts = {r["timestamp"] for r in rows}
    assert "2026-07-10T10:00:00+00:00" in ts


# ---------------------------------------------------------------------------
# aggregate_csv_files
# ---------------------------------------------------------------------------


def test_aggregate_returns_all_csvs(csv_dir: Path) -> None:
    data = aggregate_csv_files(csv_dir)
    names = set(data.keys())
    assert "eval_graph.csv" in names
    assert "fashion_eval.csv" in names


def test_aggregate_empty_dir_returns_empty(tmp_path: Path) -> None:
    data = aggregate_csv_files(tmp_path)
    assert data == {}


def test_aggregate_missing_dir_returns_empty() -> None:
    data = aggregate_csv_files(Path("/nonexistent/path"))
    assert data == {}


# ---------------------------------------------------------------------------
# build_markdown_table
# ---------------------------------------------------------------------------


def test_markdown_table_has_header_row(csv_dir: Path) -> None:
    data = aggregate_csv_files(csv_dir)
    table = build_markdown_table(data)
    assert "| Experiment | Ablation | Metric | Value | Timestamp |" in table


def test_markdown_table_includes_ablation_rows(csv_dir: Path) -> None:
    data = aggregate_csv_files(csv_dir)
    table = build_markdown_table(data)
    assert "all-seeds" in table
    assert "ask_back" in table
    assert "catalog_coverage" in table
    assert "0.72" in table


def test_markdown_table_includes_experiment_name(csv_dir: Path) -> None:
    data = aggregate_csv_files(csv_dir)
    table = build_markdown_table(data)
    assert "eval_graph.csv" in table
    assert "fashion_eval.csv" in table


# ---------------------------------------------------------------------------
# build_json_report
# ---------------------------------------------------------------------------


def test_json_report_has_generated_at(csv_dir: Path) -> None:
    data = aggregate_csv_files(csv_dir)
    report = build_json_report(data)
    assert "generated_at" in report
    assert "T" in report["generated_at"]  # ISO format


def test_json_report_nests_by_experiment_and_ablation(csv_dir: Path) -> None:
    data = aggregate_csv_files(csv_dir)
    report = build_json_report(data)
    assert "eval_graph.csv" in report["experiments"]
    assert "all-seeds" in report["experiments"]["eval_graph.csv"]
    assert "catalog_coverage" in report["experiments"]["eval_graph.csv"]["all-seeds"]


def test_json_report_metric_value_is_string(sample_csv: Path) -> None:
    data = {"test.csv": read_csv_metrics(sample_csv)}
    report = build_json_report(data)
    val = report["experiments"]["test.csv"]["all-seeds"]["catalog_coverage"]["value"]
    assert isinstance(val, str)
    assert val == "0.72"


# ---------------------------------------------------------------------------
# CLI smoke (run_cli interface)
# ---------------------------------------------------------------------------


def test_cli_exits_0_with_csvs(csv_dir: Path) -> None:
    from scripts.metrics_summary import main as summary_main

    rc = summary_main(["--dir", str(csv_dir)])
    assert rc == 0


def test_cli_exits_1_with_no_csvs(tmp_path: Path) -> None:
    from scripts.metrics_summary import main as summary_main

    rc = summary_main(["--dir", str(tmp_path)])
    assert rc == 1


def test_cli_json_format(csv_dir: Path) -> None:
    from scripts.metrics_summary import main as summary_main

    rc = summary_main(["--dir", str(csv_dir), "--format", "json"])
    assert rc == 0


def test_cli_writes_out_file(csv_dir: Path, tmp_path: Path) -> None:
    from scripts.metrics_summary import main as summary_main

    out = tmp_path / "summary.md"
    rc = summary_main(["--dir", str(csv_dir), "--out", str(out)])
    assert rc == 0
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "eval_graph.csv" in content
