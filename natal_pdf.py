"""Генерация образца PDF натальной карты для итераций дизайна (без LLM)."""

from __future__ import annotations

from pathlib import Path

from astra.reports.natal.builder import generate_natal_pdf
from astra.reports.natal.sample_data import sample_natal_report


def _main() -> None:
    out = Path("docs/output/natal_sample.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    generate_natal_pdf(str(out), sample_natal_report())
    print("PDF created:", out)


if __name__ == "__main__":
    _main()
