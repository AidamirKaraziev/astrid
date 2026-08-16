"""HTML панели — собирается здесь, без шаблонизатора.

Шаблонизатора в проекте нет и ради двух страниц заводить его не стали: панель
целиком помещается в этот модуль, а стиль (тёмный, лиловый) повторяет бота.
Всё, что приходит из БД или из адресной строки, проходит через html.escape.
"""

from __future__ import annotations

from html import escape

from astra.admin.service import PriceView, PrizeView, ProductView
from astra.payments.enums import CURRENCY_XTR

_KIND_LABELS = {
    "tarot_reading": "Расклады таро",
    "ask_answer": "Спроси Астрид",
    "wheel_spin": "Колесо фортуны",
}

_CSS = """
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
  color: #ece7f7;
  background: #0b0715;
}
/* Свечения — отдельным зафиксированным слоем: background-attachment: fixed
   мобильные браузеры отрисовывают рывками. */
body::before {
  content: ""; position: fixed; inset: 0; z-index: -1; pointer-events: none;
  background:
    radial-gradient(1100px 600px at 12% -8%, rgba(139, 92, 246, .30), transparent 60%),
    radial-gradient(900px 520px at 88% 4%, rgba(56, 189, 248, .16), transparent 58%),
    radial-gradient(700px 700px at 50% 110%, rgba(217, 70, 239, .18), transparent 62%);
}
a { color: #c4b5fd; }
.wrap { max-width: 1180px; margin: 0 auto; padding: 32px 20px 72px; }

header.top {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  padding: 22px 26px; margin-bottom: 28px;
  border-radius: 22px;
  background: linear-gradient(135deg, rgba(255,255,255,.09), rgba(255,255,255,.035));
  border: 1px solid rgba(196,181,253,.22);
  box-shadow: 0 20px 60px rgba(10, 4, 26, .55);
  backdrop-filter: blur(14px);
}
header.top h1 { margin: 0; font-size: 21px; letter-spacing: .4px; font-weight: 650; }
header.top p { margin: 4px 0 0; font-size: 13.5px; color: #a99fc4; }
header.top .spacer { flex: 1 1 auto; }

h2.section {
  margin: 34px 0 14px; font-size: 12.5px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 1.6px; color: #a99fc4;
}
h2.section span { color: #f0abfc; }

.card {
  border-radius: 20px; padding: 20px 22px; margin-bottom: 16px;
  background: linear-gradient(160deg, rgba(255,255,255,.075), rgba(255,255,255,.028));
  border: 1px solid rgba(196,181,253,.16);
  box-shadow: 0 14px 40px rgba(8, 3, 20, .45);
}
.card.muted { opacity: .58; }
.card-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-bottom: 4px; }
.card-head h3 { margin: 0; font-size: 17px; font-weight: 600; }
.chip {
  font-size: 11.5px; letter-spacing: .3px; padding: 3px 9px; border-radius: 999px;
  border: 1px solid rgba(196,181,253,.28); color: #c4b5fd; background: rgba(139,92,246,.12);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.chip.off { color: #fca5a5; border-color: rgba(252,165,165,.3); background: rgba(248,113,113,.1); }
.hint { font-size: 13px; color: #a99fc4; margin: 8px 0 0; }

form.row {
  display: flex; align-items: flex-end; gap: 14px; flex-wrap: wrap;
  padding: 14px 0 2px; border-top: 1px solid rgba(196,181,253,.12); margin-top: 14px;
}
.field { display: flex; flex-direction: column; gap: 5px; }
.field label { font-size: 11.5px; letter-spacing: .7px; text-transform: uppercase; color: #a99fc4; }
.field input, .field select {
  width: 118px; padding: 9px 11px; font-size: 15px; color: #ece7f7;
  background: rgba(12,7,24,.75); border: 1px solid rgba(196,181,253,.24);
  border-radius: 11px; outline: none;
}
.field input:focus, .field select:focus { border-color: #a78bfa; box-shadow: 0 0 0 3px rgba(167,139,250,.18); }
.field.wide input, .field.wide select { width: 150px; }
/* поле, растягивающееся по строке: поиск, выбор аудитории */
.field.grow { flex: 1 1 260px; }
.field.grow input, .field.grow select { width: 100%; }

.toggle { display: flex; align-items: center; gap: 8px; font-size: 14px; color: #cfc7e6; padding-bottom: 9px; }
.toggle input { width: 17px; height: 17px; accent-color: #a78bfa; }

.total {
  padding: 9px 14px; border-radius: 12px; font-size: 15px; white-space: nowrap;
  background: rgba(139,92,246,.16); border: 1px solid rgba(196,181,253,.26); color: #ddd6fe;
}
.total.free { background: rgba(74,222,128,.14); border-color: rgba(134,239,172,.3); color: #bbf7d0; }
.total s { color: #8b82a6; margin-right: 7px; }

button {
  padding: 10px 20px; font-size: 14.5px; font-weight: 600; color: #1a0f2e; cursor: pointer;
  background: linear-gradient(135deg, #d8b4fe, #a78bfa); border: 0; border-radius: 12px;
  transition: transform .12s ease, filter .12s ease;
}
button:hover { filter: brightness(1.08); transform: translateY(-1px); }
button.ghost {
  background: transparent; color: #c4b5fd; border: 1px solid rgba(196,181,253,.32);
  font-weight: 500;
}

details { margin-top: 12px; }
details summary { cursor: pointer; font-size: 13.5px; color: #c4b5fd; list-style: none; }
details summary::-webkit-details-marker { display: none; }
details summary::before { content: "+ "; }
details[open] summary::before { content: "− "; }

.flash {
  padding: 13px 18px; border-radius: 14px; margin-bottom: 20px; font-size: 14.5px;
  border: 1px solid rgba(134,239,172,.3); background: rgba(74,222,128,.13); color: #bbf7d0;
}
.flash.err { border-color: rgba(252,165,165,.32); background: rgba(248,113,113,.13); color: #fecaca; }

/* --- каркас: боковая навигация + содержимое --- */
.layout { display: grid; grid-template-columns: 186px 1fr; gap: 26px; align-items: start; }
/* без min-width:0 колонка растягивается под самую широкую таблицу и вбок едет
   вся страница вместо внутренней прокрутки .scroll */
.layout > main { min-width: 0; }
nav.side { position: sticky; top: 24px; display: flex; flex-direction: column; gap: 3px; }
nav.side a {
  padding: 9px 14px; border-radius: 12px; font-size: 14.5px; text-decoration: none;
  color: #cfc7e6; border: 1px solid transparent; white-space: nowrap;
}
nav.side a:hover { background: rgba(255,255,255,.055); }
nav.side a.on {
  background: rgba(139,92,246,.20); color: #f3e8ff; border-color: rgba(196,181,253,.28);
}

/* --- таблицы списков --- */
.scroll { overflow-x: auto; }
.card .scroll { margin-top: 12px; }
table.list { width: 100%; border-collapse: collapse; font-size: 14px; }
table.list th {
  text-align: left; font-size: 11px; font-weight: 600; letter-spacing: .9px;
  text-transform: uppercase; color: #a99fc4; padding: 0 14px 10px 0; white-space: nowrap;
}
/* Ячейки не переносим — таблица уезжает в горизонтальную прокрутку .scroll;
   длинным текстам (причина ошибки, текст обращения) даём класс .cell-wide. */
table.list td { padding: 11px 14px 11px 0; border-top: 1px solid rgba(196,181,253,.10); white-space: nowrap; }
table.list td.cell-wide { white-space: normal; min-width: 170px; }
table.list button { padding: 7px 12px; font-size: 13px; margin-right: 6px; }
table.list tr:hover td { background: rgba(255,255,255,.025); }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; color: #c4b5fd; }
.dim { color: #a99fc4; }

.badge {
  display: inline-block; font-size: 11.5px; padding: 3px 9px; border-radius: 999px;
  border: 1px solid rgba(196,181,253,.28); color: #c4b5fd; background: rgba(139,92,246,.12);
}
.badge.bad { color: #fca5a5; border-color: rgba(252,165,165,.32); background: rgba(248,113,113,.12); }
.badge.warn { color: #fcd34d; border-color: rgba(252,211,77,.3); background: rgba(251,191,36,.12); }
.badge.ok { color: #bbf7d0; border-color: rgba(134,239,172,.3); background: rgba(74,222,128,.12); }

/* --- метрики --- */
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(158px, 1fr)); gap: 14px; }
.tile {
  padding: 18px 20px; border-radius: 18px;
  background: linear-gradient(160deg, rgba(255,255,255,.075), rgba(255,255,255,.028));
  border: 1px solid rgba(196,181,253,.16);
}
.tile b { display: block; font-size: 27px; font-weight: 650; letter-spacing: -.5px; }
.tile span { font-size: 12.5px; color: #a99fc4; }
.tile em { font-style: normal; font-size: 12.5px; color: #bbf7d0; }
.bars { display: flex; align-items: flex-end; gap: 9px; height: 132px; margin-top: 6px; }
.bars i {
  flex: 1; border-radius: 7px 7px 0 0; background: linear-gradient(180deg, #d8b4fe, #7c3aed);
  position: relative;
}
.bars i:hover { filter: brightness(1.15); }
.bars-x { display: flex; gap: 9px; margin-top: 8px; }
.bars-x span { flex: 1; text-align: center; font-size: 11px; color: #a99fc4; }

.periods { display: flex; gap: 8px; margin-bottom: 18px; flex-wrap: wrap; }
.periods a {
  padding: 7px 14px; border-radius: 999px; font-size: 13.5px; text-decoration: none;
  color: #c4b5fd; border: 1px solid rgba(196,181,253,.24);
}
.periods a.on { background: rgba(139,92,246,.22); color: #f3e8ff; border-color: rgba(196,181,253,.4); }

/* --- график с двумя рядами --- */
.bars i.pair { position: relative; }
.bars.duo i { display: flex; align-items: flex-end; gap: 3px; background: none; height: 100%; }
.bars.duo i > b {
  flex: 1; border-radius: 5px 5px 0 0; background: linear-gradient(180deg, #d8b4fe, #7c3aed);
}
.bars.duo i > b.second { background: linear-gradient(180deg, #67e8f9, #0e7490); }
.bars i.now, .bars.duo i.now > b { opacity: .55; }
.legend { display: flex; gap: 16px; margin-top: 10px; font-size: 12.5px; color: #a99fc4; }
.legend span::before {
  content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 3px;
  margin-right: 6px; background: linear-gradient(180deg, #d8b4fe, #7c3aed);
}
.legend span.second::before { background: linear-gradient(180deg, #67e8f9, #0e7490); }
.legend span.now::before { background: rgba(196,181,253,.45); }

/* --- предпросмотр телеграма --- */
.tg-wrap { max-width: 420px; margin: 14px 0; }
.tg-bubble {
  position: relative; padding: 10px 14px 20px; border-radius: 14px 14px 14px 4px;
  background: #2b5278; color: #fff; font-size: 15px; line-height: 1.45;
  box-shadow: 0 6px 18px rgba(0,0,0,.35); word-break: break-word;
}
.tg-bubble a { color: #9dd0ff; }
.tg-bubble blockquote {
  margin: 8px 0; padding: 4px 0 4px 10px; border-left: 3px solid #9dd0ff;
  color: #e8f2ff; font-style: normal;
}
.tg-bubble tg-spoiler { background: rgba(255,255,255,.28); border-radius: 4px; color: transparent; }
.tg-bubble tg-spoiler:hover { color: inherit; background: transparent; }
.tg-bubble code { background: rgba(0,0,0,.25); padding: 1px 5px; border-radius: 5px; font-size: 14px; }
.tg-time { position: absolute; right: 12px; bottom: 5px; font-size: 11px; color: rgba(255,255,255,.6); }
.tg-btn {
  margin-top: 4px; padding: 9px 12px; text-align: center; font-size: 14.5px;
  border-radius: 10px; background: #38607f; color: #cfe6ff;
}

/* --- множественный выбор --- */
.field-group { margin: 16px 0; }
.group-title { display: block; font-size: 11.5px; letter-spacing: .7px; text-transform: uppercase; color: #a99fc4; margin-bottom: 8px; }
.picks { display: flex; flex-wrap: wrap; gap: 8px; }
.pick {
  display: inline-flex; align-items: center; gap: 7px; padding: 7px 12px; border-radius: 999px;
  font-size: 13.5px; color: #cfc7e6; border: 1px solid rgba(196,181,253,.24); cursor: pointer;
}
.pick:hover { background: rgba(255,255,255,.05); }
.pick input { accent-color: #a78bfa; }

/* --- прототип --- */
.proto {
  display: inline-block; font-size: 11px; letter-spacing: 1px; text-transform: uppercase;
  padding: 4px 10px; border-radius: 999px; margin-left: 10px; vertical-align: middle;
  color: #fcd34d; border: 1px solid rgba(252,211,77,.32); background: rgba(251,191,36,.1);
}
.note {
  padding: 12px 16px; border-radius: 14px; margin-bottom: 18px; font-size: 13.5px;
  color: #d9d0ef; border: 1px dashed rgba(196,181,253,.3); background: rgba(139,92,246,.08);
}
textarea {
  width: 100%; min-height: 120px; padding: 12px 14px; font: inherit; font-size: 14.5px;
  color: #ece7f7; background: rgba(12,7,24,.75); border: 1px solid rgba(196,181,253,.24);
  border-radius: 14px; outline: none; resize: vertical;
}
textarea:focus { border-color: #a78bfa; }

.login { max-width: 380px; margin: 14vh auto 0; padding: 0 20px; }
.login .card { padding: 30px 28px; }
.login h1 { margin: 0 0 6px; font-size: 23px; }
.login p.sub { margin: 0 0 22px; font-size: 13.5px; color: #a99fc4; }
.login .field { margin-bottom: 14px; }
.login .field input { width: 100%; }
.login button { width: 100%; margin-top: 6px; }

@media (max-width: 860px) {
  .layout { grid-template-columns: 1fr; gap: 18px; }
  nav.side {
    position: static; flex-direction: row; overflow-x: auto; gap: 6px;
    padding-bottom: 6px; scrollbar-width: none;
  }
  nav.side::-webkit-scrollbar { display: none; }
}

@media (max-width: 620px) {
  .wrap { padding: 18px 14px 56px; }
  form.row { gap: 10px; }
  .field input, .field select, .field.wide input, .field.wide select { width: 100%; }
  .field { flex: 1 1 130px; }
  form.row button { flex: 1 1 100%; }
  .tile b { font-size: 23px; }
}
"""

# Пересчёт итоговой цены прямо в поле ввода — тем же правилом, что и на сервере
# (round-half-even, платная акция не опускается ниже одной минорной единицы).
_JS = """
function roundHalfEven(x) {
  const f = Math.floor(x), d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}
function recalc(form) {
  const out = form.querySelector('[data-total]');
  if (!out) return;
  const amount = parseInt(form.querySelector('[name=amount]').value || '0', 10);
  const discount = parseInt(form.querySelector('[name=discount_percent]').value || '0', 10);
  const unit = out.dataset.unit;
  if (!(amount > 0) || discount < 0 || discount > 100) { out.textContent = '—'; return; }
  if (discount >= 100) { out.textContent = 'бесплатно'; out.classList.add('free'); return; }
  out.classList.remove('free');
  const final = discount > 0 ? Math.max(1, roundHalfEven(amount * (100 - discount) / 100)) : amount;
  out.innerHTML = (discount > 0 ? '<s>' + amount + ' ' + unit + '</s>' : '') + final + ' ' + unit;
}
document.addEventListener('input', (e) => {
  const form = e.target.closest('form.row');
  if (form) recalc(form);
});
document.querySelectorAll('form.row').forEach(recalc);
"""


def _unit(currency: str) -> str:
    return "⭐" if currency == CURRENCY_XTR else escape(currency)


def _amount_label(currency: str) -> str:
    return "Цена, ⭐" if currency == CURRENCY_XTR else f"Цена, {escape(currency)} (минорные)"


def page(title: str, body: str) -> str:
    return (
        "<!doctype html>"
        '<html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="robots" content="noindex, nofollow">'
        f"<title>{escape(title)}</title><style>{_CSS}</style></head>"
        f"<body>{body}</body></html>"
    )


# Разделы панели: slug (пустой — каталог), пункт меню, заголовок страницы.
SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("", "Каталог", "Каталог"),
    ("queue", "Очередь", "Очередь проблем"),
    ("people", "Люди", "Люди"),
    ("payments", "Платежи", "Платежи"),
    ("support", "Поддержка", "Обращения"),
    ("settings", "Настройки", "Настройки"),
    ("broadcasts", "Рассылки", "Рассылки"),
    ("metrics", "Метрики", "Метрики"),
    ("stars", "Звёзды", "Звёзды"),
)

_TITLES = {slug: title for slug, _, title in SECTIONS}


def _nav(active: str) -> str:
    items = "".join(
        f'<a href="/admin/{slug}" class="{"on" if slug == active else ""}">{escape(label)}</a>'
        for slug, label, _ in SECTIONS
    )
    return f'<nav class="side">{items}</nav>'


def shell(
    active: str,
    content: str,
    *,
    subtitle: str,
    banner: str = "",
    script: str = "",
    prototype: bool = False,
) -> str:
    """Каркас страницы: шапка, боковое меню, содержимое раздела."""
    title = _TITLES.get(active, "Панель")
    proto = '<span class="proto">прототип</span>' if prototype else ""
    tail = f"<script>{script}</script>" if script else ""
    body = (
        '<div class="wrap">'
        f'<header class="top"><div><h1>Astra ✨ {escape(title.lower())}{proto}</h1>'
        f"<p>{escape(subtitle)}</p></div>"
        '<div class="spacer"></div>'
        '<form method="post" action="/admin/logout"><button class="ghost" type=submit>Выйти</button></form>'
        "</header>"
        f'<div class="layout">{_nav(active)}<main>{banner}{content}</main></div>'
        f"</div>{tail}"
    )
    return page(f"{title} — Astra", body)


# --- кирпичики страниц: их используют и живые разделы, и макеты ---


def card(title: str, inner: str, chips: str = "") -> str:
    return f'<div class="card"><div class="card-head"><h3>{title}</h3>{chips}</div>{inner}</div>'


def tile(value: str, label: str, note: str = "") -> str:
    note_html = f"<em>{note}</em>" if note else ""
    return f'<div class="tile"><b>{value}</b><span>{label}</span> {note_html}</div>'


def tiles(*items: str) -> str:
    return f'<div class="tiles" style="margin-bottom:20px">{"".join(items)}</div>'


def table(
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


def bars(points: list[tuple[str, int]], unit: str = "⭐") -> str:
    """Столбики по дням: подпись под каждым, значение в подсказке."""
    top = max((value for _, value in points), default=0) or 1
    columns = "".join(
        f'<i style="height:{max(2, round(value * 100 / top))}%" title="{escape(label)}: {value} {unit}"></i>'
        for label, value in points
    )
    labels = "".join(f"<span>{escape(label)}</span>" for label, _ in points)
    return f'<div class="bars">{columns}</div><div class="bars-x">{labels}</div>'


def login_page(*, error: str | None = None) -> str:
    banner = f'<div class="flash err">{escape(error)}</div>' if error else ""
    body = (
        '<div class="login">'
        f"{banner}"
        '<div class="card">'
        "<h1>Astra ✨</h1>"
        '<p class="sub">Панель управления каталогом</p>'
        '<form method="post" action="/admin/login">'
        '<div class="field"><label for="u">Логин</label>'
        '<input id="u" name="username" autocomplete="username" autofocus></div>'
        '<div class="field"><label for="p">Пароль</label>'
        '<input id="p" name="password" type="password" autocomplete="current-password"></div>'
        "<button type=submit>Войти</button>"
        "</form></div></div>"
    )
    return page("Вход — Astra", body)


def _price_form(product_code: str, price: PriceView) -> str:
    unit = _unit(price.currency)
    info = price.info
    if info.is_free:
        total = f'<span class="total free" data-total data-unit="{unit}">бесплатно</span>'
    else:
        struck = f"<s>{price.amount} {unit}</s>" if info.has_discount else ""
        total = (
            f'<span class="total" data-total data-unit="{unit}">'
            f"{struck}{info.final_amount} {unit}</span>"
        )
    checked = " checked" if price.is_active else ""
    return (
        f'<form class="row" method="post" action="/admin/prices/{price.id}">'
        f'<input type="hidden" name="product_code" value="{escape(product_code)}">'
        f'<div class="field"><label>{_amount_label(price.currency)}</label>'
        f'<input type="number" name="amount" min="1" step="1" value="{price.amount}"></div>'
        '<div class="field"><label>Скидка, %</label>'
        f'<input type="number" name="discount_percent" min="0" max="100" step="1" '
        f'value="{price.discount_percent}"></div>'
        f"{total}"
        f'<label class="toggle"><input type="checkbox" name="is_active" value="1"{checked}>Продаётся</label>'
        "<button type=submit>Сохранить</button>"
        "</form>"
    )


def _add_price_form(product_code: str) -> str:
    return (
        "<details><summary>Добавить цену в другой валюте</summary>"
        f'<form class="row" method="post" action="/admin/products/{escape(product_code)}/prices">'
        '<div class="field wide"><label>Валюта</label>'
        '<select name="currency"><option value="XTR">XTR — Telegram Stars</option>'
        '<option value="RUB">RUB — рубли (копейки)</option></select></div>'
        '<div class="field"><label>Цена</label>'
        '<input type="number" name="amount" min="1" step="1" value="50"></div>'
        '<div class="field"><label>Скидка, %</label>'
        '<input type="number" name="discount_percent" min="0" max="100" step="1" value="0"></div>'
        "<button type=submit>Добавить</button></form></details>"
    )


def _product_card(product: ProductView) -> str:
    state_chip = "" if product.is_active else '<span class="chip off">выключен</span>'
    prices = "".join(_price_form(product.code, price) for price in product.prices)
    if not product.prices:
        fallback = (
            "покупка пойдёт по фолбэку TAROT_READING_PRICE_STARS из конфига"
            if product.kind == "tarot_reading"
            else "товар не продастся, пока цены нет"
        )
        prices = f'<p class="hint">Цены в каталоге нет: {fallback}.</p>'
    toggle_label = "Выключить товар" if product.is_active else "Включить товар"
    toggle = (
        f'<form method="post" action="/admin/products/{escape(product.code)}/toggle" '
        'style="display:inline">'
        f'<input type="hidden" name="is_active" value="{"0" if product.is_active else "1"}">'
        f'<button class="ghost" type=submit>{toggle_label}</button></form>'
    )
    return (
        f'<div class="card{"" if product.is_active else " muted"}">'
        f'<div class="card-head"><h3>{escape(product.title)}</h3>'
        f'<span class="chip">{escape(product.code)}</span>{state_chip}</div>'
        f"{prices}{_add_price_form(product.code)}"
        f'<div style="margin-top:14px">{toggle}</div>'
        "</div>"
    )


def _prize_form(prize: PrizeView, total_weight: int) -> str:
    checked = " checked" if prize.is_active else ""
    label = "бесплатно" if prize.discount_percent == 100 else f"−{prize.discount_percent}%"
    # Шанс считаем только у активных: у выключенного сектора его нет вовсе.
    chance = (
        f"шанс {prize.chance_percent(total_weight)}%" if prize.is_active else "не в колесе"
    )
    return (
        f'<div class="card{"" if prize.is_active else " muted"}">'
        f'<div class="card-head"><h3>{escape(prize.product_title)}</h3>'
        f'<span class="chip">{label}</span>'
        f'<span class="chip">{chance}</span></div>'
        f'<form class="row" method="post" action="/admin/prizes/{prize.id}">'
        '<div class="field"><label>Скидка, %</label>'
        f'<input type="number" name="discount_percent" min="1" max="100" step="1" '
        f'value="{prize.discount_percent}"></div>'
        '<div class="field"><label>Вес сектора</label>'
        f'<input type="number" name="weight" min="1" step="1" value="{prize.weight}"></div>'
        f'<label class="toggle"><input type="checkbox" name="is_active" value="1"{checked}>В колесе</label>'
        "<button type=submit>Сохранить</button></form></div>"
    )


def catalog_page(
    products: list[ProductView],
    prizes: list[PrizeView],
    *,
    flash: str | None = None,
    flash_error: bool = False,
) -> str:
    banner = ""
    if flash:
        banner = f'<div class="flash{" err" if flash_error else ""}">{escape(flash)}</div>'

    sections: list[str] = []
    for kind, label in _KIND_LABELS.items():
        group = [p for p in products if p.kind == kind]
        if group:
            sections.append(f'<h2 class="section">{escape(label)}</h2>')
            sections.extend(_product_card(product) for product in group)

    other = [p for p in products if p.kind not in _KIND_LABELS]
    if other:
        sections.append('<h2 class="section">Прочее</h2>')
        sections.extend(_product_card(product) for product in other)

    if not products:
        sections.append('<div class="card"><p class="hint">Каталог пуст: в базе нет ни одного товара.</p></div>')

    if prizes:
        total_weight = sum(prize.weight for prize in prizes if prize.is_active)
        sections.append('<h2 class="section">Призы колеса <span>— перебивают акции каталога</span></h2>')
        sections.extend(_prize_form(prize, total_weight) for prize in prizes)

    return shell(
        "",
        "".join(sections),
        subtitle="Правки применяются сразу — цена читается из базы на каждую покупку",
        banner=banner,
        script=_JS,
    )
