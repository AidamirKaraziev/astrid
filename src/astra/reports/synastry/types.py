"""Модели данных для PDF синастрии."""

from __future__ import annotations

from dataclasses import dataclass

from reportlab.lib import colors


@dataclass(frozen=True, slots=True)
class PersonData:
    name: str
    subtitle: str
    accent: colors.Color
    planets: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class AspectData:
    aspect_type: str
    from_planet: str
    to_planet: str
    orb: str
    strength: str
    headline: str
    body: str


@dataclass(frozen=True, slots=True)
class MetricScore:
    label: str
    value: float
    color: colors.Color


@dataclass(frozen=True, slots=True)
class ZoneBlock:
    title: str
    color: colors.Color
    items: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SynastryReportData:
    """Полный контент mobile-first PDF синастрии."""

    person_a: PersonData
    person_b: PersonData
    tldr: str
    natal_insight: str
    metrics: tuple[MetricScore, ...]
    strong_aspects: tuple[AspectData, ...]
    working_aspects: tuple[AspectData, ...]
    zone_blocks: tuple[ZoneBlock, ...]
    conclusion_quote: str
    conclusion_tip: str
    working_aspects_intro: str = "Орб 2–6° — требуют внимания, дают точки роста"
    read_time_label: str = "~4 мин чтения"
    cta_text: str = "Забери еще одно предсказание"
