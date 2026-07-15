"""Пути к ассетам карт: конвенция {card_id}.jpg, скачаны scripts/fetch_tarot_images.py."""

from __future__ import annotations

from pathlib import Path

TAROT_IMAGES_DIR = Path(__file__).resolve().parent.parent / "telegram/static/tarot"


def image_path(card_id: str) -> Path | None:
    path = TAROT_IMAGES_DIR / f"{card_id}.jpg"
    return path if path.is_file() else None
