# AMBER — «Побач себе в майбутньому»

Інтерактивна kiosk-інсталяція для музею мініатюр. Відвідувач стає перед камерою на вертикальному екрані-«дзеркалі» і бачить себе в ролі видатної особистості (президент, науковець, дипломат…) — у режимі реального часу, з PNG-костюмом, тематичним фоном і QR-кодом для скачування фото на телефон.

```
┌──────────────────────┐
│   2045               │  ← рік ролі
│                      │
│      ╭───╮           │  ← обличчя відвідувача
│     │     │          │     (з камери, сегментоване)
│      ╲___╱           │
│   ┌──┴───┴──┐        │  ← PNG-костюм, auto-fit
│   │  ░░░░░  │        │     під плечі (MediaPipe Pose)
│   │ ░тіло░  │        │
│                      │
│  Президент України   │  ← title + slogan
│   Слоган про мрію    │
└──────────────────────┘
```

---

## Як це працює (у двох реченнях)

OpenCV знімає з камери, MediaPipe SelfieSegmentation вирізає фігуру з фону, MediaPipe Pose знаходить плечі для auto-fit костюма, а потім alpha-blending композитує чотири шари (фон ролі → людина → PNG-костюм → текст) у просторі дисплея 1080×1920. Усе впродовж 30 FPS у головному циклі pygame; камера читається в окремому потоці, ресурси ролі кешуються при завантаженні.

---

## Стек

| Шар | Бібліотека |
|---|---|
| Мова | Python 3.11 / 3.12 |
| Відео / композиція | OpenCV `opencv-python==4.10.*` |
| Сегментація фігури | MediaPipe `SelfieSegmentation` |
| Pose / auto-fit костюма | MediaPipe `PoseLandmarker` |
| PNG з прозорістю | Pillow `>=10` |
| UI / fullscreen | PyGame `2.6.*` |
| QR-код | `qrcode[pil]==7.4.*` |
| HTTP для QR | `http.server` (stdlib) |
| Production runtime | systemd, unclutter, xrandr (Linux) |

---

## Setup для нових розробників

Все, що треба зробити після `git clone`. Потрібно ~10 хв і ~500 МБ диска (Python + залежності).

### Windows

**1. Встановити Python 3.12** (mediapipe не підтримує 3.13+):

```powershell
# Перевірити, чи вже є
py -3.12 --version

# Якщо нема — поставити через winget (per-user, без UAC):
winget install Python.Python.3.12
```

Альтернатива: завантажити інсталятор з [python.org/downloads/release/python-3120/](https://www.python.org/downloads/release/python-3120/) і поставити.

**2. Створити віртуальне середовище і поставити залежності:**

```powershell
cd <папка-проекту>
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Якщо `Activate.ps1` блокується політикою — або виконати один раз:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
…або просто використовувати `.\.venv\Scripts\python.exe` напряму (без активації).

**3. Згенерувати placeholder-графіку** (3 тестові ролі + mock-кадр):

```powershell
python generate_placeholders.py
```

Це створить:
- `assets/roles/{president, scientist, diplomat}/` — простенькі PNG-костюми
- `assets/dev/mock_frame.jpg` — кадр-замінник камери для розробки
- `assets/ui/idle_background.jpg` — фон заставки

**4. (Опційно) Завантажити шрифт** з кирилицею як `assets/ui/fonts/Inter-Regular.ttf`:

```powershell
# Будь-який TTF з кирилицею підійде. Наприклад, Roboto:
$ProgressPreference='SilentlyContinue'
Invoke-WebRequest `
  -Uri "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf" `
  -OutFile "assets\ui\fonts\Inter-Regular.ttf"
```

Без цього кроку UI працює, але pygame fallback на системний шрифт — може погано рендерити кирилицю.

**5. Запустити в dev-режимі:**

```powershell
# Зменшене вікно 540×960 з mock-камерою (зручно для звичайного монітора)
python main.py --mock --windowed --scale 0.5
```

`Esc` — вихід. `F12` `F12` → пароль `1234` → адмін.

**6. (Перевірка) Регресійний smoke-тест без display:**

```powershell
python smoke_test.py
```

Має вивести `OK` за ~5 секунд. Якщо так — все працює.

### Linux / macOS

Аналогічно, тільки команди дещо інші:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python generate_placeholders.py
python main.py --mock --windowed --scale 0.5
```

На Linux може знадобитись `apt install libgl1` (для OpenCV) та `apt install python3.12-venv`.

### Troubleshooting

| Симптом | Причина / рішення |
|---|---|
| `Could not find a version that satisfies the requirement mediapipe` | Використовується Python 3.13+. MediaPipe 0.10.x працює тільки на 3.9–3.12. Створіть venv на 3.12. |
| `pygame.error: No available video device` | На headless-системі (CI, SSH без X). Використайте `smoke_test.py` (він ставить `SDL_VIDEODRIVER=dummy`). |
| Вікно вище за монітор (1920px) | Запустіть з `--scale 0.5` — вікно стане 540×960. |
| `WARNING: Font not found` | Не завантажено `assets/ui/fonts/Inter-Regular.ttf`. UI працює, але кирилиця може ламатися. |
| Камера не відкривається (без `--mock`) | Перевірте `config.CAMERA_INDEX` (0 за замовчуванням), і що камера не зайнята іншим процесом (Zoom, OBS). |
| `Address already in use: 0.0.0.0:8080` | Інший процес тримає порт. Змініть `QR_SERVER_PORT` у `config.py`. |

---

## Інтерфейс

Стани UI керовані `AppState` enum у `main.py`:

| Стан | Що показує | Як виходимо |
|---|---|---|
| `IDLE` | Заставка «торкніться, щоб почати» | Тап → `MENU` |
| `MENU` | Список ролей як touch-кнопки | Тап на роль → `COUNTDOWN`; timeout 30 с → `IDLE` |
| `COUNTDOWN` | Live overlay + цифри 3-2-1 | Після 3 с → знімок → `PHOTO_QR` |
| `PHOTO_QR` | Фото + QR-код на скачування | Тап / timeout 15 с → `IDLE` |
| `ADMIN` | Пароль → меню адміна | Esc / кнопка «Закрити» |

`F12 F12` з будь-якого стану → `ADMIN` (пароль `1234` за замовчуванням, або з `admin.local.json`).

---

## Структура проєкту

```
.
├── main.py                  # state machine, головний цикл, CLI
├── config.py                # усі константи (без імпорту pygame)
├── logging_setup.py         # RotatingFileHandler + stderr
├── camera.py                # threaded capture + --mock
├── segmentation.py          # MediaPipe SelfieSegmentation, float-маска
├── pose.py                  # MediaPipe Pose → плечі/голова для auto-fit
├── roles.py                 # RoleManager: scan + кеш ресайзнутих PNG/JPG
├── overlay.py               # alpha-blend + auto-fit + center-crop + текст
├── photo.py                 # save_photo() → data/photos/...
├── photo_server.py          # http.server у потоці — віддача фото для QR
├── qr.py                    # url → BGR np.ndarray QR-коду
├── ui.py                    # рендер 5 екранів, touch-зони
├── admin.py                 # подвійне F12, пароль, меню
├── generate_placeholders.py # dev-only: 3 ролі + mock-кадр
├── smoke_test.py            # dev-only: ініціалізація + цикл без display
│
├── assets/
│   ├── roles/<id>/{costume.png, background.jpg, meta.json}
│   ├── ui/{idle_background.jpg, fonts/Inter-Regular.ttf}
│   └── dev/mock_frame.jpg
│
├── data/photos/<YYYY-MM-DD>/photo_<HHMMSS>.png   # gitignored
├── logs/kiosk.log                                 # gitignored
├── systemd/kiosk.service
├── requirements.txt
├── README_DEPLOY.md         # інструкція production-deploy на Linux
└── CLAUDE.md                # повна архітектура (джерело істини для AI-агентів)
```

---

## Додати нову роль

Створи нову папку в `assets/roles/<id>/` з трьома файлами:

```
assets/roles/astronaut/
├── costume.png      # RGBA 1080×1920, дизайн-плечі на (0.5, 0.28), ширина 0.45
├── background.jpg   # 1080×1920
└── meta.json
```

`meta.json`:
```json
{
  "id": "astronaut",
  "title": "Космонавт",
  "year": 2060,
  "slogan": "Зорі — це твій новий дім",
  "button_label": "Космонавт"
}
```

Перезапусти або натисни `F12 F12 → Перезавантажити ролі` в адмін-панелі.

Якщо ваші костюми мають інші дизайн-плечі, поправ константи `COSTUME_DESIGN_SHOULDERS_CY` / `COSTUME_DESIGN_SHOULDERS_W` у `overlay.py`.

---

## CLI флаги

```
python main.py                          # production: справжня камера, fullscreen
python main.py --mock                   # mock-кадр з assets/dev/mock_frame.jpg
python main.py --windowed               # вікно замість fullscreen (Esc — вийти)
python main.py --scale 0.5              # вікно 540×960 замість 1080×1920
python main.py --mock --windowed --scale 0.5   # стандартний dev-режим
```

`--scale` робить рендер у внутрішній `Surface 1080×1920` і потім масштабує до меншого вікна; тач-координати інверс-масштабуються, тому всі кнопки лишаються кликабельними.

---

## QR-код: як це працює

Після знімка `photo_server.py` (вже піднятий на старті на `0.0.0.0:8080`) віддає файли з `data/photos/`. QR кодує URL виду `http://<LAN_IP>:8080/2026-05-18/photo_HHMMSS.png`. Телефон у тій самій Wi-Fi сканує → у браузері відкривається PNG → «зберегти зображення».

Якщо HTTP-сервер не зміг забіндитись (порт зайнятий), стан `PHOTO_QR` показує тільки фото з текстом «фото збережено локально».

---

## Production deploy

Див. [`README_DEPLOY.md`](README_DEPLOY.md) — повна інструкція для Linux + systemd + xrandr + unclutter.

Коротко:
```bash
sudo cp systemd/kiosk.service /etc/systemd/system/
sudo systemctl enable --now kiosk.service
journalctl -u kiosk.service -f
```

---

## Конфігурація

Усе в `config.py`. Ключові параметри:

| Константа | За замовчуванням | Що робить |
|---|---|---|
| `DISPLAY_WIDTH × HEIGHT` | 1080 × 1920 | Розмір вікна / fullscreen |
| `FRAME_WIDTH × HEIGHT` | 1280 × 720 | Захоплення з камери |
| `TARGET_FPS` | 30 | Цільовий FPS головного циклу |
| `COUNTDOWN_SECONDS` | 3 | Тривалість 3-2-1 перед знімком |
| `IDLE_TIMEOUT` | 30 | Сек до повернення на IDLE з MENU |
| `PHOTO_QR_DISPLAY` | 15 | Сек показу фото з QR |
| `QR_SERVER_PORT` | 8080 | Порт локального HTTP |
| `ADMIN_PASSWORD_FALLBACK` | `1234` | Пароль, якщо нема `admin.local.json` |

---

## Архітектурні рішення

- **Камера у власному потоці** з `queue.Queue(maxsize=1)` — головний потік ніколи не блокується на `cv2.VideoCapture.read()`. Старі кадри дропаються.
- **Композиція в просторі дисплея**, не камери. Кадр 16:9 центральним кропом → 9:16 → ресайз до 1080×1920. Інакше PNG-костюм 9:16 стискався б до 16:9.
- **Alpha-blending через float-маску** [0..1], а не `cv2.bitwise_and` — щоб GaussianBlur маски насправді давав м'які краї.
- **Auto-fit костюма за позою**: MediaPipe Pose дає плечі, affine warp масштабує і зсуває PNG так, щоб дизайн-плечі збігалися з реальними. Якщо позу не виявлено — дефолтна позиція центру.
- **Кешування ресурсів ролі**: PNG і фон ресайзяться один раз при завантаженні в `RoleManager`, не на кожному кадрі.
- **`config.py` без `import pygame`** — щоб модуль був придатний для тестів/CI без display.

Повна архітектура з обґрунтуванням рішень — у [`CLAUDE.md`](CLAUDE.md).

---

## Розробка

- Запуск без камери: `python main.py --mock --windowed`
- Тест окремого модуля (камера, сегментація, поза): `python -m camera --mock`, `python -m segmentation --mock`, `python -m pose --mock`
- Регресійний smoke-тест: `python smoke_test.py` (працює без display через `SDL_VIDEODRIVER=dummy`)
- Логи: `logs/kiosk.log` (rotated, 10MB × 5)

---

## Чого НЕ робити

- ❌ Tkinter — погано з відеопотоком
- ❌ `rembg` — важка модель, потребує інтернету
- ❌ Блокувати головний потік на `cv2.VideoCapture.read()`
- ❌ Зберігати відео (тільки PNG-фото)
- ❌ `sudo` в коді
- ❌ `import pygame` у `config.py`
- ❌ `bitwise_and` для сегментації (тільки float alpha-blend)
- ❌ Ресайз костюма/фону на кожному кадрі (кешувати у `Role`)
