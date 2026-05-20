from outfitmatch.pipeline import recommend_outfit


def test_recommend_returns_outfit_slots(monkeypatch):
    monkeypatch.setattr("outfitmatch.pipeline._classify_shape",
                        lambda img: "pear")
    monkeypatch.setattr("outfitmatch.pipeline._retrieve",
                        lambda shape, occ: {"top": "t1", "bottom": "b1",
                                            "shoes": "s1", "accessory": "a1"})
    out = recommend_outfit(image_path="x.jpg", height=170, weight=60,
                           occasion="office")
    assert set(out["outfit"]) == {"top", "bottom", "shoes", "accessory"}
    assert out["body_shape"] == "pear"
