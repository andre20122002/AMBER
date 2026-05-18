"""Локальний HTTP-сервер для віддачі фото — щоб телефон міг скачати по QR-коду.

Слухає на 0.0.0.0:QR_SERVER_PORT, віддає файли з data/photos/.
Працює в окремому потоці, не блокує main loop.
"""
import logging
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def _get_lan_ip() -> str:
    """Повертає IP в локальній мережі (через UDP-сокет без реального з'єднання)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class _PhotoHandler(SimpleHTTPRequestHandler):
    photos_root: Path = config.PHOTOS_DIR

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.photos_root), **kwargs)

    def log_message(self, format: str, *args) -> None:
        logger.info("photo_server: " + format, *args)

    def end_headers(self) -> None:
        # CORS на всякий випадок, плюс заборона кешу
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class PhotoHTTPServer:
    def __init__(self, port: int | None = None, host: str | None = None):
        self.port = port or config.QR_SERVER_PORT
        self.host = host or config.QR_BIND_HOST
        self.lan_ip = _get_lan_ip()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        config.PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        _PhotoHandler.photos_root = config.PHOTOS_DIR
        try:
            self._server = ThreadingHTTPServer((self.host, self.port), _PhotoHandler)
        except OSError as exc:
            logger.error("Could not bind photo HTTP server on %s:%d — %s", self.host, self.port, exc)
            return False
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Photo HTTP server started on http://%s:%d (LAN: %s)", self.host, self.port, self.lan_ip)
        return True

    def get_url(self, photo_path: Path) -> str:
        """Будує URL відносно self.lan_ip і кореня photos.

        Підтримує підпапки YYYY-MM-DD/.
        """
        rel = photo_path.relative_to(config.PHOTOS_DIR)
        # Path → posix-style для URL
        url_path = "/".join(rel.parts)
        return f"http://{self.lan_ip}:{self.port}/{url_path}"

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            logger.info("Photo HTTP server stopped")
