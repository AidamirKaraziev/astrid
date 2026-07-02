#!/usr/bin/env python3
"""Прототип PDF синастрии v2 (моки, без LLM)."""

from __future__ import annotations

import argparse

from astra.reports.synastry import build_prototype_report, generate_synastry_pdf


def main() -> None:
    parser = argparse.ArgumentParser(description="Сгенерировать прототип PDF синастрии v2")
    parser.add_argument(
        "-o",
        "--output",
        default="docs/output/synastry_prototype_v2.pdf",
        help="Путь к выходному PDF",
    )
    args = parser.parse_args()
    path = generate_synastry_pdf(args.output, build_prototype_report())
    print("PDF created:", path)


if __name__ == "__main__":
    main()
