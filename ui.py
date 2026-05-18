"""Рендеринг екранів kiosk через pygame.

Стани: IDLE, MENU, COUNTDOWN, ACTIVE, PHOTO_QR, ADMIN (рендериться в admin.py).
Touch-зони повертаються з render_menu для обробки в state machine.
"""
import logging

import cv2
import numpy as np
import pygame

import config
from roles import Role

logger = logging.getLogger(__name__)

# Кольори
COLOR_BG = (15, 20, 30)
COLOR_TEXT = (240, 240, 240)
COLOR_ACCENT = (255, 200, 80)
COLOR_BTN_BG = (35, 50, 75)
COLOR_BTN_BORDER = (90, 130, 180)

_font_cache: dict[int, pygame.font.Font] = {}


def get_font(size: int) -> pygame.font.Font:
    if size not in _font_cache:
        if config.FONT_PATH.exists():
            _font_cache[size] = pygame.font.Font(str(config.FONT_PATH), size)
        else:
            logger.warning("Font not found, using pygame default")
            _font_cache[size] = pygame.font.SysFont(None, size)
    return _font_cache[size]


def bgr_to_surface(img_bgr: np.ndarray) -> pygame.Surface:
    """Конвертує BGR np.ndarray у pygame.Surface.

    pygame.surfarray.make_surface очікує (W, H, 3) RGB, тож swapaxes.
    """
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    return pygame.surfarray.make_surface(rgb.swapaxes(0, 1))


def _draw_centered_text(screen: pygame.Surface, text: str, y: int, font: pygame.font.Font, color=COLOR_TEXT) -> pygame.Rect:
    surf = font.render(text, True, color)
    rect = surf.get_rect(center=(screen.get_width() // 2, y))
    screen.blit(surf, rect)
    return rect


def render_idle(screen: pygame.Surface, idle_bg: pygame.Surface | None = None) -> None:
    if idle_bg is not None:
        screen.blit(idle_bg, (0, 0))
    else:
        screen.fill(COLOR_BG)
    title_font = get_font(90)
    sub_font = get_font(48)
    _draw_centered_text(screen, "Побач себе", screen.get_height() // 2 - 80, title_font, COLOR_ACCENT)
    _draw_centered_text(screen, "в майбутньому", screen.get_height() // 2 + 20, title_font, COLOR_ACCENT)
    _draw_centered_text(screen, "торкніться екрану, щоб почати", screen.get_height() - 200, sub_font, COLOR_TEXT)


def render_menu(screen: pygame.Surface, roles: list[Role]) -> list[tuple[pygame.Rect, Role]]:
    """Малює меню з кнопками-ролями. Повертає список (rect, role) для обробки тапів."""
    screen.fill(COLOR_BG)
    title_font = get_font(72)
    btn_font = get_font(56)
    _draw_centered_text(screen, "Оберіть роль", 120, title_font, COLOR_ACCENT)

    zones: list[tuple[pygame.Rect, Role]] = []
    if not roles:
        _draw_centered_text(screen, "Немає доступних ролей", screen.get_height() // 2, btn_font)
        return zones

    # Розкладка: 1 кнопка на ряд, повна ширина мінус padding
    padding = 80
    btn_h = 200
    btn_w = screen.get_width() - 2 * padding
    start_y = 280
    gap = 30

    for i, role in enumerate(roles):
        x = padding
        y = start_y + i * (btn_h + gap)
        if y + btn_h > screen.get_height() - 100:
            break  # не вміщається
        rect = pygame.Rect(x, y, btn_w, btn_h)
        pygame.draw.rect(screen, COLOR_BTN_BG, rect, border_radius=24)
        pygame.draw.rect(screen, COLOR_BTN_BORDER, rect, width=4, border_radius=24)
        label_surf = btn_font.render(role.button_label, True, COLOR_TEXT)
        label_rect = label_surf.get_rect(center=rect.center)
        screen.blit(label_surf, label_rect)
        zones.append((rect, role))

    return zones


def render_countdown(screen: pygame.Surface, composite_bgr: np.ndarray | None, seconds_left: int) -> None:
    if composite_bgr is not None:
        screen.blit(bgr_to_surface(composite_bgr), (0, 0))
    else:
        screen.fill(COLOR_BG)

    # Велика цифра по центру
    big_font = get_font(360)
    text = str(seconds_left) if seconds_left > 0 else "!"
    surf = big_font.render(text, True, COLOR_ACCENT)
    # Drop-shadow для читабельності
    shadow = big_font.render(text, True, (0, 0, 0))
    rect = surf.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2))
    screen.blit(shadow, rect.move(6, 6))
    screen.blit(surf, rect)


def render_active(screen: pygame.Surface, composite_bgr: np.ndarray | None) -> None:
    if composite_bgr is None:
        screen.fill(COLOR_BG)
        _draw_centered_text(screen, "Камера недоступна", screen.get_height() // 2, get_font(56))
        return
    screen.blit(bgr_to_surface(composite_bgr), (0, 0))


def render_photo_qr(
    screen: pygame.Surface,
    photo_bgr: np.ndarray | None,
    qr_bgr: np.ndarray | None,
    seconds_left: int,
) -> pygame.Rect | None:
    """Показує фото у верхній частині, QR-код знизу. Повертає Rect кнопки 'Готово' для тапу."""
    screen.fill(COLOR_BG)
    W, H = screen.get_size()

    # Фото-прев'ю: верхні 60% екрана
    if photo_bgr is not None:
        preview_h = int(H * 0.55)
        ratio = photo_bgr.shape[1] / photo_bgr.shape[0]
        preview_w = int(preview_h * ratio)
        if preview_w > W - 40:
            preview_w = W - 40
            preview_h = int(preview_w / ratio)
        photo_resized = cv2.resize(photo_bgr, (preview_w, preview_h), interpolation=cv2.INTER_AREA)
        photo_surf = bgr_to_surface(photo_resized)
        screen.blit(photo_surf, ((W - preview_w) // 2, 40))

    # QR-код під фото
    if qr_bgr is not None:
        qr_size = 480
        qr_resized = cv2.resize(qr_bgr, (qr_size, qr_size), interpolation=cv2.INTER_NEAREST)
        qr_surf = bgr_to_surface(qr_resized)
        qr_y = int(H * 0.62)
        screen.blit(qr_surf, ((W - qr_size) // 2, qr_y))
        cap_font = get_font(36)
        _draw_centered_text(screen, "Скануйте, щоб забрати фото", qr_y + qr_size + 40, cap_font, COLOR_TEXT)
    else:
        _draw_centered_text(screen, "Фото збережено", int(H * 0.7), get_font(48), COLOR_TEXT)

    # Лічильник внизу
    countdown_font = get_font(40)
    _draw_centered_text(
        screen,
        f"Повернення на головну через {seconds_left} с",
        H - 80,
        countdown_font,
        COLOR_TEXT,
    )
    return None
