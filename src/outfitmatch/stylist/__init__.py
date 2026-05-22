"""Conversational AI Stylist — Qwen3-VL-8B + LoRA (v3.1-lite Tầng 2).

Key responsibilities:
  - Parse user intent (height, weight, occasion, style, skin_tone) from natural text
  - Ask follow-up questions when required fields are missing
  - Call search_outfits tool with controlled-vocab parameters (vocab.py)
  - Validate all outfit_id references before presenting to user
  - Generate personalised Vietnamese explanations

Sprint 6-7 implements model.py (Qwen3-VL-8B loading + LoRA) and data.py (training data).
tools.py and validation.py are fully operational now.

See Kien_truc_v3.1.md §4 for full specification.
"""
from outfitmatch.stylist.tools import SEARCH_OUTFITS_TOOL
from outfitmatch.stylist.validation import extract_outfit_ids, validate_response

__all__ = ["SEARCH_OUTFITS_TOOL", "extract_outfit_ids", "validate_response"]
