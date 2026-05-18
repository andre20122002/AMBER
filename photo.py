"""Збереження фото на диск: data/photos/YYYY-MM-DD/photo_HHMMSS.png."""
import logging
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

import config

logger = logging.getLogger(__name__)


def save_photo(img_bgr: np.ndarray, base_dir: Path | None = None) -> Path:
    """Зберігає кадр як PNG і повертає шлях до файлу."""
    base = base_dir or config.PHOTOS_DIR
    now = datetime.now()
    day_dir = base / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    filename = f"photo_{now.strftime('%H%M%S')}.png"
    out_path = day_dir / filename

    ok = cv2.imwrite(str(out_path), img_bgr)
    if not ok:
        raise IOError(f"Failed to write photo: {out_path}")

    logger.info("Photo saved: %s", out_path)
    return out_path
