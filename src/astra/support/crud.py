"""Доступ к тикетам службы заботы."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.support.models import SupportTicket


async def create_ticket(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    telegram_id: int,
    admin_chat_id: int,
    admin_message_id: int,
    last_message: str,
) -> SupportTicket:
    ticket = SupportTicket(
        user_id=user_id,
        telegram_id=telegram_id,
        admin_chat_id=admin_chat_id,
        admin_message_id=admin_message_id,
        last_message=last_message,
    )
    session.add(ticket)
    await session.flush()
    await session.refresh(ticket)
    return ticket


async def get_ticket_by_admin_message(
    session: AsyncSession,
    admin_chat_id: int,
    admin_message_id: int,
) -> SupportTicket | None:
    result = await session.execute(
        select(SupportTicket).where(
            SupportTicket.admin_chat_id == admin_chat_id,
            SupportTicket.admin_message_id == admin_message_id,
        ),
    )
    return result.scalar_one_or_none()


async def mark_ticket_answered(session: AsyncSession, ticket: SupportTicket) -> None:
    ticket.status = "answered"
    ticket.answered_at = datetime.now(UTC)
    await session.flush()
