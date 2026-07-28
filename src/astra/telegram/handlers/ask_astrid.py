"""Раздел «Спроси Астрид»: готовые вопросы к своей карте.

Два уровня: темы → вопросы темы. Наполнена пока одна тема («Любовь,
отношения, брак»), остальные честно говорят, что вопросы готовятся.
Сам ответ по карте и оплата придут отдельно — вопрос ведёт на заглушку.

Навигация инлайновая (callback), а не Reply-кнопками: следующий уровень —
оплата и ответ — ляжет тем же механизмом, без коллизий со свободным текстом.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy.ext.asyncio import AsyncSession

from astra.ask import models as ask_crud
from astra.ask.enums import AskStatus
from astra.core.observability import Event, get_logger
from astra.messaging.publisher import publish_ask_answer_generate
from astra.payments.service import (
    ASK_PAYLOAD_PREFIX,
    ask_invoice_payload,
    get_ask_price,
    parse_ask_invoice_payload,
    register_ask_payment,
)
from astra.ask.products import get_product, is_ready
from astra.services.ask_service import (
    ASK_FAILED_REFUNDED_TEXT,
    ASK_FAILED_TEXT,
    compute_for_reading,
    result_from_reading,
)
from astra.telegram import ask_text as A
from astra.telegram.ask_keyboards import (
    ask_answer_keyboard,
    ask_archive_keyboard,
    ask_gate_keyboard,
    ask_status_keyboard,
)
from astra.telegram.button_texts import (
    BTN_ASK_ASTRID,
    CB_ASK_ARCHIVE_PREFIX,
    CB_ASK_CALIB_PREFIX,
    CB_ASK_REDO_PREFIX,
    CB_ASK_CLOSE,
    CB_ASK_COMPAT_CROSSSELL,
    CB_ASK_GATE_SKIP,
    CB_ASK_GATE_TIME,
    CB_ASK_HOME,
    CB_ASK_OWN,
    CB_ASK_QUESTION_PREFIX,
    CB_ASK_TOPIC_PREFIX,
    COMING_SOON_TEXT,
)
from astra.telegram.keyboards import (
    ask_astrid_keyboard,
    ask_back_keyboard,
    ask_questions_keyboard,
)
from astra.telegram.states import ProfileStates
from astra.users import crud as users_crud
from astra.users.gender import Gender
from astra.users.models import User

log = get_logger(__name__)

router = Router(name="ask_astrid")


async def open_ask_hub(message: Message) -> None:
    """Открыть раздел новым сообщением (из кнопки меню)."""
    await message.answer(A.ASK_HUB_TEXT, reply_markup=ask_astrid_keyboard())


async def _current_user(callback: CallbackQuery, session: AsyncSession) -> User | None:
    if callback.from_user is None:
        return None
    return await users_crud.get_user_by_telegram_id(session, callback.from_user.id)


async def _user_gender(callback: CallbackQuery, session: AsyncSession) -> Gender | None:
    """Пол из профиля: нужен для рода в подписях («одна» / «один»)."""
    user = await _current_user(callback, session)
    if user is None or user.profile is None:
        return None
    return user.profile.gender


async def _edit_or_answer(
    callback: CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup,
) -> None:
    """Правим текущее сообщение; если нельзя (фото/уже изменено) — шлём новое."""
    msg = callback.message
    if not isinstance(msg, Message):
        return
    try:
        await msg.edit_text(text, reply_markup=markup)
    except Exception:
        await msg.answer(text, reply_markup=markup)


@router.message(F.text == BTN_ASK_ASTRID)
async def ask_astrid_button(message: Message, state: FSMContext) -> None:
    """Кнопка меню вне активного сценария (в FSM её ловит navigation)."""
    await state.clear()
    await open_ask_hub(message)


@router.callback_query(F.data == CB_ASK_HOME)
async def cb_ask_home(callback: CallbackQuery) -> None:
    await callback.answer()
    await _edit_or_answer(callback, A.ASK_HUB_TEXT, ask_astrid_keyboard())


@router.callback_query(F.data.startswith(CB_ASK_TOPIC_PREFIX))
async def cb_ask_topic(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    key = (callback.data or "").removeprefix(CB_ASK_TOPIC_PREFIX)
    label = A.ASK_TOPIC_LABELS.get(key)
    if label is None:
        return

    if key not in A.ASK_QUESTIONS:
        text = A.ASK_TOPIC_SOON_TEXT.format(label=f"<b>{label}</b>")
        await _edit_or_answer(callback, text, ask_back_keyboard())
        return

    gender = await _user_gender(callback, session)
    text = A.ASK_TOPIC_INTRO_TEXT.format(label=f"<b>{label}</b>")
    await _edit_or_answer(callback, text, ask_questions_keyboard(key, gender))


@router.callback_query(F.data.startswith(CB_ASK_QUESTION_PREFIX))
async def cb_ask_question(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()
    key = (callback.data or "").removeprefix(CB_ASK_QUESTION_PREFIX)
    question = A.ASK_QUESTION_BY_KEY.get(key)
    if question is None:
        return

    # Готовые продукты уходят в покупку, остальные вопросы — на честную заглушку.
    if is_ready(key):
        await _start_paid_question(callback, state, session, question_key=key)
        return

    gender = await _user_gender(callback, session)
    text = A.ASK_QUESTION_SOON_TEXT.format(
        question=f"<b>{A.render_question(question.label, gender)}</b>",
    )
    topic = A.ASK_QUESTION_TOPIC[key]
    await _edit_or_answer(callback, text, ask_back_keyboard(f"{CB_ASK_TOPIC_PREFIX}{topic}"))


async def _start_paid_question(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    *,
    question_key: str,
    skip_archive: bool = False,
) -> None:
    """Купленный ответ из архива, иначе — экран уточнения времени рождения.

    `skip_archive` — человек сам попросил разбор заново: архив не показываем,
    ведём в обычную покупку.
    """
    user = await _current_user(callback, session)
    if user is None or user.profile is None or user.profile.birth_date is None:
        await _edit_or_answer(callback, A.ASK_NEED_PROFILE_TEXT, ask_back_keyboard())
        return

    archived = (
        None
        if skip_archive
        else await ask_crud.get_ready_reading(
            session,
            user_id=user.id,
            question_key=question_key,
        )
    )
    if archived is not None:
        log.info(Event.ASK_ANSWER_FROM_ARCHIVE, reading_id=archived.id, user_id=user.id)
        await _edit_or_answer(
            callback,
            A.ASK_ARCHIVE_TEXT,
            ask_archive_keyboard(question_key),
        )
        return

    product = get_product(question_key)
    if product is None:
        return
    await state.update_data(ask_question_key=question_key)
    if user.profile.birth_time is None:
        await _edit_or_answer(callback, A.ASK_GATE_TIME_TEXT, ask_gate_keyboard())
        return
    await _edit_or_answer(callback, product.calibration_text, ask_status_keyboard(product))


@router.callback_query(F.data.startswith(CB_ASK_REDO_PREFIX))
async def cb_ask_redo(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """«Сделать разбор заново» — новая покупка, архив не подставляем."""
    await callback.answer()
    question_key = (callback.data or "").removeprefix(CB_ASK_REDO_PREFIX)
    if not is_ready(question_key):
        return
    await _start_paid_question(
        callback,
        state,
        session,
        question_key=question_key,
        skip_archive=True,
    )


@router.callback_query(F.data == CB_ASK_GATE_TIME)
async def cb_ask_gate_time(callback: CallbackQuery, state: FSMContext) -> None:
    """Человек согласился вписать время — отдаём его в обычный флоу профиля."""
    await callback.answer()
    await state.set_state(ProfileStates.edit_birth_time)
    msg = callback.message
    if isinstance(msg, Message):
        await msg.answer(
            "Введи время рождения в формате ЧЧ:ММ (например 14:30) — "
            "и возвращайся к вопросу, посчитаю точнее ✨",
        )


@router.callback_query(F.data == CB_ASK_GATE_SKIP)
async def cb_ask_gate_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    product = get_product(data.get("ask_question_key", ""))
    if product is None:
        await _edit_or_answer(callback, A.ASK_HUB_TEXT, ask_astrid_keyboard())
        return
    await _edit_or_answer(callback, product.calibration_text, ask_status_keyboard(product))


@router.callback_query(F.data.startswith(CB_ASK_CALIB_PREFIX))
async def cb_ask_calibration(callback: CallbackQuery, session: AsyncSession) -> None:
    """Ответ на калибрующий вопрос: создаём черновик и выставляем инвойс."""
    await callback.answer()
    msg = callback.message
    user = await _current_user(callback, session)
    if not isinstance(msg, Message) or user is None:
        return

    payload = (callback.data or "").removeprefix(CB_ASK_CALIB_PREFIX)
    question_key, _, answer = payload.rpartition(":")
    product = get_product(question_key)
    if product is None:
        await msg.answer(COMING_SOON_TEXT)
        return
    calibration = answer == "yes"

    price = await get_ask_price(session, question_key)
    if price is None:
        await msg.answer(COMING_SOON_TEXT)
        return

    reading = await ask_crud.create_draft(
        session,
        user_id=user.id,
        question_key=question_key,
        in_relationship=calibration,
        context={product.calibration_field: calibration},
    )
    await session.commit()
    log.info(Event.ASK_ANSWER_CREATED, reading_id=reading.id, user_id=user.id)

    if price.is_free:
        # discount_percent = 100 в БД: инвойс на 0 звёзд Telegram не примет,
        # поэтому выдаём ответ сразу, без оплаты.
        log.info(Event.ASK_ANSWER_FREE_GRANTED, reading_id=reading.id, user_id=user.id)
        await _fulfill_reading(msg, session, reading, user, amount=0, charge_id=None)
        return

    await msg.answer_invoice(
        title=product.invoice_title[:32],
        description=product.invoice_description,
        payload=ask_invoice_payload(reading.id),
        currency=price.currency,
        prices=[LabeledPrice(label=product.invoice_title, amount=price.final_amount)],
    )


@router.pre_checkout_query(F.invoice_payload.startswith(ASK_PAYLOAD_PREFIX))
async def ask_pre_checkout(query: PreCheckoutQuery, session: AsyncSession) -> None:
    reading_id = parse_ask_invoice_payload(query.invoice_payload)
    reading = await ask_crud.get_reading(session, reading_id) if reading_id else None
    if reading is None or reading.status != AskStatus.PENDING_PAYMENT:
        await query.answer(ok=False, error_message="Платёж устарел — начни заново ✨")
        log.warning(Event.PAYMENT_PRE_CHECKOUT_REJECTED, reason="draft_missing_or_paid")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment.invoice_payload.startswith(ASK_PAYLOAD_PREFIX))
async def ask_paid(message: Message, session: AsyncSession) -> None:
    """Оплата прошла: считаем числа, отдаём карточку, разбор пишет worker."""
    payment_info = message.successful_payment
    if payment_info is None or message.from_user is None:
        return
    reading_id = parse_ask_invoice_payload(payment_info.invoice_payload)
    if reading_id is None:
        return

    charge_id = payment_info.telegram_payment_charge_id
    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    reading = await ask_crud.get_reading(session, reading_id) if user else None
    if user is None or reading is None or reading.user_id != user.id:
        # Списали, а начислить не на что — сразу возвращаем звёзды.
        log.error(Event.PAYMENT_ORPHAN, reading_id=reading_id, charge_id=charge_id)
        if message.bot is not None:
            await message.bot.refund_star_payment(
                user_id=message.from_user.id,
                telegram_payment_charge_id=charge_id,
            )
        return

    payment = await register_ask_payment(
        session,
        user=user,
        question_key=reading.question_key,
        provider_charge_id=charge_id,
        amount=payment_info.total_amount,
        currency=payment_info.currency,
    )
    if payment is None:
        return  # дубль successful_payment

    await _fulfill_reading(
        message,
        session,
        reading,
        user,
        amount=payment_info.total_amount,
        charge_id=charge_id,
    )


async def _fulfill_reading(
    message: Message,
    session: AsyncSession,
    reading,
    user: User,
    *,
    amount: int,
    charge_id: str | None,
) -> None:
    """Выдача ответа после оплаты (или сразу, если товар бесплатный).

    Расчёт идёт синхронно — он быстрый; карточка уходит до разбора и закрывает
    паузу ожидания LLM. Если посчитать не удалось, звёзды возвращаются.
    """
    product = get_product(reading.question_key)
    if product is None:
        return
    await message.answer(product.teaser)
    await message.chat.do("typing")

    try:
        result = await compute_for_reading(session, reading, user)
    except Exception:
        # Ошибка расчёта одного продукта не должна стоить человеку денег.
        log.exception("ask.compute_failed", question_key=reading.question_key)
        result = None
    if result is None:
        await session.rollback()
        refunded = False
        if charge_id and message.bot is not None:
            await message.bot.refund_star_payment(
                user_id=user.telegram_id,
                telegram_payment_charge_id=charge_id,
            )
            refunded = True
        await message.answer(ASK_FAILED_REFUNDED_TEXT if refunded else ASK_FAILED_TEXT)
        return

    await ask_crud.mark_paid(
        session,
        reading,
        amount=amount,
        charge_id=charge_id,
        computed=result.model_dump(mode="json"),
        methodology_version=result.methodology_version,
    )
    await session.commit()  # сначала commit, потом publish — worker должен видеть строку

    await _send_card(message, session, reading, result, product)
    await message.answer(A.ASK_ANSWER_COMING_TEXT)
    await publish_ask_answer_generate(reading.id)


async def _send_card(
    message: Message,
    session: AsyncSession,
    reading,
    result,
    product,
) -> None:
    """Карточка уходит сразу — она же закрывает паузу ожидания разбора."""
    caption = product.prompt.card_caption(result)
    if product.render_card is None:
        await message.answer(caption)
        return
    try:
        photo = BufferedInputFile(product.render_card(result), filename="astrid.png")
        sent = await message.answer_photo(photo, caption=caption)
        if sent.photo:
            await ask_crud.save_card_file_id(session, reading, sent.photo[-1].file_id)
            await session.commit()
    except Exception:
        # Картинка — украшение; если не собралась, ответ всё равно придёт текстом.
        log.exception("ask.card_failed")
        await message.answer(caption)


@router.callback_query(F.data.startswith(CB_ASK_ARCHIVE_PREFIX))
async def cb_ask_archive(callback: CallbackQuery, session: AsyncSession) -> None:
    """Бесплатная повторная выдача купленного ответа."""
    await callback.answer()
    msg = callback.message
    user = await _current_user(callback, session)
    if not isinstance(msg, Message) or user is None:
        return
    question_key = (callback.data or "").removeprefix(CB_ASK_ARCHIVE_PREFIX)
    reading = await ask_crud.get_ready_reading(
        session,
        user_id=user.id,
        question_key=question_key,
    )
    product = get_product(question_key)
    if reading is None or not reading.answer or product is None:
        await msg.answer(COMING_SOON_TEXT)
        return

    result = result_from_reading(reading)
    if reading.card_file_id and result is not None:
        await msg.answer_photo(
            reading.card_file_id,
            caption=product.prompt.card_caption(result),
        )
    referral_code = user.referral_code.code if user.referral_code else None
    await msg.answer(
        reading.answer.get("html", ""),
        reply_markup=ask_answer_keyboard(reading, referral_code=referral_code),
    )


@router.callback_query(F.data == CB_ASK_COMPAT_CROSSSELL)
async def cb_ask_compat_crosssell(callback: CallbackQuery) -> None:
    await callback.answer()
    msg = callback.message
    if isinstance(msg, Message):
        await msg.answer(A.ASK_COMPAT_CROSSSELL_TEXT)


@router.callback_query(F.data == CB_ASK_OWN)
async def cb_ask_own(callback: CallbackQuery) -> None:
    await callback.answer()
    await _edit_or_answer(callback, A.ASK_OWN_SOON_TEXT, ask_back_keyboard())


@router.callback_query(F.data == CB_ASK_CLOSE)
async def cb_ask_close(callback: CallbackQuery) -> None:
    await callback.answer()
    msg = callback.message
    if isinstance(msg, Message):
        try:
            await msg.delete()
        except Exception:
            pass
