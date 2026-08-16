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
    price_stars: int = 0
    """Сколько ляжет другу на счёт. 0 — цена ещё не спрошена у каталога."""


class GiftRefusal(StrEnum):
    """Почему подарок не сработал.

    Причина нужна не логу, а человеку: он пришёл по ссылке «Забрать подарок» и
    имеет право услышать, что именно пошло не так. Тексты — в `gift_delivery`.
    """

    UNKNOWN_CODE = "unknown_code"
    ALREADY_REDEEMED = "already_redeemed"
    REVOKED = "revoked"
    NOT_A_NEWCOMER = "not_a_newcomer"
    ALREADY_GIFTED_BY_GIVER = "already_gifted_by_giver"
    SELF_GIFT = "self_gift"


@dataclass(frozen=True, slots=True)
class GiftRedeemed:
    gift: Gift
    label: str
    stars: int


def giftable_products() -> list[GiftableProduct]:
    """Что вообще бывает подарком — без цен и без оглядки на акции.

    Нужен там, где важно только имя товара: подпись подарка в списке, в
    карточке новичка, в отказе. Что можно подарить **сейчас** — `giftable_offers`.

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
            # Свой значок у ветки вопросов: в общем списке они иначе сливаются
            # с раскладами, а заголовков у inline-клавиатуры не бывает.
            products.append(
                GiftableProduct(ask_product_code(key), f"💬 {product.invoice_title}"),
            )
    return products


async def giftable_offers(session: AsyncSession) -> list[GiftableProduct]:
    """Что можно подарить прямо сейчас, с ценой на каждом.

    Бесплатное сегодня в витрину не пускаем по двум причинам. Дарить то, что
    друг и так возьмёт даром, — не подарок, а пустой жест. И звёзды мы кладём
    по полной цене товара: подарить бесплатный расклад значило бы намыть другу
    50 ⭐ на платные разборы из воздуха.
    """
    offers = []
    for product in giftable_products():
        row = await payments_crud.get_product_price(session, product.code, CURRENCY_XTR)
        if row is None or row.discount_percent >= 100 or row.amount <= 0:
            continue
        offers.append(
            GiftableProduct(product.code, product.label, price_stars=int(row.amount)),
        )
    return offers


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


async def revoke_gift(session: AsyncSession, giver: User, code: str) -> Gift | None:
    """Забрать невостребованную ссылку обратно. None — отзывать нечего.

    Единственный способ освободить место, когда потолок неактивированных
    ссылок выбран брошенными новичками. Забранный подарок не отзывается: там
    уже потрачены звёзды.
    """
    gift = await gifts_crud.get_by_code(session, code)
    if gift is None or gift.giver_id != giver.id or gift.status is not GiftStatus.ISSUED:
        return None
    gift.status = GiftStatus.REVOKED
    await session.flush()
    log.info(Event.GIFT_REVOKED, user_id=giver.id, gift_id=gift.id, code=code)
    return gift


async def gift_slots_left(
    session: AsyncSession,
    giver: User,
    settings: Settings | None = None,
) -> int:
    """Сколько ссылок человек ещё может выдать, не отзывая старые."""
    cfg = settings or get_settings()
    waiting = await gifts_crud.count_unredeemed(session, giver.id)
    return max(0, cfg.gift_max_unredeemed - waiting)


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
    # Отозванный отделяем от забранного: даритель мог забрать место обратно,
    # пока новичок регистрировался, и «уже забрали» было бы неправдой.
    if gift.status is GiftStatus.REVOKED:
        return GiftRefusal.REVOKED
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
    *,
    is_newcomer: bool,
) -> str | GiftRefusal | None:
    """Разобрать подарочную ссылку, с которой человек пришёл в бота.

    Три исхода, и каждый значит своё:

    * `None` — ссылка была не подарочная, говорить не о чем;
    * `GiftRefusal` — подарок не сработает, и человеку надо сказать почему:
      он нажал «Забрать подарок» и молча получить главное меню не должен;
    * `str` — код годен, активируем его в конце онбординга.

    Сам подарок здесь не активируется: его съел бы человек, бросивший
    регистрацию на первом экране. Ни один отказ код не сжигает — ссылка
    остаётся годной для того, кому она и предназначалась.
    """
    if not code:
        return None

    def refused(reason: GiftRefusal) -> GiftRefusal:
        log.info(Event.GIFT_REFUSED, code=code, user_id=invitee.id, reason=str(reason))
        return reason

    gift = await gifts_crud.get_by_code(session, code)
    if gift is None:
        return refused(GiftRefusal.UNKNOWN_CODE)
    if gift.status is GiftStatus.REVOKED:
        return refused(GiftRefusal.REVOKED)
    if gift.status is not GiftStatus.ISSUED:
        return refused(GiftRefusal.ALREADY_REDEEMED)
    # Свою же ссылку проверяем до «не новичок»: даритель по определению не
    # новичок, и общий отказ спрятал бы от него настоящую причину.
    if gift.giver_id == invitee.id:
        return refused(GiftRefusal.SELF_GIFT)
    if not is_newcomer:
        return refused(GiftRefusal.NOT_A_NEWCOMER)

    from astra.referrals import crud as referrals_crud

    # Подарок несёт и реферальную привязку: отдельная ссылка «пригласить» тут
    # не нужна, а пригласивший получит своё, когда новичок вернётся.
    await referrals_crud.create_referral(
        session,
        referrer_id=gift.giver_id,
        invitee_id=invitee.id,
    )
    return code
