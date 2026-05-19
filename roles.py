"""RoleManager: завантаження ролей з assets/roles/ + кешування PNG/JPG ресайзнутих до DISPLAY.

Поламані ролі (битий meta.json, відсутні файли) пропускаються з log-попередженням.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import config

logger = logging.getLogger(__name__)


@dataclass
class Role:
    id: str
    title: str
    year: int
    slogan: str
    button_label: str
    dir: Path
    # Кешовані ресайзнуті ассети (заповнюються в RoleManager._load_role)
    costume_rgba: np.ndarray  # (DISPLAY_H, DISPLAY_W, 4) uint8
    background_bgr: np.ndarray  # (DISPLAY_H, DISPLAY_W, 3) uint8
    # Опційні per-role anchor overrides (де у дизайні костюма «плечі»)
    anchor_cy: float = 0.28
    anchor_w: float = 0.45


class RoleManager:
    def __init__(self, roles_dir: Path | None = None):
        self.roles_dir = roles_dir or config.ROLES_DIR
        self.roles: list[Role] = []
        self._reload()

    def _reload(self) -> None:
        self.roles.clear()
        if not self.roles_dir.exists():
            logger.warning("Roles directory does not exist: %s", self.roles_dir)
            return
        for sub in sorted(self.roles_dir.iterdir()):
            if not sub.is_dir():
                continue
            try:
                role = self._load_role(sub)
                self.roles.append(role)
                logger.info("Loaded role: %s (%s)", role.id, role.title)
            except Exception as exc:
                logger.warning("Skipping role %s: %s", sub.name, exc)

    def _load_role(self, role_dir: Path) -> Role:
        meta_path = role_dir / "meta.json"
        costume_path = role_dir / "costume.png"
        bg_path = role_dir / "background.jpg"

        if not meta_path.exists():
            raise FileNotFoundError(f"meta.json missing in {role_dir}")
        if not costume_path.exists():
            raise FileNotFoundError(f"costume.png missing in {role_dir}")
        if not bg_path.exists():
            raise FileNotFoundError(f"background.jpg missing in {role_dir}")

        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        required = ("id", "title", "year", "slogan", "button_label")
        for key in required:
            if key not in meta:
                raise ValueError(f"meta.json missing key: {key}")

        # Костюм: RGBA з ресайзом до DISPLAY (LANCZOS для якості)
        costume_pil = Image.open(costume_path).convert("RGBA")
        costume_pil = costume_pil.resize((config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT), Image.LANCZOS)
        costume_rgba = np.array(costume_pil)  # (H, W, 4) uint8 RGBA

        # Фон: BGR із ресайзом до DISPLAY
        bg = cv2.imread(str(bg_path))
        if bg is None:
            raise ValueError(f"Could not read background image: {bg_path}")
        background_bgr = cv2.resize(bg, (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT), interpolation=cv2.INTER_AREA)

        anchor = meta.get("costume_anchor") or {}
        return Role(
            id=meta["id"],
            title=meta["title"],
            year=int(meta["year"]),
            slogan=meta["slogan"],
            button_label=meta["button_label"],
            dir=role_dir,
            costume_rgba=costume_rgba,
            background_bgr=background_bgr,
            anchor_cy=float(anchor.get("shoulders_cy", 0.28)),
            anchor_w=float(anchor.get("shoulders_w", 0.45)),
        )

    def list(self) -> list[Role]:
        return list(self.roles)

    def by_id(self, role_id: str) -> Role | None:
        for r in self.roles:
            if r.id == role_id:
                return r
        return None


if __name__ == "__main__":
    from logging_setup import setup_logging
    setup_logging()
    mgr = RoleManager()
    print(f"Loaded {len(mgr.roles)} role(s):")
    for r in mgr.roles:
        print(f"  - {r.id:15s} {r.title:30s} costume={r.costume_rgba.shape} bg={r.background_bgr.shape}")
