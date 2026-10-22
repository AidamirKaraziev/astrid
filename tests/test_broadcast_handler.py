"""handle_broadcast_send целиком: замыкание sender доходит до транспорта Telegram.

Подменяем только сетевой слой (httpx.AsyncClient) и выборку получателей из БД;
`send_telegram_html` и сам `sender` остаются настоящими — иначе тест не увидит
пропавший импорт в `handlers`.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from astra.broadcasts.models import Broadcast, BroadcastStatus, DeliveryStatus
from astra.messaging.schemas import TaskMessage, TaskType
from astra.workers.handlers import handle_broadcast_send

_SERVICE = "astra.broadcasts.service"
_TRANSPORT = "astra.workers.telegram_send"


def _person(telegram_id: int):
    return SimpleNamespace(id=uuid4(), telegram_id=telegram_id, profile=None)


def _delivery():
    return SimpleNamespace(status=DeliveryStatus.PENDING, error=None, sent_at=None)


async def test_broadcast_reaches_every_recipient():
    broadcast = SimpleNamespace(
        id=uuid4(),
        final_text="Колесо ждёт тебя",
        personalize=False,
        buttons=[{"section": "wheel"}],
        status=BroadcastStatus.SENDING,
        sent_count=0,
        blocked_count=0,
        failed_count=0,
        finished_at=None,
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=broadcast)
    rows = [(_delivery(), _person(telegram_id)) for telegram_id in (101, 102, 103)]

    response = MagicMock(is_error=False, status_code=200)
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=client)
    client_cm.__aexit__ = AsyncMock(return_value=False)
    settings = SimpleNamespace(telegram_bot_token="test-token", telegram_proxy_url_effective=None)

    task = TaskMessage(type=TaskType.BROADCAST_SEND, report_id=broadcast.id)

    with (
        patch(f"{_SERVICE}.pending_deliveries", AsyncMock(return_value=rows)),
        patch(f"{_SERVICE}._count", AsyncMock(return_value=3)),
        patch(f"{_SERVICE}.asyncio.sleep", AsyncMock()),
        patch(f"{_TRANSPORT}.get_settings", return_value=settings),
        patch(f"{_TRANSPORT}.httpx.AsyncClient", return_value=client_cm),
    ):
        await handle_broadcast_send(session, task)

    # send_all глотает любое исключение замыкания в delivery.error — смотрим туда,
    # иначе NameError из handlers выглядел бы как «ничего не отправилось».
    assert [delivery.error for delivery, _ in rows] == [None, None, None]
    assert session.get.await_args.args[0] is Broadcast
    payloads = [call.kwargs["json"] for call in client.post.await_args_list]
    assert [p["chat_id"] for p in payloads] == [101, 102, 103]
    for payload in payloads:
        assert payload["text"] == "Колесо ждёт тебя"
        assert "reply_markup" in payload
    assert all(delivery.status == DeliveryStatus.SENT for delivery, _ in rows)
    session.commit.assert_awaited()
