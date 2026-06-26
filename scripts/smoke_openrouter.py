#!/usr/bin/env python3
"""Диагностика OpenRouter API: ключ, баланс, free-модели, тестовый запрос.

Запуск (читает .env через Settings, как остальные smoke-скрипты):
  uv run python scripts/smoke_openrouter.py
"""

from __future__ import annotations

import asyncio
import json

import httpx

from astra.core.config import get_settings

DEFAULT_TEST_MODEL = "google/gemma-4-26b-a4b-it:free"


def _extract_assistant_text(data: dict[str, object]) -> str:
    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""

    message = choices[0].get("message") or {}
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    reasoning = message.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning.strip()

    return ""


def _api_key() -> str:
    return get_settings().openrouter_api_key.strip()


def _base_url() -> str:
    return get_settings().openrouter_base_url.rstrip("/")


def _test_model() -> str:
    model = get_settings().openrouter_model.strip()
    return model or DEFAULT_TEST_MODEL


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # опционально для рейтинга на openrouter.ai
        "HTTP-Referer": "https://github.com/astra-bot",
        "X-OpenRouter-Title": "Astra",
    }


async def _fetch_json(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    base_url: str,
) -> tuple[int, object]:
    response = await client.request(method, f"{base_url}{path}")
    try:
        body = response.json()
    except Exception:
        body = response.text
    return response.status_code, body


def _is_free_model(model: dict[str, object]) -> bool:
    model_id = str(model.get("id") or "")
    if model_id.endswith(":free") or model_id == "openrouter/free":
        return True

    pricing = model.get("pricing")
    if not isinstance(pricing, dict):
        return False

    prompt = str(pricing.get("prompt") or "")
    completion = str(pricing.get("completion") or "")
    return prompt in {"0", "0.0", "0.00"} and completion in {"0", "0.0", "0.00"}


def _print_free_models(models: list[dict[str, object]], *, limit: int = 20) -> None:
    free = [m for m in models if _is_free_model(m)]
    print(f"Найдено free-моделей: {len(free)}")
    for model in free[:limit]:
        model_id = model.get("id")
        name = model.get("name")
        context = model.get("context_length")
        print(f"  - {model_id}  ({name}, ctx={context})")
    if len(free) > limit:
        print(f"  ... и ещё {len(free) - limit}. Полный список: https://openrouter.ai/models?fmt=table&order=pricing-low-to-high")


async def main() -> int:
    cfg = get_settings()
    api_key = _api_key()
    if not api_key:
        print("OPENROUTER_API_KEY пустой в .env")
        return 1

    base_url = _base_url()
    test_model = _test_model()
    print(f"BASE_URL={base_url}")
    print(f"TEST_MODEL={test_model}")
    print()

    async with httpx.AsyncClient(timeout=cfg.openrouter_timeout_seconds, headers=_headers(api_key)) as client:
        print("=== 1. Проверка ключа (GET /auth/key) ===")
        status, body = await _fetch_json(client, "GET", "/auth/key", base_url)
        print(f"HTTP {status}")
        if isinstance(body, dict):
            print(json.dumps(body, ensure_ascii=False, indent=2))
            if status != 200:
                print("\nКлюч не принят. Проверь OPENROUTER_API_KEY на https://openrouter.ai/keys")
                return 1
        else:
            print(body)
            return 1
        print()

        print("=== 2. Free-модели (GET /models) ===")
        status, body = await _fetch_json(client, "GET", "/models", base_url)
        print(f"HTTP {status}")
        if status == 200 and isinstance(body, dict):
            models = body.get("data") or []
            if isinstance(models, list):
                typed = [m for m in models if isinstance(m, dict)]
                _print_free_models(typed)
            else:
                print("Неожиданный формат /models")
        else:
            print(body)
        print()

        print(f"=== 3. Тест chat/completions (model={test_model}) ===")
        payload = {
            "model": test_model,
            "messages": [{"role": "user", "content": "Ответь одним словом: ок"}],
            "max_tokens": 16,
        }
        response = await client.post(f"{base_url}/chat/completions", json=payload)
        print(f"HTTP {response.status_code}")
        try:
            data = response.json()
        except Exception:
            print(response.text[:500])
            return 1

        if response.status_code != 200:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 1

        used_model = data.get("model")
        text = _extract_assistant_text(data)

        print(f"Модель в ответе: {used_model}")
        if text:
            print("OK:", text[:200])
            return 0

        print(json.dumps(data, ensure_ascii=False, indent=2)[:800])
        print("FAIL: пустой ответ")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
