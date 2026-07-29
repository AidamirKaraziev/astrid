"""Экран очереди проблем."""

from __future__ import annotations

from html import escape

from astra.admin.queue import STUCK_AFTER_MINUTES, Problem, Summary, Trouble
from astra.admin.render import card, shell, table, tile, tiles

_BADGES = {
    Trouble.FAILED: ('<span class="badge bad">упал</span>', "воркер сдался"),
    Trouble.STUCK: ('<span class="badge warn">завис</span>', "воркер не дошёл до конца"),
    Trouble.ORPHAN: ('<span class="badge bad">сирота</span>', "оплата без заказа"),
}


def _actions(problem: Problem) -> str:
    """Кнопки строки. Возврат отдельной формой с подтверждением в браузере."""
    buttons = []
    if problem.can_retry:
        buttons.append(
            f'<form method="post" action="/admin/queue/{problem.target}/{problem.entity_id}/retry" '
            'style="display:inline">'
            "<button class=ghost type=submit>Повторить</button></form>",
        )
    if problem.can_refund:
        amount = f"{problem.amount} ⭐" if problem.amount else "звёзды"
        buttons.append(
            f'<form method="post" action="/admin/queue/{problem.target}/{problem.entity_id}/refund" '
            f'style="display:inline" onsubmit="return confirm(\'Вернуть {amount}? '
            "Отменить это уже нельзя.')\">"
            "<button class=ghost type=submit>Вернуть</button></form>",
        )
    return " ".join(buttons) or '<span class="dim">—</span>'


def queue_page(
    problems: list[Problem],
    summary: Summary,
    *,
    flash: str | None = None,
    flash_error: bool = False,
) -> str:
    banner = ""
    if flash:
        banner = f'<div class="flash{" err" if flash_error else ""}">{escape(flash)}</div>'

    head = tiles(
        tile(str(summary.total), "требуют внимания"),
        tile(str(summary.stuck), "зависли", f"дольше {STUCK_AFTER_MINUTES} мин"),
        tile(f"{summary.money_at_risk} ⭐", "денег в подвешенном состоянии"),
        tile(summary.oldest, "самый старый случай"),
    )

    if problems:
        rows = [
            (
                f"{_BADGES[problem.trouble][0]} {escape(problem.product)}",
                f'<span class="mono">{escape(problem.who)}</span>',
                f"{problem.amount} ⭐" if problem.amount else '<span class="dim">бесплатно</span>',
                escape(problem.age_human),
                f'<span class="dim">{escape(problem.reason)}</span>',
                _actions(problem),
            )
            for problem in problems
        ]
        body = card(
            "Что пошло не так",
            table(
                ("Что и с чем", "Человек", "Оплачено", "Ждёт", "Причина", ""),
                rows,
                wide=(4,),
            ),
            '<span class="chip">старые сверху — они ждут дольше всех</span>',
        )
    else:
        body = card(
            "Чисто",
            '<p class="hint">Ни одного упавшего, зависшего или неприкаянного заказа. '
            "Так и должно выглядеть большинство дней.</p>",
        )

    legend = card(
        "Как это читать",
        '<p class="hint"><b>Упал</b> — воркер отработал попытки и сдался; за платные '
        "продукты звёзды он вернул сам, здесь такой заказ виден ради причины. "
        f"<b>Завис</b> — заказ в работе дольше {STUCK_AFTER_MINUTES} минут: воркер не дошёл "
        "до конца и не поставил «упал», поэтому автоматический возврат не сработал — "
        "человек заплатил и молча ничего не получил. <b>Сирота</b> — оплата прошла, "
        "а заказ к ней не привязался: восстановить нечего, только вернуть деньги.</p>",
    )

    return shell(
        "queue",
        banner + head + body + legend,
        subtitle="Заказы, которые не дошли до человека",
    )
