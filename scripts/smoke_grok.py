#!/usr/bin/env python3
"""Диагностика xAI Grok API: ACL ключа, модель, тестовый запрос."""

from __future__ import annotations

import asyncio
import json
import sys

import httpx

from astra.core.config import get_settings
from astra.llm import ChatMessage, CompletionRequest, get_grok_provider


async def _fetch_json(client: httpx.AsyncClient, method: str, url: str) -> tuple[int, object]:
    response = await client.request(method, url)
    try:
        body = response.json()
    except Exception:
        body = response.text
    return response.status_code, body


async def main() -> int:
    cfg = get_settings()
    key = cfg.xai_api_key.strip()
    if not key:
        print("XAI_API_KEY пустой в .env")
        return 1
    if not cfg.grok_enabled:
        print("GROK_ENABLED=false — включи true для теста")

    base = cfg.grok_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {key}"}
    print(f"GROK_BASE_URL={base}")
    print(f"GROK_MODEL={cfg.grok_model}")
    print(f"GROK_ENABLED={cfg.grok_enabled}")
    print()

    async with httpx.AsyncClient(timeout=cfg.grok_timeout_seconds, headers=headers) as client:
        print("=== 1. Права API-ключа (GET /api-key) ===")
        status, body = await _fetch_json(client, "GET", f"{base}/api-key")
        print(f"HTTP {status}")
        print(json.dumps(body, ensure_ascii=False, indent=2) if isinstance(body, dict) else body)
        if isinstance(body, dict):
            if body.get("team_blocked"):
                print()
                print("⚠️  team_blocked=true — у команды нет кредитов/лицензии, API режет запросы (403).")
                print("   Открой console.x.ai → Billing / Team и активируй бесплатные кредиты.")
        print()

        print("=== 2. Доступные модели (GET /models) ===")
        status, body = await _fetch_json(client, "GET", f"{base}/models")
        print(f"HTTP {status}")
        if isinstance(body, dict):
            models = body.get("data") or []
            ids = [item.get("id") for item in models if isinstance(item, dict)]
            print("model ids:", ", ".join(ids[:20]) or "(пусто)")
            if cfg.grok_model not in ids:
                print(f"⚠️  GROK_MODEL={cfg.grok_model!r} нет в списке — смени модель в .env")
        else:
            print(body)
        print()

        print("=== 3. Тест chat/completions через GrokProvider ===")
        provider = get_grok_provider(cfg)
        result = await provider.complete(
            CompletionRequest(
                messages=(ChatMessage("user", "Ответь одним словом: ок"),),
                max_tokens=8,
            ),
        )
        if result.text:
            print("OK:", result.text)
            return 0

        print("FAIL reason:", result.reason)
        if result.reason.startswith("http_403"):
            print()
            print("Частые причины 403:")
            print("  • У ключа нет ACL api-key:endpoint:chat")
            print("  • У ключа нет ACL на модель (api-key:model:<id> или api-key:model:*)")
            print("  • Ключ создан без прав в https://console.x.ai → API Keys")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
