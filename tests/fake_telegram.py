"""Ненастоящий Telegram: бот, который никуда не ходит, а пишет всё в список.

Нужен, чтобы гонять регистрацию через **настоящий** `Dispatcher` — со всеми
роутерами, фильтрами, FSM и middleware, — не трогая Bot API. Мокать сам
`session`/`message` в таких тестах нельзя: именно мок-сессия и пропустила
поломку старта — с `AsyncMock` любой код «работает».

Что здесь есть:

* `FakeTelegramSession` — транспорт aiogram: отвечает валидными объектами и
  складывает все исходящие вызовы в `calls`;
* `build_test_dispatcher` — обёртка над боевым `create_dispatcher`, которая
  ловит исключения хендлеров (боевой `@dp.errors()` их глотает, и без этого
  сломанный онбординг выглядел бы как зелёный тест);
* конструкторы апдейтов — сообщение и нажатие inline-кнопки.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import TelegramMethod
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    Update,
)
from aiogram.types import User as TgUser

BOT_TOKEN = "424242:TEST_TOKEN_FOR_FAKE_TELEGRAM"
BOT_ID = 424242
BOT_USERNAME = "TestAstraBot"


@dataclass
class SentCall:
    """Один исходящий вызов Bot API."""

    api_method: str
    method: TelegramMethod
    payload: dict[str, Any]

    @property
    def text(self) -> str:
        return str(self.payload.get("text") or self.payload.get("caption") or "")

    @property
    def reply_markup(self) -> Any:
        return getattr(self.method, "reply_markup", None)

    def buttons(self) -> list[str]:
        """Тексты кнопок (reply или inline) в порядке появления."""
        markup = self.reply_markup
        if isinstance(markup, ReplyKeyboardMarkup):
            return [btn.text for row in markup.keyboard for btn in row]
        if isinstance(markup, InlineKeyboardMarkup):
            return [btn.text for row in markup.inline_keyboard for btn in row]
        return []

    def callback_data(self) -> list[str]:
        markup = self.reply_markup
        if isinstance(markup, InlineKeyboardMarkup):
            return [
                btn.callback_data
                for row in markup.inline_keyboard
                for btn in row
                if btn.callback_data
            ]
        return []

    def __repr__(self) -> str:  # чтобы падение теста читалось глазами
        return f"<{self.api_method} {self.text[:60]!r}>"


class FakeTelegramSession(BaseSession):
    """Транспорт aiogram, который отвечает сам себе.

    Возвращает настоящие pydantic-объекты (`Message`, `True`), поэтому код
    хендлеров работает как в бою: `sent.video`, `message.answer(...)` и так
    далее ходят по обычным веткам, а не по «моку, который отвечает моком».
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[SentCall] = []
        self._message_id = 1000

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod,
        timeout: int | None = None,
    ) -> Any:
        payload = method.model_dump(warnings=False)
        self.calls.append(SentCall(method.__api_method__, method, payload))

        returning = method.__returning__
        if returning is Message:
            return self._fake_message(payload)
        if returning is TgUser:
            return TgUser(id=BOT_ID, is_bot=True, first_name="Astrid", username=BOT_USERNAME)
        if returning is bool:
            return True
        return True

    async def stream_content(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        msg = "тесты не качают файлы из Telegram"
        raise NotImplementedError(msg)

    async def close(self) -> None:
        return None

    def _fake_message(self, payload: dict[str, Any]) -> Message:
        self._message_id += 1
        # Видео намеренно не отдаём: боевой код кэширует file_id в общий ключ
        # Redis, и тест затёр бы его выдуманным значением для живого бота.
        return Message(
            message_id=self._message_id,
            date=datetime.now(UTC),
            chat=Chat(id=int(payload.get("chat_id") or 0), type="private"),
            from_user=TgUser(id=BOT_ID, is_bot=True, first_name="Astrid", username=BOT_USERNAME),
            text=payload.get("text"),
            caption=payload.get("caption"),
        )

    # --- удобные выборки для ассертов -------------------------------------

    def texts(self) -> list[str]:
        return [call.text for call in self.calls if call.text]

    def last_text(self) -> str:
        texts = self.texts()
        return texts[-1] if texts else ""

    def api_methods(self) -> list[str]:
        return [call.api_method for call in self.calls]

    def clear(self) -> None:
        self.calls.clear()


def build_bot() -> Bot:
    return Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=FakeTelegramSession(),
    )


@dataclass
class BotHarness:
    """Бот + диспетчер + запись исходящих вызовов и исключений хендлеров."""

    bot: Bot
    dispatcher: Dispatcher
    errors: list[BaseException] = field(default_factory=list)
    _update_id: int = 0

    @property
    def session(self) -> FakeTelegramSession:
        return self.bot.session  # type: ignore[return-value]

    @property
    def calls(self) -> list[SentCall]:
        return self.session.calls

    def texts(self) -> list[str]:
        return self.session.texts()

    def last_text(self) -> str:
        return self.session.last_text()

    def clear(self) -> None:
        self.session.clear()
        self.errors.clear()

    def _next_update_id(self) -> int:
        self._update_id += 1
        return self._update_id

    async def send(self, text: str, *, telegram_id: int, **user_fields: Any) -> list[SentCall]:
        """Человек пишет боту текст (или жмёт reply-кнопку)."""
        before = len(self.calls)
        update = make_message_update(
            text,
            telegram_id=telegram_id,
            update_id=self._next_update_id(),
            **user_fields,
        )
        await self._feed(update)
        return self.calls[before:]

    async def click(self, callback_data: str, *, telegram_id: int) -> list[SentCall]:
        """Человек жмёт inline-кнопку."""
        before = len(self.calls)
        update = make_callback_update(
            callback_data,
            telegram_id=telegram_id,
            update_id=self._next_update_id(),
        )
        await self._feed(update)
        return self.calls[before:]

    async def _feed(self, update: Update) -> None:
        await self.dispatcher.feed_update(self.bot, update)
        if self.errors:
            raise AssertionError(
                f"хендлер упал на апдейте {update.update_id}: {self.errors[0]!r}",
            ) from self.errors[0]


# Роутеры бота — модульные синглтоны: приклеиться ко второму `Dispatcher` они
# не могут («Router is already attached»). Поэтому диспетчер на процесс один,
# и все тесты берут его отсюда, а не собирают свой.
_dispatcher: Dispatcher | None = None
_errors: list[BaseException] = []


async def get_shared_dispatcher() -> Dispatcher:
    """Боевой диспетчер, собранный один раз на процесс."""
    global _dispatcher

    if _dispatcher is None:
        from astra.core.config import get_settings
        from astra.telegram.bot import create_dispatcher

        settings = get_settings().model_copy(update={"fsm_storage": "memory"})
        _dispatcher = await create_dispatcher(settings)

        @_dispatcher.errors.outer_middleware()
        async def _record_error(handler, event, data):  # type: ignore[no-untyped-def]
            _errors.append(event.exception)
            return await handler(event, data)

    return _dispatcher


async def build_test_dispatcher(bot: Bot) -> BotHarness:
    """Боевой диспетчер (все роутеры и middleware) + перехват падений.

    `create_dispatcher` вешает `@dp.errors()`, который логирует исключение и
    возвращает None — для прода правильно (человек не должен видеть трейс),
    для теста смертельно: сломанный `/start` прошёл бы как успешный. Поэтому
    свой наблюдатель ошибок регистрируем **до** боевого.

    Диспетчер переживает тест, а движок БД — нет (у каждого теста свой event
    loop), поэтому фабрику сессий в `DbSessionMiddleware` каждый раз
    переподключаем к текущему движку.
    """
    from astra.db.session import get_session_factory
    from astra.telegram.middlewares import DbSessionMiddleware

    dispatcher = await get_shared_dispatcher()

    factory = get_session_factory()
    for middleware in dispatcher.update.middleware:
        if isinstance(middleware, DbSessionMiddleware):
            middleware.session_factory = factory

    _errors.clear()
    return BotHarness(bot=bot, dispatcher=dispatcher, errors=_errors)


def make_user(telegram_id: int, **overrides: Any) -> TgUser:
    fields: dict[str, Any] = {
        "id": telegram_id,
        "is_bot": False,
        "first_name": "Аида",
        "username": f"user{telegram_id}",
        "language_code": "ru",
    }
    fields.update(overrides)
    return TgUser(**fields)


def make_message_update(
    text: str,
    *,
    telegram_id: int,
    update_id: int = 1,
    message_id: int = 1,
    **user_fields: Any,
) -> Update:
    user = make_user(telegram_id, **user_fields)
    message = Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat(id=telegram_id, type="private"),
        from_user=user,
        text=text,
    )
    return Update(update_id=update_id, message=message)


def make_callback_update(
    callback_data: str,
    *,
    telegram_id: int,
    update_id: int = 1,
    message_id: int = 1,
    **user_fields: Any,
) -> Update:
    user = make_user(telegram_id, **user_fields)
    message = Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat(id=telegram_id, type="private"),
        from_user=TgUser(id=BOT_ID, is_bot=True, first_name="Astrid", username=BOT_USERNAME),
        text="Выбери населённый пункт из списка:",
    )
    callback = CallbackQuery(
        id=f"cb-{update_id}",
        from_user=user,
        chat_instance=f"chat-{telegram_id}",
        message=message,
        data=callback_data,
    )
    return Update(update_id=update_id, callback_query=callback)


def find_call(calls: list[SentCall], fragment: str) -> SentCall | None:
    for call in calls:
        if fragment.lower() in call.text.lower():
            return call
    return None


def assert_said(calls: list[SentCall], fragment: str) -> SentCall:
    call = find_call(calls, fragment)
    if call is None:
        raise AssertionError(f"бот не сказал {fragment!r}; сказал: {[c.text for c in calls]}")
    return call


__all__ = [
    "BOT_ID",
    "BOT_USERNAME",
    "BotHarness",
    "FakeTelegramSession",
    "SentCall",
    "assert_said",
    "build_bot",
    "build_test_dispatcher",
    "find_call",
    "get_shared_dispatcher",
    "make_callback_update",
    "make_message_update",
]
