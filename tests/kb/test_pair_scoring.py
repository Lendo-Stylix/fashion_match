from __future__ import annotations

from outfitmatch.kb.pair_scoring import HeuristicPairScorer
from outfitmatch.kb.schema import ItemRecord


def _item(
    item_id: str,
    *,
    category: str,
    formality: str,
    price: int,
    colors: list[str],
) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path="",
        item_embedding=[],
        gender="unisex",
        formality=formality,
        store={"price_vnd": price, "colors": colors, "product_url": "x", "in_stock": True},
    )


def test_score_pair_in_unit_range_and_symmetric():
    scorer = HeuristicPairScorer()
    a = _item("a", category="top", formality="casual", price=200_000, colors=["đen"])
    b = _item("b", category="bottom", formality="casual", price=250_000, colors=["đen"])
    score = scorer.score_pair(a, b)
    assert 0.0 <= score <= 1.0
    assert score == scorer.score_pair(b, a)


def test_score_pair_deterministic():
    scorer = HeuristicPairScorer()
    a = _item("a", category="top", formality="casual", price=200_000, colors=["đen"])
    b = _item(
        "b",
        category="bottom",
        formality="smart_casual",
        price=900_000,
        colors=["trắng"],
    )
    assert scorer.score_pair(a, b) == scorer.score_pair(a, b)


def test_score_pair_handles_empty_colors():
    scorer = HeuristicPairScorer()
    a = _item("a", category="top", formality="casual", price=200_000, colors=[])
    b = _item("b", category="bottom", formality="casual", price=200_000, colors=[])
    score = scorer.score_pair(a, b)
    assert 0.0 <= score <= 1.0


def test_same_formality_scores_higher_than_distant():
    scorer = HeuristicPairScorer()
    a = _item("a", category="top", formality="casual", price=200_000, colors=["đen"])
    near = _item("n", category="bottom", formality="casual", price=200_000, colors=["đen"])
    far = _item("f", category="bottom", formality="formal", price=200_000, colors=["đen"])
    assert scorer.score_pair(a, near) > scorer.score_pair(a, far)
