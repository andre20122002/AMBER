"""ML-aging для фінального фото: викликається 1 раз при capture.

Стратегія:
  - Якщо `config.AGING_MODEL_PATH` існує і onnxruntime доступний → використати ONNX модель
  - Інакше → fallback на агресивну версію RealtimeAger (2× intensity)

Так модуль завжди працює, навіть без важкої ONNX моделі.
"""
import logging
from pathlib import Path

import numpy as np

import config
from aging_realtime import RealtimeAger
from pose import PoseResult

logger = logging.getLogger(__name__)


class MLAger:
    """Високоякісне старіння обличчя для фото-режиму (блокуюче, ~1-5с з ONNX)."""

    def __init__(self):
        self._onnx_session = None
        self._fallback = RealtimeAger(intensity_multiplier=1.8)  # агресивніше за real-time

        if config.AGING_ML_ENABLED and config.AGING_MODEL_PATH.exists():
            try:
                import onnxruntime as ort
                self._onnx_session = ort.InferenceSession(
                    str(config.AGING_MODEL_PATH),
                    providers=["CPUExecutionProvider"],
                )
                logger.info("ML aging: ONNX model loaded from %s", config.AGING_MODEL_PATH)
            except ImportError:
                logger.warning("onnxruntime not installed; using RealtimeAger fallback")
            except Exception as exc:
                logger.warning("ONNX model load failed (%s); using RealtimeAger fallback", exc)
        else:
            logger.info("ML aging: no ONNX model — using aggressive RealtimeAger fallback")

    def process(
        self,
        composite_bgr: np.ndarray,
        pose: PoseResult | None,
        age_offset: int,
    ) -> np.ndarray:
        """Повертає старішу версію composite. Блокуючий виклик.

        composite — це ВЖЕ зкомпонований кадр (з костюмом + фоном). face_landmarks
        у `pose` — у просторі ВХІДНОГО кадру камери, тож треба буде ремапати,
        але overlay вже зробив це. Тут ми працюємо у display-просторі.
        """
        if not config.AGING_ENABLED or pose is None or not pose.face_landmarks:
            return composite_bgr

        if self._onnx_session is not None:
            return self._process_onnx(composite_bgr, pose, age_offset)

        # Fallback: той самий RealtimeAger, але глибше
        # face_landmarks у composite вже remapped у display-простір (через overlay.compose)
        return self._fallback.apply(composite_bgr, pose.face_landmarks, age_offset)

    def _process_onnx(self, composite_bgr, pose, age_offset) -> np.ndarray:
        """Placeholder для майбутньої реальної моделі.

        Тут має бути:
        1. Витягнути face crop за bbox face_landmarks
        2. Resize до input size моделі (256×256 / 512×512)
        3. Run session.run(['output'], {'input': preprocessed})
        4. Postprocess, paste назад через alpha-маску по контуру обличчя
        """
        logger.warning("ONNX inference not implemented yet; using RealtimeAger fallback")
        return self._fallback.apply(composite_bgr, pose.face_landmarks, age_offset)
