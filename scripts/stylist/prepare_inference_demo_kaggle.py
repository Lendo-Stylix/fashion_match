#!/usr/bin/env python3
"""Prepare & push Kaggle inference-demo notebooks for the two production
stylist adapters:

  T3 — Qwen3-VL-8B-Thinking-bnb-4bit + LoRA
       Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora
  T2 — Qwen3.5-text-9B-bnb-4bit + LoRA
       Nhat-Quang/outfitmatch-stylist-final-qwen35-9b-bnb4-lora

Each notebook loads the base 4-bit model, attaches the LoRA adapter, and runs
ONE Vietnamese demo prompt (tool-call trigger) to prove the adapter works
end-to-end on Kaggle T4 GPU.

Authentication:
  Kaggle CLI v2 reads the access token directly from the KAGGLE_API_TOKEN
  env var (NOT KAGGLE_USERNAME/KAGGLE_KEY). This script resolves that token
  from `--token-env` (default KAGGLE_API_TOKEN_1) in .env.local and exports
  it as KAGGLE_API_TOKEN for the `kaggle kernels push` subprocess.

Usage:
  # Dry-run: build notebooks locally, do NOT push
  uv run python scripts/stylist/prepare_inference_demo_kaggle.py --clean

  # Push both notebooks to Kaggle T4
  uv run python scripts/stylist/prepare_inference_demo_kaggle.py --push
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "stylist" / "fine_tune" / "runs" / "kaggle_inference_demo"
DEFAULT_TOKEN_ENV = "KAGGLE_API_TOKEN_1"
DEFAULT_KAGGLE_OWNER = "nhatquangvominh"
DEFAULT_KERNEL_SLUG_PREFIX = "om-sty-infer-demo"

# OutfitMatch system prompt — matches the SFT training system prompt exactly.
SYSTEM_PROMPT = (
    "Bạn là AI stylist tiếng Việt của OutfitMatch cho thị trường Việt Nam. "
    "Trả lời ngắn gọn, thực tế, bám catalog thật, hỏi lại khi thiếu thông tin "
    "quan trọng, gọi đúng search_outfits khi cần, không bịa outfit_id, sản phẩm, "
    "giá, size hoặc tình trạng tồn kho."
)

# One Vietnamese demo prompt that should trigger a tool_call.
DEMO_PROMPT = (
    "Mình cao 1m60 nặng 55kg, dáng quả lê. Tuần sau mình đi dự đám cưới bạn thân "
    "vào mùa hè, ngân sách khoảng 1 triệu đồng. Gợi ý giúp mình outfit phù hợp nhé."
)


@dataclass(frozen=True)
class DemoSpec:
    """One inference-demo notebook spec."""

    model_id: str  # short tag, e.g. "T3"
    run_id: str  # kaggle kernel slug suffix
    base_model: str  # HF id of the pre-quantized 4-bit base
    adapter_repo: str  # HF id of the LoRA adapter
    is_vision: bool  # True for Qwen3-VL (needs AutoProcessor text= kwarg)
    description: str


DEMOS: tuple[DemoSpec, ...] = (
    DemoSpec(
        model_id="T3",
        run_id="qwen3vl8b-thinking",
        base_model="unsloth/Qwen3-VL-8B-Thinking-bnb-4bit",
        adapter_repo="Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora",
        is_vision=True,
        description="Qwen3-VL-8B Thinking + LoRA (production primary)",
    ),
    DemoSpec(
        model_id="T2",
        run_id="qwen35-9b",
        base_model="techwithsergiu/Qwen3.5-text-9B-bnb-4bit",
        adapter_repo="Nhat-Quang/outfitmatch-stylist-final-qwen35-9b-bnb4-lora",
        is_vision=False,
        description="Qwen3.5-9B text-only + LoRA (fallback)",
    ),
)


# ---------------------------------------------------------------------------
# .env.local reader (never prints token values)
# ---------------------------------------------------------------------------
def read_env_file(path: Path) -> dict[str, str]:
    """Read KEY=VALUE pairs from a .env file without exporting them."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_kaggle_token(token_env: str, env_path: Path) -> str | None:
    """Resolve the Kaggle API token: process env first, then .env.local."""
    return os.environ.get(token_env) or read_env_file(env_path).get(token_env)


# ---------------------------------------------------------------------------
# Notebook cell source builders
# ---------------------------------------------------------------------------
def _install_cell() -> str:
    """pip installs needed on Kaggle (transformers/accelerate already present)."""
    return (
        "# Install adapter/quant deps (Kaggle base image already has torch+transformers)\n"
        "!pip -q install -U 'transformers>=4.57.0' peft bitsandbytes accelerate sentencepiece protobuf\n"
        "import peft, bitsandbytes, accelerate\n"
        "print('peft', peft.__version__, '| bitsandbytes', bitsandbytes.__version__)"
    )


def _load_cell(spec: DemoSpec) -> str:
    """Load base 4-bit model + attach LoRA adapter.

    Applies the two learned fixes:
      - device_map={'': 0} (NOT 'auto') to skip bnb-4bit CPU-dispatch ValueError
      - For Qwen3-VL text-only: processor(text=[prompt], images=None, ...) to
        avoid 'Incorrect image source' errors.

    Plain string + .replace() (not f-string) so literal braces in emitted
    Python (dicts, f-string specs) do not collide with substitution.
    """
    common_load = (
        "t0 = time.time()\n"
        "# device_map={'': 0} avoids the bnb-4bit 'Some modules dispatched on the CPU' error.\n"
        "__IMPORT_LINE__\n"
        "model = __AUTO_CLASS__.from_pretrained(\n"
        "    BASE,\n"
        "    trust_remote_code=True,\n"
        "    device_map={'': 0},\n"
        "    torch_dtype=\"auto\",   # honor each checkpoint native dtype\n"
        ")\n"
        "model = PeftModel.from_pretrained(model, ADAPTER)\n"
        "model.eval()\n"
        'print(f"[load] base + adapter in {time.time()-t0:.1f}s")\n'
        'print(f"[vram] allocated={torch.cuda.memory_allocated()/1e9:.2f}GB "\n'
        '      f"reserved={torch.cuda.memory_reserved()/1e9:.2f}GB")'
    )
    if spec.is_vision:
        body = (
            "# Load Qwen3-VL-8B-Thinking (4-bit) + LoRA adapter\n"
            "import torch, time\n"
            "from transformers import AutoModelForImageTextToText, AutoProcessor\n"
            "from peft import PeftModel\n\n"
            'BASE = "__BASE__"\n'
            'ADAPTER = "__ADAPTER__"\n\n'
            + common_load
                .replace("__IMPORT_LINE__", "processor = AutoProcessor.from_pretrained(BASE, trust_remote_code=True)")
                .replace("__AUTO_CLASS__", "AutoModelForImageTextToText")
        )
    else:
        body = (
            "# Load Qwen3.5-9B (4-bit) + LoRA adapter\n"
            "import torch, time\n"
            "from transformers import AutoModelForCausalLM, AutoTokenizer\n"
            "from peft import PeftModel\n\n"
            'BASE = "__BASE__"\n'
            'ADAPTER = "__ADAPTER__"\n\n'
            + common_load
                .replace("__IMPORT_LINE__", "tokenizer = AutoTokenizer.from_pretrained(BASE, trust_remote_code=True)")
                .replace("__AUTO_CLASS__", "AutoModelForCausalLM")
        )
    return body.replace("__BASE__", spec.base_model).replace("__ADAPTER__", spec.adapter_repo)

def _generate_cell(spec: DemoSpec) -> str:
    """Generate output for the demo prompt and print it.

    Plain string + .replace() so literal braces in emitted Python do not
    collide with substitution.
    """
    system_py = json.dumps(SYSTEM_PROMPT, ensure_ascii=False)
    user_py = json.dumps(DEMO_PROMPT, ensure_ascii=False)
    model_label = ("T3 Qwen3-VL-8B Thinking + LoRA" if spec.is_vision
                   else "T2 Qwen3.5-9B + LoRA")
    body = (
        "# Run the demo prompt\n"
        "messages = [\n"
        '    {"role": "system", "content": __SYSTEM_PY__},\n'
        '    {"role": "user", "content": __USER_PY__},\n'
        "]\n"
        + ("prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)\n"
           "# Qwen3-VL text-only: pass text= explicitly to dodge 'Incorrect image source'.\n"
           "inputs = processor(text=[prompt], images=None, return_tensors=\"pt\")\n"
           "device = next(model.parameters()).device\n"
           'inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}\n'
           if spec.is_vision else
           "prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)\n"
           "inputs = tokenizer(prompt, return_tensors=\"pt\")\n"
           "device = next(model.parameters()).device\n"
           "inputs = {k: v.to(device) for k, v in inputs.items()}\n" )
        + "device = next(model.parameters()).device\n"
        + 'input_len = inputs["input_ids"].shape[1]\n\n'
        + "t0 = time.time()\n"
        + "with torch.no_grad():\n"
        + "    out = model.generate(\n"
        + "        **inputs,\n"
        + "        max_new_tokens=384,\n"
        + "        do_sample=False,\n"
        + "        temperature=1.0,\n"
        + "        top_p=1.0,\n"
        + "    )\n"
        + "gen_ids = out[0][input_len:]\n"
        + ( "answer = processor.decode(gen_ids, skip_special_tokens=True).strip()\n"
            if spec.is_vision else
            "answer = tokenizer.decode(gen_ids, skip_special_tokens=True).strip()\n" )
        + 'print("=" * 70)\n'
        + 'print("DEMO PROMPT:")\n'
        + "print(__USER_PY__)\n"
        + 'print("-" * 70)\n'
        + 'print("MODEL OUTPUT (__MODEL_LABEL__):")\n'
        + "print(answer)\n"
        + 'print("-" * 70)\n'
        + 'print(f"generated in {time.time()-t0:.1f}s, {len(gen_ids)} new tokens")'
    )
    return (
        body.replace("__SYSTEM_PY__", system_py)
        .replace("__USER_PY__", user_py)
        .replace("__MODEL_LABEL__", model_label)
    )

def _validate_cell() -> str:
    """Optional: validate any tool_call in the output against the schema."""
    return """# Optional: parse + validate any <tool_call> in the output
import re, json
m = re.search(r"<tool_call>\\s*(\\{.*?\\})\\s*</tool_call>", answer, re.DOTALL)
if m:
    payload = json.loads(m.group(1))
    print("PARSED TOOL CALL:", json.dumps(payload, ensure_ascii=False, indent=2))
    args = payload.get("arguments", {})
    if "occasion" not in args:
        print("[warn] tool call missing required 'occasion'")
else:
    print("[info] no <tool_call> block in output (model may have asked a clarifying question)")"""


def build_notebook(spec: DemoSpec) -> dict[str, Any]:
    """Build a Kaggle-ready .ipynb dict for one demo."""
    cells = [
        _markdown_cell(
            f"# Stylist Inference Demo — {spec.model_id}\n\n"
            f"{spec.description}\n\n"
            f"- Base: `{spec.base_model}`\n"
            f"- Adapter: `{spec.adapter_repo}`\n\n"
            "Loads the 4-bit base + LoRA adapter and runs ONE Vietnamese demo "
            "prompt to prove the fine-tuned adapter triggers a valid "
            "`<tool_call>search_outfits(...)</tool_call>`."
        ),
        _code_cell(_install_cell()),
        _code_cell(_load_cell(spec)),
        _code_cell(_generate_cell(spec)),
        _code_cell(_validate_cell()),
    ]
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10"},
            "kaggle": {
                "is_private": True,
                "machine_shape": "NvidiaTeslaT4",
                "enable_gpu": True,
                "enable_internet": True,
            },
        },
        "nbformat": 4,
        "nbformat_minor": 4,
    }


def _markdown_cell(source: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": [source]}


def _code_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


# ---------------------------------------------------------------------------
# Packaging + push
# ---------------------------------------------------------------------------
def write_kernel_folder(
    spec: DemoSpec,
    output_root: Path,
    owner: str,
    slug_prefix: str,
) -> Path:
    """Write one kernel folder with notebook + kernel-metadata.json."""
    kernel_slug = f"{slug_prefix}-{spec.run_id}"
    folder = output_root / f"kaggle_kernel_{spec.run_id}"
    folder.mkdir(parents=True, exist_ok=True)

    notebook = build_notebook(spec)
    nb_path = folder / "demo_inference.ipynb"
    nb_path.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    metadata = {
        "id": f"{owner}/{kernel_slug}",
        "title": kernel_slug,
        "code_file": "demo_inference.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": "true",
        "enable_gpu": "true",
        "enable_tpu": "false",
        "enable_internet": "true",
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
        "machine_shape": "NvidiaTeslaT4",
    }
    (folder / "kernel-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return folder


def push_kernel(folder: Path, token: str) -> tuple[int, str]:
    """Push one kernel folder via kaggle CLI with the token in env.

    Returns (returncode, combined stdout+stderr).
    """
    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = token
    # Clear legacy vars to avoid stale overrides.
    env.pop("KAGGLE_USERNAME", None)
    env.pop("KAGGLE_KEY", None)
    # Force UTF-8 so the Kaggle CLI can read the Vietnamese notebook bytes
    # (Windows default cp1252 raises 'charmap' codec errors on 0x9d etc.).
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        ["kaggle", "kernels", "push", "-p", str(folder)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Prepare & push Kaggle inference-demo notebooks for T3 + T2 adapters.",
    )
    p.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Where to write the kernel folders.",
    )
    p.add_argument(
        "--owner",
        default=DEFAULT_KAGGLE_OWNER,
        help="Kaggle owner (account bound to the API token).",
    )
    p.add_argument(
        "--slug-prefix",
        default=DEFAULT_KERNEL_SLUG_PREFIX,
        help="Kernel slug prefix.",
    )
    p.add_argument(
        "--token-env",
        default=DEFAULT_TOKEN_ENV,
        help="Env var name holding the Kaggle API token (in .env.local).",
    )
    p.add_argument(
        "--env-file",
        type=Path,
        default=REPO_ROOT / ".env.local",
        help="Path to .env.local (token source).",
    )
    p.add_argument("--clean", action="store_true", help="Remove output root before writing.")
    p.add_argument("--push", action="store_true", help="Push the notebooks to Kaggle.")
    p.add_argument(
        "--only",
        choices=[d.model_id for d in DEMOS],
        help="Build/push only one demo (default: both).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.clean and args.output_root.exists():
        import shutil

        shutil.rmtree(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)

    selected = [d for d in DEMOS if (args.only is None or d.model_id == args.only)]
    print(f"[prepare] building {len(selected)} notebook(s) under {args.output_root}")

    folders: list[Path] = []
    for spec in selected:
        folder = write_kernel_folder(spec, args.output_root, args.owner, args.slug_prefix)
        folders.append(folder)
        print(f"  [{spec.model_id}] {folder.name}  ->  {args.owner}/{args.slug_prefix}-{spec.run_id}")

    if not args.push:
        print("[prepare] --push not set; notebooks ready locally, no push performed.")
        print("           Re-run with --push to upload to Kaggle.")
        return 0

    # Push
    token = resolve_kaggle_token(args.token_env, args.env_file)
    if not token:
        print(
            f"[error] no token found in env {args.token_env!r} or {args.env_file}.",
            file=sys.stderr,
        )
        return 2
    print(f"[push] resolved token (len={len(token)}) from {args.token_env}")

    rc_overall = 0
    for spec, folder in zip(selected, folders, strict=True):
        print(f"[push] {spec.model_id}: kaggle kernels push -p {folder.name}")
        rc, out = push_kernel(folder, token)
        slug = f"{args.owner}/{args.slug_prefix}-{spec.run_id}"
        if rc == 0:
            print(f"  -> pushed: {slug}")
            print(f"     url: https://www.kaggle.com/code/{slug}")
        else:
            rc_overall = rc
            print(f"  -> FAILED (rc={rc})")
            print("     " + out.strip().replace("\n", "\n     "))
        # Be polite to the Kaggle API between pushes.
        import time as _t

        _t.sleep(3)

    if rc_overall == 0:
        print(
            "[done] all notebooks pushed. Trigger a GPU run from the Kaggle UI "
            "(each notebook needs internet=on + GPU=T4 to download HF weights).",
        )
    return rc_overall


if __name__ == "__main__":
    raise SystemExit(main())
