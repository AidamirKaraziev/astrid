"""Логика службы заботы: карточка обращения и контекст для оператора."""

from __future__ import annotations

import html
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.payments.models import Payment, Product

# Ограничиваем текст обращения в карточке — на случай очень длинных сообщений.
_MAX_TICKET_TEXT = 3000


async def latest_payment_summary(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    """Короткая сводка последней покупки — чтобы оператор сразу видел контекст.

    Включает charge_id: по нему делается ручной возврат звёзд.
    """
    result = await session.execute(
        select(Payment, Product.title)
        .join(Product, Product.code == Payment.product_code)
        .where(Payment.user_id == user_id)
        .order_by(Payment.created_at.desc())
        .limit(1),
    )
    row = result.first()
    if row is None:
        return None
    payment, title = row
    status_ru = "возвращён" if payment.status == "refunded" else "оплачен"
    when = payment.created_at.strftime("%d.%m %H:%M")
    return (
        f"{title} · {payment.amount} {payment.currency} · {when} · {status_ru}\n"
        f"charge: <code>{payment.provider_charge_id}</code>"
    )


def build_ticket_card(
    *,
    number: int | None,
    display_name: str,
    telegram_id: int,
    username: str | None,
    last_purchase: str | None,
    text: str,
) -> str:
    """HTML-карточка обращения для админ-группы. Отвечать — reply на неё."""
    header = f"🆘 <b>Обращение #{number}</b>" if number else "🆘 <b>Новое обращение</b>"
    who = html.escape(display_name or "без имени")
    handle = f" · @{html.escape(username)}" if username else ""
    purchase = last_purchase or "—"
    body = html.escape(text[:_MAX_TICKET_TEXT])
    return (
        f"{header}\n"
        f"👤 {who}{handle}\n"
        f"🆔 <code>{telegram_id}</code>\n"
        f"🧾 Последняя покупка: {purchase}\n"
        f"———\n"
        f"{body}\n\n"
        f"↩️ <i>Ответьте reply на это сообщение — доставим клиенту.</i>"
    )
