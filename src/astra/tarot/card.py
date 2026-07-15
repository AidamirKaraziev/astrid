"""Датакласс карты таро — отдельный модуль, чтобы масти не импортировали deck циклически."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Arcana = Literal["major", "wands", "cups", "swords", "pentacles"]

ARCANA_LABELS_RU: dict[str, str] = {
    "major": "старший аркан",
    "wands": "жезлы",
    "cups": "кубки",
    "swords": "мечи",
    "pentacles": "пентакли",
}


@dataclass(frozen=True, slots=True)
class TarotCard:
    id: str  # "major_07", "wands_03", "cups_queen"
    name_ru: str
    arcana: Arcana
    number: int  # у старших 0–21; у мастей 1–14 (11 паж … 14 король)
    emoji: str
    keywords: tuple[str, ...]  # прямое положение
    astro_affinity: str  # планета/знак/декан по традиционной атрибуции, по-русски
    voice: str  # 1–2 фразы «голоса карты» для промпта
    keywords_reversed: tuple[str, ...] = field(default=())  # механика reversed — этап 2
    image_file: str | None = None  # не используется: путь к ассету по конвенции в images.py
