"""Экран «Платежи»: лента событий с фильтрами и постраничным выводом."""

from __future__ import annotations

from html import escape
from urllib.parse import urlencode

from astra.admin.ledger import (
    KIND_LABELS,
    PAGE_SIZE,
    PERIODS,
    Event,
    Filters,
    Kind,
    Totals,
)
from astra.admin.render import card, shell, table, tile, tiles

_KIND_BADGES = {
    Kind.PAYMENT: '<span class="badge ok">оплата</span>',
    Kind.REFUND: '<span class="badge bad">возврат</span>',
    Kind.DELIVERY: '<span class="badge">выдача</span>',
    Kind.DRAFT: '<span class="badge warn">черновик</span>',
    Kind.TROUBLE: '<span class="badge bad">авария</span>',
    Kind.SPIN: '<span class="badge">колесо</span>',
}


def _link(filters: Filters, **changes) -> str:
    """Ссылка на ту же ленту с изменённым фильтром — состояние живёт в адресе."""
    params = {
        "period": changes.get("period", filters.period),
        "kinds": ",".join(sorted(changes.get("kinds", filters.kinds))),
        "products": ",".join(sorted(changes.get("products", filters.products))),
        "q": changes.get("query", filters.query),
        "page": changes.get("page", 1),
    }
    clean = {key: value for key, value in params.items() if value and value != 1}
    return "/admin/payments" + (f"?{urlencode(clean)}" if clean else "")


def _toggle(current: set[str], value: str) -> set[str]:
    """Чип-переключатель: клик добавляет или убирает значение из выборки."""
    return current - {value} if value in current else current | {value}


def _chips(
    filters: Filters,
    field: str,
    options: list[tuple[str, str]],
    selected: set[str],
) -> str:
    """Ряд переключателей. Пустая выборка = показываем всё."""
    all_link = _link(filters, **{field: set()})
    parts = [
        f'<a href="{all_link}" class="{"on" if not selected else ""}">Все</a>',
    ]
    for value, label in options:
        target = _toggle(selected, value)
        parts.append(
            f'<a href="{_link(filters, **{field: target})}" '
            f'class="{"on" if value in selected else ""}">{escape(label)}</a>',
        )
    return f'<div class="periods">{"".join(parts)}</div>'


def _row(event: Event) -> tuple[str, ...]:
    money = f"{event.amount} ⭐" if event.amount else '<span class="dim">бесплатно</span>'
    note = f'<span class="dim">{escape(event.note)}</span>' if event.note else ""
    return (
        event.at.strftime("%d.%m %H:%M"),
        _KIND_BADGES[event.kind],
        escape(event.title),
        f'<span class="mono">{escape(event.who)}</span>',
        money,
        escape(event.status),
        note,
    )


def _pager(filters: Filters, total: int) -> str:
    pages = max(1, -(-total // PAGE_SIZE))
    if pages == 1:
        return ""
    page = min(max(filters.page, 1), pages)
    parts = []
    if page > 1:
        parts.append(f'<a href="{_link(filters, page=page - 1)}">← назад</a>')
    parts.append(f'<a class="on">{page} из {pages}</a>')
    if page < pages:
        parts.append(f'<a href="{_link(filters, page=page + 1)}">вперёд →</a>')
    return f'<div class="periods" style="margin-top:16px">{"".join(parts)}</div>'


def ledger_page(
    events: list[Event],
    totals: Totals,
    filters: Filters,
    products: list[tuple[str, str]],
) -> str:
    head = tiles(
        tile(f"{totals.money_in} ⭐", "пришло за период"),
        tile(f"{totals.money_back} ⭐", "вернули"),
        tile(str(totals.deliveries), "выдач", f"из них бесплатных {totals.free_deliveries}"),
        tile(str(totals.events), "событий в выборке"),
    )

    period_links = "".join(
        f'<a href="{_link(filters, period=value)}" '
        f'class="{"on" if value == filters.period else ""}">{escape(label)}</a>'
        for value, label in PERIODS.items()
    )

    search = (
        f'<form class="row" method="get" action="/admin/payments" style="border:0;margin:0;padding:0">'
        f'<input type="hidden" name="period" value="{escape(filters.period)}">'
        f'<input type="hidden" name="kinds" value="{escape(",".join(sorted(filters.kinds)))}">'
        f'<input type="hidden" name="products" value="{escape(",".join(sorted(filters.products)))}">'
        '<div class="field grow"><label>Человек</label>'
        f'<input type="text" name="q" value="{escape(filters.query)}" placeholder="@username или id"></div>'
        "<button type=submit>Найти</button></form>"
    )

    filters_card = card(
        "Фильтры",
        f'<div class="periods">{period_links}</div>'
        + _chips(filters, "kinds", [(str(k), label) for k, label in KIND_LABELS.items()], filters.kinds)
        + _chips(filters, "products", products, filters.products)
        + search,
        '<span class="chip">любой товар выключается кликом</span>',
    )

    if events:
        body = card(
            "Лента событий",
            table(
                ("Когда", "Что", "Продукт", "Человек", "Сумма", "Статус", ""),
                [_row(event) for event in events],
                wide=(6,),
            )
            + _pager(filters, totals.events),
        )
    else:
        body = card(
            "Пусто",
            '<p class="hint">За выбранный период с такими фильтрами ничего не происходило.</p>',
        )

    return shell(
        "payments",
        head + filters_card + body,
        subtitle="Оплаты, выдачи, возвраты и брошенные заказы — одной лентой",
    )
