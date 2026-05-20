import numpy as np

from outfitmatch.body.pose import PoseExtractor, keypoints_to_measures


def test_keypoints_to_measures_computes_widths():
    # COCO-17: 5=L-shoulder,6=R-shoulder,11=L-hip,12=R-hip
    kp = np.zeros((17, 2))
    kp[5] = [10, 0]
    kp[6] = [50, 0]  # shoulder width 40
    kp[11] = [15, 100]
    kp[12] = [45, 100]  # hip width 30
    m = keypoints_to_measures(kp)
    assert m["shoulder"] == 40.0
    assert m["hip"] == 30.0
    assert m["waist"] > 0


def test_pose_extractor_model_name_recorded():
    pe = PoseExtractor(weights="yolov8n-pose.pt")
    assert pe.model_name == "yolov8n-pose.pt"
