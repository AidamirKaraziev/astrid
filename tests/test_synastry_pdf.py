"""Тесты генерации PDF синастрии."""

from __future__ import annotations

from pathlib import Path

import pytest

reportlab = pytest.importorskip("reportlab")

from astra.reports.synastry import (  # noqa: E402
    build_sample_report,
    generate_synastry_pdf,
    resolve_telegram_bot_url,
)


def test_resolve_telegram_bot_url_explicit() -> None:
    assert resolve_telegram_bot_url("my_bot") == "https://t.me/my_bot"
    assert resolve_telegram_bot_url("@my_bot") == "https://t.me/my_bot"


def test_resolve_telegram_bot_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "env_bot")
    assert resolve_telegram_bot_url() == "https://t.me/env_bot"


def test_generate_synastry_pdf_smoke(tmp_path: Path) -> None:
    out = tmp_path / "synastry.pdf"
    path = generate_synastry_pdf(out, build_sample_report())
    assert path.is_file()
    assert path.stat().st_size > 10_000


def test_sample_report_has_aspects() -> None:
    report = build_sample_report()
    assert len(report.strong_aspects) >= 1
    assert len(report.working_aspects) >= 1
    assert report.person_a.name and report.person_b.name
