"""Экран рассылок: аудитория, текст, предпросмотр и история.

Предпросмотр рисует настоящий телеграмный пузырь — с тем же тёмным фоном,
скруглением и кнопками. Смысл не в красоте: разметка, которую вернула модель,
должна быть видна ровно так, как её увидят люди, иначе проверять нечего.
"""

from __future__ import annotations

from html import escape

from astra.broadcasts.audience import ZODIAC_NAMES, Criteria
from astra.broadcasts.models import Broadcast, BroadcastStatus
from astra.broadcasts.sections import SECTION_TITLES
from astra.admin.render import card, shell, table, tile, tiles

# Разрешённые Telegram теги оставляем в предпросмотре как есть, всё остальное
# экранируется: сообщение показывается ровно тем, чем оно будет в чате.
_PREVIEW_TAGS = ("b", "i", "u", "s", "a", "code", "blockquote", "tg-spoiler")


def _preview_html(text: str) -> str:
    """Экранировать всё, кроме телеграмной разметки, и сохранить абзацы."""
    safe = escape(text)
    for tag in _PREVIEW_TAGS:
        safe = safe.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    # Ссылки с href разбираем отдельно: у них есть атрибут.
    safe = safe.replace("&lt;a href=&quot;", '<a href="').replace("&quot;&gt;", '">')
    return safe.replace("\n", "<br>")


def bubble(text: str, buttons: list[dict], *, name: str | None = None) -> str:
    """Телеграмный пузырь с кнопками — то, что человек увидит в чате."""
    body = _preview_html(f"{name}, {text[0].lower()}{text[1:]}" if name and text else text)
    rows = ""
    for button in buttons:
        title = button.get("title") or SECTION_TITLES.get(button.get("section", ""), "Открыть")
        rows += f'<div class="tg-btn">{escape(title)}</div>'
    return (
        '<div class="tg-wrap"><div class="tg-bubble">'
        f"{body}"
        f'<div class="tg-time">14:32</div>'
        f"</div>{rows}</div>"
    )


def _chips(name: str, options: list[tuple[str, str]], selected: set[str]) -> str:
    """Множественный выбор чекбоксами — сохраняется вместе с формой."""
    parts = []
    for value, label in options:
        checked = " checked" if value in selected else ""
        parts.append(
            f'<label class="pick"><input type="checkbox" name="{name}" '
            f'value="{escape(value)}"{checked}>{escape(label)}</label>',
        )
    return f'<div class="picks">{"".join(parts)}</div>'


def _audience_form(criteria: Criteria, products: list[tuple[str, str]], size: int | None) -> str:
    counter = (
        f'<span class="chip">под фильтры попадает {size} чел.</span>'
        if size is not None
        else '<span class="chip">нажми «посчитать», чтобы узнать охват</span>'
    )
    return card(
        "Кому",
        '<form method="post" action="/admin/broadcasts/count">'
        "<p class=\"hint\">Условия действуют одновременно. Пустое поле — фильтр не участвует.</p>"
        '<div class="field-group"><label class="group-title">Знак зодиака</label>'
        + _chips("zodiac", [(sign, sign) for sign in ZODIAC_NAMES], criteria.zodiac)
        + "</div>"
        '<div class="field-group"><label class="group-title">Пользовался продуктом</label>'
        + _chips("used_products", products, criteria.used_products)
        + "</div>"
        '<form class="row">'
        '<div class="field"><label>Активен, дней</label>'
        f'<input type="number" name="active_within_days" value="{criteria.active_within_days or ""}"></div>'
        '<div class="field"><label>Спит дольше, дней</label>'
        f'<input type="number" name="sleeping_since_days" value="{criteria.sleeping_since_days or ""}"></div>'
        '<div class="field"><label>С нами меньше, дней</label>'
        f'<input type="number" name="joined_within_days" value="{criteria.joined_within_days or ""}"></div>'
        '<div class="field wide"><label>Деньги</label>'
        '<select name="money">'
        f'<option value="">все</option>'
        f'<option value="paid"{" selected" if criteria.money == "paid" else ""}>покупали</option>'
        f'<option value="never"{" selected" if criteria.money == "never" else ""}>ни разу не платили</option>'
        "</select></div>"
        "</form>"
        '<div class="field-group"><label class="group-title">Незакрытые хвосты</label>'
        '<label class="pick"><input type="checkbox" name="abandoned_draft" value="1"'
        + (" checked" if criteria.abandoned_draft else "")
        + ">Бросили корзину</label>"
        '<label class="pick"><input type="checkbox" name="unclaimed_prize" value="1"'
        + (" checked" if criteria.unclaimed_prize else "")
        + ">Есть невостребованный приз</label>"
        "</div>"
        '<div class="field-group"><label class="group-title">Исключить</label>'
        '<label class="pick"><input type="checkbox" name="exclude_paid" value="1"'
        + (" checked" if criteria.exclude_paid else "")
        + ">Тех, кто уже покупал</label>"
        '<div class="field"><label>Активных за, дней</label>'
        f'<input type="number" name="exclude_active_within_days" '
        f'value="{criteria.exclude_active_within_days or ""}"></div>'
        "</div>"
        '<div class="field grow"><label>Или адресно: telegram_id через запятую</label>'
        '<input type="text" name="direct" placeholder="481923746, 5512094"></div>'
        '<div style="margin-top:14px"><button type=submit>Посчитать аудиторию</button></div>'
        "</form>",
        counter,
    )


def _text_form(source: str, personalize: bool, use_ai: bool) -> str:
    return card(
        "Что написать",
        '<form method="post" action="/admin/broadcasts/compose">'
        f"<textarea name=\"text\" placeholder=\"Черновик — как есть, красоту наведёт редактор\">{escape(source)}</textarea>"
        '<div class="row" style="border:0;padding-top:12px">'
        '<label class="toggle"><input type="checkbox" name="use_ai" value="1"'
        + (" checked" if use_ai else "")
        + ">Улучшить текст ИИ</label>"
        '<label class="toggle"><input type="checkbox" name="personalize" value="1"'
        + (" checked" if personalize else "")
        + ">Обращаться по имени</label>"
        "<button type=submit>Собрать сообщение</button>"
        "</div></form>",
        '<span class="chip">редактор не трогает числа и факты</span>',
    )


def _buttons_form(buttons: list[dict]) -> str:
    options = "".join(
        f'<option value="{key}">{escape(title)}</option>' for key, title in SECTION_TITLES.items()
    )
    current = "".join(
        f'<div class="chip">{escape(button.get("title") or SECTION_TITLES.get(button.get("section", ""), "кнопка"))}</div>'
        for button in buttons
    )
    return card(
        "Кнопки под сообщением",
        f'<div style="margin-bottom:10px">{current}</div>'
        '<form class="row" method="post" action="/admin/broadcasts/button">'
        f'<div class="field wide"><label>Раздел бота</label><select name="section">'
        f'<option value="">— нет —</option>{options}</select></div>'
        '<div class="field grow"><label>Или ссылка</label>'
        '<input type="text" name="url" placeholder="https://t.me/…"></div>'
        '<div class="field grow"><label>Подпись</label><input type="text" name="title"></div>'
        "<button type=submit>Добавить</button></form>",
    )


def broadcast_page(
    *,
    criteria: Criteria,
    products: list[tuple[str, str]],
    audience_size: int | None,
    source_text: str,
    final_text: str,
    warnings: tuple[str, ...],
    buttons: list[dict],
    personalize: bool,
    use_ai: bool,
    history: list[Broadcast],
    flash: str | None = None,
    flash_error: bool = False,
) -> str:
    banner = ""
    if flash:
        banner = f'<div class="flash{" err" if flash_error else ""}">{escape(flash)}</div>'

    warning_block = ""
    if warnings:
        items = "".join(f"<li>{escape(problem)}</li>" for problem in warnings)
        warning_block = f'<div class="flash err"><b>Проверь перед отправкой:</b><ul>{items}</ul></div>'

    preview = ""
    if final_text:
        preview = card(
            "Как это будет выглядеть",
            bubble(final_text, buttons, name="Алина" if personalize else None)
            + f'<p class="hint">{len(final_text)} знаков'
            + (", имя подставляется каждому своё" if personalize else "")
            + "</p>"
            + '<form method="post" action="/admin/broadcasts/test" style="display:inline">'
            "<button class=ghost type=submit>Отправить себе на проверку</button></form> "
            '<form method="post" action="/admin/broadcasts/send" style="display:inline" '
            "onsubmit=\"return confirm('Отправить рассылку? Отменить будет нельзя.')\">"
            "<button type=submit>Отправить всем</button></form>",
            f'<span class="chip">{audience_size if audience_size is not None else "?"} получателей</span>',
        )

    rows = [
        (
            item.created_at.strftime("%d.%m %H:%M"),
            escape((item.source_text or "")[:40]),
            str(item.audience_size),
            str(item.sent_count),
            str(item.blocked_count),
            (
                f'<a href="/admin/broadcasts/{item.id}/retry">{item.failed_count} — повторить</a>'
                if item.failed_count and item.status == BroadcastStatus.SENT
                else str(item.failed_count)
            ),
            escape(item.status),
        )
        for item in history
    ]
    history_card = card(
        "Прошлые рассылки",
        table(
            ("Когда", "Начало текста", "Аудитория", "Дошло", "Заблокировали", "Не дошло", "Статус"),
            rows or [("Рассылок ещё не было", "", "", "", "", "", "")],
        ),
    )

    head = tiles(
        tile(str(audience_size if audience_size is not None else "—"), "получателей сейчас"),
        tile(str(len(history)), "рассылок в истории"),
        tile(
            str(sum(item.sent_count for item in history)),
            "сообщений доставлено всего",
        ),
    )

    return shell(
        "broadcasts",
        banner
        + head
        + _audience_form(criteria, products, audience_size)
        + _text_form(source_text, personalize, use_ai)
        + _buttons_form(buttons)
        + warning_block
        + preview
        + history_card,
        subtitle="Одно сообщение — тысячи людей, поэтому с предпросмотром и подтверждением",
    )
