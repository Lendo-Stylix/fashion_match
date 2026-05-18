from __future__ import annotations

from typing import Literal

BodyShape = Literal["hourglass", "pear", "apple", "rectangle", "inverted_triangle"]


def classify_body_shape(shoulder: float, waist: float, hip: float) -> BodyShape:
    """5-class rule-based body shape from circumference proxies (pixels or cm)."""
    sh_hip = shoulder / hip
    waist_ratio = waist / max(shoulder, hip)

    if waist >= shoulder and waist >= hip:
        return "apple"
    if sh_hip > 1.05:
        return "inverted_triangle"
    if sh_hip < 0.95:
        return "pear"
    # shoulders ≈ hips
    if waist_ratio <= 0.80:
        return "hourglass"
    return "rectangle"
