"""Служба заботы: хаб/FAQ, релей обращений и ответы операторов."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from astra.core.config import Settings
from astra.telegram import support_text as T
from astra.telegram.button_texts import (
    BTN_HELP,
    CB_SUPPORT_CLOSE,
    CB_SUPPORT_FAQ_PREFIX,
    CB_SUPPORT_WRITE,
    SUPPORT_FAQ_PAYMENT,
)
from astra.telegram.handlers import support, support_relay
from astra.telegram.states import SupportStates

ADMIN_GROUP = -1001234567890


async def _fsm() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=2, user_id=3))


def _relay_settings() -> Settings:
    return Settings(telegram_admin_group_id=ADMIN_GROUP, telegram_support_username="astrid_team")


# ─────────────────────────── keyboards ───────────────────────────


def test_main_menu_has_help_button() -> None:
    from astra.telegram.keyboards import main_menu_keyboard

    texts = {btn.text for row in main_menu_keyboard().keyboard for btn in row}
    assert BTN_HELP in texts


def test_support_hub_keyboard_with_and_without_human() -> None:
    from astra.telegram.keyboards import support_hub_keyboard

    with_human = support_hub_keyboard(True).inline_keyboard
    labels = [btn.text for row in with_human for btn in row]
    data = [btn.callback_data for row in with_human for btn in row]
    # Все темы FAQ присутствуют
    assert sum(1 for d in data if d.startswith(CB_SUPPORT_FAQ_PREFIX)) == len(T.FAQ_BUTTONS)
    assert any(d == CB_SUPPORT_WRITE for d in data)
    assert data[-1] == CB_SUPPORT_CLOSE

    without = support_hub_keyboard(False).inline_keyboard
    data_wo = [btn.callback_data for row in without for btn in row]
    assert CB_SUPPORT_WRITE not in data_wo
    assert CB_SUPPORT_CLOSE in data_wo


# ─────────────────────────── hub / FAQ ───────────────────────────


@pytest.mark.asyncio
async def test_faq_callback_shows_answer() -> None:
    callback = MagicMock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    callback.data = f"{CB_SUPPORT_FAQ_PREFIX}{SUPPORT_FAQ_PAYMENT}"
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()

    with patch.object(support, "get_settings", return_value=_relay_settings()):
        await support.cb_faq(callback)

    text = callback.message.edit_text.await_args.args[0]
    assert text == T.FAQ_ANSWERS[SUPPORT_FAQ_PAYMENT]


@pytest.mark.asyncio
async def test_write_button_enters_writing_state_when_relay_on() -> None:
    state = await _fsm()
    callback = MagicMock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.answer = AsyncMock()

    with patch.object(support, "get_settings", return_value=_relay_settings()):
        await support.cb_write(callback, state)

    assert await state.get_state() == SupportStates.writing.state
    assert callback.message.answer.await_args.args[0] == T.SUPPORT_WRITE_PROMPT


@pytest.mark.asyncio
async def test_write_button_falls_back_to_account_when_no_group() -> None:
    state = await _fsm()
    callback = MagicMock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.answer = AsyncMock()
    settings = Settings(telegram_admin_group_id=0, telegram_support_username="astrid_team")

    with patch.object(support, "get_settings", return_value=settings):
        await support.cb_write(callback, state)

    assert await state.get_state() is None  # в релей не входим
    markup = callback.message.answer.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].url == "https://t.me/astrid_team"


# ─────────────────────────── relay: приём обращения ───────────────────────────


@pytest.mark.asyncio
async def test_receive_ticket_posts_card_and_creates_ticket() -> None:
    state = await _fsm()
    await state.set_state(SupportStates.writing)

    message = AsyncMock()
    message.text = "Оплатил, а расклад не пришёл"
    message.caption = None
    message.photo = None
    message.document = None
    message.from_user = MagicMock(id=42, username="anya", is_bot=False)
    message.bot = AsyncMock()
    message.bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=555))
    message.bot.edit_message_text = AsyncMock()
    message.answer = AsyncMock()

    user = MagicMock(id=uuid4(), profile=MagicMock(display_name="Аня"))
    ticket = MagicMock(number=1000, id=user.id)

    with (
        patch.object(support_relay, "get_settings", return_value=_relay_settings()),
        patch.object(support_relay.users_crud, "get_user_by_telegram_id", AsyncMock(return_value=user)),
        patch.object(support_relay, "latest_payment_summary", AsyncMock(return_value="Расклад · 50 XTR")),
        patch.object(support_relay.support_crud, "create_ticket", AsyncMock(return_value=ticket)) as create,
    ):
        await support_relay.receive_ticket(message, state, AsyncMock())

    # Карточка ушла в админ-группу
    sent_chat, sent_text = message.bot.send_message.await_args.args[0], message.bot.send_message.await_args.args[1]
    assert sent_chat == ADMIN_GROUP
    assert "42" in sent_text  # telegram_id клиента виден оператору
    # Тикет создан с id карточки для маппинга ответов
    assert create.await_args.kwargs["admin_message_id"] == 555
    # Состояние сброшено, клиент получил подтверждение
    assert await state.get_state() is None
    assert message.answer.await_args.args[0] == T.SUPPORT_TICKET_ACCEPTED


@pytest.mark.asyncio
async def test_receive_ticket_ignores_empty_message() -> None:
    state = await _fsm()
    await state.set_state(SupportStates.writing)
    message = AsyncMock()
    message.text = "   "
    message.caption = None
    message.photo = None
    message.document = None
    message.from_user = MagicMock(id=42, username="anya", is_bot=False)
    message.bot = AsyncMock()
    message.answer = AsyncMock()

    with patch.object(support_relay, "get_settings", return_value=_relay_settings()):
        await support_relay.receive_ticket(message, state, AsyncMock())

    message.bot.send_message.assert_not_awaited()
    assert await state.get_state() == SupportStates.writing.state  # остаёмся ждать текст


# ─────────────────────────── relay: ответ оператора ───────────────────────────


@pytest.mark.asyncio
async def test_operator_reply_delivers_to_client() -> None:
    message = AsyncMock()
    message.chat = MagicMock(id=ADMIN_GROUP, type="supergroup")
    message.reply_to_message = MagicMock(message_id=555)
    message.from_user = MagicMock(is_bot=False)
    message.text = "Вернули звёзды, всё хорошо 💜"
    message.caption = None
    message.photo = None
    message.document = None
    message.bot = AsyncMock()
    message.reply = AsyncMock()

    ticket = MagicMock(number=1000, telegram_id=42)

    with (
        patch.object(support_relay, "get_settings", return_value=_relay_settings()),
        patch.object(support_relay.support_crud, "get_ticket_by_admin_message", AsyncMock(return_value=ticket)),
        patch.object(support_relay.support_crud, "mark_ticket_answered", AsyncMock()) as answered,
    ):
        await support_relay.operator_reply(message, AsyncMock())

    deliver = message.bot.send_message.await_args
    assert deliver.args[0] == 42
    assert T.SUPPORT_REPLY_PREFIX in deliver.args[1]
    answered.assert_awaited_once()
    assert "Доставлено" in message.reply.await_args.args[0]


@pytest.mark.asyncio
async def test_operator_reply_ignored_when_no_ticket() -> None:
    message = AsyncMock()
    message.chat = MagicMock(id=ADMIN_GROUP, type="supergroup")
    message.reply_to_message = MagicMock(message_id=999)
    message.from_user = MagicMock(is_bot=False)
    message.text = "просто болтаю в группе"
    message.caption = None
    message.photo = None
    message.document = None
    message.bot = AsyncMock()

    with (
        patch.object(support_relay, "get_settings", return_value=_relay_settings()),
        patch.object(support_relay.support_crud, "get_ticket_by_admin_message", AsyncMock(return_value=None)),
    ):
        await support_relay.operator_reply(message, AsyncMock())

    message.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_operator_reply_ignored_outside_admin_group() -> None:
    message = AsyncMock()
    message.chat = MagicMock(id=-999, type="supergroup")  # не админ-группа
    message.reply_to_message = MagicMock(message_id=555)
    message.from_user = MagicMock(is_bot=False)
    message.bot = AsyncMock()

    with patch.object(support_relay, "get_settings", return_value=_relay_settings()):
        await support_relay.operator_reply(message, AsyncMock())

    message.bot.send_message.assert_not_awaited()


# ─────────────────────────── service helpers ───────────────────────────


def test_build_ticket_card_contains_context() -> None:
    from astra.support.service import build_ticket_card

    card = build_ticket_card(
        number=1000,
        display_name="Аня <script>",
        telegram_id=42,
        username="anya",
        last_purchase="Расклад · charge: ch_1",
        text="помогите",
    )
    assert "#1000" in card
    assert "42" in card
    assert "ch_1" in card
    assert "&lt;script&gt;" in card  # имя экранировано


@pytest.mark.asyncio
async def test_latest_payment_summary_formats_row() -> None:
    from astra.support.service import latest_payment_summary

    payment = MagicMock(
        amount=50,
        currency="XTR",
        status="completed",
        provider_charge_id="ch_1",
        created_at=datetime(2026, 7, 21, 14, 30),
    )
    result = MagicMock()
    result.first = MagicMock(return_value=(payment, "Расклад «Загадай желание»"))
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    summary = await latest_payment_summary(session, uuid4())
    assert "оплачен" in summary
    assert "ch_1" in summary
    assert "50 XTR" in summary
