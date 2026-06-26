#!/usr/bin/env python3
"""Диагностика DeepSeek API: ping и (опционально) синастрия на эталонной паре.

Запуск (читает .env через Settings):
  uv run python scripts/smoke_deepseek.py
  uv run python scripts/smoke_deepseek.py --compatibility
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx

from astra.core.config import get_settings
from astra.llm.compatibility_generate import generate_compatibility_output
from astra.llm.factory import get_deepseek_provider
from astra.llm.prompts.compatibility_fixtures import build_aidamir_angela_prompt_input


async def _ping(cfg) -> int:  # noqa: ANN001
    url = f"{cfg.deepseek_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.deepseek_api_key.strip()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg.deepseek_model,
        "messages": [{"role": "user", "content": "Ответь одним словом: ок"}],
        "max_tokens": 16,
        "thinking": {"type": "disabled"},
    }

    print(f"=== 1. Ping ({cfg.deepseek_model}) ===")
    async with httpx.AsyncClient(timeout=cfg.deepseek_timeout_seconds) as client:
        response = await client.post(url, json=payload, headers=headers)
    print(f"HTTP {response.status_code}")

    try:
        data = response.json()
    except Exception:
        print(response.text[:500])
        return 1

    if response.status_code != 200:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 1

    choices = data.get("choices") or []
    text = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        if isinstance(message, dict):
            text = str(message.get("content") or "").strip()

    usage = data.get("usage")
    print(f"Ответ: {text or '(пусто)'}")
    if isinstance(usage, dict):
        print(
            "Usage:",
            f"prompt={usage.get('prompt_tokens')}",
            f"completion={usage.get('completion_tokens')}",
            f"total={usage.get('total_tokens')}",
        )
    print()
    return 0 if text else 1


async def _compatibility(cfg) -> int:  # noqa: ANN001
    provider = get_deepseek_provider(cfg)
    if not provider.is_configured():
        print("DeepSeek не настроен (DEEPSEEK_ENABLED + DEEPSEEK_API_KEY)")
        return 1

    print("=== 2. Синастрия (Айдамир × Анжела) ===")
    prompt_input = build_aidamir_angela_prompt_input()
    output, reason = await generate_compatibility_output(prompt_input, provider, cfg)
    if output is None:
        print(f"FAIL: {reason}")
        return 1

    print(f"OK: tldr ({len(output.tldr)} chars)")
    print(output.tldr[:200] + ("…" if len(output.tldr) > 200 else ""))
    print(f"metrics={len(output.metrics)} strong={len(output.strong_aspects)} working={len(output.working_aspects)}")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test DeepSeek API")
    parser.add_argument(
        "--compatibility",
        action="store_true",
        help="Полный запрос синастрии на эталонной паре (~7k tokens)",
    )
    args = parser.parse_args()

    cfg = get_settings()
    if not cfg.deepseek_api_key.strip():
        print("DEEPSEEK_API_KEY пустой в .env")
        print("Пример: DEEPSEEK_ENABLED=true DEEPSEEK_API_KEY=sk-... uv run python scripts/smoke_deepseek.py")
        return 1

    print(f"BASE_URL={cfg.deepseek_base_url}")
    print(f"MODEL={cfg.deepseek_model}")
    print()

    code = await _ping(cfg)
    if code != 0:
        return code

    if args.compatibility:
        return await _compatibility(cfg)

    print("Подсказка: полный тест синастрии — добавь --compatibility")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
