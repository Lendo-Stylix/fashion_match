from __future__ import annotations

from outfitmatch.pipeline import RecommendRequest, RecommendResult, recommend_outfit


def test_recommend_outfit_assembles_from_injected_graph():
    from outfitmatch.kb.graph import Edge
    from outfitmatch.kb.graph_store import OutfitGraph
    from outfitmatch.kb.schema import ItemRecord

    def item(item_id: str, category: str) -> ItemRecord:
        return ItemRecord(
            item_id=item_id,
            category=category,
            image_path="",
            item_embedding=[0.1],
            gender="men",
            formality="smart_casual",
            store={
                "store_id": "aristino_vn",
                "price_vnd": 300_000,
                "colors": [],
                "product_url": "https://x",
                "in_stock": True,
            },
        )

    graph = OutfitGraph(
        [item("t", "top"), item("b", "bottom")],
        [Edge("b", "t", "bottom", "top", 0.9)],
    )
    result = recommend_outfit(RecommendRequest(occasion="office"), graph=graph, seed_ids=["t"])
    assert len(result.outfits) >= 1
    assert result.occasion == "office"
    assert result.outfits[0].gen_method == "graph_traversal"


def test_recommend_outfit_empty_seeds_is_safe():
    from outfitmatch.kb.graph_store import OutfitGraph

    result = recommend_outfit(
        RecommendRequest(occasion="office"),
        graph=OutfitGraph([], []),
        seed_ids=[],
    )
    assert result.outfits == []


def test_recommend_request_requires_occasion():
    req = RecommendRequest(occasion="date")
    assert req.occasion == "date"
    assert req.height_cm is None
    assert req.weight_kg is None
    assert req.style is None
    assert req.body_shape is None
    assert req.price_max is None
    assert req.exclude_colors == []
    assert req.quiz_answers is None


def test_recommend_result_structure():
    result = RecommendResult(
        outfits=[],
        body_shape="pear",
        occasion="office",
    )
    assert result.outfits == []
    assert result.body_shape == "pear"
    assert result.occasion == "office"
    assert result.explanation_vi == ""
    assert result.latency_ms == 0.0


def test_recommend_result_has_suggested_sizes_default():
    result = RecommendResult(outfits=[], body_shape="rectangle", occasion="office")
    assert result.suggested_sizes == {}
