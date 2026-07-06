"""Модели данных для PDF разбора натальной карты."""

from __future__ import annotations

from dataclasses import dataclass, field

from astra.astro.schemas import FullNatalChart
from astra.reports.types import AspectData, MetricScore, ZoneBlock


@dataclass(frozen=True, slots=True)
class PlanetCard:
    """Карточка планеты: заголовок-факт + интерпретация."""

    point_key: str  # en-ключ для глифа: "Sun", "Moon", "Mercury"...
    title: str  # «Солнце в Близнецах · 9 дом»
    caption: str  # «ретроградный · обитель» или ''
    text: str


@dataclass(frozen=True, slots=True)
class SphereBlock:
    title: str  # «Призвание и карьера»
    factors: str  # «MC в Раке · Юпитер в 10 доме»
    text: str
    tip: str


@dataclass(frozen=True, slots=True)
class NatalReportData:
    """Полный контент mobile-first PDF натальной карты."""

    person_name: str
    person_subtitle: str  # «15.06.1990 · 14:30 · Москва»
    chart: FullNatalChart
    tldr: str
    core_story: str  # 3 абзаца через \n\n
    metrics: tuple[MetricScore, ...]
    personality: tuple[PlanetCard, ...]  # Солнце, Луна, ASC (если есть время)
    mind_feelings_action: tuple[PlanetCard, ...]  # Меркурий, Венера, Марс
    strong_aspects: tuple[AspectData, ...]
    working_aspects: tuple[AspectData, ...]
    spheres: tuple[SphereBlock, ...]
    karmic: tuple[PlanetCard, ...]  # узлы, Лилит
    zone_blocks: tuple[ZoneBlock, ...]  # сильные стороны / зоны роста / опоры
    practical_tips: tuple[str, ...]
    conclusion_quote: str
    conclusion_tip: str
    balance_note: str = ""  # комментарий к стихиям/крестам
    accuracy_note: str = ""  # пометка про отсутствие времени рождения
    working_aspects_intro: str = "Орб 2–6° — фоновые темы, дают точки роста"
    read_time_label: str = "~6 мин чтения"
    cta_text: str = "Получи свой прогноз на день"
