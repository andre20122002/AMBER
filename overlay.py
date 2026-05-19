"""Композиція кадру → фінальне зображення для дисплея.

Виправлення з аудиту:
  B1: композиція в просторі ДИСПЛЕЯ (1080×1920), не в просторі кадру (1280×720).
  B2: alpha-blending через float-маску, не bitwise_and.
  G8: center-crop кадру 16:9 → 9:16 перед композицією.
  G1: auto-fit костюма за pose (масштаб + зсув + ротація плечей).
"""
import logging
import math

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


def _fit_costume_to_pose(
    costume_rgba: np.ndarray,
    pose: PoseResult | None,
    anchor_cy: float = COSTUME_DESIGN_SHOULDERS_CY,
    anchor_w: float = COSTUME_DESIGN_SHOULDERS_W,
) -> tuple[np.ndarray, dict]:
    """Affine warp костюма так, щоб дизайн-плечі збігалися з реальними.

    Повертає (warped, info), де info містить параметри warp'у для debug overlay:
      {'scale': float, 'angle_deg': float, 'dst_x': int, 'dst_y': int}
    """
    H, W = costume_rgba.shape[:2]

    if pose is None:
        target_cx = DEFAULT_SHOULDERS_CX
        target_cy = DEFAULT_SHOULDERS_CY
        target_w = DEFAULT_SHOULDERS_W
        angle_deg = 0.0
    else:
        target_cx, target_cy = pose.shoulders_center
        target_w = max(pose.shoulders_width, 0.1)
        # Кут нахилу плечей (вектор left → right). У дзеркальному кадрі
        # left.x < right.x, тож горизонтальні плечі → angle ≈ 0.
        dx = pose.right_shoulder[0] - pose.left_shoulder[0]
        dy = pose.right_shoulder[1] - pose.left_shoulder[1]
        angle_rad = math.atan2(dy, dx)
        angle_deg = math.degrees(angle_rad)
        # Clamp ±25°: захист від pose-glitch (різкі стрибки кутів)
        angle_deg = float(np.clip(angle_deg, -25.0, 25.0))

    scale = target_w / anchor_w
    scale = float(np.clip(scale, 0.5, 2.0))

    # Anchor у пікселях канвасу костюма (симетричний по X)
    src_x = 0.5 * W
    src_y = anchor_cy * H

    dst_x = target_cx * W
    dst_y = target_cy * H

    # Повна affine: scale + rotate навколо src, потім translate src → dst
    M = cv2.getRotationMatrix2D((src_x, src_y), -angle_deg, scale)
    # getRotationMatrix2D обертає навколо center, тримає center на місці.
    # Додаємо translation, щоб center перейшов з (src_x, src_y) у (dst_x, dst_y):
    M[0, 2] += dst_x - src_x
    M[1, 2] += dst_y - src_y

    warped = cv2.warpAffine(
        costume_rgba, M, (W, H),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    info = {
        "scale": scale,
        "angle_deg": angle_deg,
        "dst_x": int(dst_x),
        "dst_y": int(dst_y),
    }
    return warped, info


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
    debug: bool = False,
    fps: float | None = None,
) -> np.ndarray:
    """Повертає BGR-зображення (DISPLAY_H × DISPLAY_W × 3) готове до рендеру в pygame."""
    W, H = config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT

    # 1. Center-crop кадру та маски з 16:9 → 9:16, ресайз до DISPLAY
    frame_disp = center_crop_to_aspect(frame_bgr, W, H)
    mask_disp = center_crop_to_aspect(mask_float, W, H)

    # 2. Alpha-blend фігури на фоні ролі
    alpha = mask_disp[..., None]
    composite = (
        role.background_bgr.astype(np.float32) * (1.0 - alpha)
        + frame_disp.astype(np.float32) * alpha
    ).astype(np.uint8)

    # 3. Auto-fit костюма за pose. Pose координати в просторі вхідного кадру,
    # перенормалізуємо в простір display після center-crop'у.
    pose_in_display = _remap_pose_to_display(pose, frame_bgr.shape[:2], (H, W))
    anchor_cy = getattr(role, "anchor_cy", COSTUME_DESIGN_SHOULDERS_CY)
    anchor_w = getattr(role, "anchor_w", COSTUME_DESIGN_SHOULDERS_W)
    costume, warp_info = _fit_costume_to_pose(role.costume_rgba, pose_in_display, anchor_cy, anchor_w)
    composite = _alpha_paste_rgba_over_bgr(composite, costume)

    # 4. Текст
    composite = _draw_text_overlay(composite, role)

    # 5. Debug overlay (поверх всього)
    if debug:
        composite = _draw_debug_overlay(composite, pose_in_display, warp_info, fps)

    return composite


def _draw_debug_overlay(
    img_bgr: np.ndarray,
    pose: PoseResult | None,
    warp_info: dict,
    fps: float | None,
) -> np.ndarray:
    """Малює landmarks, anchor point, текстову інформацію поверх композиту."""
    H, W = img_bgr.shape[:2]
    out = img_bgr.copy()

    source_color = {
        "full": (0, 255, 0),    # зелений
        "face": (0, 200, 255),  # помаранчевий
        "hold": (180, 180, 180),  # сірий
    }

    if pose is not None:
        color = source_color.get(pose.source, (0, 255, 0))
        for label, pt in [
            ("L_sh", pose.left_shoulder),
            ("R_sh", pose.right_shoulder),
            ("head", pose.head),
            ("hips", pose.hips_center),
        ]:
            x, y = int(pt[0] * W), int(pt[1] * H)
            cv2.circle(out, (x, y), 12, color, -1)
            cv2.circle(out, (x, y), 14, (0, 0, 0), 2)
            cv2.putText(out, label, (x + 18, y + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # Лінія між плечима (видно ротацію)
        lx, ly = int(pose.left_shoulder[0] * W), int(pose.left_shoulder[1] * H)
        rx, ry = int(pose.right_shoulder[0] * W), int(pose.right_shoulder[1] * H)
        cv2.line(out, (lx, ly), (rx, ry), color, 3)

    # Anchor (де у display сидить дизайн-плече костюма)
    ax, ay = warp_info["dst_x"], warp_info["dst_y"]
    cv2.drawMarker(out, (ax, ay), (0, 0, 255), cv2.MARKER_CROSS, 30, 3)

    # Текстова інформація — верхній лівий кут
    lines = []
    if pose is not None:
        lines.append(f"source={pose.source}  conf={pose.confidence:.2f}")
    else:
        lines.append("pose=None")
    lines.append(f"scale={warp_info['scale']:.2f}  angle={warp_info['angle_deg']:+.1f}°")
    if fps is not None:
        lines.append(f"FPS={fps:.1f}")

    y0 = 50
    for i, line in enumerate(lines):
        y = y0 + i * 40
        cv2.putText(out, line, (22, y + 2), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4)
        cv2.putText(out, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

    return out


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
