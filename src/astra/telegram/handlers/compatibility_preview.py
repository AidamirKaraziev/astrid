"""Превью синастрии через DeepSeek по кнопке «Совместимость»."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import get_settings
from astra.llm.compatibility_generate import generate_compatibility_output
from astra.llm.factory import get_deepseek_provider
from astra.llm.prompts.compatibility_fixtures import build_aidamir_angela_prompt_input
from astra.llm.schemas.compatibility import CompatibilityLlmOutput
from astra.telegram.button_texts import BTN_COMPATIBILITY
from astra.telegram.keyboards import main_menu_keyboard, prediction_followup_keyboard
from astra.users import crud as users_crud

logger = logging.getLogger(__name__)

router = Router(name="compatibility_preview")

COMPATIBILITY_LLM_IN_PROGRESS = (
    "Генерирую разбор совместимости через <b>DeepSeek</b>…\n"
    "Промпт синастрии → JSON под PDF ✨"
)
COMPATIBILITY_LLM_HEADER = (
    "🧪 <b>DeepSeek</b> — превью синастрии\n"
    "Пока на эталонной паре Айдамир × Анжела (до FSM партнёра).\n\n"
)
DEEPSEEK_NOT_CONFIGURED_TEXT = (
    "DeepSeek не настроен.\n"
    "Добавь <code>DEEPSEEK_API_KEY</code> и <code>DEEPSEEK_ENABLED=true</code> в .env"
)
_COMPATIBILITY_FAILURE_TEXT = {
    "disabled": DEEPSEEK_NOT_CONFIGURED_TEXT,
    "timeout": "DeepSeek не ответил вовремя. Попробуй ещё раз чуть позже.",
    "connection": "Не удалось подключиться к DeepSeek. Проверь сеть и ключ.",
    "empty_response": "Модель вернула пустой ответ.",
}


def _failure_message(reason: str) -> str:
    if reason in _COMPATIBILITY_FAILURE_TEXT:
        return _COMPATIBILITY_FAILURE_TEXT[reason]
    if reason.startswith("http_429"):
        return (
            "DeepSeek вернул 429 — лимит запросов.\n"
            "Подожди минуту и попробуй снова."
        )
    if reason.startswith("http_"):
        detail = reason.split(":", 1)[1] if ":" in reason else ""
        code = reason.split(":", 1)[0].removeprefix("http_")
        if detail:
            return f"DeepSeek API: {code} — {detail}"
        return (
            f"DeepSeek API вернул ошибку ({reason}). "
            "Проверь ключ на platform.deepseek.com."
        )
    if reason.startswith(("json_invalid", "validation")):
        return f"Модель вернула невалидный JSON: {reason}"
    return "Не получилось сгенерировать ответ. Попробуй ещё раз."


def _format_metric_bars(output: CompatibilityLlmOutput) -> str:
    lines: list[str] = []
    for metric in output.metrics:
        pct = int(round(metric.value * 100))
        lines.append(f"• {metric.label}: {pct}%")
    return "\n".join(lines)


def _format_compatibility_preview(output: CompatibilityLlmOutput, *, model_label: str) -> str:
    header = COMPATIBILITY_LLM_HEADER.replace(
        "<b>DeepSeek</b>",
        f"<b>DeepSeek</b> ({model_label})",
        1,
    )
    parts = [
        header,
        f"<b>Краткий итог</b>\n{output.tldr}",
        f"<b>Метрики</b>\n{_format_metric_bars(output)}",
        f"<b>Натальный инсайт</b>\n{output.natal_insight}",
        f"<b>Вывод</b>\n{output.conclusion_quote}",
        f"<b>Практика на неделю</b>\n{output.conclusion_tip}",
    ]
    return "\n\n".join(parts)


@router.message(F.text == BTN_COMPATIBILITY)
async def compatibility_deepseek_preview(message: Message, session: AsyncSession) -> None:
    """Превью: промпт синастрии → DeepSeek V4-Flash → структурированный ответ."""
    if message.from_user is None:
        return

    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    if user is None or not user.onboarding_completed or user.profile is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return

    settings = get_settings()
    deepseek = get_deepseek_provider(settings)
    if not deepseek.is_configured():
        await message.answer(DEEPSEEK_NOT_CONFIGURED_TEXT, parse_mode="HTML")
        return

    await message.answer(COMPATIBILITY_LLM_IN_PROGRESS, parse_mode="HTML")

    prompt_input = build_aidamir_angela_prompt_input()
    try:
        output, failure_reason = await generate_compatibility_output(
            prompt_input,
            deepseek,
            settings,
        )
    except Exception:
        logger.exception("Compatibility DeepSeek preview failed for user %s", user.id)
        await message.answer(
            "Что-то пошло не так при генерации. Попробуй позже.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if output is None:
        await message.answer(
            _failure_message(failure_reason),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        _format_compatibility_preview(output, model_label=settings.deepseek_model),
        parse_mode="HTML",
        reply_markup=prediction_followup_keyboard(),
    )
