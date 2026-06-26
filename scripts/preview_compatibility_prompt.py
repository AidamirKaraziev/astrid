#!/usr/bin/env python3
"""Печать промпта совместимости для ручной отправки в LLM."""

from __future__ import annotations

import argparse

from astra.llm.prompts.compatibility import (
    build_compatibility_system_prompt,
    build_compatibility_user_message,
)
from astra.llm.prompts.compatibility_fixtures import build_aidamir_angela_prompt_input


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview compatibility LLM prompt")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Сохранить в файл (иначе stdout)",
    )
    parser.add_argument("--user-only", action="store_true", help="Только user message")
    args = parser.parse_args()

    data = build_aidamir_angela_prompt_input()
    parts = []
    if not args.user_only:
        parts.append("=== SYSTEM ===\n")
        parts.append(build_compatibility_system_prompt())
        parts.append("\n\n=== USER ===\n")
    parts.append(build_compatibility_user_message(data))
    text = "".join(parts)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print("Written:", args.output)
    else:
        print(text)


if __name__ == "__main__":
    main()
