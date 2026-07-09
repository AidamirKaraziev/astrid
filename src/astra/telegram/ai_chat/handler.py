"""AI-чат Astrid: точка входа в aiogram.

Ловит свободный текст (когда пользователь НЕ в FSM-флоу и не нажал кнопку) и
ведёт разговор через Astrid. Когда данных достаточно (`ready_to_route`), мягко
передаёт управление реальному продукту — кнопкой, а не автопрыжком, чтобы
пользователь оставался хозяином и мы не ломали существующие FSM-хендлеры.

Включается флагом `ai_chat_enabled` (по умолчанию выкл). Роутер регистрируется
ПОСЛЕДНИМ, поэтому кнопки меню и активные FSM перехватываются раньше — конфликтов нет.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import get_logger
from astra.telegram.ai_chat.agent import run_astrid
from astra.telegram.ai_chat.intents import AstridReply, Intent
from astra.users import crud as users_crud

log = get_logger(__name__)

router = Router(name="ai_chat")

# Куда ведёт кнопка «продолжить» для каждого продукта: callback_data существующих флоу.
_ROUTE_CALLBACK: dict[Intent, str] = {
    Intent.compatibility: "compatibility:start",   # см. handlers/compatibility.py
    Intent.natal: "natal:start",                   # см. handlers/natal.py
    Intent.daily_prediction: "menu:prediction",
    Intent.tarot: "menu:tarot",
    Intent.edit_profile: "profile:open",
    Intent.invite: "menu:invite",
}

_ROUTE_LABEL: dict[Intent, str] = {
    Intent.compatibility: "💕 Запустить совместимость",
    Intent.natal: "🌌 Собрать натальную карту",
    Intent.daily_prediction: "🔮 Показать предсказание",
    Intent.tarot: "🔮 Разложить карты",
    Intent.edit_profile: "✨ Открыть профиль",
    Intent.invite: "🎁 Пригласить друга",
}

_HISTORY_KEY = "ai_chat_history"


def _route_keyboard(reply: AstridReply) -> InlineKeyboardMarkup | None:
    """Кнопка перехода в реальный флоу — показываем, когда Astrid готова роутить."""
    if not reply.ready_to_route or reply.intent == Intent.smalltalk:
        return None
    cb = _ROUTE_CALLBACK.get(reply.intent)
    label = _ROUTE_LABEL.get(reply.intent)
    if not cb or not label:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=cb)]]
    )


@router.message(StateFilter(None), F.text & ~F.text.startswith("/"))
async def ai_chat_turn(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """Одна реплика диалога с Astrid (только вне FSM, только свободный текст)."""
    user_text = (message.text or "").strip()
    if not user_text:
        return

    tg_id = message.from_user.id if message.from_user else None
    user_name = None
    if tg_id is not None:
        user = await users_crud.get_user_by_telegram_id(session, tg_id)
        if user and user.profile:
            user_name = user.profile.display_name

    data = await state.get_data()
    history: list[dict[str, str]] = data.get(_HISTORY_KEY, [])

    await message.chat.do("typing")
    reply = await run_astrid(history, user_text, user_name=user_name)

    # Сохраняем диалог в FSM-хранилище (Redis) — state как память разговора.
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply.reply})
    await state.update_data({_HISTORY_KEY: history[-24:]})

    log.info(
        "ai_chat.turn",
        intent=reply.intent.value,
        ready=reply.ready_to_route,
        missing=reply.missing,
    )
    await message.answer(reply.reply, reply_markup=_route_keyboard(reply))


@router.callback_query(F.data == "ai_chat:reset")
async def ai_chat_reset(callback: CallbackQuery, state: FSMContext) -> None:
    """Сбросить память разговора (кнопка «начать заново»)."""
    data = await state.get_data()
    data.pop(_HISTORY_KEY, None)
    await state.set_data(data)
    if callback.message:
        await callback.message.answer("Начнём с чистого листа ✨ О чём поговорим?")
    await callback.answer()
