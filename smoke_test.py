"""Smoke-тест: ініціалізує App в windowed mode, проганяє 60 кадрів, перевіряє відсутність exceptions.

Запуск:
    .venv\\Scripts\\python smoke_test.py
"""
import logging
import os
import sys

# Drv для headless: SDL не потребує display, ми робимо dummy-driver
# щоб тест працював навіть без X/Wayland.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from logging_setup import setup_logging  # noqa: E402
from main import App, AppState  # noqa: E402

setup_logging()
logger = logging.getLogger("smoke_test")

app = App(mock=True, windowed=True)
logger.info("App initialized OK")

# Прогнати 60 кадрів вручну
for i in range(60):
    app._handle_events()
    app._tick()
    app._render()

logger.info("Rendered 60 frames in IDLE")

# Симулюємо тап → MENU
app._transition(AppState.MENU)
for i in range(30):
    app._handle_events()
    app._tick()
    app._render()
logger.info("Rendered 30 frames in MENU; roles=%d, zones=%d", len(app.role_manager.roles), len(app.menu_zones))

# Обираємо першу роль → COUNTDOWN
if app.role_manager.roles:
    app.current_role = app.role_manager.roles[0]
    app._transition(AppState.COUNTDOWN)
    for i in range(30):
        app._handle_events()
        app._tick()
        app._render()
    logger.info("Rendered 30 frames in COUNTDOWN; composite=%s",
                "OK" if app._last_composite is not None else "None")

# Симулюємо завершення countdown → захоплення → PHOTO_QR
app._capture_photo()
app._transition(AppState.PHOTO_QR)
for i in range(30):
    app._handle_events()
    app._tick()
    app._render()
logger.info("Rendered 30 frames in PHOTO_QR; photo=%s, qr=%s",
            "OK" if app.last_photo_bgr is not None else "None",
            "OK" if app.last_qr_bgr is not None else "None")

app.shutdown()
logger.info("Smoke test PASSED")
print("OK")
sys.exit(0)
