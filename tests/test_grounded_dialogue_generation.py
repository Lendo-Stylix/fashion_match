from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
from scripts.stylist.build_grounded_scenario_bank import build_grounded_scenario_bank
from scripts.stylist.generate_grounded_dialogues import (
    DEFAULT_SYSTEM_PROMPT,
    generate_dialogues_from_scenarios,
    write_generated_dialogues,
)

from outfitmatch.kb.catalog import load_catalog_items
from outfitmatch.stylist.validation import validate_tool_calls


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


def test_generate_dialogues_from_scenarios_template_backend(tmp_path: Path):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)
    scenarios = build_grounded_scenario_bank(items, seed=17, max_examples_per_task=1)

    examples = generate_dialogues_from_scenarios(
        scenarios,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        backend="template",
    )

    assert len(examples) == len(scenarios)
    by_task = {example["task_type"]: example for example in examples}

    tool_calling = by_task["tool_calling_grounded"]
    assert validate_tool_calls(tool_calling["messages"][-1]["content"])[0] is True

    explain = by_task["recommend_explain_grounded"]
    assert explain["messages"][-1]["content"]
    assert explain["messages"][-1]["content"].count("item_") == 0
    assert explain["messages"][-1]["content"] != tool_calling["messages"][-1]["content"]

    follow_up = by_task["ask_missing_info_grounded"]
    assert "<tool_call>" not in follow_up["messages"][-1]["content"]

    multi_turn = by_task["multi_turn_grounded"]
    assert [message["role"] for message in multi_turn["messages"]] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_write_generated_dialogues_writes_packaging_compatible_jsonl(tmp_path: Path):
    rows = [
        {
            "messages": [
                {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": "Mình cần outfit đi làm."},
                {
                    "role": "assistant",
                    "content": (
                        '<tool_call>{"name":"search_outfits",'
                        '"arguments":{"occasion":"office"}}</tool_call>'
                    ),
                },
            ],
            "task_type": "tool_calling_grounded",
            "source_set": "grounded_generated",
            "source_file": "scenario_bank.jsonl",
        }
    ]

    manifest = write_generated_dialogues(tmp_path, rows)

    train_path = tmp_path / "train.jsonl"
    assert train_path.is_file()
    loaded = [json.loads(line) for line in train_path.read_text(encoding="utf-8").splitlines()]
    assert loaded == rows
    assert manifest["total_examples"] == 1
    assert manifest["task_counts"] == {"tool_calling_grounded": 1}


def test_generate_grounded_dialogues_cli_runs_directly(tmp_path: Path):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)
    scenarios = build_grounded_scenario_bank(items, seed=19, max_examples_per_task=1)
    scenario_path = tmp_path / "scenario_bank.jsonl"
    scenario_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in scenarios) + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "generated_out"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/stylist/generate_grounded_dialogues.py",
            str(scenario_path),
            "--output-dir",
            str(output_dir),
            "--backend",
            "template",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "train.jsonl").is_file()
    assert (output_dir / "manifest.json").is_file()
