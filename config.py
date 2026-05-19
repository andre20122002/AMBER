"""Конфігурація kiosk-системи.

Цей модуль НЕ імпортує pygame — щоб був придатний для тестування без display.
Pygame-залежні константи (коди клавіш) зберігаємо як рядки і конвертуємо в admin.py.
"""
from pathlib import Path

# --- Відео (камера) ---
CAMERA_INDEX = 0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
TARGET_FPS = 30

# --- Екран (вертикальний дисплей) ---
DISPLAY_WIDTH = 1080
DISPLAY_HEIGHT = 1920
FULLSCREEN = True

# --- Режим розробки ---
DEV_MOCK_CAMERA = False  # перекривається --mock CLI флагом у main.py

# --- Таймінги (секунди) ---
COUNTDOWN_SECONDS = 3
IDLE_TIMEOUT = 30
PHOTO_QR_DISPLAY = 15  # довше, щоб встигнути сканувати QR

# --- Сегментація і pose ---
SEGMENTATION_THRESHOLD = 0.7  # бінарний fallback; основна логіка float
MASK_BLUR_SIZE = 21
POSE_MIN_CONFIDENCE = 0.5

# Smoothing pose landmarks (One-Euro filter)
POSE_SMOOTH_MIN_CUTOFF = 1.0   # менше → плавніше, але повільніше реагує
POSE_SMOOTH_BETA = 0.007        # більше → швидше реагує на швидкі рухи
POSE_HOLD_FRAMES = 30           # ≈1с при 30FPS — скільки тримати last-good коли pose lost

# Дзеркальне відображення кадру (як справжнє дзеркало). Pose detection
# відбувається ПІСЛЯ flip, тож координати вже в дзеркальному просторі.
MIRROR_CAMERA = True

# --- Адмін (без імпорту pygame) ---
ADMIN_KEY_NAME = "F12"        # подвійне натискання
ADMIN_KEY_TIMEOUT = 1.0       # секунди між першим і другим F12
ADMIN_PASSWORD_FILE = "admin.local.json"
ADMIN_PASSWORD_FALLBACK = "1234"

# --- QR / локальний HTTP ---
QR_SERVER_PORT = 8080
QR_BIND_HOST = "0.0.0.0"

# --- Шляхи ---
ASSETS_DIR = Path("assets")
ROLES_DIR = ASSETS_DIR / "roles"
UI_DIR = ASSETS_DIR / "ui"
DEV_DIR = ASSETS_DIR / "dev"
DATA_DIR = Path("data")
PHOTOS_DIR = DATA_DIR / "photos"
LOG_DIR = Path("logs")
FONT_PATH = UI_DIR / "fonts" / "Inter-Regular.ttf"
MOCK_FRAME_PATH = DEV_DIR / "mock_frame.jpg"
IDLE_BG_PATH = UI_DIR / "idle_background.jpg"

# --- Logging ---
LOG_LEVEL = "INFO"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5
