"""Pose detection через MediaPipe Pose + Face fallback.

Стратегія:
1. Спочатку повний pose (потрібно бачити плечі/торс)
2. Якщо не вдалось — face detection і обчислення "уявних" плечей від bbox обличчя
3. Якщо і це не вдалось — None (вище по стеку PoseTracker зробить hold-last-good)

Повертає уніфікований PoseResult з полем .source, щоб overlay/debug могли
розрізняти джерело.
"""
import logging
from dataclasses import dataclass
from typing import Literal

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

PoseSource = Literal["full", "face", "hold"]


@dataclass
class PoseResult:
    """Нормалізовані координати [0..1] відносно вхідного кадру."""
    left_shoulder: tuple[float, float]
    right_shoulder: tuple[float, float]
    head: tuple[float, float]
    hips_center: tuple[float, float]
    confidence: float
    source: PoseSource = "full"

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
        self.pose_model = mp_pose.Pose(
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=config.POSE_MIN_CONFIDENCE,
            min_tracking_confidence=config.POSE_MIN_CONFIDENCE,
        )
        mp_face = mp.solutions.face_detection
        # model_selection=1 — full-range (краще для близьких облич у kiosk)
        self.face_model = mp_face.FaceDetection(
            model_selection=1,
            min_detection_confidence=0.5,
        )
        logger.info("Pose + FaceDetection models loaded")

    def detect(self, frame_bgr: np.ndarray) -> PoseResult | None:
        """Спочатку повний pose; якщо None — face fallback."""
        full = self._detect_full_pose(frame_bgr)
        if full is not None:
            return full
        return self._detect_face_pose(frame_bgr)

    def _detect_full_pose(self, frame_bgr: np.ndarray) -> PoseResult | None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        results = self.pose_model.process(rgb)
        if not results.pose_landmarks:
            return None

        lm = results.pose_landmarks.landmark
        required = [_LEFT_SHOULDER, _RIGHT_SHOULDER, _NOSE]
        visibilities = [lm[i].visibility for i in required]
        if min(visibilities) < config.POSE_MIN_CONFIDENCE:
            return None

        left_sh = (lm[_LEFT_SHOULDER].x, lm[_LEFT_SHOULDER].y)
        right_sh = (lm[_RIGHT_SHOULDER].x, lm[_RIGHT_SHOULDER].y)
        head = (lm[_NOSE].x, lm[_NOSE].y)

        left_hip = lm[_LEFT_HIP]
        right_hip = lm[_RIGHT_HIP]
        if left_hip.visibility > 0.3 and right_hip.visibility > 0.3:
            hips_center = ((left_hip.x + right_hip.x) / 2, (left_hip.y + right_hip.y) / 2)
        else:
            hips_center = (
                (left_sh[0] + right_sh[0]) / 2,
                min(1.0, (left_sh[1] + right_sh[1]) / 2 + 0.3),
            )

        return PoseResult(
            left_shoulder=left_sh,
            right_shoulder=right_sh,
            head=head,
            hips_center=hips_center,
            confidence=float(np.mean(visibilities)),
            source="full",
        )

    def _detect_face_pose(self, frame_bgr: np.ndarray) -> PoseResult | None:
        """Будує уявні плечі/тіло від bbox обличчя (для close-up, коли торс не видно)."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        results = self.face_model.process(rgb)
        if not results.detections:
            return None

        # Беремо найбільше обличчя (близьке до камери)
        best = max(results.detections, key=lambda d: d.location_data.relative_bounding_box.width)
        bbox = best.location_data.relative_bounding_box
        x, y, w, h = bbox.xmin, bbox.ymin, bbox.width, bbox.height

        # Голова (за приблизним центром bbox, трохи вище — там очі/ніс)
        head_x = x + w / 2
        head_y = y + h * 0.4

        # Уявні плечі: на 1.8 висоти обличчя нижче верху bbox, шириною 2.5 ширини обличчя
        sh_cx = x + w / 2
        sh_cy = y + h * 1.8
        sh_half_w = w * 1.25

        # Convention як у MediaPipe Pose: left = менший X на екрані (стандарт image space)
        left_sh = (sh_cx - sh_half_w, sh_cy)
        right_sh = (sh_cx + sh_half_w, sh_cy)

        # Стегна — ще нижче (для симетрії з full-pose, хоча в face режимі вони поза кадром)
        hips_y = sh_cy + h * 1.5
        hips_center = (sh_cx, min(1.0, hips_y))

        # Clamp координат у [0..1]
        def clamp(p: tuple[float, float]) -> tuple[float, float]:
            return (float(np.clip(p[0], 0.0, 1.0)), float(np.clip(p[1], 0.0, 1.0)))

        return PoseResult(
            left_shoulder=clamp(left_sh),
            right_shoulder=clamp(right_sh),
            head=clamp((head_x, head_y)),
            hips_center=clamp(hips_center),
            confidence=float(best.score[0]) if best.score else 0.5,
            source="face",
        )

    def close(self) -> None:
        self.pose_model.close()
        self.face_model.close()


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
                color = (0, 255, 0) if pose.source == "full" else (0, 200, 255)
                for label, pt in [
                    ("L_sh", pose.left_shoulder),
                    ("R_sh", pose.right_shoulder),
                    ("head", pose.head),
                    ("hips", pose.hips_center),
                ]:
                    x, y = int(pt[0] * w), int(pt[1] * h)
                    cv2.circle(preview, (x, y), 8, color, -1)
                    cv2.putText(preview, label, (x + 10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                cv2.putText(
                    preview,
                    f"source={pose.source} conf={pose.confidence:.2f}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2,
                )
            cv2.imshow("pose", preview)
            if cv2.waitKey(30) & 0xFF == ord("q"):
                break
    finally:
        pd.close()
        cam.stop()
        cv2.destroyAllWindows()
