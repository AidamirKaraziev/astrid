"""Генерация PDF совместимости для Telegram."""

from __future__ import annotations

import tempfile
from pathlib import Path

from astra.reports.synastry import generate_synastry_pdf
from astra.reports.synastry.stub_report import build_aidamir_angela_stub_report

STUB_PDF_FILENAME = "synastry-aidamir-angela.pdf"


def render_stub_compatibility_pdf() -> Path:
    """Собрать временный PDF эталонной пары (заглушка до LLM + FSM партнёра)."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        path = Path(tmp.name)
    generate_synastry_pdf(path, build_aidamir_angela_stub_report())
    return path
