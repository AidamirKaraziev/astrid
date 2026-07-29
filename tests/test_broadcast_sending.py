"""Отправка рассылки: кнопки, судьба каждого сообщения, повтор недошедшим."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from astra.broadcasts.keyboards import broadcast_keyboard
from astra.broadcasts.models import BroadcastStatus, DeliveryStatus
from astra.broadcasts.service import send_all
from astra.workers.telegram_send import BotBlockedError

_SERVICE = "astra.broadcasts.service"


def _person(name: str | None = "Алина", telegram_id: int = 1):
    return SimpleNamespace(
        id=uuid4(),
        telegram_id=telegram_id,
        profile=SimpleNamespace(display_name=name) if name else None,
    )


def _delivery():
    return SimpleNamespace(status=DeliveryStatus.PENDING, error=None, sent_at=None)


def _broadcast(personalize: bool = False):
    return SimpleNamespace(
        id=uuid4(),
        final_text="Колесо ждёт тебя",
        personalize=personalize,
        status=BroadcastStatus.SENDING,
        sent_count=0,
        blocked_count=0,
        failed_count=0,
        finished_at=None,
    )


class TestKeyboard:
    def test_section_button_uses_default_title(self):
        markup = broadcast_keyboard([{"section": "wheel"}])
        assert markup.inline_keyboard[0][0].text == "Крутить колесо 🌀"
        assert markup.inline_keyboard[0][0].callback_data

    def test_custom_title_wins(self):
        markup = broadcast_keyboard([{"section": "tarot", "title": "Хочу расклад"}])
        assert markup.inline_keyboard[0][0].text == "Хочу расклад"

    def test_url_button(self):
        markup = broadcast_keyboard([{"title": "Канал", "url": "https://t.me/astra"}])
        assert markup.inline_keyboard[0][0].url == "https://t.me/astra"

    def test_junk_url_dropped(self):
        """Кнопка в никуда выяснится уже после отправки тысяче человек."""
        assert broadcast_keyboard([{"title": "x", "url": "javascript:alert(1)"}]) is None

    def test_unknown_section_dropped(self):
        assert broadcast_keyboard([{"section": "секретный_раздел"}]) is None

    def test_no_buttons(self):
        assert broadcast_keyboard([]) is None
        assert broadcast_keyboard(None) is None


class TestSendAll:
    async def _run(self, people_and_deliveries, sender):
        session = AsyncMock()
        session.flush = AsyncMock()
        broadcast = _broadcast()
        with (
            patch(f"{_SERVICE}.pending_deliveries", AsyncMock(return_value=people_and_deliveries)),
            patch(f"{_SERVICE}._count", AsyncMock(return_value=0)),
            patch(f"{_SERVICE}.users_crud.mark_bot_blocked", AsyncMock()) as blocked,
        ):
            progress = await send_all(session, broadcast, sender, pause=0)
        return progress, broadcast, blocked

    async def test_everyone_gets_the_message(self):
        rows = [(_delivery(), _person(telegram_id=i)) for i in range(3)]
        sender = AsyncMock()
        progress, broadcast, _ = await self._run(rows, sender)

        assert progress.sent == 3
        assert sender.await_count == 3
        assert all(delivery.status == DeliveryStatus.SENT for delivery, _ in rows)
        assert broadcast.status == BroadcastStatus.SENT

    async def test_blocked_user_marked_and_skipped(self):
        rows = [(_delivery(), _person())]
        sender = AsyncMock(side_effect=BotBlockedError(1))
        progress, _, blocked = await self._run(rows, sender)

        assert progress.blocked == 1
        assert rows[0][0].status == DeliveryStatus.BLOCKED
        blocked.assert_awaited_once()

    async def test_one_failure_does_not_stop_the_rest(self):
        """Отвалившаяся сеть у одного не должна лишить письма остальных."""
        rows = [(_delivery(), _person(telegram_id=i)) for i in range(3)]
        sender = AsyncMock(side_effect=[RuntimeError("сеть"), None, None])
        progress, _, _ = await self._run(rows, sender)

        assert (progress.sent, progress.failed) == (2, 1)
        assert rows[0][0].status == DeliveryStatus.FAILED
        assert "RuntimeError" in rows[0][0].error

    async def test_personalisation_uses_each_own_name(self):
        rows = [(_delivery(), _person("Алина")), (_delivery(), _person("Кирилл"))]
        sender = AsyncMock()
        session = AsyncMock()
        broadcast = _broadcast(personalize=True)
        with (
            patch(f"{_SERVICE}.pending_deliveries", AsyncMock(return_value=rows)),
            patch(f"{_SERVICE}._count", AsyncMock(return_value=0)),
        ):
            await send_all(session, broadcast, sender, pause=0)

        texts = [call.args[1] for call in sender.await_args_list]
        assert texts[0].startswith("Алина, ")
        assert texts[1].startswith("Кирилл, ")

    async def test_person_without_name_gets_plain_text(self):
        rows = [(_delivery(), _person(name=None))]
        sender = AsyncMock()
        session = AsyncMock()
        with (
            patch(f"{_SERVICE}.pending_deliveries", AsyncMock(return_value=rows)),
            patch(f"{_SERVICE}._count", AsyncMock(return_value=0)),
        ):
            await send_all(session, _broadcast(personalize=True), sender, pause=0)

        assert sender.await_args.args[1] == "Колесо ждёт тебя"


class TestRetry:
    async def test_only_failed_are_reset(self):
        """Заблокировавших не повторяем — им всё равно не дойдёт."""
        from astra.broadcasts.service import reset_failed

        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock(rowcount=4))
        assert await reset_failed(session, uuid4()) == 4

        statement = str(session.execute.await_args.args[0])
        assert "broadcast_deliveries" in statement
        assert "status" in statement
