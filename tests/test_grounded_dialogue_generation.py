from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
from scripts.stylist.build_grounded_scenario_bank import build_grounded_scenario_bank
from scripts.stylist.generate_grounded_dialogues import (
    DEFAULT_SYSTEM_PROMPT,
    _template_assistant_messages,
    build_generation_manifest,
    generate_dialogues_from_scenarios,
    write_generated_dialogues,
)
from scripts.stylist.verify_grounded_dialogues import build_report

from outfitmatch.kb.catalog import load_catalog_items
from outfitmatch.stylist.tools import render_search_outfits_tool_call
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
    assert manifest["unique_message_examples"] == 1
    assert manifest["duplicate_message_examples"] == 0
    assert manifest["tool_call_rows"] == 1


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


def test_generate_dialogues_from_large_grounded_batch_stays_unique(tmp_path: Path):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)
    scenarios = build_grounded_scenario_bank(
        items,
        seed=29,
        counts_by_task={
            "tool_calling_grounded": 8,
            "recommend_explain_grounded": 8,
            "ask_missing_info_grounded": 8,
            "no_result_or_relax_constraints": 8,
            "polite_decline_anti_hallucination": 4,
            "multi_turn_grounded": 4,
            "body_fit_grounded": 6,
        },
    )

    examples = generate_dialogues_from_scenarios(
        scenarios,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        backend="template",
    )
    signatures = {
        json.dumps(example["messages"], ensure_ascii=False, sort_keys=True) for example in examples
    }

    assert len(signatures) == len(examples)


def test_generate_dialogues_openai_compatible_backend_mocked(monkeypatch, tmp_path: Path):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)
    scenarios = build_grounded_scenario_bank(
        items,
        seed=23,
        counts_by_task={"tool_calling_grounded": 1, "multi_turn_grounded": 1},
    )

    tool_scenario = next(s for s in scenarios if s["task_type"] == "tool_calling_grounded")
    responses = iter(
        [
            render_search_outfits_tool_call(tool_scenario["request"]),
            "Bạn cho mình biết dịp chính nhé để mình lọc outfit chính xác hơn.",
        ]
    )

    def _fake_chat(*_args, **_kwargs):
        return next(responses)

    monkeypatch.setattr(
        "scripts.stylist.generate_grounded_dialogues._chat_completion_request",
        _fake_chat,
    )

    rows = generate_dialogues_from_scenarios(
        scenarios,
        backend="openai-compatible",
        model="openai/gpt-oss-120b",
        base_url_override="https://example.invalid/v1",
        api_key_override="token",
    )

    assert len(rows) == 2
    tool_row = next(row for row in rows if row["task_type"] == "tool_calling_grounded")
    multi_row = next(row for row in rows if row["task_type"] == "multi_turn_grounded")
    assert validate_tool_calls(tool_row["messages"][-1]["content"])[0] is True
    assert multi_row["messages"][-1]["content"].startswith("<tool_call>")
    report = build_report(rows)
    assert report["invalid_tool_rows"] == 0
    assert report["duplicate_message_rows"] == 0


def test_generate_dialogues_openai_compatible_multi_turn_strips_leaked_tool_call(
    monkeypatch, tmp_path: Path
):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)
    scenarios = build_grounded_scenario_bank(
        items,
        seed=31,
        counts_by_task={"multi_turn_grounded": 1},
    )
    scenario = scenarios[0]
    leaked = (
        "Bạn cho mình biết dịp chính nhé để mình lọc outfit chính xác hơn.\n\n"
        + render_search_outfits_tool_call(
            {**scenario["request"], "occasion": scenario["target_occasion"]}
        )
    )

    monkeypatch.setattr(
        "scripts.stylist.generate_grounded_dialogues._chat_completion_request",
        lambda *_args, **_kwargs: leaked,
    )

    rows = generate_dialogues_from_scenarios(
        scenarios,
        backend="openai-compatible",
        model="openai/gpt-oss-120b",
        base_url_override="https://example.invalid/v1",
        api_key_override="token",
    )

    assistants = [m["content"] for m in rows[0]["messages"] if m["role"] == "assistant"]
    assert len(assistants) == 2
    assert "<tool_call>" not in assistants[0]
    assert assistants[0] == "Bạn cho mình biết dịp chính nhé để mình lọc outfit chính xác hơn."
    assert assistants[1].startswith("<tool_call>")


def test_generate_dialogues_openai_compatible_multi_turn_falls_back_when_only_tool_call(
    monkeypatch, tmp_path: Path
):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)
    scenarios = build_grounded_scenario_bank(
        items,
        seed=37,
        counts_by_task={"multi_turn_grounded": 1},
    )
    scenario = scenarios[0]

    monkeypatch.setattr(
        "scripts.stylist.generate_grounded_dialogues._chat_completion_request",
        lambda *_args, **_kwargs: render_search_outfits_tool_call(
            {**scenario["request"], "occasion": scenario["target_occasion"]}
        ),
    )

    rows = generate_dialogues_from_scenarios(
        scenarios,
        backend="openai-compatible",
        model="openai/gpt-oss-120b",
        base_url_override="https://example.invalid/v1",
        api_key_override="token",
    )

    assistants = [m["content"] for m in rows[0]["messages"] if m["role"] == "assistant"]
    assert len(assistants) == 2
    assert "<tool_call>" not in assistants[0]
    assert assistants[0] == _template_assistant_messages(scenario)[1]["content"]
    assert assistants[1].startswith("<tool_call>")


def test_build_generation_manifest_reports_duplicates():
    rows = [
        {
            "messages": [
                {"role": "system", "content": "s"},
                {"role": "user", "content": "u"},
                {"role": "assistant", "content": "a"},
            ],
            "task_type": "recommend_explain_grounded",
            "source_set": "grounded_generated",
            "source_file": "scenario_bank.jsonl",
            "scenario_id": "SC_1",
        },
        {
            "messages": [
                {"role": "system", "content": "s"},
                {"role": "user", "content": "u"},
                {"role": "assistant", "content": "a"},
            ],
            "task_type": "recommend_explain_grounded",
            "source_set": "grounded_generated",
            "source_file": "scenario_bank.jsonl",
            "scenario_id": "SC_2",
        },
    ]
    manifest = build_generation_manifest(rows, Path("train.jsonl"))
    assert manifest["unique_message_examples"] == 1
    assert manifest["duplicate_message_examples"] == 1
