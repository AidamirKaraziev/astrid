"""Операции над леджером кошелька. Бизнес-правила — в services/wallet_service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.wallet.models import StarWalletEntry, WalletReason

# Сколько живёт бронь под невыставленный счёт. Час — с запасом: инвойс
# оплачивают за минуты, а простоявшую сутки бронь человек воспринял бы как
# пропавшие звёзды.
HOLD_TTL = timedelta(hours=1)


def _active(now: datetime):
    """Записи, которые сейчас участвуют в балансе: просроченные брони — нет."""
    return or_(
        StarWalletEntry.hold_expires_at.is_(None),
        StarWalletEntry.hold_expires_at > now,
    )


async def get_balance(session: AsyncSession, user_id: UUID, now: datetime | None = None) -> int:
    moment = now or datetime.now(UTC)
    result = await session.execute(
        select(func.coalesce(func.sum(StarWalletEntry.delta), 0)).where(
            StarWalletEntry.user_id == user_id,
            _active(moment),
        ),
    )
    return int(result.scalar_one())


async def add_entry(
    session: AsyncSession,
    user_id: UUID,
    delta: int,
    reason: WalletReason,
    *,
    description: str | None = None,
    payload: str | None = None,
    hold_expires_at: datetime | None = None,
) -> StarWalletEntry:
    entry = StarWalletEntry(
        user_id=user_id,
        delta=delta,
        reason=reason,
        description=description,
        payload=payload,
        hold_expires_at=hold_expires_at,
    )
    session.add(entry)
    await session.flush()
    return entry


async def hold(
    session: AsyncSession,
    user_id: UUID,
    amount: int,
    *,
    payload: str,
    description: str | None = None,
    now: datetime | None = None,
) -> StarWalletEntry:
    """Забронировать `amount` под инвойс с этим payload."""
    moment = now or datetime.now(UTC)
    return await add_entry(
        session,
        user_id,
        -amount,
        WalletReason.HOLD,
        description=description,
        payload=payload,
        hold_expires_at=moment + HOLD_TTL,
    )


async def total_outstanding(session: AsyncSession, now: datetime | None = None) -> int:
    """Сколько звёзд лежит на счетах у всех разом — по той же формуле, что баланс.

    Это обязательство: напечатанное даром, что однажды потратят вместо оплаты.
    """
    moment = now or datetime.now(UTC)
    result = await session.execute(
        select(func.coalesce(func.sum(StarWalletEntry.delta), 0)).where(_active(moment)),
    )
    return int(result.scalar_one())


async def sum_by_payload_prefix(session: AsyncSession, user_id: UUID, prefix: str) -> int:
    """Сколько всего начислено записями с таким началом payload.

    Назначение `REFERRAL_REWARD` носят три разных начисления — награда
    пригласившему, приветствие новичку и подарок, — и различает их только
    payload. Поэтому считаем по нему, а не по причине.
    """
    result = await session.execute(
        select(func.coalesce(func.sum(StarWalletEntry.delta), 0)).where(
            StarWalletEntry.user_id == user_id,
            StarWalletEntry.payload.startswith(prefix),
        ),
    )
    return int(result.scalar_one())


async def find_by_payload(
    session: AsyncSession,
    user_id: UUID,
    payload: str,
    reason: WalletReason,
) -> StarWalletEntry | None:
    """Последняя запись с этим payload и назначением. Срок брони не учитываем:
    просрочка — не «нет записи», а отдельный случай, решает сервис.
    """
    result = await session.execute(
        select(StarWalletEntry)
        .where(
            StarWalletEntry.user_id == user_id,
            StarWalletEntry.payload == payload,
            StarWalletEntry.reason == reason,
        )
        .order_by(StarWalletEntry.created_at.desc())
        .limit(1),
    )
    return result.scalar_one_or_none()


async def find_hold(
    session: AsyncSession,
    user_id: UUID,
    payload: str,
) -> StarWalletEntry | None:
    return await find_by_payload(session, user_id, payload, WalletReason.HOLD)


async def settle_hold(
    session: AsyncSession,
    entry: StarWalletEntry,
    *,
    description: str | None = None,
) -> None:
    """Бронь стала покупкой: списание постоянное, срок больше не нужен."""
    entry.reason = WalletReason.PURCHASE
    entry.hold_expires_at = None
    if description:
        entry.description = description
    await session.flush()


async def release_hold(session: AsyncSession, entry: StarWalletEntry) -> None:
    """Снять бронь: звёзды возвращаются в баланс сразу."""
    entry.reason = WalletReason.RELEASED
    entry.hold_expires_at = datetime.now(UTC)
    await session.flush()
