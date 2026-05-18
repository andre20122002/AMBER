"""Адмін-панель: подвійне F12 → ввід пароля → меню дій.

Пароль вантажиться з admin.local.json (gitignored), якщо файлу немає — fallback "1234".
"""
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pygame

import config
from ui import COLOR_ACCENT, COLOR_BG, COLOR_TEXT, _draw_centered_text, get_font

logger = logging.getLogger(__name__)


def _load_admin_password() -> str:
    p = Path(config.ADMIN_PASSWORD_FILE)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return str(data.get("password", config.ADMIN_PASSWORD_FALLBACK))
        except Exception as exc:
            logger.warning("Could not parse %s: %s", p, exc)
    return config.ADMIN_PASSWORD_FALLBACK


@dataclass
class AdminKeyDetector:
    """Детектор подвійного F12 (з timeout)."""
    timeout: float = config.ADMIN_KEY_TIMEOUT
    _first_press_at: float | None = field(default=None)

    def handle(self, event: pygame.event.Event) -> bool:
        """Повертає True, якщо подвійне F12 щойно відбулося."""
        if event.type != pygame.KEYDOWN or event.key != pygame.K_F12:
            return False
        now = time.monotonic()
        if self._first_press_at is not None and (now - self._first_press_at) <= self.timeout:
            self._first_press_at = None
            return True
        self._first_press_at = now
        return False


class AdminPanel:
    """Простий модальний UI: ввід пароля → меню дій."""

    ACTIONS = ("Перезавантажити ролі", "Відкрити папку фото", "Вихід з kiosk", "Закрити панель")

    def __init__(self, on_reload_roles, on_exit_kiosk):
        self.password = _load_admin_password()
        self.on_reload_roles = on_reload_roles
        self.on_exit_kiosk = on_exit_kiosk
        self._password_input = ""
        self._authed = False
        self._message: str | None = None

    def reset(self) -> None:
        self._password_input = ""
        self._authed = False
        self._message = None

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Повертає True, якщо панель ще активна. False — закрити."""
        if event.type != pygame.KEYDOWN and event.type != pygame.MOUSEBUTTONDOWN:
            return True

        if not self._authed:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    if self._password_input == self.password:
                        self._authed = True
                        self._message = None
                    else:
                        self._message = "Невірний пароль"
                        self._password_input = ""
                elif event.key == pygame.K_BACKSPACE:
                    self._password_input = self._password_input[:-1]
                elif event.key == pygame.K_ESCAPE:
                    return False
                elif event.unicode and event.unicode.isprintable():
                    self._password_input += event.unicode
            return True

        # autheded → меню (touch-зони)
        if event.type == pygame.MOUSEBUTTONDOWN:
            for rect, action in self._menu_zones:
                if rect.collidepoint(event.pos):
                    return self._execute(action)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return False
        return True

    def _execute(self, action: str) -> bool:
        logger.info("Admin action: %s", action)
        if action == "Перезавантажити ролі":
            try:
                self.on_reload_roles()
                self._message = "Ролі перезавантажено"
            except Exception as exc:
                self._message = f"Помилка: {exc}"
            return True
        if action == "Відкрити папку фото":
            try:
                path = str(config.PHOTOS_DIR.resolve())
                if sys.platform == "win32":
                    os.startfile(path)  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["xdg-open", path])
                self._message = "Папку відкрито"
            except Exception as exc:
                self._message = f"Помилка: {exc}"
            return True
        if action == "Вихід з kiosk":
            self.on_exit_kiosk()
            return False
        if action == "Закрити панель":
            return False
        return True

    def render(self, screen: pygame.Surface) -> None:
        screen.fill(COLOR_BG)
        title_font = get_font(72)
        body_font = get_font(48)

        _draw_centered_text(screen, "Адмін-панель", 120, title_font, COLOR_ACCENT)

        if not self._authed:
            _draw_centered_text(screen, "Введіть пароль:", 320, body_font)
            mask = "•" * len(self._password_input)
            _draw_centered_text(screen, mask or "_", 420, body_font)
            _draw_centered_text(screen, "Enter — підтвердити, Esc — вийти", 600, get_font(32))
        else:
            self._menu_zones = []
            btn_h = 130
            btn_w = screen.get_width() - 200
            start_y = 320
            gap = 24
            for i, action in enumerate(self.ACTIONS):
                rect = pygame.Rect(100, start_y + i * (btn_h + gap), btn_w, btn_h)
                pygame.draw.rect(screen, (35, 50, 75), rect, border_radius=20)
                pygame.draw.rect(screen, (90, 130, 180), rect, width=3, border_radius=20)
                surf = body_font.render(action, True, COLOR_TEXT)
                screen.blit(surf, surf.get_rect(center=rect.center))
                self._menu_zones.append((rect, action))

        if self._message:
            _draw_centered_text(screen, self._message, screen.get_height() - 120, get_font(36), COLOR_ACCENT)
