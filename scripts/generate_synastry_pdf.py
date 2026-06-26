"""CLI: генерация демо-PDF синастрии."""

from __future__ import annotations

import argparse
from pathlib import Path

from astra.reports.synastry import build_sample_report, generate_synastry_pdf


def main() -> None:
    parser = argparse.ArgumentParser(description="Сгенерировать mobile-first PDF синастрии")
    parser.add_argument(
        "-o",
        "--output",
        default="docs/output/synastry_aidamir_angela.pdf",
        help="Путь к выходному PDF",
    )
    parser.add_argument(
        "--bot-username",
        default=None,
        help="Telegram username для CTA (иначе из .env)",
    )
    args = parser.parse_args()
    path = generate_synastry_pdf(
        args.output,
        build_sample_report(),
        bot_username=args.bot_username,
    )
    print("PDF created:", path)


if __name__ == "__main__":
    main()
