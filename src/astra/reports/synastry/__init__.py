"""Публичный API генерации PDF синастрии."""

from __future__ import annotations

from pathlib import Path

from astra.reports.synastry.bot_link import resolve_telegram_bot_url
from astra.reports.synastry.builder import SynastryPdfBuilder
from astra.reports.synastry.fonts import register_synastry_fonts
from astra.reports.synastry.sample_data import build_prototype_report, build_sample_report
from astra.reports.synastry.types import (
    AspectData,
    MetricScore,
    PersonData,
    SynastryReportData,
    ZoneBlock,
)

__all__ = [
    "AspectData",
    "MetricScore",
    "PersonData",
    "SynastryPdfBuilder",
    "SynastryReportData",
    "ZoneBlock",
    "build_prototype_report",
    "build_sample_report",
    "generate_synastry_pdf",
    "resolve_telegram_bot_url",
]


def generate_synastry_pdf(
    output_path: str | Path,
    report: SynastryReportData | None = None,
    *,
    bot_username: str | None = None,
    referral_code: str | None = None,
) -> Path:
    """Собрать PDF и вернуть путь к файлу."""
    register_synastry_fonts()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = report or build_sample_report()
    SynastryPdfBuilder(
        str(path),
        data,
        bot_username=bot_username,
        referral_code=referral_code,
    ).build()
    return path
