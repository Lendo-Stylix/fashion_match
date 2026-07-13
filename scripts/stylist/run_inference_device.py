#!/usr/bin/env python3
"""On-device inference demo: T3 Qwen3-VL-8B Thinking + LoRA -> tool_call
-> OutfitMatch graph retrieval -> real outfit IDs.

Runs locally on the NVIDIA GPU (RTX 5060 Laptop 8GB, CUDA 13.3). Loads the
base 4-bit model + LoRA adapter from D:/Models, prompts the stylist with a
VIetnamese fashion request, parses the emitted `<tool_call>search_outfits
(...)</tool_call>`, and executes the retrieval against the local fashion_kb
graph (5,618 catalog items + 316K edges) to produce real outfit IDs.

NOTE: run via the venv python directly, NOT `uv run` (uv re-syncs to CPU torch).
    .venv/Scripts/python.exe scripts/stylist/run_inference_device.py

Usage:
    .venv/Scripts/python.exe scripts/stylist/run_inference_device.py
    .venv/Scripts/python.exe scripts/stylist/run_inference_device.py \
        --prompt "Mình đi cafe cuối tuần với bạn, phong cách korean, ngân sách 700k"
    .venv/Scripts/python.exe scripts/stylist/run_inference_device.py --no-adapter
    .venv/Scripts/python.exe scripts/stylist/run_inference_device.py --top-n 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Force HF caches off C: drive + offline mode (models already in D:/Models).
# Must run BEFORE any transformers import.
# ---------------------------------------------------------------------------
_MODELS_BASE = Path("D:/Models")
os.environ.setdefault("HF_HOME", str(_MODELS_BASE / "hf_home"))
os.environ.setdefault("HF_HUB_CACHE", str(_MODELS_BASE / "hf_hub"))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(_MODELS_BASE / "hf_hub"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src"
for _p in (str(_REPO_ROOT), str(_SRC_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Local paths (mirror scripts/setup_models.py layout)
_BASE_DIR = _MODELS_BASE
_HF_HUB_CACHE = _MODELS_BASE / "hf_hub"
_ADAPTERS_DIR = _MODELS_BASE / "adapters"

# T3 = Qwen3-VL-8B-Thinking-bnb-4bit + the production stylist LoRA adapter.
BASE_MODEL_DIR = _HF_HUB_CACHE / "unsloth--Qwen3-VL-8B-Thinking-bnb-4bit"
ADAPTER_DIR = _ADAPTERS_DIR / "Nhat-Quang--outfitmatch-stylist-final-qwen3vl8b-thinking-lora"

# OutfitMatch graph KB paths.
CATALOG_DIR = _REPO_ROOT / "data" / "custom" / "catalog"
CATALOG_PARQUET = CATALOG_DIR / "catalog_metadata.parquet"
LINKS_PARQUET = CATALOG_DIR / "item_store_links.parquet"
EDGES_PARQUET = _REPO_ROOT / "data" / "custom" / "graph" / "item_edges.parquet"


# ---------------------------------------------------------------------------
# System prompt — forces tool-call via few-shot examples.
# The SFT adapter biases toward prose on open-ended prompts (documented in
# docs/presentation/final_slides/04_EVALUATION.md). Few-shot demonstrations
# of the exact `<tool_call>` wire format nudge the model back to tool use.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "Bạn là AI stylist tiếng Việt của OutfitMatch. Nhiệm vụ của bạn là HIỂU "
    "yêu cầu của người dùng và GỌI tool `search_outfits` để lấy outfit từ "
    "Knowledge Base. Phải gọi tool trước khi đưa ra lời khuyên.\n\n"
    "Quy tắc:\n"
    "1. Phân tích yêu cầu -> ánh xạ sang các tham số:\n"
    "   - occasion (bắt buộc): office | interview | school | date | cafe_hangout "
    "| party | wedding | home_casual | travel\n"
    "   - style: minimalist | korean | streetwear | elegant | casual | vintage "
    "| sporty | feminine\n"
    "   - body_shape: pear | apple | hourglass | rectangle | inverted_triangle\n"
    "   - skin_tone: warm | neutral | cool\n"
    "   - price_max: số nguyên VND (vd 1000000)\n"
    "   - exclude_colors: mảng tên màu tiếng Việt\n"
    "2. Phát đúng định dạng: <tool_call>{\"name\":\"search_outfits\","
    "\"arguments\":{...}}</tool_call>\n"
    "3. KHÔNG bịa outfit_id, không bịa giá; chỉ tool_call.\n\n"
    "Ví dụ 1:\n"
    "User: Mình đi làm văn phòng, style minimalist, ngân sách 800k\n"
    "Assistant: <tool_call>{\"name\":\"search_outfits\",\"arguments\":"
    "{\"occasion\":\"office\",\"style\":\"minimalist\",\"price_max\":800000}}"
    "</tool_call>\n\n"
    "Ví dụ 2:\n"
    "User: Dáng quả lê, đi tiệc cuối năm, sang một chút\n"
    "Assistant: <tool_call>{\"name\":\"search_outfits\",\"arguments\":"
    "{\"occasion\":\"party\",\"body_shape\":\"pear\",\"style\":\"elegant\"}}"
    "</tool_call>"
)


def load_stylist(base_path: Path, adapter_path: Path | None):
    """Load T3 Qwen3-VL-8B Thinking 4-bit + optional LoRA adapter.

    Applies the 3 learned bnb-4bit / Qwen-VL fixes:
      - device_map={'': 0} (NOT 'auto') to skip the bnb CPU-dispatch ValueError
      - torch_dtype='auto' (lm_head of T3 is BFloat16; float16 downcasts it)
      - processor(text=[prompt], images=None) at call time (text-only path)
    """
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    processor = AutoProcessor.from_pretrained(str(base_path), trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        str(base_path),
        trust_remote_code=True,
        device_map={"": 0},
        torch_dtype="auto",
    )
    if adapter_path is not None:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(adapter_path))
    model.eval()
    try:
        alloc = torch.cuda.memory_allocated() / 1e9
        reserved = torch.cuda.memory_reserved() / 1e9
        print(f"[load] VRAM allocated={alloc:.2f}GB reserved={reserved:.2f}GB",
              file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass
    return model, processor


def generate(model, processor, user_prompt: str, max_new_tokens: int = 512) -> str:
    """Generate the stylist's response for one user prompt."""
    import torch

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    prompt = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    # Qwen3-VL text-only: pass text= explicitly to dodge 'Incorrect image source'.
    inputs = processor(text=[prompt], images=None, return_tensors="pt")
    device = next(model.parameters()).device
    inputs = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in inputs.items()}
    input_len = inputs["input_ids"].shape[1]

    t0 = time.time()
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=1.0,
            top_p=1.0,
        )
    gen_ids = out[0][input_len:]
    text = processor.decode(gen_ids, skip_special_tokens=True).strip()
    print(f"[gen] {time.time() - t0:.1f}s, {len(gen_ids)} new tokens", file=sys.stderr)
    return text


# ---------------------------------------------------------------------------
# Retrieval: parse tool_call -> RecommendRequest -> search_outfits -> outfit IDs
# ---------------------------------------------------------------------------
def build_graph_context():
    """Load catalog + graph edges from local parquet (no Qdrant needed)."""
    from outfitmatch.kb.catalog import load_catalog_items
    from outfitmatch.kb.graph_store import load_graph

    items = load_catalog_items(CATALOG_PARQUET, LINKS_PARQUET)
    graph = load_graph(EDGES_PARQUET, items=items)
    print(f"[kb] catalog={len(items)} items, graph nodes={len(graph._items)}",
          file=sys.stderr)
    return items, graph


def execute_tool_call(tool_call: dict, graph, top_n: int = 5):
    """Turn a parsed `search_outfits` tool_call into real OutfitRecords.

    Returns (request_brief, outfits).  Skips fields the graph MVP ignores.
    """
    from outfitmatch.pipeline import RecommendRequest
    from outfitmatch.retrieval import search_outfits
    from outfitmatch.stylist.validation import validate_tool_calls

    args = dict(tool_call.get("arguments", {}))
    # occasion is required; fall back to a safe default if the model omitted it.
    occasion = args.get("occasion") or "cafe_hangout"
    request = RecommendRequest(
        occasion=occasion,
        style=args.get("style"),
        body_shape=args.get("body_shape"),
        skin_tone=args.get("skin_tone"),
        price_max=args.get("price_max"),
        exclude_colors=list(args.get("exclude_colors") or []),
    )
    brief = (
        f"occasion={request.occasion} style={request.style} "
        f"body_shape={request.body_shape} skin_tone={request.skin_tone} "
        f"price_max={request.price_max}"
    )
    records = search_outfits(request, graph=graph, top_n=top_n)
    return brief, records


def format_outfit(record) -> str:
    """One-line human-readable outfit summary."""
    cats = [it.category for it in record.items]
    stores = sorted({(it.store.get("store_name") or "?") for it in record.items})
    return (
        f"{record.outfit_id}  score={record.compatibility_score:.2f}  "
        f"price={record.price_total_vnd:,} VND  "
        f"items=[{' + '.join(cats)}]  "
        f"style={record.style}  store={','.join(stores)}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
DEFAULT_PROMPT = (
    "Mình cao 1m60 nặng 55kg, dáng quả lê. Tuần sau mình đi dự đám cưới bạn thân "
    "vào mùa hè, ngân sách khoảng 1 triệu đồng. Gợi ý outfit phù hợp nhé."
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="On-device inference demo: T3 stylist -> tool_call -> graph KB.",
    )
    p.add_argument("--prompt", default=DEFAULT_PROMPT, help="Vietnamese user prompt.")
    p.add_argument(
        "--base", type=Path, default=BASE_MODEL_DIR, help="Local base model dir."
    )
    p.add_argument(
        "--adapter",
        type=Path,
        default=ADAPTER_DIR,
        help="Local LoRA adapter dir (use --no-adapter to skip).",
    )
    p.add_argument("--no-adapter", action="store_true", help="Skip LoRA adapter.")
    p.add_argument("--top-n", type=int, default=5, help="Number of outfits to retrieve.")
    p.add_argument("--max-new-tokens", type=int, default=512)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if not args.base.exists():
        print(f"[error] base model not found at {args.base}", file=sys.stderr)
        print(
            "        run: uv run python scripts/setup_models.py --base --models T3",
            file=sys.stderr,
        )
        return 2
    adapter_path = None if args.no_adapter else args.adapter
    if adapter_path is not None and not adapter_path.exists():
        print(f"[error] adapter not found at {adapter_path}", file=sys.stderr)
        print(
            "        run: uv run python scripts/setup_models.py --adapters --models T3",
            file=sys.stderr,
        )
        return 2

    # 1. Load KB first (fast, CPU).
    print(f"[kb] loading graph KB from {CATALOG_DIR.parent}", file=sys.stderr)
    _, graph = build_graph_context()

    # 2. Load model + adapter.
    tag = "T3 (base only)" if args.no_adapter else "T3 + LoRA adapter"
    print(f"[load] {tag}", file=sys.stderr)
    print(f"       base   = {args.base}", file=sys.stderr)
    if adapter_path:
        print(f"       adapter= {adapter_path}", file=sys.stderr)
    t0 = time.time()
    model, processor = load_stylist(args.base, adapter_path)
    print(f"[load] done in {time.time() - t0:.1f}s", file=sys.stderr)

    # 3. Generate.
    print("\n" + "=" * 72, file=sys.stderr)
    print("USER PROMPT:", file=sys.stderr)
    print(args.prompt, file=sys.stderr)
    print("-" * 72, file=sys.stderr)
    answer = generate(model, processor, args.prompt, args.max_new_tokens)

    print("\n" + "=" * 72)
    print("MODEL OUTPUT:")
    print(answer)
    print("-" * 72)

    # 4. Parse + validate tool_call.
    from outfitmatch.stylist.validation import extract_tool_calls, validate_tool_calls

    ok, errors = validate_tool_calls(answer)
    tool_calls = extract_tool_calls(answer)
    if not tool_calls:
        print("\n[parse] no <tool_call> block found -> cannot retrieve outfits.")
        print("        (documented SFT degradation; the few-shot system prompt did")
        print("        not trigger tool use this time.)")
        return 0
    if not ok:
        print("\n[parse] tool_call present but invalid:")
        for e in errors:
            print(f"        - {e}")
    payload = tool_calls[0]
    print("\n[parse] tool_call OK:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    # 5. Execute retrieval.
    try:
        brief, records = execute_tool_call(payload, graph, top_n=args.top_n)
    except Exception as exc:  # noqa: BLE001
        print(f"\n[retrieve] ERROR: {exc}")
        return 1

    print("\n" + "=" * 72)
    print(f"[retrieve] request: {brief}")
    print(f"[retrieve] search_outfits -> {len(records)} outfits (top {args.top_n}):")
    print("-" * 72)
    for i, rec in enumerate(records, 1):
        print(f"  {i}. {format_outfit(rec)}")
    if not records:
        print("  (no outfits matched — try relaxing style/price constraints)")

    print("\n" + "=" * 72)
    print("OUTFIT IDs:")
    print("  " + ", ".join(rec.outfit_id for rec in records) or "(none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
