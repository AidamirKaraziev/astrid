"""Продукт «Сколько судьбоносных партнёров?»: покупка, разбор, карточка."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from astra.ask.fated_partners import render_card
from astra.ask.fated_partners import FatedPartnersFactors, FatedPartnersResult
from astra.llm.prompts.ask import fated_partners as product
from astra.telegram.ask_keyboards import ask_answer_keyboard
from astra.telegram.button_texts import (
    CB_ASK_ARCHIVE_PREFIX,
    CB_ASK_CALIB_PREFIX,
    CB_ASK_REDO_PREFIX,
    CB_ASK_GATE_SKIP,
    CB_ASK_GATE_TIME,
    CB_ASK_QUESTION_PREFIX,
)

CALIB_YES = f"{CB_ASK_CALIB_PREFIX}{'love_fated_count'}:yes"
CALIB_NO = f"{CB_ASK_CALIB_PREFIX}{'love_fated_count'}:no"
from astra.ask.products import get_product
from astra.telegram.birth_data_gate import RETURN_PAYLOAD_KEY, RETURN_PRODUCT_KEY
from astra.telegram.handlers import ask_astrid
from astra.users.birth_data import Product
from astra.telegram import ask_text as A

QUESTION = "love_fated_count"


async def _fsm() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=2, user_id=3))


def _callback(data: str) -> MagicMock:
    callback = MagicMock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    callback.data = data
    callback.from_user = SimpleNamespace(id=777)
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.message.answer_invoice = AsyncMock()
    return callback


def _user(*, birth_time: datetime | None, birth_date: date | None = date(1990, 3, 15)):
    return SimpleNamespace(
        id=uuid4(),
        telegram_id=777,
        profile=SimpleNamespace(
            gender="женщина",
            birth_date=birth_date,
            birth_time=birth_time,
            display_name="Аня",
        ),
        referral_code=SimpleNamespace(code="abc123"),
    )


def _result(total: int = 3, past: int = 1, future: int = 2) -> FatedPartnersResult:
    return FatedPartnersResult(
        methodology_version=1,
        total=total,
        past=past,
        future=future,
        age=36,
        in_relationship=False,
        factors=FatedPartnersFactors(has_time=True, dsc_sign="Водолей"),
    )


def _patch_user(user, archived=None):
    return (
        patch.object(ask_astrid.users_crud, "get_user_by_telegram_id", AsyncMock(return_value=user)),
        patch.object(ask_astrid.ask_crud, "get_ready_reading", AsyncMock(return_value=archived)),
    )


# ─────────────────────────── вход в покупку ───────────────────────────


@pytest.mark.asyncio
async def test_without_birth_time_offers_to_fill_it() -> None:
    callback = _callback(f"{CB_ASK_QUESTION_PREFIX}{QUESTION}")
    user_patch, archive_patch = _patch_user(_user(birth_time=None))

    with user_patch, archive_patch:
        await ask_astrid.cb_ask_question(callback, await _fsm(), MagicMock())

    assert callback.message.edit_text.await_args.args[0] == A.ASK_GATE_TIME_TEXT
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert CB_ASK_GATE_TIME in data
    assert CB_ASK_GATE_SKIP in data  # не запираем: можно ответить и без времени


@pytest.mark.asyncio
async def test_with_birth_time_goes_straight_to_status_question() -> None:
    callback = _callback(f"{CB_ASK_QUESTION_PREFIX}{QUESTION}")
    user_patch, archive_patch = _patch_user(_user(birth_time=datetime(1990, 3, 15, 14, 30)))
    state = await _fsm()

    with user_patch, archive_patch:
        await ask_astrid.cb_ask_question(callback, state, MagicMock())

    calibration = get_product(QUESTION).calibration_text
    assert callback.message.edit_text.await_args.args[0] == calibration
    assert (await state.get_data())["ask_question_key"] == QUESTION


@pytest.mark.asyncio
async def test_without_birth_date_asks_it_right_here() -> None:
    """Не «заполни профиль», а вопрос на месте — с возвратом к этому же разбору."""
    callback = _callback(f"{CB_ASK_QUESTION_PREFIX}{QUESTION}")
    user_patch, archive_patch = _patch_user(_user(birth_time=None, birth_date=None))
    state = await _fsm()

    with user_patch, archive_patch:
        await ask_astrid.cb_ask_question(callback, state, MagicMock())

    asked = callback.message.answer.await_args.args[0]
    assert "дата рождения" in asked
    assert "ДД.ММ.ГГГГ" in asked

    data = await state.get_data()
    assert data[RETURN_PRODUCT_KEY] == Product.ASK_ANSWER.value
    assert data[RETURN_PAYLOAD_KEY] == QUESTION, "вопрос не запомнен — вернём не туда"


@pytest.mark.asyncio
async def test_bought_answer_is_offered_from_archive_for_free() -> None:
    callback = _callback(f"{CB_ASK_QUESTION_PREFIX}{QUESTION}")
    archived = SimpleNamespace(id=uuid4(), answer={"html": "<b>разбор</b>"})
    user_patch, archive_patch = _patch_user(_user(birth_time=None), archived=archived)

    with user_patch, archive_patch:
        await ask_astrid.cb_ask_question(callback, await _fsm(), MagicMock())

    assert callback.message.edit_text.await_args.args[0] == A.ASK_ARCHIVE_TEXT
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert f"{CB_ASK_ARCHIVE_PREFIX}{QUESTION}" in data


@pytest.mark.asyncio
async def test_status_answer_creates_draft_and_sends_invoice() -> None:
    callback = _callback(CALIB_YES)
    user = _user(birth_time=datetime(1990, 3, 15, 14, 30))
    session = MagicMock()
    session.commit = AsyncMock()
    draft = SimpleNamespace(id=uuid4())
    price = SimpleNamespace(currency="XTR", final_amount=1, is_free=False)

    with (
        patch.object(ask_astrid.users_crud, "get_user_by_telegram_id", AsyncMock(return_value=user)),
        patch.object(ask_astrid, "get_ask_price", AsyncMock(return_value=price)),
        patch.object(ask_astrid.ask_crud, "create_draft", AsyncMock(return_value=draft)) as create,
    ):
        await ask_astrid.cb_ask_calibration(callback, session)

    assert create.await_args.kwargs["in_relationship"] is True
    invoice = callback.message.answer_invoice.await_args.kwargs
    assert invoice["currency"] == "XTR"
    assert invoice["prices"][0].amount == 1


@pytest.mark.asyncio
async def test_hundred_percent_discount_skips_invoice_and_answers_at_once() -> None:
    """Скидка 100%: инвойс на 0 звёзд Telegram не примет — выдаём сразу."""
    callback = _callback(CALIB_YES)
    session = MagicMock()
    session.commit = AsyncMock()
    free_price = SimpleNamespace(currency="XTR", final_amount=0, is_free=True)

    with (
        patch.object(
            ask_astrid.users_crud,
            "get_user_by_telegram_id",
            AsyncMock(return_value=_user(birth_time=datetime(1990, 3, 15, 14, 30))),
        ),
        patch.object(ask_astrid, "get_ask_price", AsyncMock(return_value=free_price)),
        patch.object(
            ask_astrid.ask_crud,
            "create_draft",
            AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        ),
        patch.object(ask_astrid, "_fulfill_reading", AsyncMock()) as fulfill,
    ):
        await ask_astrid.cb_ask_calibration(callback, session)

    callback.message.answer_invoice.assert_not_awaited()
    assert fulfill.await_args.kwargs == {"amount": 0, "charge_id": None}


@pytest.mark.asyncio
async def test_paid_price_still_sends_invoice() -> None:
    callback = _callback(CALIB_YES)
    session = MagicMock()
    session.commit = AsyncMock()
    price = SimpleNamespace(currency="XTR", final_amount=1, is_free=False)

    with (
        patch.object(
            ask_astrid.users_crud,
            "get_user_by_telegram_id",
            AsyncMock(return_value=_user(birth_time=None)),
        ),
        patch.object(ask_astrid, "get_ask_price", AsyncMock(return_value=price)),
        patch.object(
            ask_astrid.ask_crud,
            "create_draft",
            AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        ),
        patch.object(ask_astrid, "_fulfill_reading", AsyncMock()) as fulfill,
    ):
        await ask_astrid.cb_ask_calibration(callback, session)

    callback.message.answer_invoice.assert_awaited_once()
    fulfill.assert_not_awaited()


@pytest.mark.asyncio
async def test_free_status_is_recorded_as_not_in_relationship() -> None:
    callback = _callback(CALIB_NO)
    session = MagicMock()
    session.commit = AsyncMock()

    with (
        patch.object(
            ask_astrid.users_crud,
            "get_user_by_telegram_id",
            AsyncMock(return_value=_user(birth_time=None)),
        ),
        patch.object(
            ask_astrid,
            "get_ask_price",
            AsyncMock(return_value=SimpleNamespace(currency="XTR", final_amount=1, is_free=False)),
        ),
        patch.object(
            ask_astrid.ask_crud,
            "create_draft",
            AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        ) as create,
    ):
        await ask_astrid.cb_ask_calibration(callback, session)

    assert create.await_args.kwargs["in_relationship"] is False


# ─────────────────────────── карточка и подпись ───────────────────────────


def test_card_caption_uses_both_numbers() -> None:
    caption = product.card_caption(_result(total=3, past=1, future=2))
    assert "3 судьбоносных партнёра" in caption
    assert "Уже было: <b>1</b>" in caption
    assert "Впереди: <b>2</b>" in caption


def test_card_caption_when_everything_is_ahead() -> None:
    caption = product.card_caption(_result(total=1, past=0, future=1))
    assert "1 судьбоносный партнёр" in caption
    assert "впереди" in caption.lower()


def test_card_is_rendered_as_png_without_personal_data() -> None:
    png = render_card(_result())
    assert png.startswith(b"\x89PNG")
    assert len(png) > 5000


# ─────────────────────────── схема ответа ───────────────────────────


def _answer(partners: int = 3, portrait: str | None = None) -> product.FatedPartnersAnswer:
    text = portrait or ("Он появляется в момент, когда ты занята своим делом. " * 3)
    return product.FatedPartnersAnswer(
        opening="Твоя карта отвечает на этот вопрос довольно определённо.",
        verdict="Три поворотные истории, из них одна уже прожита",
        partners=[
            product.PartnerSketch(
                stage=f"{i} история",
                portrait=text,
                brings="Приносит опору и новый круг общения.",
                teaches="Учит говорить о своих условиях вслух.",
                markers=["старше тебя", "знакомство через работу"],
            )
            for i in range(1, partners + 1)
        ],
        already_lived="Первая история пришлась на возраст около двадцати девяти лет. " * 2,
        what_you_miss="Ты уходишь в молчание там, где стоит назвать своё условие вслух. " * 2,
        closing="Смотри на тех, кто приходит без спешки.",
    )


def test_validate_requires_partner_per_number() -> None:
    assert product.validate(_answer(partners=3), expected_partners=3) is None
    assert product.validate(_answer(partners=2), expected_partners=3) == "partners_count_mismatch"


def test_validate_rejects_empty_portrait_and_banned_phrases() -> None:
    assert product.validate(_answer(portrait="Хороший."), expected_partners=3) == "portrait_too_short"

    answer = _answer()
    answer.opening = "Твои вибрации говорят сами за себя."
    assert (product.validate(answer, expected_partners=3) or "").startswith("banned_phrase")


def test_rendered_answer_keeps_structure_and_markers() -> None:
    result = _result()
    html = product.render_answer(_answer(), result)
    assert "Что уже прожито" in html
    assert "Где ты их теряешь" in html
    assert "• старше тебя" in html
    assert "1. 1 история" in html


def test_rendered_answer_admits_missing_birth_time() -> None:
    result = _result()
    result.factors.has_time = False
    html = product.render_answer(_answer(), result)
    assert "Время рождения неизвестно" in html


def test_user_message_carries_numbers_and_factors() -> None:
    result = _result()
    result.factors.notes = ["десцендент в знаке Водолей (фиксированный)"]
    message = product.build_user_message(result, user_name="Аня", gender="женщина")
    assert '"fated_partners_total": 3' in message
    assert "десцендент в знаке Водолей" in message  # факторы идут по-русски
    assert "exactly 3 items" in message
    assert "first 1 already lived, then 2 still ahead" in message


# ─────────────────────────── повтор разбора ───────────────────────────


@pytest.mark.asyncio
async def test_redo_skips_archive_and_starts_new_purchase() -> None:
    """«Сделать заново» ведёт в покупку, даже когда готовый ответ есть."""
    callback = _callback(f"{CB_ASK_REDO_PREFIX}{QUESTION}")
    archived = SimpleNamespace(id=uuid4(), answer={"html": "старый разбор"})
    user_patch, archive_patch = _patch_user(
        _user(birth_time=datetime(1990, 3, 15, 14, 30)),
        archived=archived,
    )

    with user_patch, archive_patch:
        await ask_astrid.cb_ask_redo(callback, await _fsm(), MagicMock())

    shown = callback.message.edit_text.await_args.args[0]
    assert shown != A.ASK_ARCHIVE_TEXT
    assert shown == get_product(QUESTION).calibration_text


@pytest.mark.asyncio
async def test_redo_of_unknown_question_does_nothing() -> None:
    callback = _callback(f"{CB_ASK_REDO_PREFIX}money_income_ceiling")

    await ask_astrid.cb_ask_redo(callback, await _fsm(), MagicMock())

    callback.message.edit_text.assert_not_awaited()


def test_redo_button_is_offered_in_archive_and_under_the_answer() -> None:
    from astra.telegram.ask_keyboards import ask_archive_keyboard

    archive = [
        btn.callback_data
        for row in ask_archive_keyboard(QUESTION).inline_keyboard
        for btn in row
    ]
    assert f"{CB_ASK_REDO_PREFIX}{QUESTION}" in archive

    reading = SimpleNamespace(question_key=QUESTION)
    under_answer = [
        btn.callback_data
        for row in ask_answer_keyboard(reading, referral_code=None).inline_keyboard
        for btn in row
    ]
    assert f"{CB_ASK_REDO_PREFIX}{QUESTION}" in under_answer


def test_archive_text_warns_that_numbers_will_not_change() -> None:
    """Человек платит второй раз — он должен знать, что расчёт тот же."""
    assert "не изменятся" in A.ASK_ARCHIVE_TEXT
