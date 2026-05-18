from __future__ import annotations

from outfitmatch.body.pose import PoseExtractor, keypoints_to_measures
from outfitmatch.body.shape_rules import classify_body_shape


def _classify_shape(image_path: str) -> str:
    pe = PoseExtractor()
    kp = pe.extract(image_path)
    if kp is None:
        return "rectangle"
    m = keypoints_to_measures(kp)
    return classify_body_shape(**m)


def _retrieve(shape: str, occasion: str) -> dict[str, str]:
    # Sprint 8: wire to Qdrant index in src/outfitmatch/index.py
    raise NotImplementedError(
        "Catalog index not built yet — run Sprint 8 tasks first."
    )


def recommend_outfit(
    image_path: str,
    height: float,
    weight: float,
    occasion: str,
) -> dict:
    """End-to-end recommendation: image + (h, w, occasion) → outfit slots."""
    shape = _classify_shape(image_path)
    outfit = _retrieve(shape, occasion)
    return {"body_shape": shape, "occasion": occasion, "outfit": outfit}
