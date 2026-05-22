"""Gemini Flash LLM metadata tagging for Knowledge Base outfits.

Tags each outfit with occasion/style/body_shapes_fit/season using Gemini Flash.
Validates all returned values against vocab.py enums — rejects any stray values.
Uses diskcache to avoid re-calling Gemini for the same outfit.

Only tag outfits with compatibility_score above the threshold (set in scoring.py)
to minimise API cost.

Implemented in Sprint 3-4. See Kien_truc_v3.1.md §3.4 Bước 5.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from outfitmatch.kb.schema import OutfitRecord


def tag_outfits(
    outfits: list[OutfitRecord],
    gemini_model: str = "gemini-2.0-flash",
    cache_dir: str = ".cache/gemini_tagging",
) -> list[OutfitRecord]:
    """Call Gemini Flash to fill occasion/style/body_shapes_fit/season/stylist_explanation_vi.

    Prompt forces enum-constrained output (values from vocab.py).
    Invalid enum values are logged and dropped — never written to KB.
    """
    raise NotImplementedError("Implement in Sprint 3-4: Gemini Flash LLM tagging")
