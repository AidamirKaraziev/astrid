"""Платные расклады таро: вопрос → карты мгновенно → интерпретация из worker.

LLM в хендлерах не вызывается: бот рисует карты и публикует
tarot_reading.generate, текст интерпретации доставит worker.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import get_settings
from astra.core.observability import Event, get_logger
from astra.messaging.publisher import publish_tarot_reading_generate
from astra.services.tarot_reading_service import (
    LIMIT_HIT_TEXT,
    check_daily_limit,
    create_reading,
    format_reading_caption,
    local_today,
    release_reading_lock,
    try_acquire_reading_lock,
)
from astra.tarot.spreads import SPREADS, SpreadType
from astra.telegram.button_texts import (
    BTN_BACK_MENU,
    BTN_BACK_MENU_LEGACY,
    BTN_TAROT_DECISION,
    BTN_TAROT_SKIP,
    COMING_SOON_TEXT,
)
from astra.telegram.keyboards import main_menu_keyboard, tarot_keyboard
from astra.telegram.states import TarotStates
from astra.telegram.tarot_media import send_card_photo, send_cards_album
from astra.users import crud as users_crud

log = get_logger(__name__)

router = Router(name="tarot_spreads")

_QUESTION_MIN_LEN = 3
_QUESTION_MAX_LEN = 500

# Кнопка меню → тип расклада. «3 карты» и «Отношения» подключаются в PR4.
SPREAD_BUTTONS: dict[str, SpreadType] = {
    BTN_TAROT_DECISION: SpreadType.YES_NO,
}

_IN_PROGRESS_TEXT = "Карты уже раскладываются — секунду 🕯"
_QUESTION_LENGTH_TEXT = (
    f"Напиши вопрос текстом — от {_QUESTION_MIN_LEN} до {_QUESTION_MAX_LEN} символов."
)
_QUESTION_REQUIRED_TEXT = "Для этого расклада нужен вопрос — без него карты не лягут 🙏"


def _question_keyboard(question_required: bool) -> ReplyKeyboardMarkup:
    rows = []
    if not question_required:
        rows.append([KeyboardButton(text=BTN_TAROT_SKIP)])
    rows.append([KeyboardButton(text=BTN_BACK_MENU)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


async def _require_user(message: Message, session: AsyncSession):
    if message.from_user is None:
        return None
    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    if user is None or not user.onboarding_completed or user.profile is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return None
    return user


async def _start_spread(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    spread_type: SpreadType,
) -> None:
    if not get_settings().tarot_spreads_enabled:
        await message.answer(COMING_SOON_TEXT)
        return
    user = await _require_user(message, session)
    if user is None:
        return
    if not await check_daily_limit(session, user, local_today(user)):
        log.info(Event.TAROT_READING_LIMIT_HIT, user_id=user.id, spread_type=str(spread_type))
        await message.answer(LIMIT_HIT_TEXT)
        return
    spec = SPREADS[spread_type]
    await state.clear()
    await state.set_state(TarotStates.waiting_question)
    await state.update_data(tarot_spread_type=str(spread_type))
    await message.answer(
        f"{spec.emoji} <b>{spec.title_ru}</b>\n\n{spec.question_hint}",
        parse_mode="HTML",
        reply_markup=_question_keyboard(spec.question_required),
    )


async def start_yes_no(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await _start_spread(message, state, session, SpreadType.YES_NO)


async def start_three_cards(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await _start_spread(message, state, session, SpreadType.THREE_CARDS)


async def start_relationship(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await _start_spread(message, state, session, SpreadType.RELATIONSHIP)


@router.message(F.text.in_(SPREAD_BUTTONS))
async def spread_button(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await _start_spread(message, state, session, SPREAD_BUTTONS[message.text or ""])


@router.message(TarotStates.waiting_question, F.text)
async def spread_question(message: Message, state: FSMContext, session: AsyncSession) -> None:
    text = (message.text or "").strip()

    if text in {BTN_BACK_MENU, BTN_BACK_MENU_LEGACY}:
        await state.clear()
        await message.answer("Главное меню ✨", reply_markup=main_menu_keyboard())
        return

    data = await state.get_data()
    try:
        spread_type = SpreadType(data.get("tarot_spread_type", ""))
    except ValueError:
        await state.clear()
        await message.answer("Начни расклад заново ✨", reply_markup=tarot_keyboard())
        return
    spec = SPREADS[spread_type]

    if text == BTN_TAROT_SKIP:
        if spec.question_required:
            await message.answer(_QUESTION_REQUIRED_TEXT)
            return
        question: str | None = None
    elif _QUESTION_MIN_LEN <= len(text) <= _QUESTION_MAX_LEN:
        question = text
    else:
        await message.answer(_QUESTION_LENGTH_TEXT)
        return

    user = await _require_user(message, session)
    if user is None:
        return

    if not await try_acquire_reading_lock(user.id):
        await message.answer(_IN_PROGRESS_TEXT)
        return
    try:
        target = local_today(user)
        if not await check_daily_limit(session, user, target):
            log.info(Event.TAROT_READING_LIMIT_HIT, user_id=user.id, spread_type=str(spread_type))
            await state.clear()
            await message.answer(LIMIT_HIT_TEXT, reply_markup=tarot_keyboard())
            return

        reading, cards = await create_reading(session, user, spread_type, question, target)
        await session.commit()  # сначала commit, потом publish — worker должен видеть строку
        await state.clear()

        caption = format_reading_caption(spec, cards)
        if len(cards) == 1:
            await send_card_photo(message, cards[0], caption)
        else:
            await send_cards_album(message, cards, caption)

        await publish_tarot_reading_generate(reading.id)
    finally:
        await release_reading_lock(user.id)
