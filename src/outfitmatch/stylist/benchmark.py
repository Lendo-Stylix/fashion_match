"""Benchmark evaluation for fine-tuned stylist models.

Provides lightweight, pure-Python metrics to compare generated responses
against a held-out eval dataset (e.g. `eval.jsonl`).
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from outfitmatch.stylist.validation import (
    extract_tool_calls,
    validate_tool_calls,
)


def load_eval_dataset(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL eval file into a list of conversation records."""
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _tokenize(text: str) -> list[str]:
    """Simple whitespace tokenisation for quick text-similarity."""
    return [w.lower() for w in re.findall(r"\b\w+\b", text)]


def compute_text_similarity(generated: str, reference: str) -> float:
    """Return an F1-like token overlap score between *generated* and *reference*."""
    gen_tokens = Counter(_tokenize(generated))
    ref_tokens = Counter(_tokenize(reference))
    if not gen_tokens or not ref_tokens:
        return 0.0
    overlap = sum((gen_tokens & ref_tokens).values())
    precision = overlap / max(sum(gen_tokens.values()), 1)
    recall = overlap / max(sum(ref_tokens.values()), 1)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _tool_call_to_pairs(tool_call: dict[str, Any]) -> set[tuple[str, Any]]:
    """Turn a tool-call payload into a set of (key, value) pairs for comparison."""
    pairs: set[tuple[str, Any]] = set()
    for key, value in tool_call.items():
        if key == "arguments" and isinstance(value, dict):
            for sub_key, sub_value in value.items():
                pairs.add((f"{key}.{sub_key}", str(sub_value)))
        elif key == "name":
            pairs.add((key, str(value)))
        else:
            pairs.add((key, str(value)))
    return pairs


def compute_tool_call_f1(generated: str, reference: str) -> float | None:
    """Return an F1 score comparing generated tool calls to reference tool calls.

    Returns ``None`` when the *reference* does not contain any tool call,
    because the metric is not applicable in that case.
    """
    ref_calls = extract_tool_calls(reference)
    if not ref_calls:
        return None

    gen_calls = extract_tool_calls(generated)
    if not gen_calls:
        return 0.0

    # Use the first call in each for simplicity; in practice there is only one.
    ref_pairs = _tool_call_to_pairs(ref_calls[0])
    gen_pairs = _tool_call_to_pairs(gen_calls[0])

    overlap = len(ref_pairs & gen_pairs)
    if overlap == 0:
        return 0.0

    precision = overlap / len(gen_pairs)
    recall = overlap / len(ref_pairs)
    return 2 * precision * recall / (precision + recall)


def compute_format_compliance(generated: str, reference: str) -> int:
    """Return 1 if the generated response respects the expected format, else 0.

    - If *reference* contains a ``<tool_call>`` block, the generated response
      must also contain at least one valid tool-call block.
    - If *reference* does not contain a tool call, any free-text response is
      acceptable.
    """
    ref_has_tool = "<tool_call>" in reference
    if not ref_has_tool:
        return 1
    gen_has_tool = "<tool_call>" in generated
    if not gen_has_tool:
        return 0
    gen_payloads = extract_tool_calls(generated)
    if not gen_payloads:
        return 0
    return int(validate_tool_calls(generated)[0])


def evaluate_sample(generated: str, reference: str, task_type: str = "") -> dict[str, Any]:
    """Compute all per-sample metrics."""
    return {
        "task_type": task_type,
        "tool_call_f1": compute_tool_call_f1(generated, reference),
        "text_similarity": compute_text_similarity(generated, reference),
        "format_compliance": compute_format_compliance(generated, reference),
    }


def evaluate_dataset(
    dataset: Sequence[dict[str, Any]],
    generate_fn: Callable[[list[dict[str, str]]], str],
    max_samples: int | None = None,
) -> dict[str, Any]:
    """Run *generate_fn* on every conversation in *dataset* and aggregate metrics.

    Args:
        dataset: List of records with a ``messages`` key (list of``{"role": …,
        ``"content": …}`` dicts) and optionally a ``task_type`` key.
        generate_fn: Callable that receives the full conversation (except the
            last assistant turn) and returns the model's generated string.
        max_samples: If given, only evaluate the first *n* records.

    Returns:
        Dictionary with per-sample results and aggregate statistics.
    """
    samples = dataset[:max_samples] if max_samples is not None else list(dataset)
    results: list[dict[str, Any]] = []
    for record in samples:
        messages = list(record["messages"])
        reference = messages[-1]["content"]
        context = messages[:-1]
        generated = generate_fn(context)
        metrics = evaluate_sample(generated, reference, task_type=record.get("task_type", ""))
        metrics["reference"] = reference
        metrics["generated"] = generated
        results.append(metrics)

    # Aggregate per-task-type and overall
    agg: dict[str, dict[str, Any]] = {}
    overall: dict[str, list[float]] = {
        "tool_call_f1": [],
        "text_similarity": [],
        "format_compliance": [],
    }
    for r in results:
        task = r["task_type"] or "unknown"
        if task not in agg:
            agg[task] = {
                "count": 0,
                "tool_call_f1": [],
                "text_similarity": [],
                "format_compliance": [],
            }
        agg[task]["count"] = agg[task].get("count", 0) + 1
        for key in ("tool_call_f1", "text_similarity", "format_compliance"):
            val = r[key]
            if val is not None and not math.isnan(val):
                agg[task][key].append(val)
                overall[key].append(val)

    def _mean(values: list[float]) -> float:
        return round(sum(values) / max(len(values), 1), 4)

    summary: dict[str, dict[str, Any]] = {}
    for task, vals in agg.items():
        summary[task] = {
            "count": vals["count"],
            "mean_tool_call_f1": _mean(vals["tool_call_f1"]),
            "mean_text_similarity": _mean(vals["text_similarity"]),
            "format_compliance_rate": _mean(vals["format_compliance"]),
        }

    overall_dict = {
        "count": len(results),
        "mean_tool_call_f1": _mean(overall["tool_call_f1"]),
        "mean_text_similarity": _mean(overall["text_similarity"]),
        "format_compliance_rate": _mean(overall["format_compliance"]),
    }

    return {
        "overall": overall_dict,
        "per_task": summary,
        "samples": results,
    }
