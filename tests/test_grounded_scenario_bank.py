from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
from scripts.stylist.build_grounded_scenario_bank import (
    build_grounded_scenario_bank,
    summarize_scenario_bank,
)

from outfitmatch.kb.catalog import load_catalog_items


def _write_catalog(tmp_path: Path) -> tuple[Path, Path]:
    catalog_path = tmp_path / "catalog.parquet"
    links_path = tmp_path / "links.parquet"
    pd.DataFrame(
        [
            {
                "item_id": "item_office_top",
                "category": "top",
                "image_path": "data/custom/catalog/images/item_office_top.jpg",
                "title_vi": "Áo sơ mi công sở",
                "desc_vi": "Áo sơ mi trắng",
                "colors": '["trắng"]',
                "collected_date": "2026-06-23",
                "collector": "unit",
                "formality": "smart_casual",
                "gender": "women",
            },
            {
                "item_id": "item_travel_top",
                "category": "top",
                "image_path": "data/custom/catalog/images/item_travel_top.jpg",
                "title_vi": "Áo thun du lịch",
                "desc_vi": "Áo thun thoải mái",
                "colors": '["xanh"]',
                "collected_date": "2026-06-23",
                "collector": "unit",
                "formality": "casual",
                "gender": "women",
            },
            {
                "item_id": "item_party_dress",
                "category": "dress",
                "image_path": "data/custom/catalog/images/item_party_dress.jpg",
                "title_vi": "Đầm dự tiệc",
                "desc_vi": "Đầm đen thanh lịch",
                "colors": '["đen"]',
                "collected_date": "2026-06-23",
                "collector": "unit",
                "formality": "formal",
                "gender": "women",
            },
        ]
    ).to_parquet(catalog_path, index=False)
    pd.DataFrame(
        [
            {
                "item_id": "item_office_top",
                "store_id": "yody_vn",
                "source_product_id": "p1",
                "product_url": "https://yody.vn/p1",
                "price_vnd": 350000,
                "sale_price_vnd": None,
                "sku": "SKU1",
                "in_stock": True,
                "available_sizes": '["S", "M"]',
                "sizes_in_stock": '["S", "M"]',
            },
            {
                "item_id": "item_travel_top",
                "store_id": "canifa_vn",
                "source_product_id": "p2",
                "product_url": "https://canifa.com/p2",
                "price_vnd": 250000,
                "sale_price_vnd": None,
                "sku": "SKU2",
                "in_stock": True,
                "available_sizes": '["M", "L"]',
                "sizes_in_stock": '["M"]',
            },
            {
                "item_id": "item_party_dress",
                "store_id": "format_vn",
                "source_product_id": "p3",
                "product_url": "https://format.vn/p3",
                "price_vnd": 900000,
                "sale_price_vnd": None,
                "sku": "SKU3",
                "in_stock": True,
                "available_sizes": '["S", "M"]',
                "sizes_in_stock": '["S"]',
            },
        ]
    ).to_parquet(links_path, index=False)
    return catalog_path, links_path


def test_build_grounded_scenario_bank_is_deterministic_and_uses_real_item_ids(tmp_path: Path):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)

    scenarios_a = build_grounded_scenario_bank(items, seed=7, max_examples_per_task=1)
    scenarios_b = build_grounded_scenario_bank(items, seed=7, max_examples_per_task=1)

    assert scenarios_a == scenarios_b
    item_ids = {item.item_id for item in items}
    assert scenarios_a
    assert {
        scenario["seed_item_id"] for scenario in scenarios_a if scenario["seed_item_id"]
    } <= item_ids
    assert {
        candidate_id for scenario in scenarios_a for candidate_id in scenario["candidate_item_ids"]
    } <= item_ids


def test_build_grounded_scenario_bank_includes_followup_and_zero_result_cases(tmp_path: Path):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)

    scenarios = build_grounded_scenario_bank(items, seed=11, max_examples_per_task=1)

    ask_missing = next(
        scenario for scenario in scenarios if scenario["task_type"] == "ask_missing_info_grounded"
    )
    assert ask_missing["request"]["occasion"] is None
    assert ask_missing["expected_behavior"] == {
        "should_call_tool": False,
        "should_ask_followup": True,
        "should_decline": False,
        "should_relax_constraints": False,
    }

    no_result = next(
        scenario
        for scenario in scenarios
        if scenario["task_type"] == "no_result_or_relax_constraints"
    )
    assert no_result["candidate_item_ids"] == []
    assert no_result["expected_behavior"] == {
        "should_call_tool": False,
        "should_ask_followup": False,
        "should_decline": False,
        "should_relax_constraints": True,
    }
    assert no_result["request"]["price_max"] < 250000


def test_summarize_scenario_bank_reports_task_and_occasion_coverage(tmp_path: Path):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)

    scenarios = build_grounded_scenario_bank(items, seed=5, max_examples_per_task=1)
    summary = summarize_scenario_bank(scenarios)

    assert summary["total_scenarios"] == len(scenarios)
    assert summary["task_counts"]["tool_calling_grounded"] == 1
    assert summary["task_counts"]["ask_missing_info_grounded"] == 1
    assert summary["task_counts"]["no_result_or_relax_constraints"] == 1
    assert summary["occasion_counts"]["office"] >= 1
    assert summary["occasion_counts"]["travel"] >= 1


def test_build_grounded_scenario_bank_cli_runs_directly(tmp_path: Path):
    catalog_path, links_path = _write_catalog(tmp_path)
    output_dir = tmp_path / "scenario_bank_out"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/stylist/build_grounded_scenario_bank.py",
            str(catalog_path),
            str(links_path),
            "--output-dir",
            str(output_dir),
            "--max-examples-per-task",
            "1",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "scenario_bank.jsonl").is_file()
    assert (output_dir / "scenario_manifest.json").is_file()


def test_build_grounded_scenario_bank_expands_task_coverage_and_grounding_fields(
    tmp_path: Path,
):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)

    scenarios = build_grounded_scenario_bank(items, seed=13, max_examples_per_task=1)

    assert {scenario["task_type"] for scenario in scenarios} >= {
        "tool_calling_grounded",
        "ask_missing_info_grounded",
        "no_result_or_relax_constraints",
        "recommend_explain_grounded",
        "polite_decline_anti_hallucination",
        "multi_turn_grounded",
        "body_fit_grounded",
    }

    for scenario in scenarios:
        if scenario["seed_item_id"] is not None:
            assert scenario["seed_item"]["item_id"] == scenario["seed_item_id"]
            assert scenario["seed_item"]["title_vi"]
        assert isinstance(scenario["candidate_items"], list)

    decline = next(
        scenario
        for scenario in scenarios
        if scenario["task_type"] == "polite_decline_anti_hallucination"
    )
    assert decline["expected_behavior"]["should_decline"] is True

    multi_turn = next(
        scenario for scenario in scenarios if scenario["task_type"] == "multi_turn_grounded"
    )
    assert multi_turn["target_occasion"] is not None


def test_build_grounded_scenario_bank_supports_explicit_task_counts(tmp_path: Path):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)
    target_counts = {
        "tool_calling_grounded": 2,
        "recommend_explain_grounded": 2,
        "ask_missing_info_grounded": 1,
        "no_result_or_relax_constraints": 1,
        "polite_decline_anti_hallucination": 1,
        "multi_turn_grounded": 1,
        "body_fit_grounded": 1,
    }

    scenarios = build_grounded_scenario_bank(items, seed=23, counts_by_task=target_counts)
    summary = summarize_scenario_bank(scenarios)

    assert summary["total_scenarios"] == sum(target_counts.values())
    for task_type, expected_count in target_counts.items():
        assert summary["task_counts"][task_type] == expected_count
