"""Раздел «Пригласить друга»: подарить разбор, позвать по ссылке, свой счёт.

Раздел целиком живёт в одном редактируемом экране, без исключений.

Исключение было: выданная ссылка падала в чат отдельной карточкой «Тебе
подарок» с советом переслать её другу. Держалось это на том, что найти ссылку
заново было негде. Теперь есть «Мои подарки», и карточка стала вредной —
написана она для друга, а читал её даритель и решал, что подарили ему.

Отправка идёт через `t.me/share/url`: один тап, выбор чата, и другу приходит
сообщение от самого дарителя. Это и короче ручной пересылки, и честнее — не
пересланная реклама бота, а личная рекомендация.
"""

from __future__ import annotations

from urllib.parse import quote

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import get_settings
from astra.gifts import crud as gifts_crud
from astra.gifts.models import GiftStatus
from astra.referrals.getters import get_referral_stats
from astra.services.gift_service import (
    giftable_offers,
    issue_gift,
    product_label,
    revoke_gift,
)
from astra.telegram.button_texts import (
    BTN_INVITE,
    CB_INVITE_GIFT,
    CB_INVITE_GIFT_PICK_PREFIX,
    CB_INVITE_GIFT_REVOKE_ASK_PREFIX,
    CB_INVITE_GIFT_REVOKE_DO_PREFIX,
    CB_INVITE_GIFT_SHOW_PREFIX,
    CB_INVITE_GIFTS,
    CB_INVITE_HUB,
    CB_INVITE_LINK,
)
from astra.telegram.keyboards import (
    gift_actions_keyboard,
    gift_products_keyboard,
    gift_ready_keyboard,
    gift_revoke_confirm_keyboard,
    invite_back_keyboard,
    invite_hub_keyboard,
    my_gifts_keyboard,
)
from astra.telegram.screen import alert, show_screen, toast
from astra.users import crud as users_crud
from astra.wallet.crud import get_balance

router = Router(name="invites")

INVITE_SCREEN = "invite"

# Первым делом — что человек сейчас сделает, и только потом что за это будет.
# Раньше текст начинался с награды, и раздел читался как условия программы, а
# не как понятное действие в три шага.
_HUB_TEXT = (
    "🎁 <b>Подари другу разбор</b>\n\n"
    "Платить не придётся ни тебе, ни ему — разбор за мой счёт.\n"
    "Выбираешь какой, я делаю ссылку, ты отправляешь её другу в один тап.\n\n"
    "Друг придёт и вернётся на второй день — тебе прилетит <b>{reward} ⭐</b>, "
    "и потратить их можно на любой разбор.\n\n"
    "Дарить можно сколько угодно и кому угодно — потолка нет.\n\n"
    "На счету: <b>{balance} ⭐</b>\n"
    "Пришло по твоим ссылкам: <b>{invited}</b>\n"
    "Подарков забрали: <b>{redeemed}</b>\n"
    "Ссылок в пути: <b>{waiting}</b>"
)
_PICK_TEXT = (
    "🎁 <b>Что подарить?</b>\n\n"
    "Друг получит этот разбор бесплатно — звёзды на него я положу ему сама.\n"
    "Цена на кнопке — чтобы ты видел вес подарка, платить за него не нужно."
)
# Витрина пуста: все товары каталога сейчас раздаются даром. Дарить нечего —
# и это правда, а не поломка.
_NOTHING_TO_GIFT_TEXT = (
    "Сейчас дарить нечего 🕯\n\n"
    "Все разборы и так открыты бесплатно — подарок ничего к этому не добавит. "
    "Заглядывай позже."
)
_OFFER_GONE_TEXT = "Этот разбор сейчас и так бесплатный — дарить его незачем ✨"
# Экран после выдачи: ссылка на виду, отправка — одной кнопкой. Раньше здесь
# в чат падала карточка «Тебе подарок» с советом переслать её: карточка была
# написана для друга, а читал её даритель и решал, что подарок вручили ему.
_GIFT_READY_TEXT = (
    "🎁 <b>Подарок готов</b>\n\n"
    "<b>{label}</b> — для того, кого в боте ещё нет.\n\n"
    "<code>{link}</code>\n\n"
    "Жми «Отправить другу» и выбери, кому. Ссылка не потеряется — она лежит "
    "в «Моих подарках»."
)
_MY_GIFTS_TEXT = (
    "📋 <b>Мои подарки</b>\n\n"
    "Ждут своего человека: <b>{waiting}</b>\n"
    "Забрали: <b>{redeemed}</b>\n\n"
    "Нажми на подарок, чтобы отправить ссылку заново или отозвать её."
)
_MY_GIFTS_EMPTY_TEXT = (
    "📋 <b>Мои подарки</b>\n\n"
    "Ни одной ссылки в пути.\n"
    "Все выданные разобрали — можно дарить дальше ✨"
)
# Ссылка стоит в тексте, а не только на кнопке: её копируют, чтобы отправить
# вне Telegram, и ею же подарок находится заново, если сообщение потерялось.
_GIFT_SHOW_TEXT = (
    "🎁 <b>{label}</b>\n\n"
    "<code>{link}</code>\n\n"
    "Ссылка ждёт своего человека. Сработает у того, кого в боте ещё нет."
)
_GIFT_REVOKE_ASK_TEXT = (
    "Отозвать <b>{label}</b>?\n\n"
    "Ссылка перестанет работать — если ты её уже отправил, у друга она "
    "откроется отказом."
)
_GIFT_REVOKED_TEXT = "Отозвала ✨ Эта ссылка больше не сработает."
_GIFT_GONE_TEXT = "Этого подарка больше нет — видимо, его уже забрали или отозвали."
_LINK_TEXT = (
    "🔗 <b>Твоя ссылка</b>\n\n"
    "<code>{link}</code>\n\n"
    "Тот, кто придёт по ней и вернётся на второй день, принесёт тебе "
    "<b>{reward} ⭐</b>."
)
_NO_USER_TEXT = "Сначала давай познакомимся — жми /start ✨"

# Текст, который уходит другу от лица дарителя, а не от бота. Ни слова про
# реферальную программу: подарок должен читаться как подарок, а не как
# приглашение в схему. Порядок текста и ссылки в готовом сообщении разные
# клиенты собирают по-своему, поэтому фраза читается и до ссылки, и после.
_GIFT_PITCH = "🎁 Дарю тебе разбор от Астрид — он уже оплачен, надо просто открыть"
_INVITE_PITCH = "Астрид смотрит, что происходит в небе, и рассказывает по-человечески ✨"


def _gift_link(code: str) -> str:
    username = get_settings().telegram_bot_username.lstrip("@")
    return f"https://t.me/{username}?start=gift_{code}"


def _share_url(link: str, pitch: str) -> str:
    """Ссылка на диалог «кому отправить»: один тап вместо ручной пересылки.

    Сам адрес кодируем целиком: внутри у него свой `?start=`, и первый же `&`
    в ссылке иначе оборвал бы её на полуслове.
    """
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(pitch)}"


async def _show_hub(message: Message, session: AsyncSession, user) -> None:  # noqa: ANN001
    stats = await get_referral_stats(session, user.id)
    waiting = await gifts_crud.count_unredeemed(session, user.id)
    redeemed = await gifts_crud.count_redeemed(session, user.id)
    text = _HUB_TEXT.format(
        reward=get_settings().referral_reward_stars,
        balance=await get_balance(session, user.id),
        invited=stats.invited_count,
        redeemed=redeemed,
        waiting=waiting,
    )
    await show_screen(
        message,
        text,
        scope=INVITE_SCREEN,
        parse_mode="HTML",
        reply_markup=invite_hub_keyboard(has_gifts=waiting > 0 or redeemed > 0),
    )


async def _show_my_gifts(message: Message, session: AsyncSession, user) -> None:  # noqa: ANN001
    """Выданные ссылки: единственное место, где подарок можно найти заново."""
    waiting = await gifts_crud.list_by_giver(session, user.id, status=GiftStatus.ISSUED)
    if not waiting:
        await show_screen(
            message,
            _MY_GIFTS_EMPTY_TEXT,
            scope=INVITE_SCREEN,
            parse_mode="HTML",
            reply_markup=invite_back_keyboard(),
        )
        return
    text = _MY_GIFTS_TEXT.format(
        waiting=len(waiting),
        redeemed=await gifts_crud.count_redeemed(session, user.id),
    )
    await show_screen(
        message,
        text,
        scope=INVITE_SCREEN,
        parse_mode="HTML",
        reply_markup=my_gifts_keyboard(
            [(gift.code, _gift_row_label(gift)) for gift in waiting],
        ),
    )


def _gift_row_label(gift) -> str:  # noqa: ANN001
    """Подпись строки в списке: название разбора и день выдачи.

    Без даты десять подарков одного расклада — десять одинаковых кнопок, и
    отзывать приходится наугад. День человек помнит, код подарка — нет.
    """
    return f"{product_label(gift.product_code)} · {gift.created_at:%d.%m}"


async def _show_gift(message: Message, session: AsyncSession, user, code: str) -> None:  # noqa: ANN001
    """Один выданный подарок. Чужой и уже забранный сюда не попадают."""
    gift = await gifts_crud.get_by_code(session, code)
    if gift is None or gift.giver_id != user.id or gift.status is not GiftStatus.ISSUED:
        await show_screen(
            message,
            _GIFT_GONE_TEXT,
            scope=INVITE_SCREEN,
            reply_markup=invite_back_keyboard(),
        )
        return
    link = _gift_link(gift.code)
    await show_screen(
        message,
        _GIFT_SHOW_TEXT.format(label=product_label(gift.product_code), link=link),
        scope=INVITE_SCREEN,
        parse_mode="HTML",
        reply_markup=gift_actions_keyboard(gift.code, _share_url(link, _GIFT_PITCH)),
    )


@router.message(F.text == BTN_INVITE)
async def open_invites(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    if user is None:
        await message.answer(_NO_USER_TEXT)
        return
    await state.clear()
    await _show_hub(message, session, user)


@router.callback_query(F.data == CB_INVITE_HUB)
async def cb_invite_hub(callback: CallbackQuery, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await toast(callback)
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await alert(callback, _NO_USER_TEXT)
        return
    await toast(callback)
    await _show_hub(callback.message, session, user)


@router.callback_query(F.data == CB_INVITE_GIFT)
async def cb_pick_gift(callback: CallbackQuery, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await toast(callback)
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await alert(callback, _NO_USER_TEXT)
        return
    await toast(callback)
    offers = await giftable_offers(session)
    if not offers:
        await show_screen(
            callback.message,
            _NOTHING_TO_GIFT_TEXT,
            scope=INVITE_SCREEN,
            parse_mode="HTML",
            reply_markup=invite_back_keyboard(),
        )
        return
    await show_screen(
        callback.message,
        _PICK_TEXT,
        scope=INVITE_SCREEN,
        parse_mode="HTML",
        reply_markup=gift_products_keyboard(offers),
    )


@router.callback_query(F.data == CB_INVITE_GIFTS)
async def cb_my_gifts(callback: CallbackQuery, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await toast(callback)
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await alert(callback, _NO_USER_TEXT)
        return
    await toast(callback)
    await _show_my_gifts(callback.message, session, user)


@router.callback_query(F.data.startswith(CB_INVITE_GIFT_SHOW_PREFIX))
async def cb_show_gift(callback: CallbackQuery, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await toast(callback)
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await alert(callback, _NO_USER_TEXT)
        return
    await toast(callback)
    code = (callback.data or "").removeprefix(CB_INVITE_GIFT_SHOW_PREFIX)
    await _show_gift(callback.message, session, user, code)


@router.callback_query(F.data.startswith(CB_INVITE_GIFT_REVOKE_ASK_PREFIX))
async def cb_revoke_ask(callback: CallbackQuery, session: AsyncSession) -> None:
    """Отзыв ломает ссылку, которая может быть уже у друга, — переспрашиваем."""
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await toast(callback)
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await alert(callback, _NO_USER_TEXT)
        return
    await toast(callback)
    code = (callback.data or "").removeprefix(CB_INVITE_GIFT_REVOKE_ASK_PREFIX)
    gift = await gifts_crud.get_by_code(session, code)
    if gift is None or gift.giver_id != user.id or gift.status is not GiftStatus.ISSUED:
        await _show_my_gifts(callback.message, session, user)
        return
    await show_screen(
        callback.message,
        _GIFT_REVOKE_ASK_TEXT.format(label=product_label(gift.product_code)),
        scope=INVITE_SCREEN,
        parse_mode="HTML",
        reply_markup=gift_revoke_confirm_keyboard(code),
    )


@router.callback_query(F.data.startswith(CB_INVITE_GIFT_REVOKE_DO_PREFIX))
async def cb_revoke_do(callback: CallbackQuery, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await toast(callback)
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await alert(callback, _NO_USER_TEXT)
        return
    code = (callback.data or "").removeprefix(CB_INVITE_GIFT_REVOKE_DO_PREFIX)
    revoked = await revoke_gift(session, user, code)
    if revoked is not None:
        await session.commit()
    # Отзывать было нечего — забрали, пока человек думал. Тоже говорим словами:
    # немой ответ на «Да, отозвать» читается как несработавшая кнопка.
    await toast(callback, _GIFT_REVOKED_TEXT if revoked else _GIFT_GONE_TEXT)
    await _show_my_gifts(callback.message, session, user)


@router.callback_query(F.data == CB_INVITE_LINK)
async def cb_invite_link(callback: CallbackQuery, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await toast(callback)
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await alert(callback, _NO_USER_TEXT)
        return
    await toast(callback)
    stats = await get_referral_stats(session, user.id)
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Отправить другу",
                    url=_share_url(stats.referral_link, _INVITE_PITCH),
                ),
            ],
            *invite_back_keyboard().inline_keyboard,
        ],
    )
    await show_screen(
        callback.message,
        _LINK_TEXT.format(
            link=stats.referral_link,
            reward=get_settings().referral_reward_stars,
        ),
        scope=INVITE_SCREEN,
        parse_mode="HTML",
        reply_markup=markup,
    )


@router.callback_query(F.data.startswith(CB_INVITE_GIFT_PICK_PREFIX))
async def cb_issue_gift(callback: CallbackQuery, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await toast(callback)
        return
    product_code = (callback.data or "").removeprefix(CB_INVITE_GIFT_PICK_PREFIX)
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await alert(callback, _NO_USER_TEXT)
        return
    # Сверяемся с той же витриной, что человек видел. Кнопка могла остаться от
    # прошлого экрана, а товар за это время уйти в бесплатные — и подарок из
    # него получился бы пустой.
    if product_code not in {p.code for p in await giftable_offers(session)}:
        await alert(callback, _OFFER_GONE_TEXT)
        return

    gift = await issue_gift(session, user, product_code)
    await session.commit()
    await toast(callback)

    # Раздел остаётся одним экраном до конца. Отдельная карточка в чат здесь
    # была нужна, пока выданную ссылку негде было найти заново; теперь она
    # лежит в «Моих подарках», и держать её копию в переписке незачем.
    link = _gift_link(gift.code)
    await show_screen(
        callback.message,
        _GIFT_READY_TEXT.format(label=product_label(product_code), link=link),
        scope=INVITE_SCREEN,
        parse_mode="HTML",
        reply_markup=gift_ready_keyboard(_share_url(link, _GIFT_PITCH)),
    )
