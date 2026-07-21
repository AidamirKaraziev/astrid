"""Колесо фортуны: бесплатное вращение раз в день, платные — без лимита.

Приз определяется на сервере до анимации, поэтому сбой анимации не теряет
выигрыш. Бесплатный приз сгорает в полночь по времени пользователя, платный
живёт до активации. Активация таро-приза ведёт в обычный флоу расклада,
где цена пересчитывается по скидке приза.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import Event, get_logger
from astra.payments.service import (
    WHEEL_PAYLOAD_PREFIX,
    get_wheel_spin_price,
    register_wheel_spin_payment,
    tarot_product_code,
    wheel_spin_invoice_payload,
)
from astra.tarot.spreads import SpreadType
from astra.telegram.button_texts import (
    BTN_WHEEL,
    CB_WHEEL_ACTIVATE_PREFIX,
    CB_WHEEL_HOME,
    CB_WHEEL_PRIZES,
    CB_WHEEL_SPIN_FREE,
    CB_WHEEL_SPIN_PAID,
    COMING_SOON_TEXT,
)
from astra.telegram.handlers.tarot_spreads import start_spread_with_prize
from astra.telegram.wheel_animation import play_spin_animation
from astra.users import crud as users_crud
from astra.wheel import crud as wheel_crud
from astra.wheel.display import prize_label
from astra.wheel.enums import SpinType
from astra.wheel.models import WheelWin
from astra.wheel.service import perform_spin, user_local_today, win_is_available

log = get_logger(__name__)

router = Router(name="wheel")

_INTRO_TEXT = (
    "🎡 <b>Колесо фортуны</b>\n\n"
    "Одно бесплатное вращение в день — приз выпадает всегда.\n"
    "Бесплатный приз сгорает в полночь, купленный ждёт сколько угодно."
)
_FREE_READY_LINE = "\n\nСегодня бесплатное вращение ещё не использовано ✨"
_FREE_USED_LINE = "\n\nБесплатное вращение вернётся завтра 🌙"
_ALREADY_SPUN_TEXT = "Сегодня колесо уже крутилось — возвращайся завтра 🌙"
_POOL_EMPTY_TEXT = "Колесо сейчас на паузе — призы вот-вот появятся ✨"
_NO_PRIZES_TEXT = "Активных призов пока нет — крути колесо ✨"
_PRIZE_GONE_TEXT = "Этот приз уже использован или сгорел 🕯"
_SPIN_INVOICE_TITLE = "Вращение колеса фортуны"
_SPIN_INVOICE_DESCRIPTION = "Ещё одно вращение колеса — приз гарантирован."
_REFUND_POOL_EMPTY_TEXT = (
    "Призы закончились, вращение не состоялось — звёзды уже вернулись на баланс ⭐"
)


async def _require_user(message: Message, session: AsyncSession):
    if message.from_user is None:
        return None
    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    if user is None or not user.onboarding_completed or user.profile is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return None
    return user


def _prize_expiry_line(win: WheelWin) -> str:
    if win.expires_at is None:
        return "Приз ждёт тебя — активируй когда угодно ✨"
    return "Приз сгорает сегодня в полночь 🌙"


def _prize_card_text(win: WheelWin) -> str:
    return (
        "🎉 <b>Твой приз</b>\n\n"
        f"{prize_label(win.product_code, win.discount_percent)}\n\n"
        f"{_prize_expiry_line(win)}"
    )


def _prize_keyboard(win: WheelWin) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✨ Использовать",
                    callback_data=f"{CB_WHEEL_ACTIVATE_PREFIX}{win.id}",
                ),
            ],
            [InlineKeyboardButton(text="🎡 К колесу", callback_data=CB_WHEEL_HOME)],
        ],
    )


def _wheel_keyboard(
    *,
    free_available: bool,
    spin_price_label: str | None,
    prize_count: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if free_available:
        rows.append(
            [InlineKeyboardButton(text="🎡 Крутить бесплатно", callback_data=CB_WHEEL_SPIN_FREE)],
        )
    if spin_price_label:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🎡 Крутить за {spin_price_label}",
                    callback_data=CB_WHEEL_SPIN_PAID,
                ),
            ],
        )
    if prize_count:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🎁 Мои призы ({prize_count})",
                    callback_data=CB_WHEEL_PRIZES,
                ),
            ],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_wheel(message: Message, session: AsyncSession, user) -> None:
    free_used = await wheel_crud.has_free_win_on(session, user.id, user_local_today(user))
    wins = await wheel_crud.list_available_wins(session, user.id, datetime.now(UTC))
    price = await get_wheel_spin_price(session)
    price_label = None
    if price is not None:
        price_label = "бесплатно" if price.is_free else f"{price.final_amount} ⭐"

    text = _INTRO_TEXT + (_FREE_USED_LINE if free_used else _FREE_READY_LINE)
    if wins:
        text += f"\nАктивных призов: <b>{len(wins)}</b>"
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=_wheel_keyboard(
            free_available=not free_used,
            spin_price_label=price_label,
            prize_count=len(wins),
        ),
    )


@router.message(F.text == BTN_WHEEL)
async def open_wheel(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = await _require_user(message, session)
    if user is None:
        return  # незавершённый онбординг не сбрасываем
    await state.clear()  # кнопка меню прерывает текущий сценарий
    await _show_wheel(message, session, user)


@router.callback_query(F.data == CB_WHEEL_HOME)
async def cb_wheel_home(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message) or callback.from_user is None:
        return
    await state.clear()
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None or user.profile is None:
        return
    await _show_wheel(callback.message, session, user)


async def _spin_and_reveal(
    message: Message,
    session: AsyncSession,
    user,
    spin_type: SpinType,
    *,
    payment_id: UUID | None = None,
) -> WheelWin | None:
    """Крутим, показываем анимацию и карточку приза. None — пул призов пуст."""
    prizes = await wheel_crud.list_active_prizes(session)
    win = await perform_spin(session, user, spin_type, payment_id=payment_id)
    if win is None:
        return None
    await session.commit()

    labels = [prize_label(p.product_code, p.discount_percent) for p in prizes]
    winner_index = next((i for i, p in enumerate(prizes) if p.id == win.prize_id), 0)
    await play_spin_animation(message, labels, winner_index)
    await message.answer(
        _prize_card_text(win),
        parse_mode="HTML",
        reply_markup=_prize_keyboard(win),
    )
    return win


@router.callback_query(F.data == CB_WHEEL_SPIN_FREE)
async def cb_spin_free(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message) or callback.from_user is None:
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None or user.profile is None:
        return
    if await wheel_crud.has_free_win_on(session, user.id, user_local_today(user)):
        await callback.message.answer(_ALREADY_SPUN_TEXT)
        return
    try:
        win = await _spin_and_reveal(callback.message, session, user, SpinType.FREE)
    except IntegrityError:
        # Гонка двойного тапа: уникальный индекс не дал второму вращению записаться.
        await session.rollback()
        log.warning(Event.WHEEL_FREE_SPIN_DUPLICATE, user_id=user.id)
        await callback.message.answer(_ALREADY_SPUN_TEXT)
        return
    if win is None:
        await callback.message.answer(_POOL_EMPTY_TEXT)


@router.callback_query(F.data == CB_WHEEL_SPIN_PAID)
async def cb_spin_paid(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message) or callback.from_user is None:
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None or user.profile is None:
        return
    price = await get_wheel_spin_price(session)
    if price is None:
        await callback.message.answer(COMING_SOON_TEXT)
        return
    if price.is_free:
        # discount_percent = 100 в каталоге: вращение раздаётся без инвойса.
        win = await _spin_and_reveal(callback.message, session, user, SpinType.PAID)
        if win is None:
            await callback.message.answer(_POOL_EMPTY_TEXT)
        return

    await callback.message.answer_invoice(
        title=_SPIN_INVOICE_TITLE[:32],
        description=_SPIN_INVOICE_DESCRIPTION,
        payload=wheel_spin_invoice_payload(uuid4()),
        currency=price.currency,
        prices=[LabeledPrice(label=_SPIN_INVOICE_TITLE, amount=price.final_amount)],
    )
    log.info(
        Event.PAYMENT_INVOICE_SENT,
        user_id=user.id,
        product_code="wheel_spin",
        amount=price.final_amount,
        currency=price.currency,
    )


@router.pre_checkout_query(F.invoice_payload.startswith(WHEEL_PAYLOAD_PREFIX))
async def wheel_pre_checkout(query: PreCheckoutQuery, session: AsyncSession) -> None:
    user = await users_crud.get_user_by_telegram_id(session, query.from_user.id)
    if user is None or user.profile is None:
        await query.answer(ok=False, error_message="Сначала пройди регистрацию: /start")
        log.warning(Event.PAYMENT_PRE_CHECKOUT_REJECTED, reason="wheel_user_missing")
        return
    if not await wheel_crud.list_active_prizes(session):
        await query.answer(ok=False, error_message="Колесо на паузе — попробуй позже")
        log.warning(Event.PAYMENT_PRE_CHECKOUT_REJECTED, reason="wheel_pool_empty")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment.invoice_payload.startswith(WHEEL_PAYLOAD_PREFIX))
async def wheel_spin_paid(message: Message, session: AsyncSession) -> None:
    """Оплата вращения прошла: крутим колесо; если призов нет — возвращаем звёзды."""
    payment_info = message.successful_payment
    if payment_info is None or message.from_user is None:
        return
    charge_id = payment_info.telegram_payment_charge_id
    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    if user is None or user.profile is None:
        log.error(Event.PAYMENT_ORPHAN, reason="wheel_user_missing", charge_id=charge_id)
        if message.bot is not None:
            await message.bot.refund_star_payment(
                user_id=message.from_user.id,
                telegram_payment_charge_id=charge_id,
            )
        return

    try:
        payment = await register_wheel_spin_payment(
            session,
            user=user,
            provider_charge_id=charge_id,
            amount=payment_info.total_amount,
            currency=payment_info.currency,
        )
    except IntegrityError:
        await session.rollback()  # дубль successful_payment — платёж уже записан
        return
    if payment is None:
        return  # повтор того же charge_id

    win = await _spin_and_reveal(
        message,
        session,
        user,
        SpinType.PAID,
        payment_id=payment.id,
    )
    if win is not None:
        return

    # Пул опустел между pre_checkout и оплатой — деньги не за что брать.
    await session.rollback()
    if message.bot is not None:
        await message.bot.refund_star_payment(
            user_id=message.from_user.id,
            telegram_payment_charge_id=charge_id,
        )
    log.error(Event.WHEEL_POOL_EMPTY, reason="refunded_after_payment", charge_id=charge_id)
    await message.answer(_REFUND_POOL_EMPTY_TEXT)


@router.callback_query(F.data == CB_WHEEL_PRIZES)
async def cb_wheel_prizes(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message) or callback.from_user is None:
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        return
    wins = await wheel_crud.list_available_wins(session, user.id, datetime.now(UTC))
    if not wins:
        await callback.message.answer(_NO_PRIZES_TEXT)
        return
    rows = [
        [
            InlineKeyboardButton(
                text=prize_label(win.product_code, win.discount_percent),
                callback_data=f"{CB_WHEEL_ACTIVATE_PREFIX}{win.id}",
            ),
        ]
        for win in wins
    ]
    rows.append([InlineKeyboardButton(text="🎡 К колесу", callback_data=CB_WHEEL_HOME)])
    await callback.message.answer(
        "🎁 <b>Мои призы</b>\nНажми на приз, чтобы использовать.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def _spread_type_for_product(product_code: str) -> SpreadType | None:
    for spread_type in SpreadType:
        if tarot_product_code(str(spread_type)) == product_code:
            return spread_type
    return None


@router.callback_query(F.data.startswith(CB_WHEEL_ACTIVATE_PREFIX))
async def cb_activate_prize(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message) or callback.data is None:
        return
    if callback.from_user is None:
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None or not user.onboarding_completed or user.profile is None:
        await callback.message.answer("Сначала пройди регистрацию: /start")
        return
    try:
        win_id = UUID(callback.data.removeprefix(CB_WHEEL_ACTIVATE_PREFIX))
    except ValueError:
        return
    win = await wheel_crud.get_win(session, win_id)
    if win is None or win.user_id != user.id or not win_is_available(win):
        log.warning(Event.WHEEL_PRIZE_UNAVAILABLE, user_id=user.id, win_id=str(win_id))
        await callback.message.answer(_PRIZE_GONE_TEXT)
        return

    spread_type = _spread_type_for_product(win.product_code)
    if spread_type is None:
        await callback.message.answer(COMING_SOON_TEXT)
        return
    # user передаём явно: callback.message — сообщение бота, from_user там бот.
    await start_spread_with_prize(callback.message, state, session, spread_type, win.id, user)


