# CLAUDE.md — Інсталяція «Побач себе в майбутньому»

## Що це за проєкт

Інтерактивна kiosk-система для музею мініатюр. Людина заходить у будку, стає перед камерою на вертикальному екрані-«дзеркалі» і бачить себе в ролі видатної особистості (президент, науковець, дипломат тощо). Система в реальному часі:

1. Захоплює відео з камери (окремий потік)
2. Сегментує фігуру людини через MediaPipe SelfieSegmentation
3. Визначає позу (плечі/голову) через MediaPipe PoseLandmarker — для auto-fit костюма
4. Накладає шари: фон → фігура (alpha-blend) → PNG-костюм (масштабований під позу) → текст
5. Зберігає фото, генерує QR-код для скачування з телефона

---

## Стек

| Компонент | Бібліотека / версія |
|---|---|
| Мова | Python 3.11 |
| Відео / композиція | OpenCV (`opencv-python==4.10.*`) |
| Сегментація фігури | MediaPipe `SelfieSegmentation` (`mediapipe==0.10.*`) |
| Поза для auto-fit костюма | MediaPipe `PoseLandmarker` |
| PNG з прозорістю | Pillow (`Pillow>=10.0`) |
| UI / fullscreen | PyGame (`pygame==2.6.*`) |
| QR-код | `qrcode[pil]==7.4.*` |
| Локальний HTTP (для QR) | `http.server` (stdlib) |
| Автозапуск | systemd service |
| Kiosk-режим | unclutter, xrandr |

Встановлення:
```bash
pip install -r requirements.txt
sudo apt install unclutter x11-xserver-utils  # тільки production (Linux)
```

---

## Платформи

- **Розробка:** Windows 10 (поточна). Камера може бути відсутня → mock-режим через `--mock`.
- **Production:** Linux + systemd + вертикальний touchscreen-екран 1080×1920.

---

## Структура проєкту

```
project/
├── main.py                  # Точка входу, головний цикл PyGame, --mock flag
├── config.py                # Усі константи (без імпорту pygame)
├── logging_setup.py         # RotatingFileHandler + StreamHandler
├── camera.py                # Threaded capture з queue.Queue(maxsize=1) + mock
├── segmentation.py          # MediaPipe SelfieSegmentation, float-маска [0..1]
├── pose.py                  # MediaPipe PoseLandmarker, повертає плечі/голову
├── overlay.py               # Композиція в просторі дисплея (1080×1920), alpha-blend
├── roles.py                 # RoleManager: scan + meta.json + кеш ресайзнутих картинок
├── ui.py                    # Екрани (IDLE, MENU, COUNTDOWN, ACTIVE, PHOTO_QR), touch-зони
├── photo.py                 # save_photo() → data/photos/YYYY-MM-DD/photo_HHMMSS.png
├── photo_server.py          # http.server у threading — віддає файли з data/photos/
├── qr.py                    # make_qr(url) → np.ndarray
├── admin.py                 # Подвійний F12 → пароль → меню
├── generate_placeholders.py # Скрипт: створює тестові ролі та mock-кадр
│
├── assets/
│   ├── roles/
│   │   ├── president/
│   │   │   ├── costume.png      # RGBA, 1080×1920, прозорий «силует» для тіла
│   │   │   ├── background.jpg   # 1080×1920, фонова сцена
│   │   │   └── meta.json
│   │   ├── scientist/
│   │   └── diplomat/
│   │
│   ├── ui/
│   │   ├── idle_background.jpg  # 1080×1920
│   │   ├── logo.png
│   │   └── fonts/
│   │       └── Inter-Regular.ttf  # Кириличний шрифт (OFL ліцензія)
│   │
│   └── dev/
│       └── mock_frame.jpg       # Кадр з людиною для розробки без камери
│
├── data/
│   └── photos/                  # Згенеровані фото (поза assets/)
│       └── 2026-05-18/
│           └── photo_143022.png
│
├── logs/
│   └── kiosk.log                # RotatingFileHandler 10MB×5
│
├── systemd/
│   └── kiosk.service
│
├── requirements.txt
├── README_DEPLOY.md             # Інструкція встановлення на Linux
└── CLAUDE.md
```

---

## Архітектура головного циклу (`main.py`)

```python
class AppState(Enum):
    IDLE       # Заставка, очікування відвідувача
    MENU       # Меню вибору ролі (touch-зони)
    COUNTDOWN  # Таймер 3 с перед фото
    ACTIVE     # Активна роль — відео з оверлеєм у реальному часі
    PHOTO_QR   # Збережене фото + QR-код для скачування
    ADMIN      # Адміністративна панель

# Головний цикл
camera_thread.start()
photo_http_server.start()

while running:
    frame = camera_thread.get_latest_frame()  # non-blocking, останній кадр

    # Overlay рахуємо ТІЛЬКИ якщо роль активна (фікс B5)
    composite = None
    if state in (AppState.COUNTDOWN, AppState.ACTIVE):
        mask = segmenter.get_mask(frame)              # float32 [0..1]
        pose = pose_detector.detect(frame)            # plечі/голова або None
        composite = overlay.compose(frame, mask, current_role, pose)

    ui.render(state, composite=composite, role=current_role, photo=last_photo, qr=last_qr)

    for event in pygame.event.get():
        state = state_machine.handle(state, event)    # touch, F12, тощо

    state = state_machine.tick(state)                 # idle timeout, countdown
    clock.tick(TARGET_FPS)
```

---

## Інтерфейс взаємодії: Touchscreen

Kiosk обладнаний touchscreen-екраном 1080×1920. Pygame обробляє дотики як `MOUSEBUTTONDOWN`:

```python
for event in pygame.event.get():
    if event.type == pygame.MOUSEBUTTONDOWN:
        x, y = event.pos
        for rect, role in menu_buttons:
            if rect.collidepoint(x, y):
                transition_to(AppState.COUNTDOWN, role=role)
```

Touch-зони в меню — `pygame.Rect`-list, генерується з `RoleManager.list()`.

---

## Модуль сегментації (`segmentation.py`)

```python
import mediapipe as mp, cv2, numpy as np

class Segmenter:
    def __init__(self):
        self.model = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)

    def get_mask(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Повертає float32 [0..1] маску фігури — без бінаризації, для alpha-blend."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        results = self.model.process(rgb)
        mask = results.segmentation_mask.astype(np.float32)  # [0..1]
        mask = cv2.GaussianBlur(mask, (MASK_BLUR_SIZE, MASK_BLUR_SIZE), 0)
        return mask  # shape (H, W), float32
```

---

## Модуль pose-детекції (`pose.py`)

Використовує MediaPipe `PoseLandmarker` для знаходження ключових точок (плечі, голова, стегна). Повертає нормалізовані координати, з яких `overlay.py` обчислює, як масштабувати/змістити PNG-костюм.

```python
@dataclass
class PoseResult:
    left_shoulder: tuple[float, float]   # нормалізовані [0..1]
    right_shoulder: tuple[float, float]
    head: tuple[float, float]
    hips_center: tuple[float, float]
    confidence: float

class PoseDetector:
    def detect(self, frame_bgr) -> PoseResult | None: ...
```

Якщо `pose is None` (людина не знайдена) — костюм рендериться у позиції за замовчуванням (центр екрана, скейл 1.0).

---

## Модуль композиції (`overlay.py`)

**Виправлені баги:**
- **B1:** композиція робиться в просторі ДИСПЛЕЯ (1080×1920), не в просторі кадру (1280×720).
- **B2:** alpha-blending через float-маску, а не `bitwise_and`.
- **G8:** кадр з камери center-crop'иться з 16:9 до 9:16 перед композицією.
- **G1:** костюм auto-fit за `pose` (масштаб і зсув від плечей).

Логіка шарів (знизу вгору):
1. **Background** (role.background_bgr, попередньо ресайзнутий до 1080×1920)
2. **Person** — кадр з камери, обрізаний до 9:16 + ресайзнутий до 1080×1920, накладений через float-маску
3. **Costume** (role.costume_rgba, масштабований і зсунутий за pose), накладений через alpha-канал
4. **Text** (роль, рік, слоган) — через PIL `ImageDraw` з Inter-Regular.ttf

```python
def compose(frame_bgr, mask_float, role: Role, pose: PoseResult | None) -> np.ndarray:
    # 1. Center-crop кадру 16:9 → 9:16 + ресайз до DISPLAY
    frame_cropped = center_crop_to_aspect(frame_bgr, DISPLAY_WIDTH, DISPLAY_HEIGHT)
    mask_cropped  = center_crop_to_aspect(mask_float, DISPLAY_WIDTH, DISPLAY_HEIGHT)

    # 2. Alpha-blend person on background
    alpha = mask_cropped[..., None]  # (H, W, 1) float32 [0..1]
    composite = (role.background_bgr * (1 - alpha) + frame_cropped * alpha).astype(np.uint8)

    # 3. Auto-fit костюма за pose
    costume_positioned = fit_costume_to_pose(role.costume_rgba, pose)  # RGBA (H, W, 4)
    composite = alpha_paste(composite, costume_positioned)

    # 4. Text
    composite = draw_text_overlay(composite, role)
    return composite
```

---

## Кешування ресурсів ролі (`roles.py`)

PNG і фон ресайзяться **один раз** при завантаженні ролі — не на кожному кадрі.

```python
@dataclass
class Role:
    id: str
    title: str
    year: int
    slogan: str
    button_label: str
    costume_rgba: np.ndarray   # (DISPLAY_H, DISPLAY_W, 4) uint8 — кешовано
    background_bgr: np.ndarray # (DISPLAY_H, DISPLAY_W, 3) uint8 — кешовано

class RoleManager:
    def __init__(self, roles_dir: Path):
        self.roles: list[Role] = []
        for sub in roles_dir.iterdir():
            if not sub.is_dir(): continue
            try:
                self.roles.append(self._load_role(sub))
            except Exception as e:
                logger.warning(f"Skipping role {sub.name}: {e}")
```

---

## QR-код для скачування фото

Після збереження фото показуємо екран `PHOTO_QR` з мініатюрою фото та QR-кодом, що веде на `http://<ip>:8080/<photo_filename>`. Локальний HTTP-сервер працює в окремому потоці і віддає файли з `data/photos/`.

```python
# photo_server.py
class PhotoHTTPServer:
    def start(self): ...
    def get_url(self, photo_path: Path) -> str:
        return f"http://{self.host_ip}:{config.QR_SERVER_PORT}/{photo_path.name}"
```

Відвідувач сканує QR телефоном, у браузері відкривається PNG, натискає «зберегти».

**Передумова:** телефон і kiosk у одній Wi-Fi мережі. Якщо ні — fallback показує текст «фото збережено локально».

---

## Структура ролі (`assets/roles/*/meta.json`)

```json
{
  "id": "president",
  "title": "Президент України",
  "year": 2045,
  "slogan": "Ти можеш стати тим, хто змінить країну",
  "button_label": "Президент",
  "button_icon": "icon.png"
}
```

Roles завантажуються динамічно з `assets/roles/`. Поламані `meta.json` чи відсутні файли — лог-попередження, роль пропускається.

---

## Конфігурація (`config.py`)

```python
from pathlib import Path

# Відео (камера)
CAMERA_INDEX = 0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
TARGET_FPS = 30

# Екран (дисплей)
DISPLAY_WIDTH = 1080
DISPLAY_HEIGHT = 1920
FULLSCREEN = True

# Розробка
DEV_MOCK_CAMERA = False  # перекривається --mock CLI флагом

# Таймінги (секунди)
COUNTDOWN_SECONDS = 3
IDLE_TIMEOUT = 30
PHOTO_QR_DISPLAY = 15  # довше, щоб встигнути сканувати QR

# Сегментація / pose
SEGMENTATION_THRESHOLD = 0.7  # для бінарного fallback, основна логіка float
MASK_BLUR_SIZE = 21
POSE_MIN_CONFIDENCE = 0.5

# Адмін (рядки/коди, не імпортуємо pygame у config.py)
ADMIN_KEY_CODE = "F12"          # подвійне натискання
ADMIN_KEY_TIMEOUT = 1.0          # секунди між першим і другим F12
ADMIN_PASSWORD_FILE = "admin.local.json"  # gitignored, fallback "1234"

# QR / HTTP
QR_SERVER_PORT = 8080
QR_BIND_HOST = "0.0.0.0"

# Шляхи
ASSETS_DIR = Path("assets")
ROLES_DIR = ASSETS_DIR / "roles"
UI_DIR = ASSETS_DIR / "ui"
DEV_DIR = ASSETS_DIR / "dev"
DATA_DIR = Path("data")
PHOTOS_DIR = DATA_DIR / "photos"
LOG_DIR = Path("logs")
FONT_PATH = UI_DIR / "fonts" / "Inter-Regular.ttf"
MOCK_FRAME_PATH = DEV_DIR / "mock_frame.jpg"

# Logging
LOG_LEVEL = "INFO"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5
```

---

## Логування (`logging_setup.py`)

```python
import logging
from logging.handlers import RotatingFileHandler

def setup_logging(log_dir: Path, level: str = "INFO"):
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [
        RotatingFileHandler(log_dir / "kiosk.log",
                            maxBytes=config.LOG_MAX_BYTES,
                            backupCount=config.LOG_BACKUP_COUNT,
                            encoding="utf-8"),
        logging.StreamHandler(),
    ]
    logging.basicConfig(level=level, format=fmt, handlers=handlers)
```

---

## Обробка помилок

| Сценарій | Поведінка |
|---|---|
| Камера не відкривається | Лог-error, fallback frame «Камера недоступна» на екрані, retry кожні 5 с |
| Пошкоджений `meta.json` | Лог-warning, роль пропускається, інші вантажаться |
| Відсутній `costume.png`/`background.jpg` | Роль не з'являється в меню |
| `Segmenter`/`PoseDetector` падає | Лог-exception, рендер без overlay (показуємо чистий кадр) |
| Photo HTTP server не зміг забіндитись | Лог-error, PHOTO_QR показує тільки фото без QR |

---

## Системні файли

### `systemd/kiosk.service`
```ini
[Unit]
Description=Kiosk — Побач себе в майбутньому
After=graphical.target

[Service]
User=kiosk
Environment=DISPLAY=:0
WorkingDirectory=/opt/kiosk
ExecStart=/usr/bin/python3 /opt/kiosk/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
```

### Вертикальний екран (xrandr)
```bash
# /etc/X11/Xsession.d/99-rotate
xrandr --output HDMI-1 --rotate right
unclutter -idle 0 -root &
```

---

## Порядок реалізації

1. `requirements.txt` + venv
2. `config.py`
3. `logging_setup.py`
4. `camera.py` (з mock-режимом)
5. `segmentation.py`
6. `pose.py`
7. `roles.py` (з кешуванням)
8. `overlay.py` (alpha-blend + auto-fit + crop)
9. `photo.py`
10. `photo_server.py` + `qr.py`
11. `ui.py` (всі екрани, touch-зони)
12. `admin.py`
13. `main.py` (state machine, --mock)
14. `systemd/kiosk.service` + `README_DEPLOY.md`
15. `generate_placeholders.py` (3 ролі + mock-кадр + Inter.ttf)

---

## Важливі деталі

- **Камера в окремому потоці**: `CameraThread(threading.Thread)` тримає `queue.Queue(maxsize=1)`, drop'ає старі кадри. Головний потік ніколи не блокується на `camera.read()`.
- **Fullscreen PyGame**: `pygame.display.set_mode((W, H), pygame.FULLSCREEN | pygame.NOFRAME)`.
- **Конвертація BGR/RGB**: OpenCV — BGR, PyGame — RGB. Конверсія `cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)` перед `pygame.surfarray.make_surface()`. Зверни увагу на `swapaxes(0,1)` через row-major.
- **Aspect ratio**: камера 1280×720 (16:9) → center-crop до 720×1280 (9:16) → ресайз до 1080×1920.
- **Розмір костюму**: PNG розробляється під 1080×1920 (9:16), з прозорим силуетом тіла. `pose.py` визначає, як scale/translate його під реального відвідувача.
- **Кешування**: `Image.open` і `resize` для костюма/фону — ТІЛЬКИ при завантаженні ролі (RoleManager). На рендері використовуємо готові `np.ndarray`.
- **Продуктивність**: якщо FPS < 20, зменшити FRAME_WIDTH/HEIGHT до 960×540 (зміниться тільки crop-логіка, екран лишається 1080×1920).
- **Mock-режим**: `python main.py --mock` → CameraThread читає `assets/dev/mock_frame.jpg`. Дозволяє повну розробку на Windows без камери.
- **Права**: `data/photos/` і `logs/` повинні бути writable для користувача `kiosk` на Linux.

---

## Чого НЕ робити

- ❌ Не використовувати `tkinter` — погано працює з відеопотоком
- ❌ Не використовувати `rembg` — важка модель, потребує інтернету
- ❌ Не блокувати головний потік читанням камери (тільки threaded)
- ❌ Не зберігати відео — тільки фото (PNG)
- ❌ Не використовувати `sudo` в коді
- ❌ Не імпортувати `pygame` у `config.py` (важко тестувати без display)
- ❌ Не використовувати `bitwise_and` для маски (фікс B2 — тільки float alpha-blend)
- ❌ Не ресайзити костюм/фон на кожному кадрі (кешувати в `Role`)
- ❌ Не композити в просторі кадру камери (тільки в просторі дисплея 1080×1920)
