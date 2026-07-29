"""Прототипы разделов панели: вёрстка на выдуманных данных.

Это макеты для обсуждения структуры, а не работающие экраны: в базу они не
ходят, кнопки ничего не делают. Каждый раздел помечен бейджем «прототип».
Когда раздел доводится до боевого состояния, его функция отсюда уезжает в
`render.py`, а данные начинают приходить из `service.py`.
"""

from __future__ import annotations

from astra.admin.render import shell

_DEMO_NOTE = (
    "Данные на этом экране выдуманы — макет для обсуждения структуры. "
    "Кнопки пока ничего не делают."
)


def _table(
    headers: tuple[str, ...],
    rows: list[tuple[str, ...]],
    *,
    wide: tuple[int, ...] = (),
) -> str:
    """Таблица списка; `wide` — номера колонок, где длинный текст переносится."""
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join(
        "<tr>"
        + "".join(
            f'<td{" class=cell-wide" if i in wide else ""}>{cell}</td>'
            for i, cell in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    return (
        f'<div class="scroll"><table class="list"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def _card(title: str, inner: str, chips: str = "") -> str:
    return (
        f'<div class="card"><div class="card-head"><h3>{title}</h3>{chips}</div>{inner}</div>'
    )


def _tile(value: str, label: str, note: str = "") -> str:
    note_html = f"<em>{note}</em>" if note else ""
    return f'<div class="tile"><b>{value}</b><span>{label}</span> {note_html}</div>'


def _btn(label: str, ghost: bool = True) -> str:
    return f'<button class="{"ghost" if ghost else ""}" type=button>{label}</button>'


def queue_page() -> str:
    """Упавшие и зависшие разборы + платежи без заказа."""
    rows = [
        (
            '<span class="badge bad">упал</span>',
            "Спроси Астрид · дети",
            '<span class="mono">@lunayeva</span>',
            "200 ⭐",
            "12 мин назад",
            '<span class="dim">LLM вернула 3 блока вместо 5</span>',
            _btn("Повторить") + " " + _btn("Вернуть"),
        ),
        (
            '<span class="badge warn">завис</span>',
            "Таро · на отношения",
            '<span class="mono">@kirill_m</span>',
            "150 ⭐",
            "48 мин в generating",
            '<span class="dim">воркер не ответил</span>',
            _btn("Повторить") + " " + _btn("Вернуть"),
        ),
        (
            '<span class="badge warn">завис</span>',
            "Натал · полный разбор",
            '<span class="mono">id 5512094</span>',
            "500 ⭐",
            "2 ч в generating",
            '<span class="dim">воркер не ответил</span>',
            _btn("Повторить") + " " + _btn("Вернуть"),
        ),
        (
            '<span class="badge bad">сирота</span>',
            "Таро · три карты",
            '<span class="mono">@dashaaa</span>',
            "50 ⭐",
            "вчера, 21:14",
            '<span class="dim">оплата пришла, черновик не найден</span>',
            _btn("Создать заказ") + " " + _btn("Вернуть"),
        ),
    ]
    content = (
        f'<div class="note">{_DEMO_NOTE}</div>'
        '<div class="tiles" style="margin-bottom:20px">'
        + _tile("4", "требуют внимания")
        + _tile("900 ⭐", "денег в подвешенном состоянии")
        + _tile("2 ч", "самый старый случай")
        + "</div>"
        + _card(
            "Что пошло не так",
            _table(
                ("Статус", "Продукт", "Человек", "Оплачено", "Когда", "Причина", ""),
                rows,
                wide=(5,),
            ),
            '<span class="chip">обновляется само раз в минуту</span>',
        )
        + _card(
            "Как это работает",
            '<p class="hint">Упавшие разборы воркер уже пытался переделать и вернул звёзды сам — '
            "здесь они, чтобы понять причину. Зависшие в generating не разрулит никто: "
            "их надо либо перезапустить, либо вернуть деньги руками. Сироты — оплата дошла, "
            "а заказ к ней не привязался.</p>",
        )
    )
    return shell("queue", content, subtitle="Заказы, которые не дошли до человека", prototype=True)


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


def payments_page() -> str:
    """Список оплат с фильтрами и возвратом."""
    filters = (
        '<form class="row" style="border:0;margin:0;padding:0">'
        '<div class="field wide"><label>Период</label>'
        "<select><option>Сегодня</option><option selected>7 дней</option>"
        "<option>30 дней</option><option>Всё время</option></select></div>"
        '<div class="field wide"><label>Товар</label>'
        "<select><option>Все</option><option>Таро</option><option>Спроси Астрид</option>"
        "<option>Колесо</option></select></div>"
        '<div class="field wide"><label>Статус</label>'
        "<select><option>Все</option><option>Оплачен</option><option>Возвращён</option></select></div>"
        "<button type=button>Показать</button></form>"
    )
    rows = [
        ("29.07 14:02", "@lunayeva", "Спроси Астрид · дети", "200 ⭐", "200 ⭐", '<span class="badge ok">оплачен</span>', _btn("Вернуть")),
        ("29.07 12:41", "@kirill_m", "Таро · на отношения", "150 ⭐", "105 ⭐", '<span class="badge">−30%</span>', _btn("Вернуть")),
        ("29.07 09:15", "id 5512094", "Натал · полный разбор", "500 ⭐", "500 ⭐", '<span class="badge ok">оплачен</span>', _btn("Вернуть")),
        ("28.07 21:14", "@dashaaa", "Таро · три карты", "50 ⭐", "50 ⭐", '<span class="badge bad">возвращён</span>', ""),
        ("28.07 19:03", "@marina.k", "Колесо · вращение", "25 ⭐", "25 ⭐", '<span class="badge ok">оплачен</span>', _btn("Вернуть")),
    ]
    content = (
        f'<div class="note">{_DEMO_NOTE}</div>'
        '<div class="tiles" style="margin-bottom:20px">'
        + _tile("4 830 ⭐", "за 7 дней", "+18% к прошлой неделе")
        + _tile("41", "оплаты")
        + _tile("118 ⭐", "средний чек")
        + _tile("3", "возврата", "60 ⭐")
        + "</div>"
        + _card("Фильтры", filters)
        + _card(
            "Оплаты",
            _table(("Когда", "Человек", "Товар", "Цена", "Уплачено", "Статус", ""), rows),
        )
    )
    return shell("payments", content, subtitle="Деньги: что пришло, что вернули", prototype=True)


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


def settings_page() -> str:
    """Флаги функций и тексты продуктов."""
    flags = _table(
        ("Функция", "Состояние", "Что выключится", ""),
        [
            ("Расклады таро", '<span class="badge ok">включено</span>', "раздел таро в меню", _btn("Выключить")),
            ("Спроси Астрид", '<span class="badge ok">включено</span>', "все платные вопросы", _btn("Выключить")),
            ("Колесо фортуны", '<span class="badge ok">включено</span>', "кнопка колеса", _btn("Выключить")),
            ("AI-чат Astrid", '<span class="badge">выключено</span>', "свободный текст вне сценариев", _btn("Включить")),
            ("Персональные прогнозы", '<span class="badge ok">включено</span>', "перейдём на общий гороскоп по знаку", _btn("Выключить")),
            ("DeepSeek", '<span class="badge ok">включено</span>', "разборы встанут", _btn("Выключить")),
        ],
    )
    texts = (
        '<form class="row" style="flex-direction:column;align-items:stretch;gap:14px">'
        '<div class="field" style="width:100%"><label>Заголовок инвойса</label>'
        '<input type="text" style="width:100%" value="Будут ли у меня дети"></div>'
        '<div class="field" style="width:100%"><label>Описание в инвойсе</label>'
        "<textarea>Разбор по твоей натальной карте: какой у тебя сценарий темы детей, "
        "сколько показывает карта, когда открываются лучшие окна и что для тебя значит "
        "родительство.</textarea></div>"
        '<div class="field" style="width:100%"><label>Тизер перед покупкой</label>'
        "<textarea>Смотрю твой пятый дом, Луну и Юпитер — ищу, как в твоей карте устроена "
        "тема детей и когда её лучшие окна ✨</textarea></div>"
        + _btn("Сохранить", ghost=False)
        + "</form>"
    )
    content = (
        f'<div class="note">{_DEMO_NOTE}</div>'
        + _card(
            "Флаги функций",
            flags,
            '<span class="chip">сейчас это .env и перезапуск контейнера</span>',
        )
        + '<h2 class="section">Тексты продуктов <span>— сейчас лежат в коде</span></h2>'
        + _card(
            "Спроси Астрид · дети",
            texts,
            '<span class="chip">ask_love_kids</span>',
        )
    )
    return shell("settings", content, subtitle="Что можно менять без релиза", prototype=True)


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


def metrics_page() -> str:
    """Дашборд: деньги и воронка."""
    days = (("23.07", 380), ("24.07", 520), ("25.07", 610), ("26.07", 440),
            ("27.07", 720), ("28.07", 890), ("29.07", 1270))
    top = max(value for _, value in days)
    bars = "".join(
        f'<i style="height:{round(value * 100 / top)}%" title="{label}: {value} ⭐"></i>'
        for label, value in days
    )
    labels = "".join(f"<span>{label}</span>" for label, _ in days)
    funnel = _table(
        ("Шаг", "Людей", "Доля"),
        [
            ("Запустили бота", "3 412", "100%"),
            ("Прошли онбординг", "2 640", "77%"),
            ("Открыли платный раздел", "1 108", "32%"),
            ("Дошли до инвойса", "742", "22%"),
            ("Оплатили", "604", "18%"),
            ("Купили второй раз", "213", "6%"),
        ],
    )
    products = _table(
        ("Товар", "Оплат", "Выручка", "Средний чек"),
        [
            ("Спроси Астрид · дети", "96", "19 200 ⭐", "200 ⭐"),
            ("Таро · на отношения", "88", "11 220 ⭐", "128 ⭐"),
            ("Натал · полный разбор", "22", "11 000 ⭐", "500 ⭐"),
            ("Таро · на желание", "104", "5 200 ⭐", "50 ⭐"),
            ("Колесо · вращение", "141", "3 525 ⭐", "25 ⭐"),
        ],
    )
    content = (
        f'<div class="note">{_DEMO_NOTE}</div>'
        '<div class="tiles" style="margin-bottom:20px">'
        + _tile("4 830 ⭐", "выручка за 7 дней", "+18%")
        + _tile("41", "оплаты", "+6")
        + _tile("18%", "старт → покупка")
        + _tile("118 ⭐", "средний чек")
        + _tile("512", "активных за день")
        + "</div>"
        + _card(
            "Выручка по дням",
            f'<div class="bars">{bars}</div><div class="bars-x">{labels}</div>',
        )
        + _card("Воронка", funnel)
        + _card("Товары за 7 дней", products)
    )
    return shell("metrics", content, subtitle="Деньги, воронка и что покупают", prototype=True)


PROTOTYPES = {
    "queue": queue_page,
    "people": people_page,
    "payments": payments_page,
    "support": support_page,
    "settings": settings_page,
    "broadcasts": broadcasts_page,
    "metrics": metrics_page,
}
