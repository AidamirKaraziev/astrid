"""Контракт отправки: контент остаётся, экран переписывается, тост исчезает.

Тесты гоняют настоящий `Bot` поверх `FakeTelegramSession`, поэтому видно
реальные вызовы Bot API — `sendMessage`, `editMessageText`, `deleteMessage`, —
а не то, что вернул мок. Реестр экрана (Redis) подменяется словарём в памяти.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText
from aiogram.types import Chat, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.types import User as TgUser

from fake_telegram import BOT_ID, build_bot

from astra.telegram.screen import (
    alert,
    close_screen,
    send_content,
    show_screen,
    toast,
)
from astra.telegram.screen_store import Screen, ScreenKind

CHAT_ID = 5001
SCOPE = "tarot"


def _markup(text: str = "Три карты") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data="tarot:three")]],
    )


def _incoming(bot: Any) -> Message:
    """Сообщение от человека: текст или нажатие reply-кнопки."""
    message = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=CHAT_ID, type="private"),
        from_user=TgUser(id=CHAT_ID, is_bot=False, first_name="Аида"),
        text="🔮 Карты Таро",
    )
    return message.as_(bot)


def _tap(bot: Any) -> Message:
    """Нажатие кнопки на самом экране: апдейт приходит с сообщения бота."""
    message = Message(
        message_id=1001,
        date=datetime.now(UTC),
        chat=Chat(id=CHAT_ID, type="private"),
        from_user=TgUser(id=BOT_ID, is_bot=True, first_name="Astrid"),
        text="Выбери расклад",
    )
    return message.as_(bot)


class FakeScreenStore:
    """Реестр экранов в памяти вместо Redis."""

    def __init__(self, initial: Screen | None = None) -> None:
        self.screen = initial

    async def get(self, chat_id: int, scope: str) -> Screen | None:
        return self.screen

    async def set(self, chat_id: int, scope: str, message_id: int, kind: ScreenKind) -> None:
        self.screen = Screen(message_id, kind)

    async def clear(self, chat_id: int, scope: str) -> Screen | None:
        previous, self.screen = self.screen, None
        return previous


def _with_store(store: FakeScreenStore) -> Any:
    return patch.multiple(
        "astra.telegram.screen",
        get_screen=AsyncMock(side_effect=store.get),
        set_screen=AsyncMock(side_effect=store.set),
        clear_screen=AsyncMock(side_effect=store.clear),
    )


def _bad_request(text: str) -> TelegramBadRequest:
    return TelegramBadRequest(
        method=EditMessageText(chat_id=CHAT_ID, message_id=777, text="x"),
        message=text,
    )


@pytest.mark.asyncio
async def test_first_show_sends_message_and_remembers_it() -> None:
    bot = build_bot()
    store = FakeScreenStore()

    with _with_store(store):
        message_id = await show_screen(
            _incoming(bot),
            "Выбери расклад",
            scope=SCOPE,
            reply_markup=_markup(),
        )

    assert bot.session.api_methods() == ["sendMessage"]
    assert store.screen == Screen(message_id, ScreenKind.TEXT)


@pytest.mark.asyncio
async def test_second_show_edits_instead_of_sending() -> None:
    bot = build_bot()
    store = FakeScreenStore(Screen(1001, ScreenKind.TEXT))

    with _with_store(store):
        message_id = await show_screen(
            _tap(bot),
            "О чём спросишь карты?",
            scope=SCOPE,
            reply_markup=_markup("Пропустить"),
        )

    assert bot.session.api_methods() == ["editMessageText"]
    assert message_id == 1001
    assert store.screen == Screen(1001, ScreenKind.TEXT)


@pytest.mark.asyncio
async def test_not_modified_is_swallowed() -> None:
    """Двойной тап по кнопке — не ошибка, экран остаётся прежним."""
    bot = build_bot()
    store = FakeScreenStore(Screen(1001, ScreenKind.TEXT))

    with (
        _with_store(store),
        patch.object(
            type(bot),
            "edit_message_text",
            new=AsyncMock(side_effect=_bad_request("Bad Request: message is not modified")),
        ),
    ):
        message_id = await show_screen(_tap(bot), "Тот же текст", scope=SCOPE)

    assert message_id == 1001
    assert bot.session.api_methods() == []
    assert store.screen == Screen(1001, ScreenKind.TEXT)


@pytest.mark.asyncio
async def test_unreachable_screen_is_recreated() -> None:
    """Человек удалил экран или ему больше 48 часов — сценарий не падает."""
    bot = build_bot()
    # id заведомо не из счётчика фейка (тот начинает с 1000), чтобы «пересоздали»
    # не спуталось с «отредактировали».
    store = FakeScreenStore(Screen(77, ScreenKind.TEXT))

    with (
        _with_store(store),
        patch.object(
            type(bot),
            "edit_message_text",
            new=AsyncMock(side_effect=_bad_request("Bad Request: message to edit not found")),
        ),
    ):
        message_id = await show_screen(_tap(bot), "Выбери расклад", scope=SCOPE)

    assert bot.session.api_methods() == ["sendMessage"]
    assert message_id != 77
    assert store.screen == Screen(message_id, ScreenKind.TEXT)


@pytest.mark.asyncio
async def test_unexpected_bad_request_is_not_hidden() -> None:
    """Ошибка разметки должна долетать до Sentry, а не тонуть в фолбэке."""
    bot = build_bot()
    store = FakeScreenStore(Screen(1001, ScreenKind.TEXT))

    with (
        _with_store(store),
        patch.object(
            type(bot),
            "edit_message_text",
            new=AsyncMock(side_effect=_bad_request("Bad Request: can't parse entities")),
        ),
        pytest.raises(TelegramBadRequest),
    ):
        await show_screen(_tap(bot), "<b>сломанный", scope=SCOPE)


@pytest.mark.asyncio
async def test_media_screen_is_replaced_by_text_screen() -> None:
    """Фото не превращается в текст: старый экран удаляется, шлётся новый."""
    bot = build_bot()
    store = FakeScreenStore(Screen(1001, ScreenKind.MEDIA))

    with _with_store(store):
        message_id = await show_screen(_tap(bot), "Расклад готов", scope=SCOPE)

    assert bot.session.api_methods() == ["deleteMessage", "sendMessage"]
    assert store.screen == Screen(message_id, ScreenKind.TEXT)


@pytest.mark.asyncio
async def test_close_screen_deletes_and_forgets() -> None:
    bot = build_bot()
    store = FakeScreenStore(Screen(1001, ScreenKind.TEXT))

    with _with_store(store):
        await close_screen(_incoming(bot), SCOPE)

    assert bot.session.api_methods() == ["deleteMessage"]
    assert store.screen is None


@pytest.mark.asyncio
async def test_close_screen_survives_already_deleted_message() -> None:
    bot = build_bot()
    store = FakeScreenStore(Screen(1001, ScreenKind.TEXT))

    with (
        _with_store(store),
        patch.object(
            type(bot),
            "delete_message",
            new=AsyncMock(side_effect=_bad_request("Bad Request: message to delete not found")),
        ),
    ):
        await close_screen(_incoming(bot), SCOPE)

    assert store.screen is None


@pytest.mark.asyncio
async def test_content_closes_screen_and_always_sends_new() -> None:
    """Результат не должен выезжать из-под живого меню."""
    bot = build_bot()
    store = FakeScreenStore(Screen(1001, ScreenKind.TEXT))

    with _with_store(store):
        await send_content(_incoming(bot), "Прошлое — Башня…", scope=SCOPE)

    assert bot.session.api_methods() == ["deleteMessage", "sendMessage"]
    assert store.screen is None


@pytest.mark.asyncio
async def test_content_without_scope_leaves_screen_alone() -> None:
    bot = build_bot()
    store = FakeScreenStore(Screen(1001, ScreenKind.TEXT))

    with _with_store(store):
        await send_content(_incoming(bot), "Карта дня ✨")

    assert bot.session.api_methods() == ["sendMessage"]
    assert store.screen == Screen(1001, ScreenKind.TEXT)


@pytest.mark.asyncio
async def test_toast_and_alert_fit_telegram_limit() -> None:
    """Telegram режет ответ на callback по 200 символам — режем сами."""
    answered: list[dict[str, Any]] = []

    class FakeCallback:
        async def answer(self, text: str = "", show_alert: bool = False) -> None:
            answered.append({"text": text, "show_alert": show_alert})

    callback = FakeCallback()
    await toast(callback, "Приз твой ✨")  # type: ignore[arg-type]
    await alert(callback, "Ж" * 300)  # type: ignore[arg-type]

    assert answered[0] == {"text": "Приз твой ✨", "show_alert": False}
    assert answered[1]["show_alert"] is True
    assert len(answered[1]["text"]) == 200


@pytest.mark.asyncio
async def test_screen_is_sent_by_bot_not_by_message_answer() -> None:
    """Экран идёт мимо AutoKeyboardMiddleware: reply_markup занят inline-кнопками."""
    bot = build_bot()
    store = FakeScreenStore()
    incoming = _incoming(bot)
    answer_mock = AsyncMock()
    object.__setattr__(incoming, "answer", answer_mock)

    with _with_store(store):
        await show_screen(incoming, "Выбери расклад", scope=SCOPE, reply_markup=_markup())

    answer_mock.assert_not_awaited()
    assert bot.session.api_methods() == ["sendMessage"]
    assert bot.session.calls[0].payload.get("from_user") is None
    assert bot.session.calls[0].method.chat_id == CHAT_ID
    assert BOT_ID  # бот в фейке настоящий, id зафиксирован в fake_telegram


@pytest.mark.asyncio
async def test_human_message_moves_the_screen_down() -> None:
    """Человек написал или нажал reply-кнопку — экран переезжает вниз чата.

    Регрессия: после неоплаченного инвойса экран раздела оставался выше него.
    Повторный вход в раздел правил то самое сообщение наверху, и человек решал,
    что раздел сломан и держит его в неоплаченном раскладе.
    """
    bot = build_bot()
    # id вне счётчика фейка (тот начинает с 1000): «перенесли» не спутается
    # с «отредактировали на месте».
    store = FakeScreenStore(Screen(77, ScreenKind.TEXT))

    with _with_store(store):
        message_id = await show_screen(
            _incoming(bot),
            "Выбери расклад",
            scope=SCOPE,
            reply_markup=_markup(),
        )

    assert bot.session.api_methods() == ["deleteMessage", "sendMessage"]
    assert message_id != 77
    assert store.screen == Screen(message_id, ScreenKind.TEXT)


@pytest.mark.asyncio
async def test_tap_on_the_screen_keeps_it_in_place() -> None:
    """Кнопка на самом экране — человек смотрит на него, двигать некуда."""
    bot = build_bot()
    store = FakeScreenStore(Screen(1001, ScreenKind.TEXT))

    with _with_store(store):
        message_id = await show_screen(_tap(bot), "О чём спросишь карты?", scope=SCOPE)

    assert bot.session.api_methods() == ["editMessageText"]
    assert message_id == 1001
