"""Страница метрик: та же вёрстка, что у макета, но данные настоящие."""

from __future__ import annotations

from html import escape

from astra.admin.metrics import Dashboard
from astra.admin.render import card, shell, table, tile, tiles
from astra.admin.render_timeline import charts


def _stars(amount: int) -> str:
    """Звёзды с разделителем тысяч: 4830 → «4 830 ⭐»."""
    return f"{amount:,}".replace(",", " ") + " ⭐"


def _delta(current: int, previous: int) -> str:
    """Сравнение с предыдущим таким же периодом — без него число немое."""
    if not previous:
        return "первые данные" if current else ""
    change = round((current - previous) * 100 / previous)
    return f"{'+' if change >= 0 else ''}{change}% к прошлому периоду"


def metrics_page(dash: Dashboard, timeline, spend, spend_rows) -> str:
    money = dash.money
    failed, total_readings = dash.failed
    failed_share = round(failed * 100 / total_readings, 1) if total_readings else 0.0

    head = tiles(
        tile(_stars(money.revenue), f"выручка за {dash.days} дн.", _delta(money.revenue, dash.previous.revenue)),
        tile(str(money.payments), "оплат", _delta(money.payments, dash.previous.payments)),
        tile(_stars(money.average_check), "средний чек"),
        tile(str(dash.audience.dau), "активных за день", f"липкость {dash.audience.stickiness}%"),
        tile(str(dash.signups), "новых людей"),
        tile(f"{failed_share}%", "разборов упало", f"{failed} из {total_readings}"),
    )

    # --- деньги ---
    money_rows = [
        ("Выручка", _stars(money.revenue), _delta(money.revenue, dash.previous.revenue)),
        ("Оплат", str(money.payments), f"платили {money.buyers} чел."),
        ("Средний чек", _stars(money.average_check), ""),
        ("Отдано в скидках", _stars(money.discount_given), "сколько стоили акции"),
        ("Возвраты", str(money.refunds), _stars(money.refunded_amount)),
        (
            "Выручка на платящего",
            _stars(dash.repeat.revenue_per_buyer),
            "за всё время",
        ),
        (
            "Покупают повторно",
            f"{dash.repeat.repeat_share}%",
            f"{dash.repeat.repeat_users} из {dash.repeat.paying_users} платящих",
        ),
        (
            "От регистрации до покупки",
            f"{dash.days_to_purchase} дн." if dash.days_to_purchase is not None else "—",
            "медиана",
        ),
    ]

    # --- воронка ---
    base = dash.funnel[0].people if dash.funnel else 0
    funnel_rows = []
    for index, step in enumerate(dash.funnel):
        previous_step = dash.funnel[index - 1].people if index else 0
        step_share = (
            f"{round(step.people * 100 / previous_step, 1)}%" if index and previous_step else "—"
        )
        funnel_rows.append((step.name, str(step.people), f"{step.share(base)}%", step_share))

    # --- продукты ---
    product_rows = [
        (
            escape(product.title),
            f'<span class="mono">{escape(product.action)}</span>',
            str(product.uses),
            str(product.users),
            str(product.paid_uses),
            str(product.free_uses),
        )
        for product in dash.products
    ] or [("Использований пока нет", "", "", "", "", "")]

    # --- аудитория и серии ---
    audience_rows = [
        ("Активных за день (DAU)", str(dash.audience.dau), ""),
        ("За неделю (WAU)", str(dash.audience.wau), ""),
        ("За месяц (MAU)", str(dash.audience.mau), ""),
        (
            "Липкость DAU/MAU",
            f"{dash.audience.stickiness}%",
            "у ежедневных продуктов здорово 20–30%",
        ),
        ("Вернулись на 2-й день", f"{dash.audience.retention.get(1, 0)}%", "когорта недели"),
        ("Вернулись на 7-й", f"{dash.audience.retention.get(7, 0)}%", ""),
        ("Вернулись на 30-й", f"{dash.audience.retention.get(30, 0)}%", ""),
    ]
    streak_rows = [(label, str(people)) for label, people in dash.streaks]

    # --- колесо ---
    wheel = dash.wheel
    wheel_rows = [
        ("Вращений", str(wheel.spins), f"бесплатных {wheel.spins_free}, платных {wheel.spins_paid}"),
        ("Призов выпало", str(wheel.wins_total), ""),
        (
            "Активировано",
            f"{wheel.activation_share}%",
            f"{wheel.wins_activated} из {wheel.wins_total}",
        ),
        ("Сгорело не использованными", str(wheel.wins_expired), ""),
        ("Выручка через призы", _stars(wheel.revenue_from_prizes), "оплаты с активированным призом"),
    ]
    prize_rows = [
        (escape(name), str(hits), f"{actual}%", f"{expected}%")
        for name, hits, actual, expected in wheel.prize_rows
    ] or [("Призов пока не выпадало", "", "", "")]

    # --- рефералы ---
    ref = dash.referrals
    referral_rows = [
        ("Пришли по приглашению", str(ref.invited), f"{ref.invited_conversion}% из них купили"),
        ("Пришли сами", str(ref.organic), f"{ref.organic_conversion}% из них купили"),
    ]

    llm_rows = [
        (escape(purpose), str(calls), f"${cost:.2f}")
        for purpose, calls, cost in spend_rows
    ] or [("Вызовов пока не было", "", "")]

    content = (
        charts(timeline, spend)
        + head
        + card(
            "Расход на модели",
            table(("Продукт", "Вызовов", "Стоимость"), llm_rows),
            f'<span class="chip">токенов {spend.tokens:,}</span>'.replace(",", " ")
            + (
                f'<span class="chip">{spend.unknown_tokens} вызовов без учёта токенов</span>'
                if spend.unknown_tokens
                else ""
            ),
        )
        + card("Деньги", table(("Показатель", "Значение", ""), money_rows, wide=(2,)))
        + card(
            "Воронка",
            table(("Шаг", "Людей", "От старта", "От предыдущего"), funnel_rows),
            '<span class="chip">за всё время</span>',
        )
        + card(
            "Чем пользуются",
            table(
                ("Продукт", "Ключ", "Использований", "Людей", "Платно", "Бесплатно"),
                product_rows,
            ),
            f'<span class="chip">за {dash.days} дн.</span>',
        )
        + card("Аудитория", table(("Показатель", "Значение", ""), audience_rows, wide=(2,)))
        + card(
            "Серии дней",
            table(("Серия", "Людей"), streak_rows),
            '<span class="chip">серию двигает любое использование продукта</span>',
        )
        + card("Колесо фортуны", table(("Показатель", "Значение", ""), wheel_rows, wide=(2,)))
        + card(
            "Призы: факт против весов",
            table(("Сектор", "Выпал раз", "Доля", "Заявленный шанс"), prize_rows),
        )
        + card(
            "Рефералы",
            table(("Откуда", "Людей", "Конверсия в покупку"), referral_rows, wide=(2,)),
        )
    )
    return shell(
        "metrics",
        content,
        subtitle="Календарные периоды по Москве; таблицы ниже — за то же окно",
    )
