"""Прототипы разделов панели: вёрстка на выдуманных данных.

Это макеты для обсуждения структуры, а не работающие экраны: в базу они не
ходят, кнопки ничего не делают. Каждый раздел помечен бейджем «прототип».
Когда раздел доводится до боевого состояния, его функция отсюда уезжает в
`render.py`, а данные начинают приходить из `service.py`.
"""

from __future__ import annotations

from astra.admin.render import card as _card, shell, table as _table, tile as _tile

_DEMO_NOTE = (
    "Данные на этом экране выдуманы — макет для обсуждения структуры. "
    "Кнопки пока ничего не делают."
)


def _btn(label: str, ghost: bool = True) -> str:
    return f'<button class="{"ghost" if ghost else ""}" type=button>{label}</button>'


def people_page() -> str:
    """Поиск человека и его карточка."""
    search = (
        '<form class="row" style="border:0;margin:0;padding:0">'
        '<div class="field grow"><label>Telegram ID или @username</label>'
        '<input type="text" value="@lunayeva"></div>'
        "<button type=button>Найти</button></form>"
    )
    profile = _table(
        ("Поле", "Значение", ""),
        [
            ("Имя", "Алина", _btn("Изменить")),
            ("Дата рождения", "14 марта 1993", _btn("Изменить")),
            ("Время", "07:20", _btn("Изменить")),
            ("Место", "Махачкала, Россия", _btn("Изменить")),
            ("Пол", "женский", _btn("Изменить")),
        ],
    )
    purchases = _table(
        ("Когда", "Товар", "Сумма", "Статус", ""),
        [
            ("29 июля", "Спроси Астрид · дети", "200 ⭐", '<span class="badge ok">оплачен</span>', _btn("Вернуть")),
            ("21 июля", "Таро · на желание", "50 ⭐", '<span class="badge ok">оплачен</span>', _btn("Вернуть")),
            ("18 июля", "Таро · три карты", "0 ⭐", '<span class="badge">приз колеса</span>', ""),
        ],
    )
    readings = _table(
        ("Когда", "Продукт", "Статус", ""),
        [
            ("29 июля", "Спроси Астрид · дети", '<span class="badge bad">упал</span>', _btn("Повторить")),
            ("21 июля", "Таро · на желание", '<span class="badge ok">готов</span>', _btn("Открыть текст")),
            ("18 июля", "Таро · три карты", '<span class="badge ok">готов</span>', _btn("Открыть текст")),
        ],
    )
    actions = (
        '<form class="row">'
        '<div class="field"><label>Начислить очки</label><input type="number" value="50"></div>'
        '<div class="field grow"><label>Выдать бесплатно</label>'
        "<select><option>Таро · на желание</option><option>Спроси Астрид · дети</option>"
        "<option>Натал · полный разбор</option></select></div>"
        + _btn("Применить", ghost=False)
        + "</form>"
    )
    content = (
        f'<div class="note">{_DEMO_NOTE}</div>'
        + _card("Поиск", search)
        + _card(
            "Алина · @lunayeva",
            '<div class="tiles" style="margin-top:14px">'
            + _tile("250 ⭐", "принесла всего")
            + _tile("3", "покупки")
            + _tile("47", "очков", "серия 12 дней")
            + _tile("6 мес", "с нами")
            + "</div>",
            '<span class="chip">id 481923746</span>'
            '<span class="badge ok">онбординг пройден</span>'
            '<span class="badge">бот не заблокирован</span>',
        )
        + _card(
            "Данные рождения",
            profile,
            '<span class="chip">самая частая причина «разбор не про меня»</span>',
        )
        + _card("Покупки", purchases)
        + _card("Разборы", readings)
        + _card("Действия", actions)
    )
    return shell("people", content, subtitle="Кто это, что купил и что у него сломалось", prototype=True)


def support_page() -> str:
    """Обращения из «Службы заботы»."""
    rows = [
        (
            '<span class="badge bad">4 ч без ответа</span>',
            '<span class="mono">@lunayeva</span>',
            "«Оплатила разбор про детей, ничего не пришло»",
            "29.07 14:10",
            _btn("Ответить") + " " + _btn("Закрыть"),
        ),
        (
            '<span class="badge warn">40 мин</span>',
            '<span class="mono">@kirill_m</span>',
            "«Можно поменять время рождения?»",
            "29.07 17:30",
            _btn("Ответить") + " " + _btn("Закрыть"),
        ),
        (
            '<span class="badge ok">отвечено</span>',
            '<span class="mono">@marina.k</span>',
            "«Как работает колесо?»",
            "28.07 11:02",
            _btn("Открыть"),
        ),
    ]
    content = (
        f'<div class="note">{_DEMO_NOTE}</div>'
        '<div class="tiles" style="margin-bottom:20px">'
        + _tile("2", "ждут ответа")
        + _tile("4 ч", "самое долгое ожидание")
        + _tile("11", "закрыто за неделю")
        + "</div>"
        + _card(
            "Обращения",
            _table(("Ожидание", "Человек", "Первое сообщение", "Когда", ""), rows, wide=(2,)),
            '<span class="chip">то же, что уходит в группу операторов</span>',
        )
    )
    return shell("support", content, subtitle="Кто ждёт ответа дольше всех", prototype=True)


def broadcasts_page() -> str:
    """Рассылка по сегменту."""
    compose = (
        '<form class="row" style="flex-direction:column;align-items:stretch;gap:14px">'
        '<div class="field grow"><label>Кому</label>'
        "<select><option>Все активные — 3 412</option>"
        "<option>Покупали хоть раз — 604</option>"
        "<option selected>Не покупали ни разу — 2 808</option>"
        "<option>Молчат больше 7 дней — 1 190</option></select></div>"
        '<div class="field" style="width:100%"><label>Сообщение</label>'
        "<textarea>Астрид приготовила для тебя расклад на неделю 💫 "
        "Загляни — первые три карты бесплатно.</textarea></div>"
        '<label class="toggle"><input type="checkbox" checked>Пропускать тех, кто заблокировал бота</label>'
        "</form>"
    )
    preview = (
        '<p class="hint">Получателей: <b>2 808</b>. Отправка пачками по 25 в секунду, '
        "около <b>2 минут</b>. Заблокировавшие бота (<b>314</b>) пропускаются.</p>"
        f'<div style="margin-top:14px">{_btn("Предпросмотр")} {_btn("Отправить", ghost=False)}</div>'
    )
    history = _table(
        ("Когда", "Кому", "Отправлено", "Прочитали", "Отписались"),
        [
            ("22.07", "Все активные", "3 380", "2 104", "18"),
            ("14.07", "Не покупали", "2 640", "1 402", "41"),
            ("01.07", "Покупали хоть раз", "580", "497", "2"),
        ],
    )
    content = (
        f'<div class="note">{_DEMO_NOTE}</div>'
        + _card("Новая рассылка", compose)
        + _card(
            "Перед отправкой",
            preview,
            '<span class="chip">отправка уходит в воркер, панель только ставит задачу</span>',
        )
        + _card("Прошлые рассылки", history)
    )
    return shell("broadcasts", content, subtitle="Одно сообщение — тысячи людей, поэтому с подтверждением", prototype=True)


PROTOTYPES = {
    "people": people_page,
    "support": support_page,
    "broadcasts": broadcasts_page,
}
