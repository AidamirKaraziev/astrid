"""Чтение и правка каталога из панели.

Все проверки повторяют ограничения БД (amount > 0, скидка 0..100), но падают
понятной ошибкой на экране, а не 500-й. Итоговая цена считается тем же
`ProductPriceInfo`, что и на покупке, — панель показывает ровно то, что заплатит
человек.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.payments.models import Product, ProductPrice
from astra.payments.service import ProductPriceInfo
from astra.wheel.models import WheelPrize


class AdminError(ValueError):
    """Ошибка ввода: текст показываем администратору как есть."""


@dataclass(frozen=True, slots=True)
class PriceView:
    id: uuid.UUID
    currency: str
    amount: int
    discount_percent: int
    is_active: bool

    @property
    def info(self) -> ProductPriceInfo:
        return ProductPriceInfo(self.currency, self.amount, self.discount_percent)


@dataclass(frozen=True, slots=True)
class ProductView:
    code: str
    kind: str
    title: str
    is_active: bool
    prices: tuple[PriceView, ...]


@dataclass(frozen=True, slots=True)
class PrizeView:
    id: uuid.UUID
    product_code: str
    product_title: str
    discount_percent: int
    weight: int
    is_active: bool

    def chance_percent(self, total_weight: int) -> float:
        return round(self.weight * 100 / total_weight, 1) if total_weight else 0.0


async def list_catalog(session: AsyncSession) -> list[ProductView]:
    """Все товары с их ценами — включая выключенные и вовсе без цены."""
    products = (await session.execute(select(Product).order_by(Product.kind, Product.code))).scalars()
    prices = (await session.execute(select(ProductPrice).order_by(ProductPrice.currency))).scalars()

    by_product: dict[str, list[PriceView]] = {}
    for row in prices:
        by_product.setdefault(row.product_code, []).append(
            PriceView(
                id=row.id,
                currency=row.currency,
                amount=row.amount,
                discount_percent=row.discount_percent,
                is_active=row.is_active,
            ),
        )

    return [
        ProductView(
            code=product.code,
            kind=product.kind,
            title=product.title,
            is_active=product.is_active,
            prices=tuple(by_product.get(product.code, ())),
        )
        for product in products
    ]


def _validate_price(amount: int, discount_percent: int) -> None:
    if amount <= 0:
        raise AdminError("Цена должна быть больше нуля.")
    if not 0 <= discount_percent <= 100:
        raise AdminError("Скидка — от 0 до 100 процентов.")


async def update_price(
    session: AsyncSession,
    price_id: uuid.UUID,
    *,
    amount: int,
    discount_percent: int,
    is_active: bool,
) -> tuple[ProductPrice, ProductPriceInfo]:
    """Правка цены. Возвращает строку и прежнее состояние — для лога."""
    _validate_price(amount, discount_percent)
    row = await session.get(ProductPrice, price_id)
    if row is None:
        raise AdminError("Цена не найдена — возможно, её удалили в другой вкладке.")

    before = ProductPriceInfo(row.currency, row.amount, row.discount_percent)
    row.amount = amount
    row.discount_percent = discount_percent
    row.is_active = is_active
    await session.flush()
    return row, before


async def create_price(
    session: AsyncSession,
    product_code: str,
    *,
    currency: str,
    amount: int,
    discount_percent: int,
) -> ProductPrice:
    """Новая валюта для товара; на пару товар × валюта в БД стоит уникальность."""
    _validate_price(amount, discount_percent)
    currency = currency.strip().upper()
    if not currency:
        raise AdminError("Укажите валюту.")

    product = await session.get(Product, product_code)
    if product is None:
        raise AdminError(f"Товара {product_code} нет в каталоге.")

    existing = await session.execute(
        select(ProductPrice).where(
            ProductPrice.product_code == product_code,
            ProductPrice.currency == currency,
        ),
    )
    if existing.scalar_one_or_none() is not None:
        raise AdminError(f"Цена в {currency} у этого товара уже есть.")

    row = ProductPrice(
        product_code=product_code,
        currency=currency,
        amount=amount,
        discount_percent=discount_percent,
        is_active=True,
    )
    session.add(row)
    await session.flush()
    return row


async def set_product_active(session: AsyncSession, product_code: str, *, is_active: bool) -> Product:
    product = await session.get(Product, product_code)
    if product is None:
        raise AdminError(f"Товара {product_code} нет в каталоге.")
    product.is_active = is_active
    await session.flush()
    return product


async def list_prizes(session: AsyncSession) -> list[PrizeView]:
    """Сектора колеса вместе с названиями товаров."""
    prizes = (
        await session.execute(select(WheelPrize).order_by(WheelPrize.product_code, WheelPrize.discount_percent))
    ).scalars()
    titles = {
        code: title
        for code, title in (await session.execute(select(Product.code, Product.title))).all()
    }
    return [
        PrizeView(
            id=prize.id,
            product_code=prize.product_code,
            product_title=titles.get(prize.product_code, prize.product_code),
            discount_percent=prize.discount_percent,
            weight=prize.weight,
            is_active=prize.is_active,
        )
        for prize in prizes
    ]


async def update_prize(
    session: AsyncSession,
    prize_id: uuid.UUID,
    *,
    discount_percent: int,
    weight: int,
    is_active: bool,
) -> WheelPrize:
    if not 1 <= discount_percent <= 100:
        raise AdminError("Скидка приза — от 1 до 100 процентов (100 = бесплатно).")
    if weight <= 0:
        raise AdminError("Вес сектора должен быть больше нуля.")

    prize = await session.get(WheelPrize, prize_id)
    if prize is None:
        raise AdminError("Приз не найден — возможно, его удалили в другой вкладке.")

    prize.discount_percent = discount_percent
    prize.weight = weight
    prize.is_active = is_active
    await session.flush()
    return prize
