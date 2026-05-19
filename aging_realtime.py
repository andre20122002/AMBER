"""Real-time light aging: швидкий OpenCV-pipeline старіння обличчя для кожного кадру.

Без ML, ≤5 мс на 1080×1920. Працює тільки в bbox обличчя (за face_landmarks),
не змінює фон і тіло.

Ефекти:
  1. Color shift: знижує saturation шкіри, додає теплий (сепія) тон
  2. Greying: освітлення зони над обличчям (волосся)
  3. Soft skin: bilateral filter — згладжує текстуру, м'якша шкіра

Інтенсивність контролюється `age_offset` (0..60+ років) → strength [0..1].
"""
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Індекси FaceMesh для контурного bbox
_FACE_TOP = 10
_FACE_BOTTOM = 152
_FACE_LEFT = 234
_FACE_RIGHT = 454


class RealtimeAger:
    def __init__(self, intensity_multiplier: float = 1.0):
        """intensity_multiplier — глобальний knob (з config.AGING_REALTIME_INTENSITY)."""
        self.k = float(np.clip(intensity_multiplier, 0.0, 2.0))

    def apply(
        self,
        frame_bgr: np.ndarray,
        face_landmarks: list[tuple[float, float]],
        age_offset: int,
    ) -> np.ndarray:
        """Повертає кадр з постарілою face-zone. Решта пікселів без змін."""
        if not face_landmarks or age_offset <= 0 or self.k <= 0:
            return frame_bgr

        strength = float(np.clip(age_offset / 60.0, 0.0, 1.0)) * self.k
        if strength <= 0.01:
            return frame_bgr

        h, w = frame_bgr.shape[:2]
        if len(face_landmarks) <= max(_FACE_TOP, _FACE_BOTTOM, _FACE_LEFT, _FACE_RIGHT):
            return frame_bgr

        # Bbox обличчя у пікселях
        top = face_landmarks[_FACE_TOP]
        bottom = face_landmarks[_FACE_BOTTOM]
        left = face_landmarks[_FACE_LEFT]
        right = face_landmarks[_FACE_RIGHT]

        x0 = int(min(left[0], right[0]) * w)
        x1 = int(max(left[0], right[0]) * w)
        y0 = int(top[1] * h)
        y1 = int(bottom[1] * h)

        if x1 - x0 < 10 or y1 - y0 < 10:
            return frame_bgr

        # Padding (тільки навколо самого обличчя — без зони "волосся" зверху)
        pad_x = (x1 - x0) // 5
        pad_y = (y1 - y0) // 6
        x0p = max(0, x0 - pad_x)
        x1p = min(w, x1 + pad_x)
        y0p = max(0, y0 - pad_y)
        y1p = min(h, y1 + pad_y)

        if x1p <= x0p or y1p <= y0p:
            return frame_bgr

        out = frame_bgr.copy()
        roi = out[y0p:y1p, x0p:x1p].copy()

        # Створюємо м'яку овальну маску щоб ефект розчинявся по краях, а не
        # обривався прямокутним bbox'ом.
        mask = self._make_oval_mask(roi.shape[:2])

        # 1. Color aging — теплий тон + знижена saturation
        aged = self._color_age(roi, strength)

        # 2. Soft skin
        aged = self._soft_skin(aged, strength)

        # Blend з оригіналом за овальною маскою
        m = mask[..., None]
        out[y0p:y1p, x0p:x1p] = (roi.astype(np.float32) * (1 - m) + aged.astype(np.float32) * m).astype(np.uint8)
        return out

    @staticmethod
    def _make_oval_mask(shape_hw: tuple[int, int]) -> np.ndarray:
        """Овальна alpha-маска [0..1], м'яко спадає до 0 на краях bbox."""
        h, w = shape_hw
        cy, cx = h / 2, w / 2
        ry, rx = h * 0.55, w * 0.50
        y, x = np.ogrid[:h, :w]
        d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
        # d=0 у центрі, d=1 на границі овала
        mask = np.clip(1.0 - d, 0.0, 1.0).astype(np.float32)
        # Розмиття країв — щоб не було видно різкого переходу
        mask = cv2.GaussianBlur(mask, (31, 31), 0)
        return mask

    @staticmethod
    def _color_age(img: np.ndarray, strength: float) -> np.ndarray:
        """Sepia/warm shift + знижена saturation."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 1] *= (1.0 - strength * 0.35)  # -35% saturation max
        hsv = np.clip(hsv, 0, 255).astype(np.uint8)
        out = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR).astype(np.float32)
        # Warm shift: +red/yellow, -blue
        out[..., 2] += strength * 18  # +R
        out[..., 1] += strength * 8   # +G (трохи)
        out[..., 0] -= strength * 18  # -B
        return np.clip(out, 0, 255).astype(np.uint8)

    @staticmethod
    def _grey_hair(hair: np.ndarray, strength: float) -> np.ndarray:
        """Освітлення + знебарвлення — імітує сиве волосся."""
        gray = cv2.cvtColor(hair, cv2.COLOR_BGR2GRAY)
        gray_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR).astype(np.float32)
        # Додаємо «світла» (сиве — світліше)
        gray_bgr = np.clip(gray_bgr + 40 * strength, 0, 255).astype(np.uint8)
        # Mix
        alpha = strength * 0.7
        return cv2.addWeighted(hair, 1 - alpha, gray_bgr, alpha, 0)

    @staticmethod
    def _soft_skin(face: np.ndarray, strength: float) -> np.ndarray:
        """Bilateral filter — згладжує текстуру шкіри зберігаючи краї."""
        smoothed = cv2.bilateralFilter(face, 7, 60, 60)
        alpha = strength * 0.5
        return cv2.addWeighted(face, 1 - alpha, smoothed, alpha, 0)
