from __future__ import annotations

import pytest

from outfitmatch.pipeline import RecommendRequest, recommend_outfit


def test_recommend_raises_not_implemented():
    req = RecommendRequest(occasion="office", image_path="x.jpg", height_cm=170, weight_kg=60)
    with pytest.raises(NotImplementedError):
        recommend_outfit(req)
