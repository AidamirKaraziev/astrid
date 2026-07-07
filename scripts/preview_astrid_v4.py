"""Превью Astrid v4: контекст, промпт и (опционально) живой вызов DeepSeek.

Запуск:
    uv run python scripts/preview_astrid_v4.py                # только промпт
    uv run python scripts/preview_astrid_v4.py --generate     # + вызов LLM
    uv run python scripts/preview_astrid_v4.py --date 2026-07-08
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime

from astra.astro.calculator import build_full_natal_chart
from astra.astro.daily_context import build_daily_context_v2
from astra.llm.prompts.astrid import pick_question_archetype
from astra.llm.prompts.astrid_v4 import SYSTEM_PROMPT_V4, build_user_message_v4
from uuid import UUID


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--generate", action="store_true", help="вызвать LLM")
    parser.add_argument("--birth", default="1990-06-15T14:30", help="ISO дата-время рождения")
    parser.add_argument("--no-time", action="store_true", help="без времени рождения")
    parser.add_argument("--tarot", action="store_true", help="+ вытянуть и раскрыть карту")
    args = parser.parse_args()

    birth_dt = datetime.fromisoformat(args.birth)
    target = date.fromisoformat(args.date)

    chart = build_full_natal_chart(
        name="Превью",
        birth_date=birth_dt.date(),
        birth_time=None if args.no_time else birth_dt,
        lat=55.7558,
        lon=37.6176,
        timezone="Europe/Moscow",
    )
    archetype = pick_question_archetype(UUID(int=42), target)
    ctx = build_daily_context_v2(
        chart, target, accuracy_tier=33 if args.no_time else 100,
        question_archetype_id=archetype.id,
    )

    print("=== КОНТЕКСТ V2 ===")
    print(json.dumps(ctx.model_dump(mode="json"), ensure_ascii=False, indent=2))
    print("\n=== SYSTEM ===")
    print(SYSTEM_PROMPT_V4)
    print("\n=== USER ===")
    print(build_user_message_v4(ctx))

    if args.generate:
        from astra.llm.daily_llm import generate_daily_body_v4

        body, reason = asyncio.run(generate_daily_body_v4(ctx))
        print("\n=== ОТВЕТ LLM ===")
        print(body if body else f"ОШИБКА: {reason}")
        if body:
            from types import SimpleNamespace

            from astra.services.prediction_service import format_compass_message

            fake = SimpleNamespace(text=body, astro_context=ctx.model_dump(mode="json"))
            print("\n=== УТРЕННЕЕ СООБЩЕНИЕ (HTML) ===")
            print(format_compass_message(fake))

            if args.tarot:
                from astra.llm.prompts.astrid import sanitize_prediction_output
                from astra.llm.prompts.tarot_daily import (
                    TAROT_SYSTEM_PROMPT,
                    build_tarot_user_message,
                    validate_tarot_output,
                )
                from astra.llm.types import ChatMessage, CompletionRequest
                from astra.llm.daily_llm import get_daily_provider
                from astra.core.config import get_settings
                from astra.services.tarot_daily_service import format_tarot_reveal
                from astra.tarot.draw import draw_card

                card = draw_card()
                print(f"\n=== ВЫТЯНУТА КАРТА: {card.name_ru} {card.emoji} ===")
                cfg = get_settings()
                provider = get_daily_provider(cfg)
                result = asyncio.run(
                    provider.complete(
                        CompletionRequest(
                            messages=(
                                ChatMessage("system", TAROT_SYSTEM_PROMPT),
                                ChatMessage(
                                    "user",
                                    build_tarot_user_message(
                                        card, ctx.model_dump(mode="json")
                                    ),
                                ),
                            ),
                            temperature=0.8,
                            max_tokens=450,
                            timeout_seconds=cfg.deepseek_timeout_seconds,
                            extra={"thinking_disabled": True},
                        ),
                    ),
                )
                from astra.llm.prompts.tarot_daily import normalize_tarot_blocks

                cleaned = sanitize_prediction_output(result.text or "") or (result.text or "")
                cleaned = normalize_tarot_blocks(cleaned)
                err = validate_tarot_output(cleaned)
                if err:
                    print(f"ВАЛИДАЦИЯ НЕ ПРОШЛА: {err}\n{result.text}")
                else:
                    print("\n=== СООБЩЕНИЕ КАРТЫ (HTML) ===")
                    print(format_tarot_reveal(card, cleaned))


if __name__ == "__main__":
    _main()
