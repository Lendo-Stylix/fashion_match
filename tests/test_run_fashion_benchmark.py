"""Tests for the fashion-benchmark runner CLI (mock / no-GPU path)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.stylist.run_fashion_benchmark import (
    ALL_ITEM_TYPES,
    build_fashion_dataset,
    make_mock_generate_fn,
    run_cli,
)


# ---------------------------------------------------------------------------
# build_fashion_dataset
# ---------------------------------------------------------------------------
def test_build_fashion_dataset_covers_all_item_types() -> None:
    dataset = build_fashion_dataset()
    types_present = {record["item_type"] for record in dataset}
    assert types_present == set(ALL_ITEM_TYPES)
    for item_type in ALL_ITEM_TYPES:
        subset = [r for r in dataset if r["item_type"] == item_type]
        assert len(subset) >= 1, f"no items for {item_type}"


def test_build_fashion_dataset_records_have_prompt() -> None:
    dataset = build_fashion_dataset()
    for record in dataset:
        assert isinstance(record.get("prompt"), str) and record["prompt"]
        assert "item_type" in record


def test_build_fashion_dataset_type_filter() -> None:
    only_ask = build_fashion_dataset(types=["ask_back"])
    assert only_ask
    assert all(r["item_type"] == "ask_back" for r in only_ask)
    empty = build_fashion_dataset(types=["does_not_exist"])
    assert empty == []


# ---------------------------------------------------------------------------
# make_mock_generate_fn
# ---------------------------------------------------------------------------
def test_mock_generate_fn_returns_string() -> None:
    gen = make_mock_generate_fn()
    out = gen([{"role": "user", "content": "hello"}])
    assert isinstance(out, str) and out


# ---------------------------------------------------------------------------
# run_cli --mock end-to-end (no GPU)
# ---------------------------------------------------------------------------
def test_run_cli_mock_writes_valid_report(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    code = run_cli(
        ["--mock", "--output-json", str(out), "--max-samples", "3", "--types", "ask_back"]
    )
    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert "overall" in report and "per_task" in report
    assert "ask_back" in report["per_task"]
    assert report["overall"]["count"] >= 1
    for sample in report["samples"]:
        assert "generated" in sample
        assert "score" in sample


def test_run_cli_mock_runs_all_types(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    code = run_cli(["--mock", "--output-json", str(out)])
    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert set(report["per_task"]) == set(ALL_ITEM_TYPES)


def test_run_cli_mock_stdout_when_no_output(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli(["--mock", "--max-samples", "2"])
    assert code == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)  # valid JSON printed
