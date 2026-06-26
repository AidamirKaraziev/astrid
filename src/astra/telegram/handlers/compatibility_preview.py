"""Временный A/B: Astrid v3 через OpenRouter по кнопке «Совместимость»."""

from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import get_settings
from astra.llm.astrid_generate import generate_astrid_body
from astra.llm.factory import get_openrouter_provider
from astra.llm.prompts.astrid import pick_question_archetype
from astra.services.astro_service import build_context_for_date
from astra.telegram.button_texts import BTN_COMPATIBILITY
from astra.telegram.keyboards import main_menu_keyboard, prediction_followup_keyboard
from astra.users import crud as users_crud

logger = logging.getLogger(__name__)

router = Router(name="compatibility_preview")

COMPATIBILITY_LLM_IN_PROGRESS = (
    "Генерирую через <b>OpenRouter</b>…\n"
    "Тот же промпт, что в «Предсказание на сегодня» — сравни ответы ✨"
)
COMPATIBILITY_LLM_HEADER = (
    "🧪 <b>OpenRouter</b> — тот же промпт Astrid v3\n"
    "Сравни с «Предсказание на сегодня» (Ollama) и выбери, что лучше.\n\n"
)
OPENROUTER_NOT_CONFIGURED_TEXT = (
    "OpenRouter не настроен.\n"
    "Добавь <code>OPENROUTER_API_KEY</code> и <code>OPENROUTER_ENABLED=true</code> в .env"
)
_COMPATIBILITY_FAILURE_TEXT = {
    "disabled": OPENROUTER_NOT_CONFIGURED_TEXT,
    "timeout": "OpenRouter не ответил вовремя. Попробуй ещё раз чуть позже.",
    "connection": "Не удалось подключиться к OpenRouter. Проверь сеть и ключ.",
    "sanitize_empty": "Модель вернула пустой текст после очистки.",
    "empty_response": "Модель вернула пустой ответ.",
}


def _failure_message(reason: str) -> str:
    if reason in _COMPATIBILITY_FAILURE_TEXT:
        return _COMPATIBILITY_FAILURE_TEXT[reason]
    if reason.startswith("http_429"):
        return (
            "Free-модель на OpenRouter перегружена (лимит провайдера).\n"
            "Подожди 1–2 минуты и нажми снова. "
            "Лимит free: ~20 запросов/мин и ~50/день — см. openrouter.ai/docs."
        )
    if reason.startswith("http_"):
        detail = reason.split(":", 1)[1] if ":" in reason else ""
        code = reason.split(":", 1)[0].removeprefix("http_")
        if detail:
            return f"OpenRouter API: {code} — {detail}"
        return f"OpenRouter API вернул ошибку ({reason}). Проверь ключ на openrouter.ai."
    return "Не получилось сгенерировать ответ. Попробуй ещё раз."


def _today_for_profile(profile) -> date:  # noqa: ANN001
    return datetime.now(ZoneInfo(profile.timezone)).date()


@router.message(F.text == BTN_COMPATIBILITY)
async def compatibility_openrouter_preview(message: Message, session: AsyncSession) -> None:
    """Временно: OpenRouter с тем же Astrid-промптом для сравнения с Ollama."""
    if message.from_user is None:
        return

    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    if user is None or not user.onboarding_completed or user.profile is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return

    settings = get_settings()
    openrouter = get_openrouter_provider(settings)
    if not openrouter.is_configured():
        await message.answer(OPENROUTER_NOT_CONFIGURED_TEXT, parse_mode="HTML")
        return

    await message.answer(COMPATIBILITY_LLM_IN_PROGRESS, parse_mode="HTML")

    profile = user.profile
    target = _today_for_profile(profile)
    try:
        ctx, chart = await build_context_for_date(session, user, profile, target)
        archetype = pick_question_archetype(user.id, target)
        body, failure_reason = await generate_astrid_body(
            ctx,
            profile,
            chart,
            openrouter,
            settings,
            archetype=archetype,
        )
    except Exception:
        logger.exception("Compatibility OpenRouter preview failed for user %s", user.id)
        await message.answer(
            "Что-то пошло не так при подготовке данных. Попробуй позже.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if not body:
        await message.answer(
            _failure_message(failure_reason),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    model_label = settings.openrouter_model
    header = COMPATIBILITY_LLM_HEADER.replace(
        "<b>OpenRouter</b>",
        f"<b>OpenRouter</b> ({model_label})",
        1,
    )
    await message.answer(
        header + body,
        parse_mode="HTML",
        reply_markup=prediction_followup_keyboard(),
    )
