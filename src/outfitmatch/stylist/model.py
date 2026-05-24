"""Qwen3-VL-8B model loading + LoRA inference.

Correct class: Qwen3VLForConditionalGeneration (NOT Qwen2VLForConditionalGeneration).
Quantise to 4-bit (BitsAndBytesConfig, nf4) for ~8GB VRAM demo deployment.
TrainingArguments: use eval_strategy (not evaluation_strategy — deprecated).

Implemented in Sprint 6-7. See Kien_truc_v3.1.md §4.2.
"""

from __future__ import annotations

from typing import Any


def load_stylist_model(
    base_model: str = "Qwen/Qwen3-VL-8B-Instruct",
    lora_checkpoint: str | None = None,
    load_in_4bit: bool = True,
) -> Any:
    """Load Qwen3-VL-8B with optional LoRA weights, quantised to 4-bit.

    Args:
        base_model: HuggingFace model ID.
        lora_checkpoint: Path to LoRA adapter directory, or None for base model only.
        load_in_4bit: Whether to quantise (reduces VRAM from ~16GB to ~8GB).

    Returns:
        (model, processor) tuple ready for inference.
    """
    raise NotImplementedError("Implement in Sprint 6-7: Qwen3-VL-8B + LoRA loading")
