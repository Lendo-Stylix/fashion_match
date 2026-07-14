"""POST /api/recommend — structured recommendation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from outfitmatch.server.schemas import (
    ItemCardDTO,
    OutfitCardDTO,
    RecommendRequestDTO,
)

router = APIRouter()


@router.post("")
async def recommend(req: RecommendRequestDTO) -> dict[str, Any]:
    """Recommend outfits from a structured request."""
    from outfitmatch.pipeline import RecommendRequest, recommend_outfit
    from outfitmatch.quiz.schema import QuizAnswers
    from outfitmatch.server.deps import get_graph, get_stylist_service

    graph = get_graph()
    stylist = get_stylist_service()

    quiz = None
    if req.quiz_answers:
        quiz = QuizAnswers(**req.quiz_answers)

    request = RecommendRequest(
        occasion=req.occasion,
        style=req.style,
        body_shape=req.body_shape,
        skin_tone=req.skin_tone,
        price_max=req.price_max,
        exclude_colors=req.exclude_colors,
        height_cm=req.height_cm,
        weight_kg=req.weight_kg,
        quiz_answers=quiz,
    )
    result = recommend_outfit(request, graph=graph, stylist=stylist)

    outfits = []
    for rec in result.outfits:
        items = [
            ItemCardDTO(
                item_id=it.item_id,
                category=it.category,
                title_vi=it.store.get("title_vi", ""),
                price_vnd=int(it.store.get("price_vnd") or 0),
                store_name=it.store.get("store_name", ""),
                product_url=it.store.get("product_url", ""),
                image_path=it.image_path,
            )
            for it in rec.items
        ]
        outfits.append(
            OutfitCardDTO(
                outfit_id=rec.outfit_id,
                explanation_vi=rec.stylist_explanation_vi,
                price_total_vnd=rec.price_total_vnd,
                price_tier=rec.price_tier,
                style=rec.style,
                occasion=rec.occasion,
                color_palette=rec.color_palette,
                items=items,
                compatibility_score=rec.compatibility_score,
            )
        )

    return {
        "outfits": [o.model_dump() for o in outfits],
        "body_shape": result.body_shape,
        "occasion": result.occasion,
        "explanation_vi": result.explanation_vi,
        "suggested_sizes": result.suggested_sizes,
        "latency_ms": result.latency_ms,
    }
