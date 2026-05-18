"""Композиція кадру → фінальне зображення для дисплея.

Виправлення з аудиту:
  B1: композиція в просторі ДИСПЛЕЯ (1080×1920), не в просторі кадру (1280×720).
  B2: alpha-blending через float-маску, не bitwise_and.
  G8: center-crop кадру 16:9 → 9:16 перед композицією.
  G1: auto-fit костюма за pose (масштаб + зсув від плечей).
"""
import logging

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config
from pose import PoseResult
from roles import Role

logger = logging.getLogger(__name__)

# Параметри дизайну костюма: де (у нормалізованих координатах) на canvas 1080×1920
# намальовані плечі і яка їх ширина.
# Якщо костюми будуть інші — змінити тут (або винести в meta.json як override).
COSTUME_DESIGN_SHOULDERS_CY = 0.28   # y центру плечей костюма (28% від верху)
COSTUME_DESIGN_SHOULDERS_W = 0.45    # ширина плечей костюма (45% ширини canvas)

# Дефолтна позиція, якщо pose не визначений
DEFAULT_SHOULDERS_CX = 0.5
DEFAULT_SHOULDERS_CY = 0.30
DEFAULT_SHOULDERS_W = 0.40

# Шрифт кешуємо на рівні модуля
_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _FONT_CACHE:
        if config.FONT_PATH.exists():
            _FONT_CACHE[size] = ImageFont.truetype(str(config.FONT_PATH), size)
        else:
            logger.warning("Font not found at %s, using PIL default", config.FONT_PATH)
            _FONT_CACHE[size] = ImageFont.load_default()
    return _FONT_CACHE[size]


def center_crop_to_aspect(img: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """Center-crop зображення до aspect ratio target_w:target_h, потім ресайз.

    Працює і для BGR (H,W,3), і для float маски (H,W).
    """
    src_h, src_w = img.shape[:2]
    target_aspect = target_w / target_h
    src_aspect = src_w / src_h

    if src_aspect > target_aspect:
        # Джерело ширше — обрізаємо боки
        new_w = int(src_h * target_aspect)
        x0 = (src_w - new_w) // 2
        cropped = img[:, x0:x0 + new_w]
    else:
        # Джерело вище — обрізаємо верх/низ
        new_h = int(src_w / target_aspect)
        y0 = (src_h - new_h) // 2
        cropped = img[y0:y0 + new_h, :]

    interp = cv2.INTER_LINEAR if img.dtype == np.float32 else cv2.INTER_AREA
    return cv2.resize(cropped, (target_w, target_h), interpolation=interp)


def _fit_costume_to_pose(costume_rgba: np.ndarray, pose: PoseResult | None) -> np.ndarray:
    """Affine warp костюма так, щоб дизайн-плечі збігалися з реальними плечима.

    Костюм має ту саму розмірність, що й DISPLAY (попередньо ресайзнутий у RoleManager).
    Якщо pose=None, повертаємо костюм без змін (у дефолтній позиції).
    """
    H, W = costume_rgba.shape[:2]

    if pose is None:
        target_cx = DEFAULT_SHOULDERS_CX
        target_cy = DEFAULT_SHOULDERS_CY
        target_w = DEFAULT_SHOULDERS_W
    else:
        target_cx, target_cy = pose.shoulders_center
        target_w = max(pose.shoulders_width, 0.1)  # avoid divide-by-zero

    scale = target_w / COSTUME_DESIGN_SHOULDERS_W
    # обмеження, щоб уникнути екстремального скейлу
    scale = float(np.clip(scale, 0.5, 2.0))

    # Координати точки відліку (плечі) у пікселях канвасу костюма (симетричний)
    src_x = 0.5 * W
    src_y = COSTUME_DESIGN_SHOULDERS_CY * H

    dst_x = target_cx * W
    dst_y = target_cy * H

    # Affine: масштабуємо навколо src, потім транслюємо так, щоб src перейшло в dst
    M = np.array([
        [scale, 0, dst_x - src_x * scale],
        [0, scale, dst_y - src_y * scale],
    ], dtype=np.float32)

    warped = cv2.warpAffine(
        costume_rgba, M, (W, H),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    return warped


def _alpha_paste_rgba_over_bgr(bgr: np.ndarray, rgba: np.ndarray) -> np.ndarray:
    """Накладає RGBA на BGR через alpha-канал. Розміри мають збігатися."""
    alpha = (rgba[..., 3:4].astype(np.float32)) / 255.0  # (H,W,1)
    # rgba — RGB, треба переставити в BGR щоб збігалося з background
    rgb = rgba[..., :3]
    bgr_layer = rgb[..., ::-1]  # RGB → BGR
    result = bgr.astype(np.float32) * (1.0 - alpha) + bgr_layer.astype(np.float32) * alpha
    return result.astype(np.uint8)


def _draw_text_overlay(img_bgr: np.ndarray, role: Role) -> np.ndarray:
    """Малює title / year / slogan через PIL для коректної підтримки кирилиці."""
    pil = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)

    W, H = pil.size
    title_font = _get_font(72)
    year_font = _get_font(56)
    slogan_font = _get_font(40)

    # Title — внизу екрана, з тінню
    title = role.title
    year = str(role.year)
    slogan = role.slogan

    # Простий drop-shadow: чорний текст зі зміщенням +2,+2
    def text_with_shadow(xy, text, font, fill=(255, 255, 255)):
        x, y = xy
        draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 200))
        draw.text((x, y), text, font=font, fill=fill)

    # Year — зверху по центру
    bbox = draw.textbbox((0, 0), year, font=year_font)
    year_w = bbox[2] - bbox[0]
    text_with_shadow(((W - year_w) // 2, int(H * 0.05)), year, year_font, fill=(255, 230, 100))

    # Title — внизу
    bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = bbox[2] - bbox[0]
    text_with_shadow(((W - title_w) // 2, int(H * 0.82)), title, title_font)

    # Slogan — нижче title
    bbox = draw.textbbox((0, 0), slogan, font=slogan_font)
    slogan_w = bbox[2] - bbox[0]
    text_with_shadow(((W - slogan_w) // 2, int(H * 0.92)), slogan, slogan_font, fill=(220, 220, 220))

    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def compose(
    frame_bgr: np.ndarray,
    mask_float: np.ndarray,
    role: Role,
    pose: PoseResult | None,
) -> np.ndarray:
    """Повертає BGR-зображення (DISPLAY_H × DISPLAY_W × 3) готове до рендеру в pygame."""
    W, H = config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT

    # 1. Center-crop кадру та маски з 16:9 → 9:16, ресайз до DISPLAY
    frame_disp = center_crop_to_aspect(frame_bgr, W, H)
    mask_disp = center_crop_to_aspect(mask_float, W, H)

    # 2. Alpha-blend фігури на фоні ролі
    alpha = mask_disp[..., None]  # (H, W, 1) float32
    composite = (
        role.background_bgr.astype(np.float32) * (1.0 - alpha)
        + frame_disp.astype(np.float32) * alpha
    ).astype(np.uint8)

    # 3. Auto-fit костюма за pose, накладаємо через alpha-канал
    # Pose координати — у просторі ВХІДНОГО кадру камери. Після center-crop'у та ресайзу
    # вони можуть зсунутися. Робимо пере-нормалізацію.
    pose_in_display = _remap_pose_to_display(pose, frame_bgr.shape[:2], (H, W))
    costume = _fit_costume_to_pose(role.costume_rgba, pose_in_display)
    composite = _alpha_paste_rgba_over_bgr(composite, costume)

    # 4. Текст
    composite = _draw_text_overlay(composite, role)
    return composite


def _remap_pose_to_display(
    pose: PoseResult | None,
    src_hw: tuple[int, int],
    dst_hw: tuple[int, int],
) -> PoseResult | None:
    """Перенормалізує координати pose з простору камери в простір дисплея після center-crop."""
    if pose is None:
        return None

    src_h, src_w = src_hw
    dst_h, dst_w = dst_hw
    target_aspect = dst_w / dst_h
    src_aspect = src_w / src_h

    def remap(x: float, y: float) -> tuple[float, float]:
        # Перевести нормалізовані координати в піксельні (відносно вхідного кадру)
        px = x * src_w
        py = y * src_h
        # Обчислити, який саме crop ми робили
        if src_aspect > target_aspect:
            new_w = int(src_h * target_aspect)
            x0 = (src_w - new_w) // 2
            px -= x0
            new_h_after_crop = src_h
            new_w_after_crop = new_w
        else:
            new_h = int(src_w / target_aspect)
            y0 = (src_h - new_h) // 2
            py -= y0
            new_h_after_crop = new_h
            new_w_after_crop = src_w
        # Тепер нормалізувати назад у [0..1] відносно cropped + ресайзнутого = dst
        return (px / new_w_after_crop, py / new_h_after_crop)

    return PoseResult(
        left_shoulder=remap(*pose.left_shoulder),
        right_shoulder=remap(*pose.right_shoulder),
        head=remap(*pose.head),
        hips_center=remap(*pose.hips_center),
        confidence=pose.confidence,
    )
