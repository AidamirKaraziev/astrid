#!/usr/bin/env python3
"""Диагностика Google Gemini API (AI Studio)."""

from __future__ import annotations

import asyncio
import sys

from astra.core.config import get_settings
from astra.llm import ChatMessage, CompletionRequest, get_gemini_provider


async def main() -> int:
    cfg = get_settings()
    if not cfg.gemini_api_key.strip():
        print("GEMINI_API_KEY пустой в .env")
        return 1

    print(f"GEMINI_BASE_URL={cfg.gemini_base_url}")
    print(f"GEMINI_MODEL={cfg.gemini_model}")
    print(f"GEMINI_ENABLED={cfg.gemini_enabled}")
    print()

    provider = get_gemini_provider(cfg)
    result = await provider.complete(
        CompletionRequest(
            messages=(ChatMessage("user", "Ответь одним словом: ок"),),
            max_tokens=16,
        ),
    )
    if result.text:
        print("OK:", result.text)
        return 0

    print("FAIL reason:", result.reason)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
