"""AI-чат Astrid: точка входа в aiogram.

Ловит свободный текст (когда пользователь НЕ в FSM-флоу и не нажал кнопку) и
ведёт разговор через Astrid. Когда данных достаточно (`ready_to_route`), мягко
передаёт управление реальному продукту — вызывает ту же функцию входа, что и
кнопка меню, с настоящим сообщением пользователя. Существующие FSM-хендлеры не
переписываются: мы просто зовём их точку входа.

Включается флагом `ai_chat_enabled` (по умолчанию выкл). Роутер регистрируется
ПОСЛЕДНИМ, поэтому кнопки меню и активные FSM перехватываются раньше — конфликтов нет.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import get_logger
from astra.telegram.ai_chat.agent import run_astrid
from astra.telegram.ai_chat.intents import Intent
from astra.telegram.button_texts import (
    BTN_ASK_ASTRID_LEGACY,
    BTN_ASK_ASTRID_LEGACY_LATIN,
    BTN_BACK_MENU,
)
from astra.telegram.states import AiChatStates
from astra.users import crud as users_crud

log = get_logger(__name__)

router = Router(name="ai_chat")

_HISTORY_KEY = "ai_chat_history"

_GREETING = (
    "Это я, Астрид ✨ Пиши мне обычным текстом — что хочешь узнать или сделать.\n\n"
    "Например: «проверь совместимость с парнем, он родился 3 марта 92-го в Алматы» "
    "или «что там у меня по гороскопу на сегодня».\n\n"
    "Чтобы выйти — жми «🔙 Назад»."
)


def _ai_chat_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура режима чата: только выход, всё остальное — текстом."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_BACK_MENU)]],
        resize_keyboard=True,
    )

# Тип адаптера: приводим разные сигнатуры точек входа к (message, state, session).
_FlowEntry = Callable[[Message, FSMContext, AsyncSession], Awaitable[None]]


def _flow_dispatch() -> dict[Intent, _FlowEntry]:
    """Intent → реальная точка входа существующего флоу.

    Импорт ленивый: тянем хендлеры только при первом роутинге, без циклов на старте.
    Сигнатуры унифицируем адаптерами (не у всех входов есть state/session).
    """
    from astra.telegram.handlers.catalog import open_tarot_menu
    from astra.telegram.handlers.compatibility import start_compatibility
    from astra.telegram.handlers.day_card import legacy_button
    from astra.telegram.handlers.invites import open_invites
    from astra.telegram.handlers.menu import show_profile
    from astra.telegram.handlers.natal import start_natal
    from astra.telegram.handlers.tarot_spreads import (
        start_relationship,
        start_three_cards,
        start_wish,
    )

    async def _prediction(m: Message, s: FSMContext, _db: AsyncSession) -> None:
        # Ежедневного прогноза больше нет: объясняем, что теперь приходит карта дня.
        await s.clear()  # one-shot действие: выходим из режима чата
        await legacy_button(m)

    async def _tarot(m: Message, s: FSMContext, _db: AsyncSession) -> None:
        await s.clear()
        await open_tarot_menu(m)

    async def _profile(m: Message, s: FSMContext, db: AsyncSession) -> None:
        await s.clear()
        await show_profile(m, db)

    async def _invite(m: Message, s: FSMContext, db: AsyncSession) -> None:
        await open_invites(m, s, db)

    return {
        Intent.compatibility: start_compatibility,
        Intent.natal: start_natal,
        Intent.daily_prediction: _prediction,
        Intent.tarot: _tarot,
        # Конкретные расклады: сами ставят TarotStates.waiting_question и спросят вопрос
        Intent.tarot_wish: start_wish,
        Intent.tarot_three_cards: start_three_cards,
        Intent.tarot_relationship: start_relationship,
        Intent.edit_profile: _profile,
        Intent.invite: _invite,
    }


@router.message(F.text.in_({BTN_ASK_ASTRID_LEGACY, BTN_ASK_ASTRID_LEGACY_LATIN}))
async def ai_chat_enter(message: Message, state: FSMContext) -> None:
    """Вход в режим чата по кнопке «💬 Написать Астрид»."""
    await state.set_state(AiChatStates.chatting)
    await state.update_data({_HISTORY_KEY: []})
    await message.answer(_GREETING, reply_markup=_ai_chat_keyboard())


@router.message(AiChatStates.chatting, F.text & ~F.text.startswith("/"))
async def ai_chat_turn(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """Одна реплика диалога с Astrid (только внутри режима чата, свободный текст)."""
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

    log.info(
        "ai_chat.turn",
        intent=reply.intent.value,
        ready=reply.ready_to_route,
        missing=reply.missing,
    )

    # Сначала Astrid отвечает словами...
    await message.answer(reply.reply)

    # ...потом, если данных хватает — передаём управление реальному флоу.
    flow = _flow_dispatch().get(reply.intent) if reply.ready_to_route else None
    if flow is not None:
        await flow(message, state, session)
        return

    # Иначе продолжаем разговор: копим историю в FSM-хранилище (Redis) как память.
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply.reply})
    await state.update_data({_HISTORY_KEY: history[-24:]})
