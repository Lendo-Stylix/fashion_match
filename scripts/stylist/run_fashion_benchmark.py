#!/usr/bin/env python3
"""CLI chạy fashion-knowledge & fashion-logic benchmark trên stylist model.

Hai chế độ chạy:

* ``--mock`` : dùng generate_fn cứng, không cần GPU — smoke test / regression
  guard, reproducible 100%. Phù hợp chạy trong CI và trên branch không có model.
* ``--model <HF_id|path> [--adapter <path>]`` : load transformers + peft
  (4-bit BNB) giống scripts/stylist/benchmark_stylist.py, build generate_fn
  qua chat template rồi chạy benchmark thật trên adapter fine-tuned.

Report JSON có cùng schema với outfitmatch.stylist.fashion_eval.evaluate_fashion_dataset
(overall / per_task / samples).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from outfitmatch.stylist.fashion_eval import (
    ASK_BACK_ITEMS,
    BODY_SHAPE_ADVICE_ITEMS,
    COHERENCE_ITEMS,
    OCCASION_FORMALITY_ITEMS,
    SEASON_ADVICE_ITEMS,
    TOOL_CALL_DERIVATION_ITEMS,
    evaluate_fashion_dataset,
)

# ---------------------------------------------------------------------------
# Item banks per task type
# ---------------------------------------------------------------------------
ITEM_BANKS: dict[str, list[dict[str, Any]]] = {
    "occasion_formality": OCCASION_FORMALITY_ITEMS,
    "body_shape_advice": BODY_SHAPE_ADVICE_ITEMS,
    "season_advice": SEASON_ADVICE_ITEMS,
    "coherence": COHERENCE_ITEMS,
    "ask_back": ASK_BACK_ITEMS,
    "tool_call_derivation": TOOL_CALL_DERIVATION_ITEMS,
}
ALL_ITEM_TYPES: tuple[str, ...] = tuple(ITEM_BANKS)


def build_fashion_dataset(types: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Assemble the benchmark dataset from item banks, tagging each item_type.

    types optionally restricts to a subset of ALL_ITEM_TYPES.
    """
    selected: set[str] = set(types) if types else set(ALL_ITEM_TYPES)
    dataset: list[dict[str, Any]] = []
    for item_type in ALL_ITEM_TYPES:
        if item_type not in selected:
            continue
        for item in ITEM_BANKS[item_type]:
            record = dict(item)
            record["item_type"] = item_type
            dataset.append(record)
    return dataset


def make_mock_generate_fn() -> Callable[[list[dict[str, str]], str]]:
    """Return a deterministic generate_fn for --mock (no GPU).

    Always asks back about the occasion — this naturally aces ask_back items
    and fails the knowledge/derivation items, so the report is meaningful and
    the runner can be smoke-tested without a model.
    """

    def _generate(messages: list[dict[str, str]]) -> str:
        return "Bạn muốn mặc cho dịp nào ạ? (đi làm, hẹn hò, đám cưới, ...)"

    return _generate


def _make_model_generate_fn(model_name: str, adapter_path: str | None):
    """Load a transformers+peft model and return a generate_fn (requires GPU)."""
    import torch
    from peft import PeftModel
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )

    quant_config = BitsAndBytesConfig(load_in_4bit=True)
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        trust_remote_code=True,
        quantization_config=quant_config,
        device_map="auto",
        torch_dtype=torch.float16,
    )
    if adapter_path is not None:
        model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()

    def _generate(messages: list[dict[str, str]]) -> str:
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=512, do_sample=False)
        input_len = inputs["input_ids"].shape[1]
        return tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True).strip()

    return _generate


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fashion-knowledge & fashion-logic benchmark cho stylist."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock", action="store_true", help="Chạy không cần GPU (generate_fn cứng).")
    mode.add_argument("--model", default=None, help="HuggingFace model ID / local path.")
    parser.add_argument("--adapter", default=None, help="Path tới LoRA adapter (tuỳ chọn).")
    parser.add_argument("--output-json", type=Path, default=None, help="Lưu report ra JSON.")
    parser.add_argument("--max-samples", type=int, default=None, help="Giới hạn số sample eval.")
    parser.add_argument(
        "--types",
        nargs="+",
        default=None,
        choices=list(ALL_ITEM_TYPES),
        help="Chỉ chạy subset item bank.",
    )
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Entry point cho test & CLI. Trả exit code."""
    args = _build_parser().parse_args(argv)
    dataset = build_fashion_dataset(types=args.types)

    if args.mock:
        generate_fn = make_mock_generate_fn()
    else:
        if not args.model:
            print("--model là bắt buộc khi không dùng --mock", file=sys.stderr)
            return 2
        generate_fn = _make_model_generate_fn(args.model, args.adapter)

    report = evaluate_fashion_dataset(dataset, generate_fn, max_samples=args.max_samples)
    payload = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output_json:
        args.output_json.write_text(payload, encoding="utf-8")
        print(f"Report saved to {args.output_json}")
    else:
        print(payload)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    sys.exit(main())
