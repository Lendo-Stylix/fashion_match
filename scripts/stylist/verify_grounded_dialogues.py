"""Verification checks for grounded stylist dialogue datasets."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # pragma: no cover
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    src_root_str = str(repo_root / "src")
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    if src_root_str not in sys.path:
        sys.path.insert(0, src_root_str)

from outfitmatch.stylist.validation import validate_tool_calls


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def build_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    signatures = {
        json.dumps(row.get("messages", []), ensure_ascii=False, sort_keys=True) for row in rows
    }
    scenario_ids = [str(row.get("scenario_id", "")) for row in rows]
    assistant_texts = []
    turn_counts = []
    valid_tool_rows = 0
    invalid_tool_rows = 0
    tool_rows = 0
    for row in rows:
        messages = row.get("messages", [])
        turn_counts.append(len(messages))
        assistant_text = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "assistant"
        )
        assistant_texts.append(assistant_text)
        if "<tool_call>" in assistant_text:
            tool_rows += 1
            ok, _ = validate_tool_calls(assistant_text)
            if ok:
                valid_tool_rows += 1
            else:
                invalid_tool_rows += 1
    duplicate_ids = len(scenario_ids) - len(set(scenario_ids))
    return {
        "total_rows": len(rows),
        "unique_message_rows": len(signatures),
        "duplicate_message_rows": len(rows) - len(signatures),
        "tool_call_rows": tool_rows,
        "valid_tool_rows": valid_tool_rows,
        "invalid_tool_rows": invalid_tool_rows,
        "duplicate_scenario_ids": duplicate_ids,
        "avg_turns": round(sum(turn_counts) / len(turn_counts), 2) if turn_counts else 0.0,
        "max_turns": max(turn_counts, default=0),
        "task_counts": dict(sorted(Counter(str(row.get("task_type", "")) for row in rows).items())),
        "source_counts": dict(
            sorted(Counter(str(row.get("source_set", "")) for row in rows).items())
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generated_jsonl", type=Path)
    parser.add_argument("--fail-on-duplicates", action="store_true")
    parser.add_argument("--require-valid-tool-calls", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_rows(args.generated_jsonl)
    report = build_report(rows)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_on_duplicates and report["duplicate_message_rows"] > 0:
        raise SystemExit(1)
    if args.require_valid_tool_calls and report["invalid_tool_rows"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
