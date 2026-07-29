"""Экран настроек: пока только цены моделей — то, что нужно править чаще всего."""

from __future__ import annotations

from html import escape

from astra.admin.service import LlmPriceView
from astra.admin.render import card, shell

# Типовой разбор: столько токенов уходит на один платный продукт. Нужно, чтобы
# цена за миллион не была абстракцией — рядом сразу видно цену одного ответа.
SAMPLE_PROMPT_TOKENS = 3000
SAMPLE_COMPLETION_TOKENS = 1500


def _price_form(price: LlmPriceView) -> str:
    missing = not price.input_per_million and not price.output_per_million
    chips = ""
    if price.in_use:
        chips += '<span class="badge ok">используется</span>'
    if missing:
        chips += '<span class="badge bad">цены нет</span>'
    elif price.note:
        chips += f'<span class="chip">{escape(price.note)}</span>'

    sample = ""
    if not missing:
        cost = price.cost_of(SAMPLE_PROMPT_TOKENS, SAMPLE_COMPLETION_TOKENS)
        sample = f'<span class="total">разбор ≈ ${cost}</span>'

    return (
        f'<div class="card{"" if price.in_use else " muted"}">'
        f'<div class="card-head"><h3>{escape(price.model)}</h3>{chips}</div>'
        f'<form class="row" method="post" action="/admin/llm-prices/{escape(price.model)}">'
        '<div class="field"><label>Вход, $/млн</label>'
        f'<input type="text" name="input" value="{price.input_per_million}"></div>'
        '<div class="field"><label>Выход, $/млн</label>'
        f'<input type="text" name="output" value="{price.output_per_million}"></div>'
        '<div class="field grow"><label>Заметка</label>'
        f'<input type="text" name="note" value="{escape(price.note or "")}"></div>'
        f"{sample}"
        "<button type=submit>Сохранить</button></form></div>"
    )


def _new_price_form() -> str:
    return (
        "<details><summary>Добавить модель</summary>"
        '<form class="row" method="post" action="/admin/llm-prices">'
        '<div class="field grow"><label>Модель</label>'
        '<input type="text" name="model" placeholder="deepseek-v4-flash"></div>'
        '<div class="field"><label>Вход, $/млн</label>'
        '<input type="text" name="input" value="0"></div>'
        '<div class="field"><label>Выход, $/млн</label>'
        '<input type="text" name="output" value="0"></div>'
        "<button type=submit>Добавить</button></form></details>"
    )


def settings_page(
    prices: list[LlmPriceView],
    *,
    flash: str | None = None,
    flash_error: bool = False,
) -> str:
    banner = ""
    if flash:
        banner = f'<div class="flash{" err" if flash_error else ""}">{escape(flash)}</div>'

    intro = card(
        "Цены моделей",
        '<p class="hint">Доллары за миллион токенов, как в прайсе провайдера. '
        "По ним считается себестоимость каждого вызова — и считается <b>в момент "
        "вызова</b>: правка цены меняет будущие расчёты, а не переписывает историю. "
        f"Рядом с каждой моделью — во сколько обойдётся типовой разбор "
        f"({SAMPLE_PROMPT_TOKENS} токенов вопроса и {SAMPLE_COMPLETION_TOKENS} ответа).</p>"
        + _new_price_form(),
        '<span class="chip">меняются чаще, чем выходят релизы</span>',
    )

    cards = "".join(_price_form(price) for price in prices)
    if not prices:
        cards = card("Пусто", '<p class="hint">Ни одной модели в прайсе.</p>')

    missing = [price.model for price in prices if price.in_use and not price.input_per_million]
    warning = ""
    if missing:
        warning = (
            f'<div class="flash err">Без цены работают модели: {escape(", ".join(missing))}. '
            "Их вызовы считаются, но себестоимость по ним неизвестна.</div>"
        )

    later = card(
        "Что появится здесь дальше",
        '<p class="hint">Флаги функций (сейчас .env и перезапуск контейнера) и тексты '
        "продуктов — заголовки инвойсов, описания и тизеры, которые пока лежат в коде.</p>",
    )

    return shell(
        "settings",
        banner + warning + intro + cards + later,
        subtitle="Что можно менять без релиза",
    )
