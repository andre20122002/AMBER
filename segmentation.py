"""Сегментація фігури через MediaPipe SelfieSegmentation.

Повертає float32 [0..1] маску — БЕЗ бінаризації, для alpha-blending у overlay.py.
(Фікс B2: cv2.bitwise_and робив би blur безкорисним.)
"""
import logging

import cv2
import mediapipe as mp
import numpy as np

import config

logger = logging.getLogger(__name__)


class Segmenter:
    def __init__(self):
        mp_selfie = mp.solutions.selfie_segmentation
        self.model = mp_selfie.SelfieSegmentation(model_selection=1)
        logger.info("SelfieSegmentation model loaded (model_selection=1)")

    def get_mask(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Повертає float32 [0..1] маску, розмиту для м'яких країв."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        results = self.model.process(rgb)
        mask = results.segmentation_mask.astype(np.float32)
        mask = np.clip(mask, 0.0, 1.0)
        if config.MASK_BLUR_SIZE > 1:
            k = config.MASK_BLUR_SIZE | 1  # ядро має бути непарним
            mask = cv2.GaussianBlur(mask, (k, k), 0)
        return mask

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
    seg = Segmenter()

    try:
        while True:
            frame = cam.get_latest_frame()
            if frame is None:
                cv2.waitKey(10)
                continue
            mask = seg.get_mask(frame)
            preview = (mask * 255).astype(np.uint8)
            cv2.imshow("camera", frame)
            cv2.imshow("mask", preview)
            if cv2.waitKey(30) & 0xFF == ord("q"):
                break
    finally:
        seg.close()
        cam.stop()
        cv2.destroyAllWindows()
