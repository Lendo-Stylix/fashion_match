from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.stylist.judge_grounded_dialogues import (
    judge_generated_dialogues,
    write_judged_dialogues,
)
from scripts.stylist.package_grounded_bundle import package_grounded_bundle


def _row(task_type: str, assistant_text: str, *, source_set: str = "grounded_generated") -> dict:
    return {
        "messages": [
            {"role": "system", "content": "Bạn là stylist."},
            {"role": "user", "content": "Tư vấn giúp mình."},
            {"role": "assistant", "content": assistant_text},
        ],
        "task_type": task_type,
        "source_set": source_set,
        "source_file": "train.jsonl",
        "scenario_id": f"SC_{task_type}",
    }


def test_judge_generated_dialogues_rejects_invalid_tool_rows(tmp_path: Path):
    rows = [
        _row(
            "tool_calling_grounded",
            '<tool_call>{"name":"search_outfits","arguments":{"occasion":"office"}}</tool_call>',
        ),
        _row(
            "ask_missing_info_grounded",
            "Bạn cho mình biết dịp mặc chính để mình tư vấn chính xác hơn nhé.",
        ),
        _row(
            "tool_calling_grounded",
            '<tool_call>{"name":"search_outfits","arguments":{"bad_key":"office"}}</tool_call>',
        ),
        _row("recommend_explain_grounded", "   "),
    ]

    accepted, rejected, summary = judge_generated_dialogues(rows)

    assert len(accepted) == 2
    assert len(rejected) == 2
    assert summary["accepted_rows"] == 2
    assert summary["rejected_rows"] == 2
    assert summary["rejection_reason_counts"]["assistant_empty"] == 1
    assert summary["rejection_reason_counts"]["invalid_tool_call"] == 1

    manifest = write_judged_dialogues(tmp_path, accepted, rejected, summary)
    assert (tmp_path / "accepted.jsonl").is_file()
    assert (tmp_path / "rejected.jsonl").is_file()
    assert manifest["accepted_rows"] == 2


def test_package_grounded_bundle_splits_and_merges_knowledge_core(tmp_path: Path):
    accepted_rows = [
        _row(
            "tool_calling_grounded",
            '<tool_call>{"name":"search_outfits","arguments":{"occasion":"office"}}</tool_call>',
        ),
        _row("ask_missing_info_grounded", "Bạn cho mình biết dịp mặc chính nhé."),
        _row("recommend_explain_grounded", "Mình ưu tiên áo sơ mi công sở vì dễ phối."),
        _row("body_fit_grounded", "Phom áo này cân bằng cho dáng quả lê tốt hơn."),
    ]
    accepted_path = tmp_path / "accepted.jsonl"
    accepted_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in accepted_rows) + "\n",
        encoding="utf-8",
    )

    knowledge_dir = tmp_path / "knowledge_core"
    knowledge_dir.mkdir()
    knowledge_row = _row(
        "stylist_knowledge",
        "Blazer màu trung tính phù hợp môi trường công sở và dễ phối nhiều lớp.",
        source_set="stylist_knowledge",
    )
    (knowledge_dir / "train.jsonl").write_text(
        json.dumps(knowledge_row, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    manifest = package_grounded_bundle(
        accepted_path=accepted_path,
        output_dir=tmp_path / "bundle_out",
        eval_fraction=0.25,
        max_eval_records=2,
        seed=7,
        knowledge_core_dir=knowledge_dir,
    )

    train_rows = [
        json.loads(line)
        for line in (tmp_path / "bundle_out" / "train.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    eval_rows = [
        json.loads(line)
        for line in (tmp_path / "bundle_out" / "eval.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]

    assert manifest["total_examples"] == 5
    assert manifest["train_examples"] + manifest["eval_examples"] == 5
    assert manifest["source_counts"]["grounded_generated"] == 4
    assert manifest["source_counts"]["stylist_knowledge"] == 1
    assert any(row["source_set"] == "stylist_knowledge" for row in train_rows + eval_rows)
    assert any(row["task_type"] == "tool_calling_grounded" for row in train_rows + eval_rows)


def test_grounded_judge_and_package_scripts_run_directly(tmp_path: Path):
    generated_path = tmp_path / "generated.jsonl"
    generated_rows = [
        _row(
            "tool_calling_grounded",
            '<tool_call>{"name":"search_outfits","arguments":{"occasion":"office"}}</tool_call>',
        ),
        _row("recommend_explain_grounded", "Áo sơ mi trắng hợp môi trường công sở."),
    ]
    generated_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in generated_rows) + "\n",
        encoding="utf-8",
    )
    judged_dir = tmp_path / "judged"
    bundle_dir = tmp_path / "bundle"

    judge_result = subprocess.run(
        [
            sys.executable,
            "scripts/stylist/judge_grounded_dialogues.py",
            str(generated_path),
            "--output-dir",
            str(judged_dir),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert judge_result.returncode == 0, judge_result.stderr
    assert (judged_dir / "accepted.jsonl").is_file()

    package_result = subprocess.run(
        [
            sys.executable,
            "scripts/stylist/package_grounded_bundle.py",
            str(judged_dir / "accepted.jsonl"),
            "--output-dir",
            str(bundle_dir),
            "--eval-fraction",
            "0.5",
            "--max-eval-records",
            "1",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert package_result.returncode == 0, package_result.stderr
    assert (bundle_dir / "train.jsonl").is_file()
    assert (bundle_dir / "eval.jsonl").is_file()
