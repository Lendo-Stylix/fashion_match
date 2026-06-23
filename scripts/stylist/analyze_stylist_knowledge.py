"""Analyze stylist_knowledge quality and build a Qwen3.5-9B-friendly distilled bundle."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

try:
    from scripts.stylist.distill_stylist_dataset import (
        RECOMMENDED_QWEN35_TASK_COUNTS,
        build_distilled_bundle,
        build_prompt_document_frequency,
        classify_prompt_style,
        classify_topic,
        collect_source_examples,
        inspect_example_quality,
        load_dataset_config,
        near_duplicate_family_key,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from distill_stylist_dataset import (  # type: ignore[no-redef]
        RECOMMENDED_QWEN35_TASK_COUNTS,
        build_distilled_bundle,
        build_prompt_document_frequency,
        classify_prompt_style,
        classify_topic,
        collect_source_examples,
        inspect_example_quality,
        load_dataset_config,
        near_duplicate_family_key,
    )

DEFAULT_CONFIG = Path("configs/stylist_finetune_kaggle.yaml")
DEFAULT_OUTPUT_DIR = Path("data/stylist/fine_tune/runs/stylist_distilled_qwen35_under10k")
DEFAULT_REPORT_DIR = Path("docs/reports/stylist_knowledge_qwen35_under10k")
LEGACY_MANIFEST = Path("data/stylist/fine_tune/runs/stylist_distilled_behavioral/manifest.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--knowledge-target", type=int, default=7200)
    parser.add_argument("--max-per-family", type=int, default=3)
    parser.add_argument("--max-answer-words", type=int, default=280)
    parser.add_argument("--echo-threshold", type=float, default=0.65)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def _truncate(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _word_lengths(examples: list[Any], accessor) -> list[int]:
    return [len(accessor(example).split()) for example in examples]


def _counter(examples: list[Any], fn) -> Counter[str]:
    return Counter(fn(example) for example in examples)


def _plot_counter_compare(
    raw_counts: Counter[str], distilled_counts: Counter[str], *, title: str, path: Path
) -> None:
    labels = sorted(set(raw_counts) | set(distilled_counts))
    raw_values = [raw_counts.get(label, 0) for label in labels]
    distilled_values = [distilled_counts.get(label, 0) for label in labels]
    x = range(len(labels))

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar([idx - 0.2 for idx in x], raw_values, width=0.4, label="raw", color="#94a3b8")
    ax.bar(
        [idx + 0.2 for idx in x],
        distilled_values,
        width=0.4,
        label="distilled",
        color="#2563eb",
    )
    ax.set_title(title)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_quality_flags(flag_counts: dict[str, int], path: Path) -> None:
    labels = list(flag_counts)
    values = [flag_counts[label] for label in labels]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(labels, values, color=["#dc2626", "#ea580c", "#7c3aed"][: len(labels)])
    ax.set_title("Rows bị loại bởi quality gate")
    ax.set_ylabel("rows")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_length_hist(raw_lengths: list[int], distilled_lengths: list[int], path: Path) -> None:
    bins = [0, 40, 80, 120, 180, 240, 280, 360, 500, 800]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(raw_lengths, bins=bins, alpha=0.6, label="raw", color="#94a3b8")
    ax.hist(distilled_lengths, bins=bins, alpha=0.7, label="distilled", color="#2563eb")
    ax.set_title("Phân phối độ dài câu trả lời (word count)")
    ax.set_xlabel("assistant words")
    ax.set_ylabel("rows")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _bucket_family_sizes(examples: list[Any]) -> Counter[str]:
    prompt_df = build_prompt_document_frequency(examples)
    counts = Counter(
        near_duplicate_family_key(example, prompt_document_frequency=prompt_df)
        for example in examples
    )
    buckets = Counter()
    for size in counts.values():
        if size == 1:
            buckets["1"] += 1
        elif size == 2:
            buckets["2"] += 1
        elif size <= 5:
            buckets["3-5"] += 1
        elif size <= 10:
            buckets["6-10"] += 1
        elif size <= 20:
            buckets["11-20"] += 1
        else:
            buckets["21+"] += 1
    return buckets


def _plot_family_buckets(
    raw_examples: list[Any], distilled_examples: list[Any], path: Path
) -> None:
    _plot_counter_compare(
        _bucket_family_sizes(raw_examples),
        _bucket_family_sizes(distilled_examples),
        title="Near-duplicate family size buckets",
        path=path,
    )


def _sample_flagged_examples(
    raw_examples: list[Any], *, max_answer_words: int, echo_threshold: float
) -> list[dict[str, str]]:
    samples: list[dict[str, str]] = []
    for example in raw_examples:
        quality = inspect_example_quality(
            example,
            max_answer_words=max_answer_words,
            echo_threshold=echo_threshold,
        )
        if not quality.flags:
            continue
        samples.append(
            {
                "flags": ", ".join(quality.flags),
                "user": _truncate(example.messages[1]["content"]),
                "assistant": _truncate(example.messages[-1]["content"], 180),
            }
        )
        if len(samples) >= 5:
            break
    return samples


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    dataset = load_dataset_config(args.config)
    system_prompt = str(dataset["system_prompt"])
    prefer_translated = bool(dataset.get("prefer_translated_columns", True))
    source_dir = Path(str(dataset["stylist_knowledge_dir"]))

    raw_examples = collect_source_examples(
        source_dir,
        system_prompt=system_prompt,
        prefer_translated=prefer_translated,
    )
    manifest = build_distilled_bundle(
        source_dir=source_dir,
        output_dir=args.output_dir,
        system_prompt=system_prompt,
        knowledge_target=args.knowledge_target,
        seed=args.seed,
        max_per_family=args.max_per_family,
        counts_by_task=dict(RECOMMENDED_QWEN35_TASK_COUNTS),
        prefer_translated=prefer_translated,
        clean=True,
        max_answer_words=args.max_answer_words,
        echo_threshold=args.echo_threshold,
    )

    knowledge_path = args.output_dir / "knowledge_distilled.jsonl"
    distilled_examples = [
        json.loads(line) for line in knowledge_path.read_text(encoding="utf-8").splitlines()
    ]
    report_dir = args.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    raw_topic = _counter(raw_examples, classify_topic)
    raw_style = _counter(raw_examples, classify_prompt_style)
    distilled_topic = Counter(manifest["knowledge_summary"]["topic_counts"])
    distilled_style = Counter(manifest["knowledge_summary"]["prompt_style_counts"])

    raw_answer_lengths = _word_lengths(raw_examples, lambda ex: ex.messages[-1]["content"])
    distilled_answer_lengths = [
        len(row["messages"][-1]["content"].split()) for row in distilled_examples
    ]

    chart_paths = {
        "topic": report_dir / "topic_distribution_raw_vs_distilled.png",
        "style": report_dir / "prompt_style_raw_vs_distilled.png",
        "length_hist": report_dir / "answer_length_hist_raw_vs_distilled.png",
        "quality": report_dir / "quality_gate_drops.png",
        "family": report_dir / "family_size_buckets_raw_vs_distilled.png",
    }
    _plot_counter_compare(
        raw_topic, distilled_topic, title="Topic distribution", path=chart_paths["topic"]
    )
    _plot_counter_compare(
        raw_style, distilled_style, title="Prompt style distribution", path=chart_paths["style"]
    )
    _plot_length_hist(raw_answer_lengths, distilled_answer_lengths, chart_paths["length_hist"])
    _plot_quality_flags(manifest["quality_gate"]["dropped_flag_counts"], chart_paths["quality"])

    # Reuse the family plot helper with JSONL rows adapted back to lightweight objects.
    class _RowWrap:
        def __init__(self, row: dict[str, Any]):
            self.messages = row["messages"]

    _plot_family_buckets(
        raw_examples, [_RowWrap(row) for row in distilled_examples], chart_paths["family"]
    )

    flagged_samples = _sample_flagged_examples(
        raw_examples,
        max_answer_words=args.max_answer_words,
        echo_threshold=args.echo_threshold,
    )
    legacy_manifest = _load_json(LEGACY_MANIFEST)

    combined_words = manifest["combined_summary"]["word_stats"]["combined_words_total"]
    approx_tokens = manifest["combined_summary"]["word_stats"]["approx_qwen_tokens"]
    legacy_note = ""
    if legacy_manifest is not None:
        legacy_old = (
            f"- Bundle cũ: {legacy_manifest['combined_examples']} rows "
            f"({legacy_manifest['knowledge_examples']} knowledge + "
            f"{legacy_manifest['behavioral_examples']} behavioral)."
        )
        legacy_new = (
            f"- Bundle mới: {manifest['combined_examples']} rows "
            f"({manifest['knowledge_examples']} knowledge + "
            f"{manifest['behavioral_examples']} behavioral)."
        )
        legacy_note = legacy_old + chr(10) + legacy_new + chr(10)

    sample_lines = chr(10).join(
        f"- **{sample['flags']}** — Q: {sample['user']} / A: {sample['assistant']}"
        for sample in flagged_samples
    )
    report_lines = [
        "# Stylist knowledge distillation report",
        "",
        "**Date:** 2026-06-23  ",
        "**Branch:** feature/stylist-knowledge-distill-report",
        "",
        "## 1. Executive summary",
        "",
        f"- Raw `stylist_knowledge`: **{len(raw_examples):,}** rows.",
        (
            "- Quality gate removed "
            f"**{manifest['quality_gate']['dropped_examples']:,}** rows, "
            f"giữ lại **{manifest['quality_gate']['clean_pool_examples']:,}** clean rows."
        ),
        (
            "- Final Qwen3.5-9B bundle: "
            f"**{manifest['combined_examples']:,}** rows "
            f"(**{manifest['knowledge_examples']:,} knowledge + "
            f"{manifest['behavioral_examples']:,} behavioral**)."
        ),
        (
            f"- Approx training budget: **{combined_words:,} words** ≈ "
            f"**{approx_tokens:,} Qwen tokens**."
        ),
        "",
        legacy_note.rstrip(),
        "## 2. Findings",
        "",
        (
            "1. **Topic skew rất mạnh**: raw data dồn vào `color_analysis` và "
            "`wardrobe_capsule`, nên body/occasion/season bị chìm nếu chỉ sample ngẫu nhiên."
        ),
        (
            "2. **Nhiễu dịch máy có thật**: quality gate phát hiện mixed-script / "
            "prompt-echo / overlong essay. Các lỗi này làm model học văn phong lệch, "
            "verbose và kém tự nhiên."
        ),
        (
            "3. **Near-duplicate density cao**: nhiều prompt chỉ thay 1 vài cụm nhỏ. "
            f"Cap `max_per_family={args.max_per_family}` giúp giữ coverage "
            "mà không nhồi lặp template."
        ),
        (
            "4. **Qwen3.5-9B cần behavioral rows nhiều hơn bundle cũ**: tăng "
            "tool-calling, ask-missing-info, recommend-explain để cân bằng giữa knowledge "
            "và hành vi hội thoại."
        ),
        "",
        "## 3. Charts",
        "",
        "### Topic distribution",
        "![topic](topic_distribution_raw_vs_distilled.png)",
        "",
        "### Prompt style distribution",
        "![style](prompt_style_raw_vs_distilled.png)",
        "",
        "### Answer length histogram",
        "![length](answer_length_hist_raw_vs_distilled.png)",
        "",
        "### Quality-gate drops",
        "![quality](quality_gate_drops.png)",
        "",
        "### Near-duplicate family buckets",
        "![family](family_size_buckets_raw_vs_distilled.png)",
        "",
        "## 4. Distillation recipe used",
        "",
        f"- `knowledge_target={args.knowledge_target}`",
        f"- `max_per_family={args.max_per_family}`",
        f"- `max_answer_words={args.max_answer_words}`",
        f"- `echo_threshold={args.echo_threshold}`",
        (
            "- Behavioral task mix: "
            f"`{json.dumps(RECOMMENDED_QWEN35_TASK_COUNTS, ensure_ascii=False)}`"
        ),
        "",
        "## 5. Flagged raw examples",
        "",
        sample_lines,
        "",
        "## 6. Recommended artifact",
        "",
        f"- Distilled bundle: `{args.output_dir.as_posix()}`",
        f"- Manifest: `{(args.output_dir / 'manifest.json').as_posix()}`",
        (
            "- Recommended for: **QLoRA SFT on Qwen/Qwen3.5-9B** with packing enabled "
            "and 1 epoch baseline."
        ),
    ]
    report = chr(10).join(line for line in report_lines if line != "")
    (report_dir / "README.md").write_text(report, encoding="utf-8")
    (report_dir / "summary.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {"report_dir": str(report_dir), "output_dir": str(args.output_dir)}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
