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
from PIL import Image, ImageDraw, ImageFilter, ImageFont

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
        "age_offset": 25,
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
        "age_offset": 40,
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
        "age_offset": 30,
    },
]

W, H = config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT


def _get_font(size: int) -> ImageFont.ImageFont:
    if config.FONT_PATH.exists():
        return ImageFont.truetype(str(config.FONT_PATH), size)
    return ImageFont.load_default()


def _vertical_gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    """Швидкий вертикальний градієнт через numpy."""
    t = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    top_arr = np.array(top, dtype=np.float32)
    bot_arr = np.array(bottom, dtype=np.float32)
    col = top_arr * (1 - t) + bot_arr * t
    arr = np.tile(col[:, None, :], (1, w, 1)).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def _add_noise(img: Image.Image, amount: int = 8) -> Image.Image:
    """Дрібний шум поверх — імітує текстуру/фотозернистість."""
    arr = np.array(img, dtype=np.int16)
    noise = np.random.randint(-amount, amount + 1, arr.shape, dtype=np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def _bg_president(out_path: Path) -> None:
    """Інтер'єр кабінету: темно-сині панелі знизу, м'яке тепле світло зверху."""
    img = _vertical_gradient(W, H, (45, 55, 90), (15, 22, 40))
    draw = ImageDraw.Draw(img, "RGBA")
    # Вертикальні дерев'яні панелі знизу
    panel_top = int(H * 0.45)
    panel_w = W // 6
    for i in range(7):
        x = i * panel_w
        col = (28, 32, 50) if i % 2 == 0 else (35, 40, 60)
        draw.rectangle([x, panel_top, x + panel_w, H], fill=col)
        # Тонка лінія між панелями
        draw.line([(x, panel_top), (x, H)], fill=(15, 18, 28), width=2)
    # Горизонтальна планка над панелями
    draw.rectangle([0, panel_top - 8, W, panel_top + 4], fill=(60, 50, 30))
    # М'яке тепле "сяйво" зверху-центру (як від люстри)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for r in range(int(H * 0.4), 0, -20):
        a = int(60 * (1 - r / (H * 0.4)))
        gd.ellipse([W // 2 - r, int(H * 0.1) - r // 2, W // 2 + r, int(H * 0.1) + r // 2],
                   fill=(255, 220, 150, a))
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    img = _add_noise(img, 5)
    img.save(out_path, "JPEG", quality=88)


def _bg_scientist(out_path: Path) -> None:
    """Лабораторія: холодний синьо-зелений, ледь видна сітка/світло від моніторів."""
    img = _vertical_gradient(W, H, (30, 60, 70), (10, 25, 35))
    draw = ImageDraw.Draw(img, "RGBA")
    # Сітка scientific HUD
    grid_col = (90, 180, 200, 50)
    for x in range(0, W, 80):
        draw.line([(x, 0), (x, H)], fill=grid_col, width=1)
    for y in range(0, H, 80):
        draw.line([(0, y), (W, y)], fill=grid_col, width=1)
    # Холодні відблиски (як від моніторів) ліворуч-знизу і праворуч-знизу
    for side_x in (int(W * 0.2), int(W * 0.8)):
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for r in range(int(H * 0.3), 0, -15):
            a = int(50 * (1 - r / (H * 0.3)))
            gd.ellipse([side_x - r, int(H * 0.7) - r // 2, side_x + r, int(H * 0.7) + r // 2],
                       fill=(80, 200, 230, a))
        glow = glow.filter(ImageFilter.GaussianBlur(30))
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    img = _add_noise(img, 4)
    img.save(out_path, "JPEG", quality=88)


def _bg_diplomat(out_path: Path) -> None:
    """Зал ООН: тепле бежеве світло зверху, темно-сірі панелі знизу, золоті акценти."""
    img = _vertical_gradient(W, H, (90, 75, 50), (25, 25, 30))
    draw = ImageDraw.Draw(img, "RGBA")
    # Горизонтальні золоті полоси (як облицювання трибуни)
    for i, y in enumerate([int(H * 0.55), int(H * 0.62), int(H * 0.69)]):
        draw.rectangle([0, y, W, y + 4], fill=(180, 140, 80))
    # Нижня темна панель — трибуна
    draw.rectangle([0, int(H * 0.75), W, H], fill=(35, 30, 35))
    # Великий "герб" — золотий вінок-коло за фігурою
    cx, cy = W // 2, int(H * 0.35)
    for r in (int(W * 0.32), int(W * 0.30)):
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(180, 140, 80), width=4)
    # Лаврові «риски» по колу
    for i in range(24):
        a = i * (2 * np.pi / 24)
        x1 = cx + int(np.cos(a) * W * 0.31)
        y1 = cy + int(np.sin(a) * W * 0.31)
        x2 = cx + int(np.cos(a) * W * 0.34)
        y2 = cy + int(np.sin(a) * W * 0.34)
        draw.line([(x1, y1), (x2, y2)], fill=(180, 140, 80), width=3)
    img = _add_noise(img, 5)
    img.save(out_path, "JPEG", quality=88)


def make_background(role_data: dict, out_path: Path) -> None:
    fn = {"president": _bg_president, "scientist": _bg_scientist, "diplomat": _bg_diplomat}.get(role_data["id"])
    if fn is None:
        # Fallback на простий градієнт
        img = _vertical_gradient(W, H, role_data["bg_color"], (10, 10, 20))
        img.save(out_path, "JPEG", quality=85)
        return
    fn(out_path)


def _torso_polygon(draw: ImageDraw.ImageDraw, color: tuple, sh_w_mult: float = 1.0) -> dict:
    """Малює базовий торс-трапецію і повертає ключові координати для наступних деталей."""
    sh_cy = int(H * DESIGN_SHOULDERS_CY)
    sh_w = int(W * DESIGN_SHOULDERS_W * sh_w_mult)
    sh_left = W // 2 - sh_w // 2
    sh_right = W // 2 + sh_w // 2
    waist_w = int(sh_w * 0.78)
    waist_cy = int(H * 0.98)
    waist_left = W // 2 - waist_w // 2
    waist_right = W // 2 + waist_w // 2
    draw.polygon(
        [(sh_left, sh_cy), (sh_right, sh_cy), (waist_right, waist_cy), (waist_left, waist_cy)],
        fill=color,
    )
    return {"sh_cy": sh_cy, "sh_w": sh_w, "sh_left": sh_left, "sh_right": sh_right,
            "waist_cy": waist_cy, "waist_left": waist_left, "waist_right": waist_right,
            "cx": W // 2}


def _add_shadow(img: Image.Image, alpha: int = 80) -> Image.Image:
    """Дублює alpha-силует, blur'ить і кладе під оригінал — м'яка тінь."""
    rgba = np.array(img)
    shadow_alpha = (rgba[..., 3].astype(np.float32) * (alpha / 255.0)).astype(np.uint8)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow_arr = np.zeros_like(rgba)
    shadow_arr[..., 3] = shadow_alpha
    shadow = Image.fromarray(shadow_arr).filter(ImageFilter.GaussianBlur(8))
    out = Image.alpha_composite(shadow, img)
    return out


def _costume_president(role_data: dict, out_path: Path) -> None:
    """Чорний костюм + біла сорочка + синьо-жовта орденська стрічка."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    suit = (25, 28, 38, 255)
    shirt = (240, 240, 235, 255)
    tie = (130, 30, 40, 255)
    gold = (200, 165, 70, 255)

    t = _torso_polygon(draw, suit)
    # Біла сорочка (вузька вертикальна смуга з V-вирізом)
    shirt_w = int(W * 0.13)
    shirt_top = t["sh_cy"]
    shirt_bot = t["waist_cy"]
    draw.polygon([
        (t["cx"] - shirt_w // 2, shirt_top),
        (t["cx"] + shirt_w // 2, shirt_top),
        (t["cx"] + shirt_w // 2 - 10, shirt_bot),
        (t["cx"] - shirt_w // 2 + 10, shirt_bot),
    ], fill=shirt)
    # Лацкани (V-форма від плечей до грудей)
    lap_y_top = t["sh_cy"]
    lap_y_bot = t["sh_cy"] + int(H * 0.18)
    inner = int(W * 0.05)
    outer = int(W * 0.13)
    draw.polygon([
        (t["sh_left"] + 20, lap_y_top),
        (t["cx"] - inner, lap_y_bot),
        (t["cx"] - outer, lap_y_top),
    ], fill=(15, 18, 25))
    draw.polygon([
        (t["sh_right"] - 20, lap_y_top),
        (t["cx"] + inner, lap_y_bot),
        (t["cx"] + outer, lap_y_top),
    ], fill=(15, 18, 25))
    # Краватка (трапеція)
    tie_top = lap_y_bot
    tie_bot = tie_top + int(H * 0.30)
    draw.polygon([
        (t["cx"] - 18, tie_top), (t["cx"] + 18, tie_top),
        (t["cx"] + 28, tie_bot), (t["cx"] - 28, tie_bot),
    ], fill=tie)
    # Орденська стрічка через плече (синьо-жовта)
    ribbon_pts_blue = [
        (t["sh_left"] + 30, t["sh_cy"] + 15),
        (t["cx"] + 30, t["sh_cy"] + int(H * 0.22)),
        (t["cx"] + 60, t["sh_cy"] + int(H * 0.22)),
        (t["sh_left"] + 60, t["sh_cy"] + 15),
    ]
    draw.polygon(ribbon_pts_blue, fill=(40, 80, 180, 235))
    ribbon_pts_yellow = [(x, y + 16) for (x, y) in ribbon_pts_blue]
    draw.polygon(ribbon_pts_yellow, fill=(245, 200, 50, 235))
    # Золотий значок на лацкані
    badge_cx = t["cx"] - int(W * 0.10)
    badge_cy = t["sh_cy"] + int(H * 0.08)
    r = 18
    draw.ellipse([badge_cx - r, badge_cy - r, badge_cx + r, badge_cy + r], fill=gold, outline=(120, 90, 30), width=2)
    # Ґудзики на сорочці
    for i in range(3):
        by = shirt_top + int(H * (0.22 + i * 0.10))
        draw.ellipse([t["cx"] - 6, by - 6, t["cx"] + 6, by + 6], fill=(50, 50, 60))

    img = _add_shadow(img, alpha=90)
    img.save(out_path, "PNG")


def _costume_scientist(role_data: dict, out_path: Path) -> None:
    """Білий лаб халат + ID бейдж + ручки в кишені."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    coat = (235, 238, 240, 245)
    coat_shadow = (190, 200, 210, 245)
    shirt = (60, 90, 130, 255)
    blue = (70, 140, 200, 255)

    t = _torso_polygon(draw, coat, sh_w_mult=1.05)
    # Темна сорочка з V-вирізом
    v_top = t["sh_cy"]
    v_bot = t["sh_cy"] + int(H * 0.15)
    draw.polygon([
        (t["cx"] - int(W * 0.10), v_top),
        (t["cx"] + int(W * 0.10), v_top),
        (t["cx"], v_bot),
    ], fill=shirt)
    # Розгорнуті поли халата — дві вертикальні лінії-тіні
    lap_off = int(W * 0.04)
    draw.line([(t["cx"] - lap_off, v_top), (t["cx"] - lap_off // 2, t["waist_cy"])], fill=coat_shadow, width=5)
    draw.line([(t["cx"] + lap_off, v_top), (t["cx"] + lap_off // 2, t["waist_cy"])], fill=coat_shadow, width=5)
    # Нагрудна кишеня — прямокутник з тінню
    pocket_x = t["cx"] + int(W * 0.08)
    pocket_y = t["sh_cy"] + int(H * 0.10)
    pw, ph = int(W * 0.10), int(H * 0.06)
    draw.rectangle([pocket_x, pocket_y, pocket_x + pw, pocket_y + ph],
                   outline=coat_shadow, width=4)
    # Ручки в кишені
    for i in range(2):
        pen_x = pocket_x + 15 + i * 14
        draw.rectangle([pen_x, pocket_y - 18, pen_x + 6, pocket_y + 8],
                       fill=(40, 50, 60) if i == 0 else (130, 30, 30))
    # ID бейдж на лівій стороні (з точки зору глядача), нижче — не торкається V-вирізу
    badge_x = t["cx"] - int(W * 0.14)
    badge_y = t["sh_cy"] + int(H * 0.18)
    bw, bh = int(W * 0.10), int(H * 0.06)
    draw.rectangle([badge_x, badge_y, badge_x + bw, badge_y + bh],
                   fill=(250, 250, 250), outline=(50, 50, 50), width=2)
    # Кольорова смуга на бейджі
    draw.rectangle([badge_x, badge_y, badge_x + bw, badge_y + 16], fill=blue)
    # Короткий шнурок — тільки вертикально від верху бейджа в халат (без перетину з V-вирізом)
    draw.line(
        [(badge_x + bw // 2, badge_y - 30), (badge_x + bw // 2, badge_y)],
        fill=(40, 50, 60), width=4,
    )
    # Кліпса/защіпка на верху шнурка
    draw.rectangle(
        [badge_x + bw // 2 - 6, badge_y - 36, badge_x + bw // 2 + 6, badge_y - 28],
        fill=(150, 150, 160),
    )

    img = _add_shadow(img, alpha=70)
    img.save(out_path, "PNG")


def _costume_diplomat(role_data: dict, out_path: Path) -> None:
    """Темно-синій костюм + блакитна краватка ООН + значок ООН."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    suit = (35, 45, 75, 255)
    shirt = (240, 245, 250, 255)
    un_blue = (90, 160, 220, 255)
    gold = (210, 175, 80, 255)

    t = _torso_polygon(draw, suit)
    # Біла сорочка
    shirt_w = int(W * 0.13)
    draw.polygon([
        (t["cx"] - shirt_w // 2, t["sh_cy"]),
        (t["cx"] + shirt_w // 2, t["sh_cy"]),
        (t["cx"] + shirt_w // 2 - 10, t["waist_cy"]),
        (t["cx"] - shirt_w // 2 + 10, t["waist_cy"]),
    ], fill=shirt)
    # Лацкани
    lap_y_top = t["sh_cy"]
    lap_y_bot = t["sh_cy"] + int(H * 0.18)
    inner = int(W * 0.05)
    outer = int(W * 0.13)
    lap_col = (25, 32, 55)
    draw.polygon([(t["sh_left"] + 20, lap_y_top), (t["cx"] - inner, lap_y_bot), (t["cx"] - outer, lap_y_top)], fill=lap_col)
    draw.polygon([(t["sh_right"] - 20, lap_y_top), (t["cx"] + inner, lap_y_bot), (t["cx"] + outer, lap_y_top)], fill=lap_col)
    # Краватка — однотонна блакитна з вузлом
    tie_top = lap_y_bot
    tie_bot = tie_top + int(H * 0.32)
    tie_poly = [(t["cx"] - 22, tie_top), (t["cx"] + 22, tie_top),
                (t["cx"] + 32, tie_bot), (t["cx"] - 32, tie_bot)]
    draw.polygon(tie_poly, fill=un_blue)
    # Вузол краватки — трохи темніший трапецоїд зверху
    knot_h = int(H * 0.04)
    draw.polygon([
        (t["cx"] - 24, tie_top),
        (t["cx"] + 24, tie_top),
        (t["cx"] + 20, tie_top + knot_h),
        (t["cx"] - 20, tie_top + knot_h),
    ], fill=(60, 110, 170))
    # 2 акуратні білі діагональні смужки (як на офіційних краватках ООН)
    for stripe_y in (tie_top + int(H * 0.10), tie_top + int(H * 0.22)):
        draw.line(
            [(t["cx"] - 20, stripe_y + 14), (t["cx"] + 26, stripe_y - 6)],
            fill=(235, 240, 245), width=6,
        )
    # Значок ООН на лацкані (золотий)
    badge_cx = t["cx"] - int(W * 0.09)
    badge_cy = t["sh_cy"] + int(H * 0.07)
    r = 20
    draw.ellipse([badge_cx - r, badge_cy - r, badge_cx + r, badge_cy + r],
                 fill=gold, outline=(120, 90, 30), width=2)
    # Маленькі лаврові «риски» навколо значка
    for k in range(8):
        a = k * (2 * np.pi / 8)
        x1 = badge_cx + int(np.cos(a) * (r + 4))
        y1 = badge_cy + int(np.sin(a) * (r + 4))
        x2 = badge_cx + int(np.cos(a) * (r + 10))
        y2 = badge_cy + int(np.sin(a) * (r + 10))
        draw.line([(x1, y1), (x2, y2)], fill=gold, width=2)

    img = _add_shadow(img, alpha=90)
    img.save(out_path, "PNG")


def make_costume(role_data: dict, out_path: Path) -> None:
    fn = {"president": _costume_president, "scientist": _costume_scientist, "diplomat": _costume_diplomat}.get(role_data["id"])
    if fn is None:
        # Fallback — той самий проcеду рний дизайн
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        _torso_polygon(draw, role_data["costume_color"])
        img.save(out_path, "PNG")
        return
    fn(role_data, out_path)


def make_meta(role_data: dict, out_path: Path) -> None:
    meta = {k: role_data[k] for k in ("id", "title", "year", "slogan", "button_label", "age_offset")}
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
