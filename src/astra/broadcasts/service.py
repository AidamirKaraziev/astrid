"""Жизненный цикл рассылки: черновик → список получателей → отправка → итоги.

Отправку делает воркер, а не панель: тысяча сообщений — это минуты работы, и
держать всё это время открытым HTTP-запрос из браузера нельзя. Панель только
готовит рассылку и ставит задачу.

Список получателей фиксируется в момент запуска отдельными строками. Так
рассылка не «поедет» из-за того, что кто-то зарегистрировался или заблокировал
бота на середине, и появляется точный ответ на вопрос «кому не дошло».
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from astra.broadcasts.audience import Criteria, resolve
from astra.broadcasts.editor import personalize_text
from astra.broadcasts.models import (
    Broadcast,
    BroadcastDelivery,
    BroadcastStatus,
    DeliveryStatus,
)
from astra.core.observability import get_logger
from astra.users import crud as users_crud
from astra.users.models import User

log = get_logger(__name__)

# Telegram разрешает около 30 сообщений в секунду на бота. Держимся ниже:
# упереться в лимит на середине рассылки дороже, чем закончить на минуту позже.
MESSAGES_PER_SECOND = 20
_PAUSE = 1 / MESSAGES_PER_SECOND


@dataclass(frozen=True, slots=True)
class Progress:
    sent: int = 0
    blocked: int = 0
    failed: int = 0

    @property
    def total(self) -> int:
        return self.sent + self.blocked + self.failed


async def create_draft(
    session: AsyncSession,
    *,
    source_text: str,
    final_text: str,
    criteria: dict,
    used_ai: bool = False,
    personalize: bool = False,
    buttons: list[dict] | None = None,
    image_path: str | None = None,
    direct_recipients: list[int] | None = None,
) -> Broadcast:
    broadcast = Broadcast(
        source_text=source_text,
        final_text=final_text,
        criteria=criteria,
        used_ai=used_ai,
        personalize=personalize,
        buttons=buttons or [],
        image_path=image_path,
        direct_recipients=direct_recipients or [],
        status=BroadcastStatus.DRAFT,
    )
    session.add(broadcast)
    await session.flush()
    return broadcast


async def recipients_for(session: AsyncSession, broadcast: Broadcast) -> list[User]:
    """Кому пойдёт: либо адресный список, либо выборка по фильтрам."""
    if broadcast.direct_recipients:
        rows = await session.execute(
            select(User).where(
                User.telegram_id.in_(broadcast.direct_recipients),
                User.bot_blocked_at.is_(None),
            ),
        )
        return list(rows.scalars().all())

    return await resolve(session, Criteria(**broadcast.criteria))


async def prepare(session: AsyncSession, broadcast: Broadcast) -> int:
    """Зафиксировать получателей строками. Возвращает размер аудитории."""
    people = await recipients_for(session, broadcast)
    for person in people:
        session.add(
            BroadcastDelivery(
                broadcast_id=broadcast.id,
                user_id=person.id,
                status=DeliveryStatus.PENDING,
            ),
        )

    broadcast.audience_size = len(people)
    broadcast.status = BroadcastStatus.SENDING
    broadcast.started_at = datetime.now(UTC)
    await session.flush()
    log.info("broadcast.prepared", broadcast_id=broadcast.id, audience=len(people))
    return len(people)


async def pending_deliveries(
    session: AsyncSession,
    broadcast_id: uuid.UUID,
) -> list[tuple[BroadcastDelivery, User]]:
    rows = await session.execute(
        select(BroadcastDelivery, User)
        .join(User, User.id == BroadcastDelivery.user_id)
        .where(
            BroadcastDelivery.broadcast_id == broadcast_id,
            BroadcastDelivery.status.in_([DeliveryStatus.PENDING, DeliveryStatus.FAILED]),
        ),
    )
    return list(rows.all())


async def send_all(
    session: AsyncSession,
    broadcast: Broadcast,
    sender,
    *,
    pause: float = _PAUSE,
) -> Progress:
    """Разослать всем, кто ещё ждёт. `sender(user, text) -> None` бросает при ошибке.

    Ошибка одного сообщения не останавливает рассылку: человек с заблокированным
    ботом или отвалившейся сетью не должен лишать письма остальных.
    """
    from astra.workers.telegram_send import BotBlockedError

    sent = blocked = failed = 0

    for delivery, person in await pending_deliveries(session, broadcast.id):
        text = broadcast.final_text
        if broadcast.personalize:
            name = person.profile.display_name if person.profile else None
            text = personalize_text(text, name)

        try:
            await sender(person, text)
        except BotBlockedError:
            delivery.status = DeliveryStatus.BLOCKED
            delivery.error = "бот заблокирован"
            blocked += 1
            await users_crud.mark_bot_blocked(session, person.telegram_id)
        except Exception as exc:  # noqa: BLE001 — причину показываем в истории
            delivery.status = DeliveryStatus.FAILED
            delivery.error = f"{type(exc).__name__}: {exc}"[:200]
            failed += 1
        else:
            delivery.status = DeliveryStatus.SENT
            delivery.sent_at = datetime.now(UTC)
            delivery.error = None
            sent += 1

        await session.flush()
        if pause:
            await asyncio.sleep(pause)

    broadcast.sent_count = await _count(session, broadcast.id, DeliveryStatus.SENT)
    broadcast.blocked_count = await _count(session, broadcast.id, DeliveryStatus.BLOCKED)
    broadcast.failed_count = await _count(session, broadcast.id, DeliveryStatus.FAILED)
    broadcast.status = BroadcastStatus.SENT
    broadcast.finished_at = datetime.now(UTC)
    await session.flush()

    log.info(
        "broadcast.finished",
        broadcast_id=broadcast.id,
        sent=broadcast.sent_count,
        blocked=broadcast.blocked_count,
        failed=broadcast.failed_count,
    )
    return Progress(sent=sent, blocked=blocked, failed=failed)


async def _count(session: AsyncSession, broadcast_id: uuid.UUID, status: DeliveryStatus) -> int:
    return (
        await session.execute(
            select(func.count(BroadcastDelivery.id)).where(
                BroadcastDelivery.broadcast_id == broadcast_id,
                BroadcastDelivery.status == status,
            ),
        )
    ).scalar_one()


async def reset_failed(session: AsyncSession, broadcast_id: uuid.UUID) -> int:
    """Вернуть недошедшие в очередь. Заблокировавших не трогаем — им не дойдёт."""
    result = await session.execute(
        update(BroadcastDelivery)
        .where(
            BroadcastDelivery.broadcast_id == broadcast_id,
            BroadcastDelivery.status == DeliveryStatus.FAILED,
        )
        .values(status=DeliveryStatus.PENDING, error=None),
    )
    return result.rowcount or 0


async def history(session: AsyncSession, limit: int = 20) -> list[Broadcast]:
    rows = await session.execute(
        select(Broadcast).order_by(Broadcast.created_at.desc()).limit(limit),
    )
    return list(rows.scalars().all())
