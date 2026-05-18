"""Генерує placeholder-графіку: 3 ролі + mock-кадр + структуру папок.

НЕ замінює фінальний дизайн — це для розробки і первинного тестування.
Шрифт Inter-Regular.ttf треба завантажити окремо з https://rsms.me/inter/
(або скрипт використає системний default — буде менш красиво).

Запуск:
    python generate_placeholders.py
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config

# Дизайн-константи мають збігатися з overlay.py
DESIGN_SHOULDERS_CY = 0.28
DESIGN_SHOULDERS_W = 0.45

ROLES_DATA = [
    {
        "id": "president",
        "title": "Президент України",
        "year": 2045,
        "slogan": "Ти можеш стати тим, хто змінить країну",
        "button_label": "Президент",
        "bg_color": (28, 50, 120),       # синій
        "costume_color": (40, 40, 60, 230),
        "accent_color": (255, 215, 80, 255),
    },
    {
        "id": "scientist",
        "title": "Науковець",
        "year": 2050,
        "slogan": "Твої відкриття — це майбутнє людства",
        "button_label": "Науковець",
        "bg_color": (40, 100, 90),       # зелено-бірюзовий
        "costume_color": (240, 240, 240, 235),
        "accent_color": (100, 200, 255, 255),
    },
    {
        "id": "diplomat",
        "title": "Дипломат ООН",
        "year": 2055,
        "slogan": "Ти будуєш мости між народами",
        "button_label": "Дипломат",
        "bg_color": (90, 60, 110),       # фіолетовий
        "costume_color": (50, 60, 80, 230),
        "accent_color": (220, 180, 100, 255),
    },
]

W, H = config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT


def _get_font(size: int) -> ImageFont.ImageFont:
    if config.FONT_PATH.exists():
        return ImageFont.truetype(str(config.FONT_PATH), size)
    return ImageFont.load_default()


def make_background(role_data: dict, out_path: Path) -> None:
    """Простий градієнт + назва ролі великим текстом унизу як «декорація»."""
    img = Image.new("RGB", (W, H), role_data["bg_color"])
    draw = ImageDraw.Draw(img)

    # Градієнт згори донизу (затемнення)
    for y in range(H):
        t = y / H
        r = int(role_data["bg_color"][0] * (1 - 0.5 * t))
        g = int(role_data["bg_color"][1] * (1 - 0.5 * t))
        b = int(role_data["bg_color"][2] * (1 - 0.5 * t))
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Декоративні «промені»
    cx, cy = W // 2, int(H * 0.15)
    for angle in range(0, 360, 15):
        rad = angle * 3.14159 / 180
        x2 = cx + int(2000 * np.cos(rad))
        y2 = cy + int(2000 * np.sin(rad))
        draw.line([(cx, cy), (x2, y2)], fill=(*role_data["accent_color"][:3], 60), width=2)

    img.save(out_path, "JPEG", quality=85)


def make_costume(role_data: dict, out_path: Path) -> None:
    """PNG RGBA: верхня частина — «капелюх/декорація», середина прозора (там буде людина),
    низ — силует плечей з кольором ролі.

    Дизайн узгоджений з COSTUME_DESIGN_SHOULDERS_CY=0.28, _W=0.45.
    """
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    accent = role_data["accent_color"]
    costume_col = role_data["costume_color"]

    # «Капелюх/корона» — еліпс зверху
    hat_cy = int(H * 0.08)
    hat_w = int(W * 0.35)
    hat_h = int(H * 0.05)
    draw.ellipse(
        [W // 2 - hat_w // 2, hat_cy - hat_h, W // 2 + hat_w // 2, hat_cy + hat_h],
        fill=accent,
    )

    # «Плечі» — трапеція з центром на (0.5, 0.28) і шириною 0.45*W
    sh_cy = int(H * DESIGN_SHOULDERS_CY)
    sh_w = int(W * DESIGN_SHOULDERS_W)
    sh_left = W // 2 - sh_w // 2
    sh_right = W // 2 + sh_w // 2
    # Трапеція вниз (плечі → пояс)
    waist_w = int(sh_w * 0.7)
    waist_cy = int(H * 0.85)
    waist_left = W // 2 - waist_w // 2
    waist_right = W // 2 + waist_w // 2
    draw.polygon(
        [(sh_left, sh_cy), (sh_right, sh_cy), (waist_right, waist_cy), (waist_left, waist_cy)],
        fill=costume_col,
    )

    # Комір
    collar_y = sh_cy
    collar_w = int(W * 0.12)
    draw.polygon(
        [
            (W // 2 - collar_w, collar_y),
            (W // 2 + collar_w, collar_y),
            (W // 2, collar_y + int(H * 0.08)),
        ],
        fill=accent,
    )

    # Декоративна стрічка (як орденська)
    ribbon_y1 = sh_cy + int(H * 0.05)
    ribbon_y2 = sh_cy + int(H * 0.20)
    ribbon_x1 = W // 2 - int(W * 0.04)
    ribbon_x2 = W // 2 + int(W * 0.04)
    draw.rectangle([ribbon_x1, ribbon_y1, ribbon_x2, ribbon_y2], fill=accent)

    # Лейбл «PLACEHOLDER» дрібним текстом у куті
    font = _get_font(28)
    draw.text((20, H - 60), f"placeholder: {role_data['id']}", font=font, fill=(255, 255, 255, 180))

    img.save(out_path, "PNG")


def make_meta(role_data: dict, out_path: Path) -> None:
    meta = {k: role_data[k] for k in ("id", "title", "year", "slogan", "button_label")}
    out_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def make_mock_frame(out_path: Path) -> None:
    """Простий «кадр з камери» 1280×720: градієнт + силует людини по центру."""
    fw, fh = config.FRAME_WIDTH, config.FRAME_HEIGHT
    img = Image.new("RGB", (fw, fh), (180, 200, 220))
    draw = ImageDraw.Draw(img)

    # Градієнт-фон
    for y in range(fh):
        t = y / fh
        r = int(180 - 60 * t)
        g = int(200 - 80 * t)
        b = int(220 - 100 * t)
        draw.line([(0, y), (fw, y)], fill=(r, g, b))

    # Силует людини (тіло + голова) — як суцільна темна форма
    cx = fw // 2
    head_r = int(fh * 0.10)
    head_cy = int(fh * 0.25)
    draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill=(60, 50, 50))

    body_top = head_cy + head_r - 10
    body_w = int(fh * 0.35)
    draw.polygon(
        [
            (cx - body_w // 2, fh),
            (cx + body_w // 2, fh),
            (cx + int(body_w * 0.6), body_top),
            (cx - int(body_w * 0.6), body_top),
        ],
        fill=(70, 60, 70),
    )

    img.save(out_path, "JPEG", quality=90)


def make_idle_bg(out_path: Path) -> None:
    img = Image.new("RGB", (W, H), (15, 25, 45))
    draw = ImageDraw.Draw(img)
    # Радіальний градієнт-імітація
    for r in range(min(W, H) // 2, 0, -10):
        alpha = 1.0 - r / (min(W, H) / 2)
        v = int(40 + 60 * alpha)
        draw.ellipse(
            [W // 2 - r, H // 2 - r, W // 2 + r, H // 2 + r],
            outline=(v, v // 2 + 20, v + 40),
            width=3,
        )
    img.save(out_path, "JPEG", quality=85)


def main() -> None:
    config.ROLES_DIR.mkdir(parents=True, exist_ok=True)
    config.DEV_DIR.mkdir(parents=True, exist_ok=True)
    config.UI_DIR.mkdir(parents=True, exist_ok=True)
    (config.UI_DIR / "fonts").mkdir(parents=True, exist_ok=True)

    if not config.FONT_PATH.exists():
        print(f"!! Шрифт {config.FONT_PATH} не знайдено.")
        print("   Завантаж Inter-Regular.ttf з https://rsms.me/inter/ і поклади за вказаним шляхом.")
        print("   Поки що використається системний default — кирилиця може погано рендеритись.\n")

    for rd in ROLES_DATA:
        role_dir = config.ROLES_DIR / rd["id"]
        role_dir.mkdir(parents=True, exist_ok=True)
        make_background(rd, role_dir / "background.jpg")
        make_costume(rd, role_dir / "costume.png")
        make_meta(rd, role_dir / "meta.json")
        print(f"Created role: {rd['id']}")

    make_mock_frame(config.MOCK_FRAME_PATH)
    print(f"Created mock frame: {config.MOCK_FRAME_PATH}")

    make_idle_bg(config.IDLE_BG_PATH)
    print(f"Created idle background: {config.IDLE_BG_PATH}")

    print("\nDone. Run with: python main.py --mock --windowed")


if __name__ == "__main__":
    main()
