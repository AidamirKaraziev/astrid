"""Deprecated: используй astra.reports.synastry или scripts/generate_synastry_pdf.py."""

from __future__ import annotations

from astra.reports.synastry import build_sample_report, generate_synastry_pdf

__all__ = ["generate_synastry_pdf"]


def _main() -> None:
    path = generate_synastry_pdf("docs/output/synastry_aidamir_angela.pdf", build_sample_report())
    print("PDF created:", path)


if __name__ == "__main__":
    _main()
