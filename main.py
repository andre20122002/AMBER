"""Точка входу kiosk — state machine + головний цикл pygame.

Flow:
  IDLE → (тап) → MENU → (тап на роль) → COUNTDOWN → PHOTO_QR → IDLE

CLI:
  python main.py            # production: справжня камера, fullscreen
  python main.py --mock     # розробка: mock-кадр з assets/dev/mock_frame.jpg
  python main.py --windowed # розробка: вікно замість fullscreen
"""
import argparse
import logging
import sys
import time
from enum import Enum, auto
from pathlib import Path

import cv2
import pygame

import config
from admin import AdminKeyDetector, AdminPanel
from camera import CameraThread
from logging_setup import setup_logging
from overlay import compose
from photo import save_photo
from photo_server import PhotoHTTPServer
from pose import PoseDetector
from qr import make_qr
from roles import Role, RoleManager
from segmentation import Segmenter
import ui

logger = logging.getLogger(__name__)


class AppState(Enum):
    IDLE = auto()
    MENU = auto()
    COUNTDOWN = auto()
    PHOTO_QR = auto()
    ADMIN = auto()


class App:
    def __init__(self, mock: bool = False, windowed: bool = False):
        self.mock = mock
        self.windowed = windowed
        self.running = True

        pygame.init()
        flags = 0 if windowed else (pygame.FULLSCREEN | pygame.NOFRAME)
        self.screen = pygame.display.set_mode((config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT), flags)
        pygame.display.set_caption("Побач себе в майбутньому")
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()

        # IDLE background (опціонально)
        self.idle_bg: pygame.Surface | None = None
        if config.IDLE_BG_PATH.exists():
            self.idle_bg = pygame.transform.smoothscale(
                pygame.image.load(str(config.IDLE_BG_PATH)).convert(),
                (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT),
            )

        # Підсистеми
        self.camera = CameraThread(mock=mock)
        self.camera.start()
        self.segmenter = Segmenter()
        self.pose_detector = PoseDetector()
        self.role_manager = RoleManager()
        self.photo_server = PhotoHTTPServer()
        self.photo_server_ok = self.photo_server.start()
        self.admin = AdminPanel(
            on_reload_roles=self.role_manager._reload,
            on_exit_kiosk=self._request_quit,
        )
        self.admin_key = AdminKeyDetector()

        # State
        self.state = AppState.IDLE
        self.prev_state: AppState | None = None
        self.current_role: Role | None = None
        self.state_entered_at = time.monotonic()
        self.countdown_started_at: float | None = None
        self.last_photo_bgr = None
        self.last_qr_bgr = None
        self.menu_zones: list[tuple[pygame.Rect, Role]] = []

        # Кеш останнього composite — щоб PHOTO_QR показував саме той кадр, що зберегли
        self._last_composite = None

    def _request_quit(self) -> None:
        self.running = False

    def _transition(self, new_state: AppState) -> None:
        if new_state == self.state:
            return
        logger.info("State %s → %s", self.state.name, new_state.name)
        self.prev_state = self.state
        self.state = new_state
        self.state_entered_at = time.monotonic()
        if new_state == AppState.COUNTDOWN:
            self.countdown_started_at = time.monotonic()
        if new_state == AppState.ADMIN:
            self.admin.reset()

    def _time_in_state(self) -> float:
        return time.monotonic() - self.state_entered_at

    # --- Обробка подій ---

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return

            # Esc — глобальний вихід (для розробки)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and self.windowed:
                self.running = False
                return

            # Подвійне F12 — вхід в адмін з будь-якого стану
            if self.state != AppState.ADMIN and self.admin_key.handle(event):
                self._transition(AppState.ADMIN)
                continue

            if self.state == AppState.ADMIN:
                still_active = self.admin.handle_event(event)
                if not still_active:
                    self._transition(self.prev_state or AppState.IDLE)
                continue

            if self.state == AppState.IDLE:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    self._transition(AppState.MENU)

            elif self.state == AppState.MENU:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    for rect, role in self.menu_zones:
                        if rect.collidepoint(event.pos):
                            self.current_role = role
                            self._transition(AppState.COUNTDOWN)
                            break

            elif self.state == AppState.PHOTO_QR:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    self._reset_to_idle()

    # --- Поточний composite (live overlay) ---

    def _render_composite(self) -> "np.ndarray | None":
        if self.current_role is None:
            return None
        frame = self.camera.get_latest_frame()
        if frame is None:
            return None
        try:
            mask = self.segmenter.get_mask(frame)
            pose = self.pose_detector.detect(frame)
            return compose(frame, mask, self.current_role, pose)
        except Exception:
            logger.exception("compose failed")
            return None

    # --- Tick (стан-залежна логіка) ---

    def _tick(self) -> None:
        if self.state == AppState.IDLE:
            return  # без таймауту в IDLE

        if self.state == AppState.MENU:
            if self._time_in_state() > config.IDLE_TIMEOUT:
                self._reset_to_idle()
            return

        if self.state == AppState.COUNTDOWN:
            elapsed = time.monotonic() - (self.countdown_started_at or time.monotonic())
            if elapsed >= config.COUNTDOWN_SECONDS:
                self._capture_photo()
                self._transition(AppState.PHOTO_QR)
            return

        if self.state == AppState.PHOTO_QR:
            if self._time_in_state() > config.PHOTO_QR_DISPLAY:
                self._reset_to_idle()
            return

    def _capture_photo(self) -> None:
        composite = self._last_composite if self._last_composite is not None else self._render_composite()
        if composite is None:
            logger.warning("No composite available for capture")
            return
        try:
            path = save_photo(composite)
            self.last_photo_bgr = composite
            if self.photo_server_ok:
                url = self.photo_server.get_url(path)
                logger.info("Photo URL: %s", url)
                self.last_qr_bgr = make_qr(url)
            else:
                self.last_qr_bgr = None
        except Exception:
            logger.exception("Photo capture failed")

    def _reset_to_idle(self) -> None:
        self.current_role = None
        self.last_photo_bgr = None
        self.last_qr_bgr = None
        self._last_composite = None
        self._transition(AppState.IDLE)

    # --- Render ---

    def _render(self) -> None:
        if self.state == AppState.IDLE:
            ui.render_idle(self.screen, self.idle_bg)

        elif self.state == AppState.MENU:
            self.menu_zones = ui.render_menu(self.screen, self.role_manager.list())

        elif self.state == AppState.COUNTDOWN:
            self._last_composite = self._render_composite()
            elapsed = time.monotonic() - (self.countdown_started_at or time.monotonic())
            remaining = max(0, int(config.COUNTDOWN_SECONDS - elapsed) + 1)
            remaining = min(remaining, config.COUNTDOWN_SECONDS)
            ui.render_countdown(self.screen, self._last_composite, remaining)

        elif self.state == AppState.PHOTO_QR:
            seconds_left = max(0, int(config.PHOTO_QR_DISPLAY - self._time_in_state()))
            ui.render_photo_qr(self.screen, self.last_photo_bgr, self.last_qr_bgr, seconds_left)

        elif self.state == AppState.ADMIN:
            self.admin.render(self.screen)

        pygame.display.flip()

    # --- Main loop ---

    def run(self) -> None:
        logger.info("Entering main loop (mock=%s, windowed=%s)", self.mock, self.windowed)
        try:
            while self.running:
                self._handle_events()
                self._tick()
                self._render()
                self.clock.tick(config.TARGET_FPS)
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        logger.info("Shutting down")
        try:
            self.camera.stop()
            self.segmenter.close()
            self.pose_detector.close()
            self.photo_server.stop()
            pygame.quit()
        except Exception:
            logger.exception("Error during shutdown")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kiosk «Побач себе в майбутньому»")
    p.add_argument("--mock", action="store_true", help="Mock-камера з assets/dev/mock_frame.jpg")
    p.add_argument("--windowed", action="store_true", help="Вікно замість fullscreen (для розробки)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging()
    logger.info("Starting kiosk; argv=%s", sys.argv)
    app = App(mock=args.mock, windowed=args.windowed)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
