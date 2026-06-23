"""Judge grounded stylist dialogue rows with deterministic checks first."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # pragma: no cover - direct script execution path
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    src_root_str = str(repo_root / "src")
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    if src_root_str not in sys.path:
        sys.path.insert(0, src_root_str)

from outfitmatch.stylist.validation import validate_tool_calls

DEFAULT_OUTPUT_DIR = Path("data/stylist/fine_tune/runs/stylist_grounded_v2/judged_dialogues")
TOOL_REQUIRED_TASKS = {"tool_calling_grounded", "multi_turn_grounded"}
TOOL_FORBIDDEN_TASKS = {
    "ask_missing_info_grounded",
    "no_result_or_relax_constraints",
    "recommend_explain_grounded",
    "polite_decline_anti_hallucination",
    "body_fit_grounded",
}


def load_dialogue_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _assistant_messages(row: dict[str, Any]) -> list[str]:
    messages = row.get("messages")
    if not isinstance(messages, list):
        return []
    return [
        str(message.get("content", ""))
        for message in messages
        if isinstance(message, dict) and message.get("role") == "assistant"
    ]


def judge_row(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    task_type = str(row.get("task_type", ""))
    messages = row.get("messages")
    if not isinstance(messages, list) or len(messages) < 3:
        return ["invalid_message_shape"]

    assistant_messages = _assistant_messages(row)
    if not assistant_messages:
        return ["missing_assistant_message"]
    if any(not content.strip() for content in assistant_messages):
        reasons.append("assistant_empty")

    has_tool_call = any("<tool_call>" in content for content in assistant_messages)
    if task_type in TOOL_REQUIRED_TASKS and not has_tool_call:
        reasons.append("missing_required_tool_call")
    if task_type in TOOL_FORBIDDEN_TASKS and has_tool_call:
        reasons.append("unexpected_tool_call")

    for content in assistant_messages:
        if "<tool_call>" not in content:
            continue
        ok, errors = validate_tool_calls(content)
        if not ok:
            reasons.append("invalid_tool_call")
            reasons.extend(f"invalid_tool_call_detail:{error}" for error in errors)

    if task_type == "multi_turn_grounded":
        roles = [str(message.get("role", "")) for message in messages if isinstance(message, dict)]
        if roles != ["system", "user", "assistant", "user", "assistant"]:
            reasons.append("invalid_multi_turn_shape")

    return reasons


def judge_generated_dialogues(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()

    for row in rows:
        reasons = judge_row(row)
        if reasons:
            rejected.append({**row, "judge_reasons": reasons})
            reason_counts.update(
                reason for reason in reasons if not reason.startswith("invalid_tool")
            )
            if any(reason.startswith("invalid_tool_call") for reason in reasons):
                reason_counts["invalid_tool_call"] += 1
        else:
            accepted.append(row)

    summary = {
        "total_rows": len(rows),
        "accepted_rows": len(accepted),
        "rejected_rows": len(rejected),
        "rejection_reason_counts": dict(sorted(reason_counts.items())),
        "task_counts": dict(
            sorted(Counter(str(row.get("task_type", "")) for row in accepted).items())
        ),
    }
    return accepted, rejected, summary


def write_judged_dialogues(
    output_dir: Path,
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    accepted_path = output_dir / "accepted.jsonl"
    rejected_path = output_dir / "rejected.jsonl"
    accepted_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in accepted) + "\n",
        encoding="utf-8",
    )
    rejected_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rejected) + "\n",
        encoding="utf-8",
    )
    manifest = {
        **summary,
        "accepted_file": str(accepted_path),
        "rejected_file": str(rejected_path),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generated_dialogues", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_dialogue_rows(args.generated_dialogues)
    accepted, rejected, summary = judge_generated_dialogues(rows)
    manifest = write_judged_dialogues(args.output_dir, accepted, rejected, summary)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
