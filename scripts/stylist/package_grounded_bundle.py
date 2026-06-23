"""Package judged grounded dialogues into train/eval JSONL bundle."""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
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

DEFAULT_OUTPUT_DIR = Path("data/stylist/fine_tune/runs/stylist_grounded_v2/final_bundle")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _load_knowledge_core(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    train_path = path / "train.jsonl"
    if not train_path.is_file():
        return []
    return _load_jsonl(train_path)


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        digest = json.dumps(row.get("messages", []), ensure_ascii=False, sort_keys=True)
        if digest in seen:
            continue
        seen.add(digest)
        deduped.append(row)
    return deduped


def _split_rows(
    rows: list[dict[str, Any]],
    *,
    eval_fraction: float,
    max_eval_records: int,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("task_type", "unknown"))].append(row)

    rng = random.Random(seed)
    train_rows: list[dict[str, Any]] = []
    eval_rows: list[dict[str, Any]] = []
    remaining_eval = max_eval_records

    for task_type in sorted(grouped):
        task_rows = list(grouped[task_type])
        rng.shuffle(task_rows)
        desired_eval = int(len(task_rows) * eval_fraction)
        if len(task_rows) > 1 and eval_fraction > 0:
            desired_eval = max(1, desired_eval)
        desired_eval = min(desired_eval, remaining_eval, max(0, len(task_rows) - 1))
        eval_rows.extend(task_rows[:desired_eval])
        train_rows.extend(task_rows[desired_eval:])
        remaining_eval = max(0, remaining_eval - desired_eval)

    if not eval_rows and len(train_rows) > 1 and max_eval_records > 0:
        eval_rows.append(train_rows.pop())
    return train_rows, eval_rows


def package_grounded_bundle(
    *,
    accepted_path: Path,
    output_dir: Path,
    eval_fraction: float,
    max_eval_records: int,
    seed: int,
    knowledge_core_dir: Path | None = None,
) -> dict[str, Any]:
    grounded_rows = _load_jsonl(accepted_path)
    knowledge_rows = _load_knowledge_core(knowledge_core_dir)
    all_rows = _dedupe_rows(grounded_rows + knowledge_rows)
    if len(all_rows) < 2:
        raise ValueError("Need at least 2 rows to package a grounded bundle")

    train_rows, eval_rows = _split_rows(
        all_rows,
        eval_fraction=eval_fraction,
        max_eval_records=max_eval_records,
        seed=seed,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / "train.jsonl"
    eval_path = output_dir / "eval.jsonl"
    train_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in train_rows) + "\n",
        encoding="utf-8",
    )
    eval_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in eval_rows) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "total_examples": len(all_rows),
        "train_examples": len(train_rows),
        "eval_examples": len(eval_rows),
        "task_counts": dict(
            sorted(Counter(str(row.get("task_type", "")) for row in all_rows).items())
        ),
        "source_counts": dict(
            sorted(Counter(str(row.get("source_set", "")) for row in all_rows).items())
        ),
        "train_file": str(train_path),
        "eval_file": str(eval_path),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accepted_dialogues", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--eval-fraction", type=float, default=0.03)
    parser.add_argument("--max-eval-records", type=int, default=256)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--knowledge-core-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = package_grounded_bundle(
        accepted_path=args.accepted_dialogues,
        output_dir=args.output_dir,
        eval_fraction=args.eval_fraction,
        max_eval_records=args.max_eval_records,
        seed=args.seed,
        knowledge_core_dir=args.knowledge_core_dir,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
