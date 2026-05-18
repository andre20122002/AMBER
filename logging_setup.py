"""Налаштування логування з ротацією файлів + дублюванням у stdout."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import config


def setup_logging(log_dir: Path | None = None, level: str | None = None) -> logging.Logger:
    log_dir = log_dir or config.LOG_DIR
    level = level or config.LOG_LEVEL

    log_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_dir / "kiosk.log",
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    return root
