"""Qwen3-VL-8B model loading + LoRA inference.

Correct class: Qwen3VLForConditionalGeneration (NOT Qwen2VL and NOT
AutoModelForCausalLM - the VL model is a vision-LM).

Quantise to 4-bit via BitsAndBytesConfig (nf4 + double-quant) for ~8GB VRAM
demo deployment. TrainingArguments: use eval_strategy (not
evaluation_strategy - deprecated).

Implemented in Sprint 6-7. See Kien_truc_v3.1.md section 4.2.

Notes from proven local runtime (see scripts/stylist/run_inference_device.py
and memory notes):

* device_map={'': 0} - NOT 'auto'. 'auto' triggers a bnb CPU-dispatch
  ValueError because infer_auto_device_map tries to spill embed_tokens /
  lm_head to CPU, which the bnb validator rejects.
* torch_dtype='auto' - pre-quantized bnb-4bit checkpoints store lm_head as
  BFloat16; forcing torch.float16 downcasts it and raises
  RuntimeError: expected scalar type BFloat16 but found Half at generate().
* Qwen3VLForConditionalGeneration + AutoProcessor - the canonical VL
  class. Do NOT use AutoModelForCausalLM (wrong class for VL).
* For text-only prompts, call processor(text=[prompt], images=None, ...) to
  avoid the Incorrect image source error from treating the rendered chat
  string as an image URL.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default local model paths (mirror scripts/setup_models.py layout).
_MODELS_BASE = Path(os.environ.get("OUTFITMATCH_MODELS_BASE", "D:/Models"))
DEFAULT_BASE_MODEL_DIR = _MODELS_BASE / "hf_hub" / "unsloth--Qwen3-VL-8B-Thinking-bnb-4bit"
DEFAULT_ADAPTER_DIR = (
    _MODELS_BASE / "adapters" / "Nhat-Quang--outfitmatch-stylist-final-qwen3vl8b-thinking-lora"
)

# Default system prompt (few-shot tool-call format) - same as
# scripts/stylist/run_inference_device.py. Kept here so the server can use it
# without importing the demo script.
DEFAULT_SYSTEM_PROMPT = (
    "Ban la AI stylist tieng Viet cua OutfitMatch. Nhiem vu cua ban la HIEU "
    "yeu cau cua nguoi dung va GOI tool search_outfits de lay outfit tu "
    "Knowledge Base. Phai goi tool truoc khi dua ra loi khuyen.\n\n"
    "Quy tac:\n"
    "1. Phan tich yeu cau -> anh xa sang cac tham so:\n"
    "   - occasion (bat buoc): office | interview | school | date | cafe_hangout "
    "| party | wedding | home_casual | travel\n"
    "   - style: minimalist | korean | streetwear | elegant | casual | vintage "
    "| sporty | feminine\n"
    "   - body_shape: pear | apple | hourglass | rectangle | inverted_triangle\n"
    "   - skin_tone: warm | neutral | cool\n"
    "   - price_max: so nguyen VND (vd 1000000)\n"
    "   - exclude_colors: mang ten mau tieng Viet\n"
    '2. Phat dung dinh dang: <tool_call>{"name":"search_outfits",'
    '"arguments":{...}}</tool_call>\n'
    "3. KHONG bia outfit_id, khong bia gia; chi tool_call.\n\n"
    "Vi du 1:\n"
    "User: Minh di lam van phong, style minimalist, ngan sach 800k\n"
    'Assistant: <tool_call>{"name":"search_outfits","arguments":'
    '{"occasion":"office","style":"minimalist","price_max":800000}'
    "}</tool_call>\n\n"
    "Vi du 2:\n"
    "User: Dang qua le, di tiec cuoi nam, sang mot chut\n"
    'Assistant: <tool_call>{"name":"search_outfits","arguments":'
    '{"occasion":"party","body_shape":"pear","style":"elegant"}'
    "}</tool_call>"
)


def _bnb_config(load_in_4bit: bool) -> Any | None:
    """Build BitsAndBytesConfig for 4-bit NF4 quantisation (or None)."""
    if not load_in_4bit:
        return None
    from transformers import BitsAndBytesConfig

    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=None,  # let model decide per-layer
        bnb_4bit_use_double_quant=True,
    )


def load_stylist_model(
    base_model: str | Path = DEFAULT_BASE_MODEL_DIR,
    lora_checkpoint: str | Path | None = DEFAULT_ADAPTER_DIR,
    load_in_4bit: bool = True,
    device_map: dict[str, int] | None = None,
) -> tuple[Any, Any]:
    """Load Qwen3-VL-8B with optional LoRA weights, quantised to 4-bit.

    Args:
        base_model: HuggingFace model ID or local path.
        lora_checkpoint: Path to LoRA adapter directory, or None for base only.
        load_in_4bit: Whether to quantise (reduces VRAM from ~16GB to ~8GB).
        device_map: Device mapping. Defaults to {'': 0} (single GPU, no
            CPU offload). Pass None to use default.

    Returns:
        (model, processor) tuple ready for inference.

    Critical: device_map MUST be {'': 0} for bnb-4bit (NOT 'auto').
    torch_dtype MUST be 'auto' for pre-quantized checkpoints (NOT float16).
    """
    from transformers import (
        AutoProcessor,
        Qwen3VLForConditionalGeneration,
    )

    if device_map is None:
        device_map = {"": 0}

    quantization_config = _bnb_config(load_in_4bit)

    logger.info("Loading base model: %s", base_model)
    t0 = time.time()

    model: Any = Qwen3VLForConditionalGeneration.from_pretrained(
        str(base_model),
        trust_remote_code=True,
        device_map=device_map,
        torch_dtype="auto",
        quantization_config=quantization_config,
    )

    if lora_checkpoint is not None:
        from peft import PeftModel

        logger.info("Loading LoRA adapter: %s", lora_checkpoint)
        model = PeftModel.from_pretrained(model, str(lora_checkpoint))

    model.eval()
    processor = AutoProcessor.from_pretrained(str(base_model), trust_remote_code=True)

    elapsed = time.time() - t0
    logger.info("Model loaded in %.1fs", elapsed)

    # Log VRAM usage if CUDA available
    try:
        import torch

        if torch.cuda.is_available():
            alloc = torch.cuda.memory_allocated() / 1e9
            reserved = torch.cuda.memory_reserved() / 1e9
            logger.info("VRAM allocated=%.2fGB reserved=%.2fGB", alloc, reserved)
    except Exception:  # noqa: BLE001
        pass

    return model, processor


def generate_stylist_response(
    model: Any,
    processor: Any,
    user_prompt: str,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    max_new_tokens: int = 512,
    temperature: float = 0.7,
    top_p: float = 0.9,
    enable_thinking: bool | None = None,
) -> str:
    """Generate the stylist response for one user prompt.

    Args:
        model: Loaded Qwen3-VL model (from load_stylist_model).
        processor: Loaded AutoProcessor (from load_stylist_model).
        user_prompt: User message in Vietnamese.
        system_prompt: System prompt (default: few-shot tool-call format).
        max_new_tokens: Max tokens to generate.
        temperature: Sampling temperature (0.0 = greedy).
        top_p: Nucleus sampling top-p.

    Returns:
        Generated text response.

    Note: Uses processor(text=[prompt], images=None, ...) for text-only
    prompts to avoid the 'Incorrect image source' error.
    """
    import torch

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    prompt = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=enable_thinking,
    )

    # Text-only: use text=[prompt], images=None to avoid image-source errors
    inputs = processor(text=[prompt], images=None, return_tensors="pt")
    device = next(model.parameters()).device
    inputs = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in inputs.items()}
    input_len = inputs["input_ids"].shape[1]

    t0 = time.time()
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=temperature > 0.0,
            temperature=temperature if temperature > 0.0 else 1.0,
            top_p=top_p,
        )
    gen_ids = out[0][input_len:]
    text = processor.decode(gen_ids, skip_special_tokens=True).strip()

    elapsed = time.time() - t0
    logger.info(
        "Generated %d tokens in %.1fs (%.1f tok/s)",
        len(gen_ids),
        elapsed,
        len(gen_ids) / elapsed if elapsed > 0 else 0,
    )

    return text
