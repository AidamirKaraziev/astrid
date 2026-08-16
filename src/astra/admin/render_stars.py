"""Страница «Звёзды»: пришедшие деньги отдельно от напечатанных обязательств."""

from __future__ import annotations

from html import escape

from astra.admin.render import card, shell, table, tile, tiles
from astra.admin.stars import Stars, TelegramStars, Wallet


def _stars(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ⭐"


def _share(part: int, whole: int) -> str:
    return f"{round(part * 100 / whole)}% от напечатанного" if whole else ""


def _telegram_card(tg: TelegramStars) -> str:
    if not tg.alive:
        return card(
            "Telegram",
            '<p class="muted">Bot API не ответил, поэтому настоящий баланс здесь '
            f"неизвестен. Внутренние цифры ниже считаются по своей базе и верны.<br>"
            f"<code>{escape(tg.error or '')}</code></p>",
        )
    rows = [
        ("Баланс сейчас", _stars(tg.balance), "то, что реально лежит у бота"),
        ("Пришло", _stars(tg.incoming), "за последние операции"),
        ("Ушло", _stars(tg.outgoing), "возвраты и выплаты"),
    ]
    return card("Telegram — настоящие деньги", table(("", "Сколько", ""), rows))


def _wallet_card(wallet: Wallet) -> str:
    rows = [
        ("Награды за приглашённых", _stars(wallet.rewards), _share(wallet.rewards, wallet.minted)),
        ("Приветствия новичкам", _stars(wallet.welcome), _share(wallet.welcome, wallet.minted)),
        ("Подарки", _stars(wallet.gifts), _share(wallet.gifts, wallet.minted)),
        ("Миграция и ручные", _stars(wallet.other), _share(wallet.other, wallet.minted)),
        ("<b>Напечатано всего</b>", f"<b>{_stars(wallet.minted)}</b>", ""),
    ]
    return card("Внутренний кошелёк — что напечатано даром", table(("", "Сколько", ""), rows))


def _transactions_card(tg: TelegramStars) -> str:
    if not tg.alive:
        return ""
    if not tg.transactions:
        return card("Последние операции", '<p class="muted">Пока ни одной операции.</p>')
    rows = [
        (
            transaction.at.strftime("%d.%m %H:%M"),
            '<span class="badge ok">приход</span>'
            if transaction.incoming
            else '<span class="badge bad">возврат</span>',
            _stars(transaction.amount),
            escape(transaction.counterparty),
        )
        for transaction in tg.transactions
    ]
    return card("Последние операции", table(("Когда", "Что", "Сколько", "Кто"), rows, wide=(3,)))


def stars_page(data: Stars) -> str:
    tg, wallet = data.telegram, data.wallet
    # Потраченное из кошелька — это выручка, которую мы не получили: человек
    # закрыл цену напечатанными звёздами вместо инвойса. Ставим рядом с
    # балансом Telegram, потому что вместе они и отвечают «во что обошлось».
    head = tiles(
        tile(_stars(tg.balance) if tg.alive else "—", "баланс Telegram"),
        tile(_stars(wallet.minted), "напечатано даром"),
        tile(_stars(wallet.spent), "потрачено вместо оплаты"),
        tile(_stars(wallet.outstanding), "лежит на счетах", "потратят когда-нибудь"),
    )
    content = (
        head
        + _telegram_card(tg)
        + _wallet_card(wallet)
        + _transactions_card(tg)
    )
    return shell(
        "stars",
        content,
        subtitle=(
            "Слева настоящие деньги Telegram, справа обязательства внутреннего "
            "кошелька. Складывать их нельзя: напечатанное звёзды выручкой не было."
        ),
    )
