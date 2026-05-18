"""Threaded camera capture з queue.Queue(maxsize=1) — головний потік ніколи не блокується.

Підтримує mock-режим (читання assets/dev/mock_frame.jpg у циклі) для розробки без камери.
"""
import logging
import queue
import threading
import time
from pathlib import Path

import cv2
import numpy as np

import config

logger = logging.getLogger(__name__)


class CameraThread(threading.Thread):
    def __init__(self, mock: bool = False):
        super().__init__(daemon=True)
        self.mock = mock
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._cap: cv2.VideoCapture | None = None
        self._mock_frame: np.ndarray | None = None

    def _open_camera(self) -> bool:
        self._cap = cv2.VideoCapture(config.CAMERA_INDEX)
        if not self._cap.isOpened():
            logger.error("Camera index %s could not be opened", config.CAMERA_INDEX)
            return False
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
        self._cap.set(cv2.CAP_PROP_FPS, config.TARGET_FPS)
        logger.info("Camera opened: %dx%d", config.FRAME_WIDTH, config.FRAME_HEIGHT)
        return True

    def _load_mock(self) -> bool:
        path: Path = config.MOCK_FRAME_PATH
        if not path.exists():
            logger.error("Mock frame not found: %s", path)
            return False
        img = cv2.imread(str(path))
        if img is None:
            logger.error("Mock frame could not be read: %s", path)
            return False
        self._mock_frame = cv2.resize(img, (config.FRAME_WIDTH, config.FRAME_HEIGHT))
        logger.info("Mock camera loaded from %s", path)
        return True

    def run(self) -> None:
        if self.mock:
            if not self._load_mock():
                self._stop_event.set()
                return
        else:
            if not self._open_camera():
                # retry loop: спробувати знову через 5 с, інакше main отримує None
                while not self._stop_event.is_set():
                    time.sleep(5.0)
                    if self._open_camera():
                        break

        frame_interval = 1.0 / config.TARGET_FPS
        while not self._stop_event.is_set():
            t0 = time.monotonic()
            if self.mock:
                frame = self._mock_frame.copy()
            else:
                ok, frame = self._cap.read()
                if not ok:
                    logger.warning("Camera read failed; retrying")
                    time.sleep(0.1)
                    continue

            # drop старого кадру, поклади новий
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put(frame)

            elapsed = time.monotonic() - t0
            sleep = frame_interval - elapsed
            if sleep > 0:
                time.sleep(sleep)

        if self._cap is not None:
            self._cap.release()
        logger.info("Camera thread stopped")

    def get_latest_frame(self) -> np.ndarray | None:
        """Non-blocking: повертає останній кадр або None, якщо ще немає."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def stop(self) -> None:
        self._stop_event.set()


if __name__ == "__main__":
    # Smoke test: показуємо live preview у вікні OpenCV
    import sys
    from logging_setup import setup_logging
    setup_logging()

    mock = "--mock" in sys.argv
    cam = CameraThread(mock=mock)
    cam.start()

    try:
        while True:
            frame = cam.get_latest_frame()
            if frame is not None:
                cv2.imshow("camera preview (q to quit)", frame)
            if cv2.waitKey(30) & 0xFF == ord("q"):
                break
    finally:
        cam.stop()
        cv2.destroyAllWindows()
