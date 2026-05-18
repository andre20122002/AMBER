"""QR-код генерація: URL → BGR numpy array, придатний для рендеру в pygame чи OpenCV."""
import logging

import numpy as np
import qrcode
from PIL import Image

logger = logging.getLogger(__name__)


def make_qr(url: str, box_size: int = 12, border: int = 2) -> np.ndarray:
    """Генерує QR-код як BGR numpy array.

    box_size: розмір одного «модуля» (квадратика) у пікселях.
    border: ширина білої рамки в модулях (стандарт ≥ 4, але 2 ок для kiosk).
    """
    qr = qrcode.QRCode(
        version=None,  # автодобір розміру
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img: Image.Image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    arr = np.array(img)  # (H, W, 3) RGB
    return arr[..., ::-1].copy()  # RGB → BGR
