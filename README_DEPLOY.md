# Deploy kiosk на Linux (production)

## Передумови
- Debian/Ubuntu з графічною оболонкою (X11)
- Користувач `kiosk` з логіном без пароля
- Підключені: камера (USB), touchscreen 1080×1920 (HDMI)

## Кроки

### 1. Інсталяція
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv git unclutter x11-xserver-utils
sudo useradd -m -s /bin/bash kiosk
sudo mkdir -p /opt/kiosk /var/log/kiosk
sudo chown kiosk:kiosk /opt/kiosk /var/log/kiosk

sudo -u kiosk git clone <repo-url> /opt/kiosk
cd /opt/kiosk
sudo -u kiosk python3.11 -m venv .venv
sudo -u kiosk .venv/bin/pip install -r requirements.txt
```

### 2. Розворот екрана (вертикальний)
```bash
echo 'xrandr --output HDMI-1 --rotate right' | sudo tee /etc/X11/Xsession.d/99-rotate
echo 'unclutter -idle 0 -root &' | sudo tee -a /etc/X11/Xsession.d/99-rotate
sudo chmod +x /etc/X11/Xsession.d/99-rotate
```
*Скоригуй `HDMI-1` на свій вихід (`xrandr` без аргументів покаже доступні).*

### 3. systemd unit
```bash
sudo cp systemd/kiosk.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kiosk.service
sudo systemctl status kiosk.service
```

### 4. Логи
```bash
tail -f /opt/kiosk/logs/kiosk.log       # app-level
sudo journalctl -u kiosk.service -f      # systemd
```

### 5. QR-код у локальній мережі
Kiosk сам визначає LAN IP і слухає на `0.0.0.0:8080`. Переконайся, що:
- Wi-Fi роутер дозволяє внутрішні з'єднання (більшість дозволяє)
- Firewall (`ufw`) дозволяє 8080 на внутрішньому інтерфейсі:
  ```bash
  sudo ufw allow from 192.168.0.0/16 to any port 8080
  ```

### 6. Пароль адміна
За замовчуванням `1234` (з `config.ADMIN_PASSWORD_FALLBACK`). Щоб змінити:
```bash
sudo -u kiosk tee /opt/kiosk/admin.local.json <<EOF
{ "password": "ВАШ_СЕКРЕТНИЙ_ПАРОЛЬ" }
EOF
sudo -u kiosk chmod 600 /opt/kiosk/admin.local.json
sudo systemctl restart kiosk.service
```

## Перевірка
1. Reboot → kiosk запускається у fullscreen.
2. Туч → меню → роль → countdown → фото з QR.
3. Скан QR з телефона у тій же Wi-Fi → відкривається PNG → "Зберегти зображення".
4. F12 F12 → пароль → меню адміна.
