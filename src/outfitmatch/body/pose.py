from __future__ import annotations

from typing import Any

import numpy as np


def keypoints_to_measures(kp: np.ndarray) -> dict[str, float]:
    """COCO-17 keypoints → shoulder/waist/hip width proxies.

    COCO-17 index: 5=L-shoulder, 6=R-shoulder, 11=L-hip, 12=R-hip
    Waist is estimated (no COCO keypoint) as proportional mean.
    """
    shoulder = float(np.linalg.norm(kp[5] - kp[6]))
    hip = float(np.linalg.norm(kp[11] - kp[12]))
    waist = (shoulder + hip) / 2.0 * 0.85  # proxy
    return {"shoulder": shoulder, "waist": waist, "hip": hip}


class PoseExtractor:
    """Wraps ultralytics YOLO-pose. Lazy-loads model on first call."""

    def __init__(self, weights: str = "yolov8n-pose.pt") -> None:
        self.model_name = weights
        self._model: Any | None = None

    def _lazy(self) -> Any:
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self.model_name)
        return self._model

    def extract(self, image_path: str) -> np.ndarray | None:
        """Returns (17, 2) keypoint array or None if no person detected."""
        res = self._lazy()(image_path, verbose=False)
        kp = res[0].keypoints
        if kp is None or kp.xy.shape[1] == 0:
            return None
        return kp.xy[0].cpu().numpy()
