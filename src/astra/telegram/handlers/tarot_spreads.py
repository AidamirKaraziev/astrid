"""Платные расклады таро: вопрос → инвойс Stars → оплата → карты → интерпретация.

Оплата показывается в момент максимальной вовлечённости — после вопроса,
перед картами. LLM в хендлерах не вызывается: после оплаты бот показывает
карты и публикует tarot_reading.generate, текст интерпретации доставит worker.
"""

from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import get_settings
from astra.core.observability import Event, get_logger
from astra.messaging.publisher import publish_tarot_reading_generate
from astra.payments.service import (
    ProductPriceInfo,
    TAROT_PAYLOAD_PREFIX,
    get_tarot_price,
    parse_tarot_invoice_payload,
    register_tarot_payment,
    tarot_invoice_payload,
    tarot_product_code,
)
from astra.services.tarot_reading_service import (
    create_reading_draft,
    format_reading_caption,
    local_today,
    mark_reading_paid,
    reading_cards,
    release_reading_lock,
    try_acquire_reading_lock,
)
from astra.tarot.enums import ReadingStatus
from astra.tarot.models import get_reading
from astra.tarot.spreads import SPREADS, SpreadType
from astra.telegram.button_texts import (
    BTN_BACK_MENU,
    BTN_BACK_MENU_LEGACY,
    BTN_TAROT_DECISION_LEGACY,
    BTN_TAROT_RELATIONS,
    BTN_TAROT_SKIP,
    BTN_TAROT_THREE,
    BTN_TAROT_WISH,
    COMING_SOON_TEXT,
)
from astra.telegram.keyboards import main_menu_keyboard, tarot_keyboard
from astra.telegram.states import TarotStates
from astra.telegram.tarot_media import send_card_photo, send_cards_album
from astra.users import crud as users_crud
from astra.wheel import crud as wheel_crud
from astra.wheel.service import mark_win_activated, reserve_win_for_reading, win_is_available

log = get_logger(__name__)

router = Router(name="tarot_spreads")

_QUESTION_MIN_LEN = 3
_QUESTION_MAX_LEN = 500

SPREAD_BUTTONS: dict[str, SpreadType] = {
    BTN_TAROT_WISH: SpreadType.WISH,
    BTN_TAROT_DECISION_LEGACY: SpreadType.WISH,  # старая кнопка у закэшированных клиентов
    BTN_TAROT_THREE: SpreadType.THREE_CARDS,
    BTN_TAROT_RELATIONS: SpreadType.RELATIONSHIP,
}

_IN_PROGRESS_TEXT = "Карты уже раскладываются — секунду 🕯"
_QUESTION_LENGTH_TEXT = (
    f"Напиши вопрос текстом — от {_QUESTION_MIN_LEN} до {_QUESTION_MAX_LEN} символов."
)
_QUESTION_REQUIRED_TEXT = "Для этого расклада нужен вопрос — без него карты не лягут 🙏"
_INVOICE_SENT_TEXT = (
    "Вопрос принят ✨ Оплати расклад — и карты лягут сразу же.\n"
    "Если передумаешь, просто вернись в меню — ничего не спишется."
)
_DISCOUNT_LINE = "\n\nСегодня скидка −{percent}%: <s>{base} ⭐</s> → {final} ⭐"


def _strike_digits(value: int) -> str:
    """Юникод-зачёркивание (U+0336) — для текста платёжной кнопки, где нет HTML."""
    return "".join(f"{char}̶" for char in str(value))
_PAYMENT_STALE_TEXT = "Этот расклад уже оплачен или устарел — начни новый ✨"
_PRIZE_GONE_TEXT = "Приз с колеса уже сгорел или использован — расклад по обычной цене 🕯"
_PAID_THANKS_TEXT = "Оплата получена ⭐ Тяну карты…"
_FREE_TODAY_TEXT = "Сегодня этот расклад — подарок от Астрид, бесплатно ✨ Тяну карты…"


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
    *,
    wheel_win_id: UUID | None = None,
    actor=None,
) -> None:
    """wheel_win_id — расклад запущен призом колеса: цену пересчитаем по скидке приза.

    actor — пользователь, когда расклад запускается из callback'а: там message
    принадлежит боту, и определять пользователя по message.from_user нельзя.
    """
    if not get_settings().tarot_spreads_enabled:
        await message.answer(COMING_SOON_TEXT)
        return
    user = actor if actor is not None else await _require_user(message, session)
    if user is None:
        return
    spec = SPREADS[spread_type]
    await state.clear()
    await state.set_state(TarotStates.waiting_question)
    await state.update_data(tarot_spread_type=str(spread_type))
    if wheel_win_id is not None:
        await state.update_data(wheel_win_id=str(wheel_win_id))
    await message.answer(
        f"{spec.emoji} <b>{spec.title_ru}</b>\n\n{spec.question_hint}",
        parse_mode="HTML",
        reply_markup=_question_keyboard(spec.question_required),
    )


async def start_wish(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await _start_spread(message, state, session, SpreadType.WISH)


async def start_three_cards(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await _start_spread(message, state, session, SpreadType.THREE_CARDS)


async def start_relationship(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await _start_spread(message, state, session, SpreadType.RELATIONSHIP)


async def start_spread_with_prize(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    spread_type: SpreadType,
    wheel_win_id: UUID,
    actor,
) -> None:
    """Запуск расклада призом колеса (вызывается из хендлера колеса).

    actor обязателен: message здесь — сообщение бота, у него from_user это бот.
    """
    await _start_spread(
        message,
        state,
        session,
        spread_type,
        wheel_win_id=wheel_win_id,
        actor=actor,
    )


@router.message(F.text.in_(SPREAD_BUTTONS))
async def spread_button(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await _start_spread(message, state, session, SPREAD_BUTTONS[message.text or ""])


async def _reveal_reading(message: Message, reading) -> None:
    """Показать карты расклада; интерпретацию доставит worker."""
    spec = SPREADS[SpreadType(reading.spread_type)]
    cards = reading_cards(reading)
    caption = format_reading_caption(spec, cards)
    if len(cards) == 1:
        await send_card_photo(message, cards[0], caption)
    else:
        await send_cards_album(message, cards, caption)


async def send_reading_invoice(
    message: Message,
    reading_id,
    spec,
    price: ProductPriceInfo,
) -> None:
    """Инвойс Stars; при акции платёжная кнопка показывает зачёркнутую старую цену.

    Утверждённый вариант B: «5̶0̶ ⭐ → 5 ⭐ · скидка −90%». Текст на pay-кнопке
    разрешён Bot API, ⭐ Telegram заменяет своей иконкой; зачёркивание — U+0336.
    """
    kwargs: dict = {}
    if price.has_discount:
        pay_button = InlineKeyboardButton(
            text=(
                f"{_strike_digits(price.base_amount)} ⭐ → {price.final_amount} ⭐"
                f" · скидка −{price.discount_percent}%"
            ),
            pay=True,
        )
        kwargs["reply_markup"] = InlineKeyboardMarkup(inline_keyboard=[[pay_button]])
    await message.answer_invoice(
        title=f"{spec.emoji} {spec.title_ru}"[:32],
        description=(
            "Карты Райдер-Уэйт и личная интерпретация от Астрид — по твоему вопросу."
        ),
        payload=tarot_invoice_payload(reading_id),
        currency=price.currency,
        prices=[LabeledPrice(label=spec.title_ru, amount=price.final_amount)],
        **kwargs,
    )


async def _wheel_win_for_spread(
    session: AsyncSession,
    user,
    spread_type: SpreadType,
    data: dict,
):
    """Приз колеса, которым запущен этот расклад; None — приза нет или он сгорел."""
    raw_id = data.get("wheel_win_id")
    if not raw_id:
        return None
    try:
        win = await wheel_crud.get_win(session, UUID(str(raw_id)))
    except ValueError:
        return None
    if win is None or win.user_id != user.id or not win_is_available(win):
        log.warning(Event.WHEEL_PRIZE_UNAVAILABLE, user_id=user.id, win_id=raw_id)
        return None
    if win.product_code != tarot_product_code(str(spread_type)):
        log.warning(Event.WHEEL_PRIZE_UNAVAILABLE, reason="product_mismatch", win_id=raw_id)
        return None
    return win


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
        # Цена — из БД на каждый товар; в текстах её нет, покажет кнопка инвойса.
        price = await get_tarot_price(session, str(spread_type))
        win = await _wheel_win_for_spread(session, user, spread_type, data)
        if win is not None:
            # Приз колеса перебивает акцию каталога: считаем от базовой цены.
            price = ProductPriceInfo(price.currency, price.base_amount, win.discount_percent)
        elif data.get("wheel_win_id"):
            await message.answer(_PRIZE_GONE_TEXT)

        reading = await create_reading_draft(
            session, user, spread_type, question, local_today(user),
        )

        if price.is_free:
            # discount_percent = 100 в БД: без инвойса, карты сразу.
            await mark_reading_paid(session, reading, 0)
            if win is not None:
                await reserve_win_for_reading(session, win, reading.id)
                await mark_win_activated(session, win)
            await session.commit()
            await state.clear()
            log.info(
                Event.TAROT_READING_FREE_GRANTED,
                user_id=user.id,
                reading_id=reading.id,
                wheel_win_id=win.id if win else None,
            )
            await message.answer(_FREE_TODAY_TEXT, reply_markup=tarot_keyboard())
            await _reveal_reading(message, reading)
            await publish_tarot_reading_generate(reading.id)
            return

        if win is not None:
            # Приз тратится только вместе с оплатой — пока лишь резервируем.
            await reserve_win_for_reading(session, win, reading.id)
        await session.commit()  # черновик должен пережить рестарт до оплаты
        await state.clear()

        sent_text = _INVOICE_SENT_TEXT
        if price.has_discount:
            sent_text += _DISCOUNT_LINE.format(
                percent=price.discount_percent,
                base=price.base_amount,
                final=price.final_amount,
            )
        await message.answer(sent_text, reply_markup=tarot_keyboard())
        await send_reading_invoice(message, reading.id, spec, price)
        log.info(
            Event.PAYMENT_INVOICE_SENT,
            user_id=user.id,
            reading_id=reading.id,
            amount=price.final_amount,
            currency=price.currency,
            discount_percent=price.discount_percent,
        )
    finally:
        await release_reading_lock(user.id)


# Старая инлайн-кнопка «Сделать ещё расклад» (бесплатный бонус) в исторических
# сообщениях: бонусов больше нет — просто ведём в меню раскладов.
_LEGACY_UNLOCK_CB = "tarot:reading:unlock"


@router.callback_query(F.data == _LEGACY_UNLOCK_CB)
async def cb_legacy_unlock(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("Выбери расклад ✨", reply_markup=tarot_keyboard())


@router.pre_checkout_query(F.invoice_payload.startswith(TAROT_PAYLOAD_PREFIX))
async def pre_checkout(query: PreCheckoutQuery, session: AsyncSession) -> None:
    """Последняя проверка перед списанием звёзд: черновик существует и не оплачен."""
    reading_id = parse_tarot_invoice_payload(query.invoice_payload)
    if reading_id is None:
        await query.answer(ok=False, error_message=_PAYMENT_STALE_TEXT)
        log.warning(Event.PAYMENT_PRE_CHECKOUT_REJECTED, reason="bad_payload")
        return
    reading = await get_reading(session, reading_id)
    if reading is None or reading.status != ReadingStatus.PENDING_PAYMENT:
        await query.answer(ok=False, error_message=_PAYMENT_STALE_TEXT)
        log.warning(
            Event.PAYMENT_PRE_CHECKOUT_REJECTED,
            reason="draft_missing_or_paid",
            reading_id=reading_id,
        )
        return
    await query.answer(ok=True)


@router.message(F.successful_payment.invoice_payload.startswith(TAROT_PAYLOAD_PREFIX))
async def spread_paid(message: Message, session: AsyncSession) -> None:
    """Оплата прошла: фиксируем платёж, показываем карты, запускаем интерпретацию."""
    payment_info = message.successful_payment
    if payment_info is None or message.from_user is None:
        return
    reading_id = parse_tarot_invoice_payload(payment_info.invoice_payload)
    if reading_id is None:
        log.warning(Event.PAYMENT_ORPHAN, reason="foreign_payload")
        return

    charge_id = payment_info.telegram_payment_charge_id
    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    reading = await get_reading(session, reading_id) if user else None
    if user is None or reading is None or reading.user_id != user.id:
        # Деньги списаны, а начислить не на что — сразу возвращаем звёзды.
        log.error(Event.PAYMENT_ORPHAN, reading_id=reading_id, charge_id=charge_id)
        if message.bot is not None:
            await message.bot.refund_star_payment(
                user_id=message.from_user.id,
                telegram_payment_charge_id=charge_id,
            )
        return

    try:
        payment = await register_tarot_payment(
            session,
            user=user,
            reading=reading,
            provider_charge_id=charge_id,
            amount=payment_info.total_amount,
            currency=payment_info.currency,
        )
        if payment is None:
            return  # дубль successful_payment — уже обработан
        if reading.status == ReadingStatus.PENDING_PAYMENT:
            await mark_reading_paid(session, reading, payment_info.total_amount)
        # Скидочный приз колеса тратится в момент оплаты расклада.
        win = await wheel_crud.get_pending_win_for_reading(session, reading.id)
        if win is not None:
            await mark_win_activated(session, win)
        await session.commit()  # сначала commit, потом publish — worker должен видеть строку
    except IntegrityError:
        await session.rollback()  # гонка двух повторных апдейтов — платёж уже записан
        return

    await message.answer(_PAID_THANKS_TEXT)
    await _reveal_reading(message, reading)
    await publish_tarot_reading_generate(reading.id)
