# src/outfitmatch/pipeline.py
"""E2E recommendation orchestrator for v3.1-lite.

Pipeline (7 steps from Kien_truc_v3.1.md §7):
  1. Accept RecommendRequest (occasion required; everything else optional)
  2. Qwen3-VL parses intent → structured fields (Sprint 6-7)
  3. If missing required info → ask follow-up (Sprint 6-7)
  4. Call search_outfits → Qdrant filter+sort → 30-50 outfits (Sprint 5)
  5. Re-rank by PreferenceProfile from quiz (Sprint 8)
  6. Validate outfit_id refs (hallucination check)
  7. Qwen generates Vietnamese explanation (Sprint 6-7)

Sprints 5-8 implement the full pipeline. Until then each step raises
NotImplementedError with a clear sprint reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from outfitmatch.kb.schema import OutfitRecord
    from outfitmatch.quiz.schema import QuizAnswers


@dataclass
class RecommendRequest:
    """Input to the v3.1-lite recommendation pipeline."""

    occasion: str  # Required — OCCASION enum value
    height_cm: int | None = None
    weight_kg: int | None = None
    style: str | None = None  # STYLE enum value
    body_shape: str | None = None  # BODY_SHAPE enum value
    skin_tone: str | None = None  # SKIN_TONE enum value
    price_max: int | None = None  # Budget cap (VND)
    exclude_colors: list[str] = field(default_factory=list)
    quiz_answers: QuizAnswers | None = None  # From onboarding quiz (Tầng 4)
    image_path: str | None = None  # Optional selfie for body analysis


@dataclass
class RecommendResult:
    """Output from the v3.1-lite recommendation pipeline."""

    outfits: list[OutfitRecord]
    body_shape: str
    occasion: str
    explanation_vi: str = ""
    latency_ms: float = 0.0


def recommend_outfit(request: RecommendRequest) -> RecommendResult:
    """Orchestrate the v3.1-lite 4-tier recommendation pipeline.

    Steps 4-7 are implemented across Sprints 5-8.
    Returns RecommendResult with top 3-5 outfits + Vietnamese explanation.
    """
    raise NotImplementedError(
        "v3.1-lite pipeline: implement Sprint 5 (Qdrant retrieval), "
        "Sprint 6-7 (Qwen3-VL stylist), Sprint 8 (E2E wire-up). "
        "See docs/ARCHITECTURE.md §7 for the full flow."
    )
