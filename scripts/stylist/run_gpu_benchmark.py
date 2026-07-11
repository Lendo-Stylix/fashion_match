#!/usr/bin/env python3
"""GPU benchmark runner for fine-tuned stylist models (Qwen3-VL aware).

Loads a pre-quantized base model (Unsloth bnb-4bit) + optional LoRA adapter
on the local NVIDIA GPU (RTX 5060 Laptop, 8GB VRAM), then runs the
fashion-knowledge & fashion-logic benchmark (28 items, 6 scorers).

Usage (run via venv python directly, NOT uv run - uv run re-syncs to CPU torch):

    .venv/Scripts/python.exe scripts/stylist/run_gpu_benchmark.py \
        --model-id T3 \
        --output-json docs/reports/stylist_benchmark_expansion/gpu_T3.json

Model IDs T1-T4 are resolved via scripts/setup_models.py MODEL_REGISTRY.
T4 (Gemma 4 12B) will OOM on 8GB; run on Kaggle instead.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Force HF caches off C: drive (must run before any transformers import).
# ---------------------------------------------------------------------------
_BASE = Path("D:/Models")
os.environ.setdefault("HF_HUB_CACHE", str(_BASE / "hf_hub"))
os.environ.setdefault("HF_HOME", str(_BASE / "hf_home"))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(_BASE / "hf_hub"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # models already local
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# Import MODEL_REGISTRY from setup_models (in same scripts/ tree)
_THIS = Path(__file__).resolve().parent.parent  # scripts/
sys.path.insert(0, str(_THIS))
sys.path.insert(0, str(_THIS / "stylist"))
from setup_models import (  # noqa: E402, I001
    ADAPTERS_DIR,
    HF_HUB_CACHE,
    MODEL_REGISTRY,
    _local_name,
)

# OutfitMatch source on path
sys.path.insert(0, str(_THIS.parent / "src"))
from outfitmatch.stylist.fashion_eval import evaluate_fashion_dataset  # noqa: E402, I001
from run_fashion_benchmark import build_fashion_dataset  # noqa: E402, I001


def _resolve_model_path(model_id: str) -> str:
    """Return local path of the base model snapshot (local_dir form)."""
    spec = MODEL_REGISTRY[model_id]
    local = HF_HUB_CACHE / _local_name(spec["base"])
    if not local.exists():
        raise FileNotFoundError(
            f"Base model not found locally at {local}. "
            "Run: uv run python scripts/setup_models.py --base "
            f"--models {model_id}"
        )
    return str(local)


def _resolve_adapter_path(model_id: str) -> str:
    """Return local path of the LoRA adapter."""
    spec = MODEL_REGISTRY[model_id]
    local = ADAPTERS_DIR / _local_name(spec["adapter"])
    if not local.exists():
        raise FileNotFoundError(
            f"Adapter not found at {local}. "
            "Run: uv run python scripts/setup_models.py --adapters "
            f"--models {model_id}"
        )
    return str(local)


def _load_model(model_path: str, adapter_path: str | None):
    """Load model + processor/tokenizer.

    Auto-dispatches: qwen3_vl / qwen3_vl_omni -> AutoProcessor + image-text-to-text;
    text-only -> AutoTokenizer + causal LM. Pre-quantized 4-bit: NO extra
    BitsAndBytesConfig (config.json already carries quantization_config).
    """
    import torch
    from transformers import AutoConfig

    cfg = AutoConfig.from_pretrained(model_path, trust_remote_code=True)
    model_type = getattr(cfg, "model_type", "")
    is_vl = model_type in ("qwen3_vl", "qwen3_vl_omni", "qwen2_vl", "qwen2_5_vl")

    if is_vl:
        from transformers import (
            AutoModelForImageTextToText,
            AutoProcessor,
        )

        processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForImageTextToText.from_pretrained(
            model_path,
            trust_remote_code=True,
            device_map={"": 0},
            torch_dtype=torch.bfloat16,
        )
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        processor = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            trust_remote_code=True,
            device_map={"": 0},
            torch_dtype=torch.bfloat16,
        )

    if adapter_path is not None:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()

    # Report VRAM
    try:
        import torch as _t

        if _t.cuda.is_available():
            alloc = _t.cuda.memory_allocated() / 1e9
            reserved = _t.cuda.memory_reserved() / 1e9
            print(f"[gpu] VRAM allocated={alloc:.2f}GB reserved={reserved:.2f}GB", file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass
    return model, processor, is_vl


def _make_generate_fn(model, processor, is_vl: bool):
    """Build generate_fn(messages) -> str compatible with evaluate_fashion_dataset."""
    import torch

    def _generate(messages: list[dict[str, str]]) -> str:
        # Render chat to a single text prompt via the processor's template.
        try:
            prompt = processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:  # noqa: BLE001
            # Fallback: naive concat if no chat template
            prompt = "\n".join(m.get("content", "") for m in messages) + "\n"

        if is_vl:
            # Qwen3-VL processor: pass rendered text explicitly (no images).
            try:
                inputs = processor(text=[prompt], images=None, return_tensors="pt", padding=True)
            except Exception:  # noqa: BLE001
                inputs = processor(text=[prompt], return_tensors="pt")
        else:
            inputs = processor(prompt, return_tensors="pt")

        # Move all tensors to the model's device
        device = next(model.parameters()).device
        inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}
        input_len = inputs["input_ids"].shape[1]
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False,
                temperature=1.0,
                top_p=1.0,
            )
        gen_ids = out[0][input_len:]
        text = processor.decode(gen_ids, skip_special_tokens=True).strip()
        return text

    return _generate


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="GPU benchmark cho stylist (Qwen3-VL aware).")
    p.add_argument("--model-id", required=True, choices=list(MODEL_REGISTRY), help="T1-T4")
    p.add_argument(
        "--no-adapter", action="store_true", help="Skip LoRA adapter (evaluate base only)."
    )
    p.add_argument("--output-json", type=Path, default=None, help="Save report to JSON file.")
    p.add_argument("--max-samples", type=int, default=None)
    p.add_argument("--types", nargs="+", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    model_path = _resolve_model_path(args.model_id)
    adapter_path = None if args.no_adapter else _resolve_adapter_path(args.model_id)
    print(f"[load] base={model_path}", file=sys.stderr)
    if adapter_path:
        print(f"[load] adapter={adapter_path}", file=sys.stderr)

    t0 = time.time()
    model, processor, is_vl = _load_model(model_path, adapter_path)
    load_s = time.time() - t0
    print(f"[load] done in {load_s:.1f}s (is_vl={is_vl})", file=sys.stderr)

    generate_fn = _make_generate_fn(model, processor, is_vl)
    dataset = build_fashion_dataset(types=args.types)

    # Per-sample progress (28 items, ~3-8s each on GPU)
    _counter = {"i": 0}
    _orig_fn = generate_fn

    def _progress_fn(messages):
        _counter["i"] += 1
        ts = time.time()
        result = _orig_fn(messages)
        dt = time.time() - ts
        preview = (result[:60] + "...") if len(result) > 60 else result
        print(f"  [{_counter['i']}/{len(dataset)}] {dt:.1f}s -> {preview!r}", file=sys.stderr)
        return result

    t1 = time.time()
    report = evaluate_fashion_dataset(dataset, _progress_fn, max_samples=args.max_samples)
    eval_s = time.time() - t1
    report["_meta"] = {
        "model_id": args.model_id,
        "base": MODEL_REGISTRY[args.model_id]["base"],
        "adapter": MODEL_REGISTRY[args.model_id]["adapter"] if adapter_path else None,
        "load_s": round(load_s, 1),
        "eval_s": round(eval_s, 1),
        "n_items": len(dataset),
        "device": "cuda",
        "torch": _torch_version(),
    }
    print(
        f"[done] eval in {eval_s:.1f}s; mean={report.get('overall', {}).get('mean', '?')}",
        file=sys.stderr,
    )

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload, encoding="utf-8")
        print(f"[saved] {args.output_json}", file=sys.stderr)
    else:
        print(payload)
    # Cleanup
    del model, generate_fn
    gc.collect()
    try:
        import torch as _t

        _t.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass
    return 0


def _torch_version() -> str:
    try:
        import torch as _t

        return _t.__version__
    except Exception:  # noqa: BLE001
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
