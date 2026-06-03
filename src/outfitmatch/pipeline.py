# src/outfitmatch/pipeline.py
"""E2E recommendation orchestrator for v3.1-lite.

Pipeline (7 steps from Kien_truc_v3.1.md §7):
  1. Accept RecommendRequest (occasion required; everything else optional)
  2. Qwen3-VL parses intent → structured fields (Sprint 6-7)
  3. If missing required info → ask follow-up (Sprint 6-7)
  4. Call search_outfits → Qdrant items seed filter + graph traversal → 30-50 outfits
  5. Re-rank by PreferenceProfile from quiz (Sprint 8)
  6. Validate outfit_id refs (hallucination check)
  7. Qwen generates Vietnamese explanation (Sprint 6-7)

Sprints 5-8 implement the full pipeline. Until then each step raises
NotImplementedError with a clear sprint reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from outfitmatch.kb.graph_store import OutfitGraph
    from outfitmatch.kb.schema import ItemRecord, OutfitRecord
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
    suggested_sizes: dict[str, str] = field(default_factory=dict)


@lru_cache(maxsize=1)
def _default_items() -> tuple[ItemRecord, ...]:
    from scripts.data.scrape.base import CATALOG_DIR

    from outfitmatch.kb.catalog import load_catalog_items

    return tuple(
        load_catalog_items(
            CATALOG_DIR / "catalog_metadata.parquet",
            CATALOG_DIR / "item_store_links.parquet",
        )
    )


@lru_cache(maxsize=1)
def _default_graph() -> OutfitGraph:
    from outfitmatch.kb.graph_store import load_graph

    return load_graph(items=list(_default_items()))


def recommend_outfit(
    request: RecommendRequest,
    *,
    graph: OutfitGraph | None = None,
    items: list[ItemRecord] | None = None,
    seed_ids: list[str] | None = None,
    qdrant_url: str = "path://data/cache/qdrant",
) -> RecommendResult:
    """Orchestrate Tầng 3 graph retrieval plus Tầng 4 rerank/sizing."""
    import time

    from outfitmatch.kb.graph_store import load_graph
    from outfitmatch.quiz.rerank import rerank_by_preference
    from outfitmatch.quiz.schema import quiz_to_profile
    from outfitmatch.quiz.sizing import suggest_sizes_for_outfit
    from outfitmatch.retrieval import search_outfits

    start = time.perf_counter()
    if graph is None:
        graph = load_graph(items=items) if items is not None else _default_graph()

    records = search_outfits(
        request,
        graph=graph,
        seed_ids=seed_ids,
        qdrant_url=None if seed_ids is not None else qdrant_url,
    )

    if request.quiz_answers is not None:
        preference = quiz_to_profile(request.quiz_answers)
        records = rerank_by_preference(records, preference, top_k=5)
    else:
        records = records[:5]

    suggested_sizes = (
        suggest_sizes_for_outfit(records[0].items, request.height_cm, request.weight_kg)
        if records
        else {}
    )
    return RecommendResult(
        outfits=records,
        body_shape=request.body_shape or "",
        occasion=request.occasion,
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
        suggested_sizes=suggested_sizes,
    )
