"""Релей службы заботы: обращение клиента ↔ ответ оператора через админ-группу.

Клиент пишет в боте (состояние SupportStates.writing) → бот кладёт карточку
обращения в закрытую группу операторов. Оператор отвечает reply на карточку →
бот находит тикет по id сообщения и доставляет ответ клиенту в бот.
"""

from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import get_settings
from astra.core.observability import Event, get_logger
from astra.support import crud as support_crud
from astra.support.service import build_ticket_card, latest_payment_summary
from astra.telegram import support_text as T
from astra.telegram.keyboards import main_menu_keyboard
from astra.telegram.states import SupportStates
from astra.users import crud as users_crud

log = get_logger(__name__)

router = Router(name="support_relay")


@router.message(SupportStates.writing)
async def receive_ticket(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """Клиент прислал обращение — кладём карточку в админ-группу."""
    settings = get_settings()
    admin_chat_id = settings.telegram_admin_group_id
    if admin_chat_id == 0 or message.bot is None or message.from_user is None:
        await state.clear()
        return

    text = (message.text or message.caption or "").strip()
    has_media = bool(message.photo or message.document)
    if not text and not has_media:
        from astra.telegram.keyboards import support_writing_keyboard

        await message.answer(
            "Напиши, что случилось — обычным текстом 💜",
            reply_markup=support_writing_keyboard(),
        )
        return

    tg_id = message.from_user.id
    user = await users_crud.get_user_by_telegram_id(session, tg_id)
    if user is None:
        await state.clear()
        await message.answer(T.SUPPORT_NO_CHANNEL, reply_markup=main_menu_keyboard())
        return

    display_name = user.profile.display_name if user.profile else ""
    last_purchase = await latest_payment_summary(session, user.id)

    # Сначала кладём карточку без номера — получаем message_id для маппинга.
    placeholder = build_ticket_card(
        number=None,
        display_name=display_name,
        telegram_id=tg_id,
        username=message.from_user.username,
        last_purchase=last_purchase,
        text=text or "(вложение без текста)",
    )
    card_msg = await message.bot.send_message(admin_chat_id, placeholder)

    ticket = await support_crud.create_ticket(
        session,
        user_id=user.id,
        telegram_id=tg_id,
        admin_chat_id=admin_chat_id,
        admin_message_id=card_msg.message_id,
        last_message=text or "(вложение без текста)",
    )

    # Дополняем карточку номером обращения (косметика, не критично при сбое).
    try:
        await message.bot.edit_message_text(
            build_ticket_card(
                number=ticket.number,
                display_name=display_name,
                telegram_id=tg_id,
                username=message.from_user.username,
                last_purchase=last_purchase,
                text=text or "(вложение без текста)",
            ),
            chat_id=admin_chat_id,
            message_id=card_msg.message_id,
        )
    except Exception:
        log.warning(Event.SUPPORT_TICKET_CARD_FAILED, stage="number_edit", ticket=ticket.number)

    # Вложение (скриншот оплаты и т.п.) — копируем ответом на карточку.
    if has_media:
        try:
            await message.copy_to(chat_id=admin_chat_id, reply_to_message_id=card_msg.message_id)
        except Exception:
            log.warning(Event.SUPPORT_TICKET_CARD_FAILED, stage="media_copy", ticket=ticket.number)

    log.info(Event.SUPPORT_TICKET_CREATED, ticket=ticket.number, user_id=str(user.id))
    await state.clear()
    await message.answer(T.SUPPORT_TICKET_ACCEPTED, reply_markup=main_menu_keyboard())


@router.message(F.chat.type.in_({"group", "supergroup"}), F.reply_to_message)
async def operator_reply(message: Message, session: AsyncSession) -> None:
    """Оператор ответил reply на карточку в админ-группе — доставляем клиенту."""
    settings = get_settings()
    if message.chat.id != settings.telegram_admin_group_id or message.bot is None:
        return
    if message.reply_to_message is None or message.from_user is None or message.from_user.is_bot:
        return

    ticket = await support_crud.get_ticket_by_admin_message(
        session,
        admin_chat_id=message.chat.id,
        admin_message_id=message.reply_to_message.message_id,
    )
    if ticket is None:
        return

    reply_text = (message.text or message.caption or "").strip()
    delivered = False
    try:
        if reply_text:
            await message.bot.send_message(
                ticket.telegram_id,
                T.SUPPORT_REPLY_PREFIX + html.escape(reply_text),
            )
            delivered = True
        if message.photo or message.document:
            await message.copy_to(chat_id=ticket.telegram_id)
            delivered = True
    except Exception as exc:
        log.warning(
            Event.SUPPORT_REPLY_DELIVER_FAILED,
            ticket=ticket.number,
            error_type=type(exc).__name__,
        )
        await message.reply("⚠️ Не доставлено: возможно, клиент заблокировал бота.")
        return

    if not delivered:
        return

    await support_crud.mark_ticket_answered(session, ticket)
    log.info(Event.SUPPORT_REPLY_DELIVERED, ticket=ticket.number)
    await message.reply("✅ Доставлено клиенту", disable_notification=True)
