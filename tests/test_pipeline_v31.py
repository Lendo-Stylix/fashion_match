from __future__ import annotations

import pytest

from outfitmatch.pipeline import RecommendRequest, RecommendResult, recommend_outfit


def test_recommend_outfit_raises_not_implemented():
    req = RecommendRequest(occasion="office")
    with pytest.raises(NotImplementedError, match="Sprint"):
        recommend_outfit(req)


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
