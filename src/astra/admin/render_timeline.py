"""Три графика дашборда: люди, генерации, выручка."""

from __future__ import annotations

from html import escape

from astra.admin.timeline import GRAIN_LABELS, Grain, LlmSpend, Timeline
from astra.admin.render import card


def _labels(timeline: Timeline) -> str:
    """Подписи под столбиками; при тридцати днях показываем каждую пятую."""
    total = len(timeline.buckets)
    step = max(1, round(total / 8))
    parts = []
    for index, bucket in enumerate(timeline.buckets):
        show = index % step == 0 or index == total - 1
        parts.append(f"<span>{escape(bucket.label) if show else ''}</span>")
    return "".join(parts)


def _height(value: int, top: int) -> int:
    """Высота столбика в процентах; ноль тоже видно полоской."""
    return max(2, round(value * 100 / top)) if top else 2


def grain_switch(active: Grain) -> str:
    links = "".join(
        f'<a href="/admin/metrics?grain={grain}" class="{"on" if grain == active else ""}">'
        f"{escape(label)}</a>"
        for grain, label in GRAIN_LABELS.items()
    )
    return f'<div class="periods">{links}</div>'


def _single_chart(
    title: str,
    timeline: Timeline,
    values: list[int],
    unit: str,
    chips: str = "",
) -> str:
    top = max(values, default=0)
    columns = "".join(
        f'<i class="{"now" if bucket.current else ""}" '
        f'style="height:{_height(value, top)}%" '
        f'title="{escape(bucket.label)}: {value} {unit}"></i>'
        for bucket, value in zip(timeline.buckets, values, strict=True)
    )
    legend = '<div class="legend"><span class="now">текущий период ещё идёт</span></div>'
    return card(
        title,
        f'<div class="bars">{columns}</div><div class="bars-x">{_labels(timeline)}</div>{legend}',
        chips,
    )


def _duo_chart(title: str, timeline: Timeline, chips: str = "") -> str:
    """Генерации: выдано продуктов против сделанных вызовов модели."""
    top = max([*timeline.products, *timeline.calls], default=0)
    columns = "".join(
        f'<i class="{"now" if bucket.current else ""}">'
        f'<b style="height:{_height(products, top)}%" '
        f'title="{escape(bucket.label)}: выдано {products}"></b>'
        f'<b class="second" style="height:{_height(calls, top)}%" '
        f'title="{escape(bucket.label)}: вызовов {calls}"></b>'
        "</i>"
        for bucket, products, calls in zip(
            timeline.buckets, timeline.products, timeline.calls, strict=True,
        )
    )
    legend = (
        '<div class="legend"><span>выдано продуктов</span>'
        '<span class="second">вызовов модели</span>'
        '<span class="now">период ещё идёт</span></div>'
    )
    return card(
        title,
        f'<div class="bars duo">{columns}</div><div class="bars-x">{_labels(timeline)}</div>{legend}',
        chips,
    )


def charts(timeline: Timeline, spend: LlmSpend) -> str:
    """Три графика подряд — как и договаривались, без переключателя метрики."""
    unique_note = (
        '<span class="chip">уникальные внутри периода — месяц ≠ сумма дней</span>'
    )
    ratio = ""
    if timeline.products and sum(timeline.products):
        per_product = sum(timeline.calls) / sum(timeline.products)
        ratio = f'<span class="chip">{per_product:.1f} вызова на продукт</span>'

    money_chip = ""
    if spend.cost_usd:
        money_chip = f'<span class="chip">модели за период: ${spend.cost_usd:.2f}</span>'

    return (
        grain_switch(timeline.grain)
        + _single_chart("Активные люди", timeline, timeline.people, "чел.", unique_note)
        + _duo_chart("Генерации", timeline, ratio + money_chip)
        + _single_chart("Выручка", timeline, timeline.money, "⭐")
    )
