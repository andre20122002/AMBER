"""Pose detection через MediaPipe Pose — для auto-fit PNG-костюма під фігуру відвідувача.

Повертає нормалізовані координати плечей, голови та центру стегон.
overlay.py використовує їх, щоб scale/translate костюм перед накладанням.
"""
import logging
from dataclasses import dataclass

import cv2
import mediapipe as mp
import numpy as np

import config

logger = logging.getLogger(__name__)

# Індекси landmarks у MediaPipe Pose
_NOSE = 0
_LEFT_SHOULDER = 11
_RIGHT_SHOULDER = 12
_LEFT_HIP = 23
_RIGHT_HIP = 24


@dataclass
class PoseResult:
    """Нормалізовані координати [0..1] відносно вхідного кадру."""
    left_shoulder: tuple[float, float]
    right_shoulder: tuple[float, float]
    head: tuple[float, float]
    hips_center: tuple[float, float]
    confidence: float

    @property
    def shoulders_center(self) -> tuple[float, float]:
        return (
            (self.left_shoulder[0] + self.right_shoulder[0]) / 2,
            (self.left_shoulder[1] + self.right_shoulder[1]) / 2,
        )

    @property
    def shoulders_width(self) -> float:
        dx = self.left_shoulder[0] - self.right_shoulder[0]
        dy = self.left_shoulder[1] - self.right_shoulder[1]
        return float(np.hypot(dx, dy))


class PoseDetector:
    def __init__(self):
        mp_pose = mp.solutions.pose
        self.model = mp_pose.Pose(
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=config.POSE_MIN_CONFIDENCE,
            min_tracking_confidence=config.POSE_MIN_CONFIDENCE,
        )
        logger.info("Pose model loaded")

    def detect(self, frame_bgr: np.ndarray) -> PoseResult | None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        results = self.model.process(rgb)
        if not results.pose_landmarks:
            return None

        lm = results.pose_landmarks.landmark

        # Перевірка видимості ключових точок
        required = [_LEFT_SHOULDER, _RIGHT_SHOULDER, _NOSE]
        visibilities = [lm[i].visibility for i in required]
        if min(visibilities) < config.POSE_MIN_CONFIDENCE:
            return None

        left_sh = (lm[_LEFT_SHOULDER].x, lm[_LEFT_SHOULDER].y)
        right_sh = (lm[_RIGHT_SHOULDER].x, lm[_RIGHT_SHOULDER].y)
        head = (lm[_NOSE].x, lm[_NOSE].y)

        # Hips можуть бути не видні (низ кадру обрізаний) — fallback на shoulders+offset
        left_hip = lm[_LEFT_HIP]
        right_hip = lm[_RIGHT_HIP]
        if left_hip.visibility > 0.3 and right_hip.visibility > 0.3:
            hips_center = ((left_hip.x + right_hip.x) / 2, (left_hip.y + right_hip.y) / 2)
        else:
            hips_center = ((left_sh[0] + right_sh[0]) / 2, min(1.0, (left_sh[1] + right_sh[1]) / 2 + 0.3))

        return PoseResult(
            left_shoulder=left_sh,
            right_shoulder=right_sh,
            head=head,
            hips_center=hips_center,
            confidence=float(np.mean(visibilities)),
        )

    def close(self) -> None:
        self.model.close()


if __name__ == "__main__":
    import sys
    from logging_setup import setup_logging
    from camera import CameraThread
    setup_logging()

    mock = "--mock" in sys.argv
    cam = CameraThread(mock=mock)
    cam.start()
    pd = PoseDetector()

    try:
        while True:
            frame = cam.get_latest_frame()
            if frame is None:
                cv2.waitKey(10)
                continue
            pose = pd.detect(frame)
            preview = frame.copy()
            if pose:
                h, w = frame.shape[:2]
                for label, pt in [
                    ("L_sh", pose.left_shoulder),
                    ("R_sh", pose.right_shoulder),
                    ("head", pose.head),
                    ("hips", pose.hips_center),
                ]:
                    x, y = int(pt[0] * w), int(pt[1] * h)
                    cv2.circle(preview, (x, y), 8, (0, 255, 0), -1)
                    cv2.putText(preview, label, (x + 10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.imshow("pose", preview)
            if cv2.waitKey(30) & 0xFF == ord("q"):
                break
    finally:
        pd.close()
        cam.stop()
        cv2.destroyAllWindows()
