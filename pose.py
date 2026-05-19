"""Pose + Face + Hands детекція через MediaPipe Holistic.

Holistic дає одним проходом:
  - 33 pose landmarks (тіло)
  - 468 face landmarks (FaceMesh)
  - 21 + 21 = 42 hand landmarks
  ─────────────────────────────
  Разом ≈ 543 точки по всьому тілу.

PoseResult зберігає:
  - 4 ключові точки (left_sh, right_sh, head, hips_center) для overlay/smoothing
  - all_landmarks (повний список) для debug-візуалізації
"""
import logging
from dataclasses import dataclass, field
from typing import Literal

import cv2
import mediapipe as mp
import numpy as np

import config

logger = logging.getLogger(__name__)

# Pose індекси
_NOSE = 0
_LEFT_SHOULDER = 11
_RIGHT_SHOULDER = 12
_LEFT_HIP = 23
_RIGHT_HIP = 24

# FaceMesh індекси для контурного bbox
_FACE_TOP = 10
_FACE_BOTTOM = 152
_FACE_LEFT = 234
_FACE_RIGHT = 454
_FACE_NOSE = 1

PoseSource = Literal["full", "face", "hold"]


@dataclass
class PoseResult:
    """Уніфікований результат для overlay/smoothing.

    Нормалізовані координати [0..1] відносно вхідного кадру.
    """
    left_shoulder: tuple[float, float]
    right_shoulder: tuple[float, float]
    head: tuple[float, float]
    hips_center: tuple[float, float]
    confidence: float
    source: PoseSource = "full"
    # Всі landmarks для debug-візуалізації: list[(x, y)] у нормалізованих координатах
    all_landmarks: list[tuple[float, float]] = field(default_factory=list)

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


def _collect_all_landmarks(results) -> list[tuple[float, float]]:
    """Збирає всі landmarks (pose + face + hands) в один list для debug."""
    out: list[tuple[float, float]] = []
    if results.pose_landmarks:
        out.extend((lm.x, lm.y) for lm in results.pose_landmarks.landmark)
    if results.face_landmarks:
        out.extend((lm.x, lm.y) for lm in results.face_landmarks.landmark)
    if results.left_hand_landmarks:
        out.extend((lm.x, lm.y) for lm in results.left_hand_landmarks.landmark)
    if results.right_hand_landmarks:
        out.extend((lm.x, lm.y) for lm in results.right_hand_landmarks.landmark)
    return out


class PoseDetector:
    def __init__(self):
        mp_holistic = mp.solutions.holistic
        self.model = mp_holistic.Holistic(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            refine_face_landmarks=False,  # False: 468 точок; True: 478 (з iris) — повільніше
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        logger.info("Holistic model loaded (pose+face+hands)")

    def detect(self, frame_bgr: np.ndarray) -> PoseResult | None:
        """Розумне об'єднання pose + face з пріоритетом за умовами."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        results = self.model.process(rgb)
        all_lms = _collect_all_landmarks(results)

        # Face-pose з FaceMesh (якщо є)
        face_pose = self._face_pose_from_mesh(results, all_lms)

        # Якщо face займає >20% ширини кадру — це close-up, trust face
        # (pose дає галюцинації плечей коли торса не видно)
        if face_pose is not None and self._face_bbox_width(face_pose) > 0.20:
            return face_pose

        # Спроба повного pose
        full_pose = self._full_pose_from_results(results, all_lms)
        if full_pose is not None:
            return full_pose

        # Fallback на face (якщо є)
        return face_pose

    def _full_pose_from_results(self, results, all_lms: list) -> PoseResult | None:
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

        # Sanity-check: на close-up pose галюцинує плечі через увесь кадр
        sh_width = float(np.hypot(left_sh[0] - right_sh[0], left_sh[1] - right_sh[1]))
        if sh_width > 0.75:
            return None
        if head[1] < 0.05:
            return None

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
            all_landmarks=all_lms,
        )

    def _face_pose_from_mesh(self, results, all_lms: list) -> PoseResult | None:
        """Будує уявні плечі/тіло з FaceMesh-контуру обличчя."""
        if not results.face_landmarks:
            return None

        face = results.face_landmarks.landmark
        top = face[_FACE_TOP]
        bottom = face[_FACE_BOTTOM]
        left = face[_FACE_LEFT]
        right = face[_FACE_RIGHT]
        nose = face[_FACE_NOSE]

        # bbox обличчя
        x = min(left.x, right.x)
        y = top.y
        w = abs(right.x - left.x)
        h = abs(bottom.y - top.y)

        # Уявні плечі: на 1.8 висоти обличчя нижче, шириною 2.5x ширини обличчя.
        # АЛЕ clamp до 0.85 по Y — щоб костюм-комір не «приклеювався» до низу кадру
        # коли обличчя близько (тоді shoulders розрахункові поза кадром).
        sh_cx = x + w / 2
        sh_cy = min(y + h * 1.8, 0.85)
        sh_half_w = w * 1.25
        # left = менший X (convention як у MediaPipe Pose)
        left_sh = (sh_cx - sh_half_w, sh_cy)
        right_sh = (sh_cx + sh_half_w, sh_cy)

        hips_y = min(sh_cy + h * 1.5, 0.98)
        hips_center = (sh_cx, hips_y)

        def clamp(p: tuple[float, float]) -> tuple[float, float]:
            return (float(np.clip(p[0], 0.0, 1.0)), float(np.clip(p[1], 0.0, 1.0)))

        return PoseResult(
            left_shoulder=clamp(left_sh),
            right_shoulder=clamp(right_sh),
            head=clamp((nose.x, nose.y)),
            hips_center=clamp(hips_center),
            confidence=0.9,  # FaceMesh не дає score, але якщо знайдено — впевнено
            source="face",
            all_landmarks=all_lms,
        )

    @staticmethod
    def _face_bbox_width(face_pose: PoseResult) -> float:
        """face_bbox_width ≈ shoulders_width / 2.5 (бо плечі генерувались як face_w * 2.5)."""
        sh_width = abs(face_pose.right_shoulder[0] - face_pose.left_shoulder[0])
        return sh_width / 2.5

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
                # Малюємо всі landmarks
                for (lx, ly) in pose.all_landmarks:
                    px, py = int(lx * w), int(ly * h)
                    cv2.circle(preview, (px, py), 1, (0, 255, 255), -1)
                # Ключові підкреслено
                color = (0, 255, 0) if pose.source == "full" else (0, 200, 255)
                for label, pt in [
                    ("L_sh", pose.left_shoulder),
                    ("R_sh", pose.right_shoulder),
                    ("head", pose.head),
                    ("hips", pose.hips_center),
                ]:
                    x, y = int(pt[0] * w), int(pt[1] * h)
                    cv2.circle(preview, (x, y), 8, color, -1)
                cv2.putText(
                    preview,
                    f"source={pose.source} N={len(pose.all_landmarks)}",
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
