"""Подарки: что можно дарить, кому это засчитывается и что получает новичок.

**Как подарок превращается в разбор.** При активации мы кладём на счёт новичка
ровно цену подаренного продукта и говорим, что именно ему подарили. Дальше
работает обычная покупка: внутренний баланс закрывает всю цену, инвойса нет,
разбор выдаётся сразу.

Отдельной сущности «право на продукт» здесь нет намеренно. Она означала бы
третий способ оплаты рядом с инвойсом и кошельком — и свою ветку в каждом из
трёх платных сценариев. Кошелёк уже встроен во все три, и подарок ложится в
него без единой новой ветки. Побочный эффект честный: если новичок не дойдёт до
подаренного разбора, звёзды останутся у него на счету, а не пропадут.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from astra.ask.products import SPECS, get_product
from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.gifts import crud as gifts_crud
from astra.gifts.models import Gift, GiftStatus
from astra.payments import models as payments_crud
from astra.payments.enums import CURRENCY_XTR
from astra.payments.service import ask_product_code, tarot_product_code
from astra.tarot.spreads import SPREADS, SpreadType
from astra.users.models import User
from astra.wallet import crud as wallet_crud
from astra.wallet.models import WalletReason

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class GiftableProduct:
    code: str
    label: str


class GiftRefusal(StrEnum):
    """Почему подарок не сработал. Тексты для человека — в хендлере."""

    UNKNOWN_CODE = "unknown_code"
    ALREADY_REDEEMED = "already_redeemed"
    NOT_A_NEWCOMER = "not_a_newcomer"
    ALREADY_GIFTED_BY_GIVER = "already_gifted_by_giver"
    SELF_GIFT = "self_gift"


@dataclass(frozen=True, slots=True)
class GiftRedeemed:
    gift: Gift
    label: str
    stars: int


def giftable_products() -> list[GiftableProduct]:
    """Что реально продаётся и потому может быть подарено.

    Натал и совместимость сюда не попадают: их нет в каталоге товаров. Появятся
    там — появятся и здесь, отдельной правки не нужно.
    """
    products = [
        GiftableProduct(
            code=tarot_product_code(str(spread)),
            label=f"{SPREADS[spread].emoji} {SPREADS[spread].title_ru}",
        )
        for spread in SpreadType
    ]
    for key in SPECS:
        product = get_product(key)
        if product is not None:
            products.append(GiftableProduct(ask_product_code(key), product.invoice_title))
    return products


def product_label(product_code: str) -> str:
    for product in giftable_products():
        if product.code == product_code:
            return product.label
    return "разбор от Астрид"


async def _product_price_stars(session: AsyncSession, product_code: str) -> int:
    row = await payments_crud.get_product_price(session, product_code, CURRENCY_XTR)
    if row is None:
        return 0
    # Дарим по полной цене товара: акция каталога — дело покупателя, а не
    # дарителя, и завтра её может не быть.
    return int(row.amount)


async def issue_gift(
    session: AsyncSession,
    giver: User,
    product_code: str,
    settings: Settings | None = None,
) -> Gift | None:
    """Выдать подарочный код. None — у человека слишком много неактивированных.

    Дарить можно скольким угодно людям; ограничен только запас невостребованных
    ссылок, иначе безлимит превращается в генератор кодов.
    """
    cfg = settings or get_settings()
    waiting = await gifts_crud.count_unredeemed(session, giver.id)
    if waiting >= cfg.gift_max_unredeemed:
        log.info(Event.GIFT_LIMIT_REACHED, user_id=giver.id, waiting=waiting)
        return None
    gift = await gifts_crud.create_gift(session, giver_id=giver.id, product_code=product_code)
    log.info(
        Event.GIFT_ISSUED,
        user_id=giver.id,
        gift_id=gift.id,
        product_code=product_code,
    )
    return gift


async def redeem_gift(
    session: AsyncSession,
    code: str,
    invitee: User,
    *,
    is_newcomer: bool,
) -> GiftRedeemed | GiftRefusal:
    """Активировать подарок для новичка: цена продукта ложится ему на счёт."""
    gift = await gifts_crud.get_by_code(session, code)
    if gift is None:
        return GiftRefusal.UNKNOWN_CODE
    if gift.status is not GiftStatus.ISSUED:
        return GiftRefusal.ALREADY_REDEEMED
    if gift.giver_id == invitee.id:
        return GiftRefusal.SELF_GIFT
    if not is_newcomer:
        return GiftRefusal.NOT_A_NEWCOMER
    if await gifts_crud.already_gifted(session, gift.giver_id, invitee.id):
        return GiftRefusal.ALREADY_GIFTED_BY_GIVER

    stars = await _product_price_stars(session, gift.product_code)
    label = product_label(gift.product_code)
    if stars > 0:
        await wallet_crud.add_entry(
            session,
            invitee.id,
            stars,
            WalletReason.REFERRAL_REWARD,
            description=f"Подарок: {label}",
            payload=f"gift:{gift.id}",
        )
    gift.status = GiftStatus.REDEEMED
    gift.redeemed_by = invitee.id
    gift.redeemed_at = datetime.now(UTC)
    await session.flush()
    log.info(
        Event.GIFT_REDEEMED,
        gift_id=gift.id,
        user_id=invitee.id,
        giver_id=gift.giver_id,
        product_code=gift.product_code,
        stars=stars,
    )
    return GiftRedeemed(gift=gift, label=label, stars=stars)


async def link_gift_on_start(
    session: AsyncSession,
    invitee: User,
    code: str | None,
) -> str | None:
    """Привязать нового человека к дарителю. Возвращает код, если подарок годен.

    Сам подарок здесь не активируется: его съел бы человек, бросивший
    регистрацию на первом экране. Активация — в конце онбординга.
    """
    if not code:
        return None
    gift = await gifts_crud.get_by_code(session, code)
    if gift is None or gift.status is not GiftStatus.ISSUED or gift.giver_id == invitee.id:
        log.info(Event.GIFT_REFUSED, code=code, user_id=invitee.id, reason="not_usable")
        return None

    from astra.referrals import crud as referrals_crud

    # Подарок несёт и реферальную привязку: отдельная ссылка «пригласить» тут
    # не нужна, а пригласивший получит своё, когда новичок вернётся.
    await referrals_crud.create_referral(
        session,
        referrer_id=gift.giver_id,
        invitee_id=invitee.id,
    )
    return code
