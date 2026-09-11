"""Операции над подарками. Правила «кому можно» — в services/gift_service."""

from __future__ import annotations

import secrets
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.gifts.models import Gift, GiftStatus

# Без 0/O и 1/l/I: код читают с чужого экрана и набирают руками.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_CODE_LENGTH = 8


def generate_code(length: int = _CODE_LENGTH) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


async def create_gift(
    session: AsyncSession,
    *,
    giver_id: UUID,
    product_code: str,
) -> Gift:
    for _ in range(10):
        code = generate_code()
        if await get_by_code(session, code) is None:
            gift = Gift(giver_id=giver_id, code=code, product_code=product_code)
            session.add(gift)
            await session.flush()
            return gift
    msg = "не удалось выдать уникальный код подарка"
    raise RuntimeError(msg)


async def get_by_code(session: AsyncSession, code: str) -> Gift | None:
    result = await session.execute(select(Gift).where(Gift.code == code))
    return result.scalar_one_or_none()


async def count_unredeemed(session: AsyncSession, giver_id: UUID) -> int:
    """Сколько подарков этого человека ждут активации."""
    result = await session.execute(
        select(func.count())
        .select_from(Gift)
        .where(Gift.giver_id == giver_id, Gift.status == GiftStatus.ISSUED),
    )
    return int(result.scalar_one())


async def already_gifted(session: AsyncSession, giver_id: UUID, invitee_id: UUID) -> bool:
    """Этот человек уже забирал подарок у этого дарителя."""
    result = await session.execute(
        select(func.count())
        .select_from(Gift)
        .where(Gift.giver_id == giver_id, Gift.redeemed_by == invitee_id),
    )
    return int(result.scalar_one()) > 0


async def list_by_giver(
    session: AsyncSession,
    giver_id: UUID,
    limit: int = 20,
    status: GiftStatus | None = None,
) -> list[Gift]:
    """Подарки человека, свежие сверху. `status` — только нужное состояние."""
    query = select(Gift).where(Gift.giver_id == giver_id)
    if status is not None:
        query = query.where(Gift.status == status)
    result = await session.execute(query.order_by(Gift.created_at.desc()).limit(limit))
    return list(result.scalars())


async def count_redeemed(session: AsyncSession, giver_id: UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Gift)
        .where(Gift.giver_id == giver_id, Gift.status == GiftStatus.REDEEMED),
    )
    return int(result.scalar_one())
