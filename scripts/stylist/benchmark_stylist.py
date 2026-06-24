#!/usr/bin/env python3
"""CLI để chạy benchmark trên fine-tuned stylist models."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from outfitmatch.stylist.benchmark import evaluate_dataset, load_eval_dataset


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark fine-tuned stylist models.")
    parser.add_argument("--eval-path", type=Path, required=True, help="Path to eval.jsonl.")
    parser.add_argument("--model-name", required=True, help="HuggingFace model ID or local path.")
    parser.add_argument("--adapter-path", default=None, help="Path to LoRA adapter (optional).")
    parser.add_argument("--max-samples", type=int, default=None, help="Limit evaluation samples.")
    parser.add_argument("--output-json", type=Path, default=None, help="Save report to JSON file.")
    return parser


def _load_model_and_tokenizer(model_name: str, adapter_path: str | None = None):
    """Load model and tokenizer using transformers (Auto classes)."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

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

    return model, tokenizer


def _make_generate_fn(model, tokenizer):
    """Build a generate_fn compatible with evaluate_dataset."""
    import torch

    def _generate(messages: list[dict[str, str]]) -> str:
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=512, do_sample=False)
        input_len = inputs["input_ids"].shape[1]
        return tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True).strip()

    return _generate


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    dataset = load_eval_dataset(args.eval_path)

    model, tokenizer = _load_model_and_tokenizer(args.model_name, args.adapter_path)
    generate_fn = _make_generate_fn(model, tokenizer)
    report = evaluate_dataset(dataset, generate_fn, max_samples=args.max_samples)

    if args.output_json:
        args.output_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Report saved to {args.output_json}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
