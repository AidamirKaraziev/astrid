"""Карточка «Обо мне»: портрет человека по его натальной карте.

Собирается кодом из уже посчитанной карты и рукописных фраз
(`portrait_texts.py`) — без LLM: экран открывают десятки раз, он должен
появляться мгновенно и всегда одинаково.

Что показываем, зависит от полноты данных, и границы здесь жёсткие:

* дома, асцендент и MC требуют **и времени, и разрешённого места рождения**.
  Без координат kerykeion считает их от Москвы, и человек из Краснодара
  увидит чужой асцендент — это хуже, чем не показать ничего;
* без времени Луна могла сменить знак за сутки — тогда называем оба знака,
  а не выбираем наугад;
* знаки Солнца, Меркурия, Венеры и Марса от места и времени не зависят —
  их показываем всегда.

Портрет намеренно не пересекается с платным «Разбором натала»: здесь только
знаки и по одной фразе на точку, без аспектов, конфигураций и прогнозов.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from astra.astro.birth_time import format_birth_time
from astra.astro.constants import SIGN_RU_PREPOSITIONAL
from astra.astro.schemas import FullNatalChart
from astra.core.observability import Event, get_logger
from astra.telegram.portrait_texts import (
    ASC_BY_SIGN,
    ELEMENT_BALANCED_LINE,
    ELEMENT_LINE,
    MARS_BY_SIGN,
    MERCURY_BY_SIGN,
    MODALITY_LINE,
    MOON_BY_SIGN,
    SUN_BY_SIGN,
    SUN_HOUSE_ACCENT,
    VENUS_BY_SIGN,
)
from astra.telegram.profile_text import shorten_city_label, shorten_place_display
from astra.users.gender import Gender

log = get_logger(__name__)

_SEPARATOR = "──────────────"

RU_MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

_HINT_TIME = (
    "🕐 <i>Время рождения покажет асцендент и дома — каким тебя видят "
    "и куда уходят силы.</i>"
)
_HINT_PLACE_EMPTY = (
    "📍 <i>Добавь место рождения — без координат асцендент и дома "
    "не посчитать.</i>"
)
_HINT_PLACE_UNRESOLVED = (
    "📍 <i>Не нашла «{place}» в справочнике городов — уточни, и посчитаю "
    "асцендент с домами.</i>"
)
_HINT_GENDER = "⚧ <i>Укажи пол — формулировки в разборах станут точнее.</i>"
_HINT_NOTIFICATION_CITY = (
    "🌍 <i>Выбери город для уведомлений — пришлю предсказание в 09:00 "
    "по твоему времени.</i>"
)

_MOON_UNCERTAIN = (
    "В те сутки Луна меняла знак. Какой из двух твой — покажет время рождения."
)

_CHART_UNAVAILABLE = (
    "🌌 <i>Карту сейчас посчитать не получилось. Загляни в раздел позже — "
    "портрет будет здесь.</i>"
)


class _ProfileView(Protocol):
    display_name: str
    gender: Gender | None
    birth_date: date
    birth_time: datetime | None
    birth_place: str | None
    notification_place_id: object | None
    city: str
    timezone: str


class _UserView(Protocol):
    points: int
    streak_current: int


def _birth_line(profile: _ProfileView, chart: FullNatalChart | None) -> str:
    day = profile.birth_date.day
    month = RU_MONTHS_GENITIVE[profile.birth_date.month - 1]
    head = f"{day} {month} {profile.birth_date.year}"
    clock = format_birth_time(profile.birth_time)
    if clock:
        head = f"{head}, {clock}"
    parts = [head]
    place = (profile.birth_place or "").strip()
    if place:
        parts.append(shorten_place_display(place))
    if chart is not None and chart.moon_phase:
        parts.append(chart.moon_phase)
    return f"<i>{' · '.join(parts)}</i>"


def _point_sign(chart: FullNatalChart, name: str) -> str | None:
    point = chart.point(name)
    return point.sign if point else None


def _headline(label: str, sign: str, house: int | None) -> str:
    tail = f", {house} дом" if house else ""
    return f"<b>{label} — {sign}</b>{tail}"


def _dominant(balance: dict[str, float]) -> str | None:
    """Самая весомая стихия или крест; None, если лидера нет."""
    if not balance:
        return None
    ranked = sorted(balance.items(), key=lambda kv: kv[1], reverse=True)
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def _house_of(chart: FullNatalChart, name: str, *, show_houses: bool) -> int | None:
    if not show_houses:
        return None
    point = chart.point(name)
    return point.house if point else None


def _asc_paragraph(chart: FullNatalChart, *, show_houses: bool) -> str | None:
    if not show_houses or chart.asc is None:
        return None
    text = ASC_BY_SIGN.get(chart.asc.sign)
    if text is None:
        return None
    return f"🌅 {_headline('Асцендент', chart.asc.sign, None)}\n{text}"


def _sun_paragraph(chart: FullNatalChart, *, show_houses: bool) -> str | None:
    sign = _point_sign(chart, "Sun")
    if sign is None:
        return None
    house = _house_of(chart, "Sun", show_houses=show_houses)
    story = [SUN_BY_SIGN.get(sign, "")]
    if house is not None:
        story.append(SUN_HOUSE_ACCENT.get(house, ""))
    body = " ".join(part for part in story if part)
    return f"🌞 {_headline('Солнце', sign, house)}\n{body}"


def _moon_paragraph(
    chart: FullNatalChart,
    *,
    show_houses: bool,
    moon_bounds: tuple[str, str] | None,
) -> str | None:
    if chart.moon_sign_uncertain and moon_bounds is not None:
        first, last = moon_bounds
        return f"🌙 <b>Луна — {first} или {last}</b>\n{_MOON_UNCERTAIN}"
    sign = _point_sign(chart, "Moon")
    if sign is None:
        return None
    house = _house_of(chart, "Moon", show_houses=show_houses)
    return f"🌙 {_headline('Луна', sign, house)}\n{MOON_BY_SIGN.get(sign, '')}"


def _minor_paragraph(chart: FullNatalChart) -> str | None:
    """Меркурий, Венера, Марс — по строке.

    Астрологические глифы вместо эмодзи: 🗣 💗 ⚔️ рядом с 🌞 🌙 🌅 рябят, а
    ☿ ♀ ♂ читаются как продолжение той же карты.
    """
    rows = (
        ("☿", "Меркурий", "Mercury", MERCURY_BY_SIGN),
        ("♀", "Венера", "Venus", VENUS_BY_SIGN),
        ("♂", "Марс", "Mars", MARS_BY_SIGN),
    )
    lines: list[str] = []
    for glyph, label, key, texts in rows:
        sign = _point_sign(chart, key)
        if sign is None:
            continue
        clause = texts.get(sign)
        if clause is None:
            continue
        where = SIGN_RU_PREPOSITIONAL.get(sign, sign)
        lines.append(f"{glyph} <b>{label}</b> в {where} — {clause}.")
    return "\n".join(lines) if lines else None


def _balance_paragraph(chart: FullNatalChart) -> str | None:
    lines: list[str] = []
    element = _dominant(chart.element_balance)
    if element is None and chart.element_balance:
        lines.append(ELEMENT_BALANCED_LINE)
    elif element in ELEMENT_LINE:
        lines.append(ELEMENT_LINE[element])
    modality = _dominant(chart.modality_balance)
    if modality in MODALITY_LINE:
        lines.append(MODALITY_LINE[modality])
    return "\n".join(lines) if lines else None


def _hints_paragraph(profile: _ProfileView, *, has_birth_coords: bool) -> str | None:
    """Чего не хватает для полного портрета.

    Время и координаты проверяются по отдельности: место может быть вписано
    текстом, но не найтись в справочнике — тогда просим уточнить именно его,
    а не «добавить».
    """
    hints: list[str] = []
    if profile.birth_time is None:
        hints.append(_HINT_TIME)
    if not has_birth_coords:
        place = (profile.birth_place or "").strip()
        if place:
            hints.append(_HINT_PLACE_UNRESOLVED.format(place=shorten_place_display(place)))
        else:
            hints.append(_HINT_PLACE_EMPTY)
    if profile.gender is None:
        hints.append(_HINT_GENDER)
    return "\n".join(hints) if hints else None


def _footer_paragraph(user: _UserView, profile: _ProfileView) -> str:
    if profile.notification_place_id is None:
        notification = _HINT_NOTIFICATION_CITY
    else:
        notification = f"🌍 {shorten_city_label(profile.city)} · предсказание в 09:00"
    return (
        f"{notification}\n{_SEPARATOR}\n"
        f"🔥 Серия {user.streak_current} дн.  ·  ⭐ {user.points} баллов"
    )


def format_portrait_card(
    user: _UserView,
    profile: _ProfileView,
    chart: FullNatalChart | None,
    *,
    has_birth_coords: bool,
    moon_bounds: tuple[str, str] | None = None,
) -> str:
    """Текст карточки «Обо мне».

    `has_birth_coords` — место рождения разрешилось в координаты. Без него
    дома и асцендент не показываем, даже если время известно.
    `moon_bounds` — знаки Луны на границах суток рождения; нужны только когда
    карта сообщила `moon_sign_uncertain`.
    """
    show_houses = bool(chart and chart.has_time and has_birth_coords)
    sun_sign = _point_sign(chart, "Sun") if chart else None

    title = f"✨ <b>{profile.display_name}</b>"
    if sun_sign:
        title = f"{title} · {sun_sign}"

    paragraphs: list[str | None] = [f"{title}\n{_birth_line(profile, chart)}"]
    if chart is None:
        paragraphs.append(_CHART_UNAVAILABLE)
    else:
        paragraphs += [
            _asc_paragraph(chart, show_houses=show_houses),
            _sun_paragraph(chart, show_houses=show_houses),
            _moon_paragraph(chart, show_houses=show_houses, moon_bounds=moon_bounds),
            _minor_paragraph(chart),
            _balance_paragraph(chart),
        ]
    paragraphs.append(_hints_paragraph(profile, has_birth_coords=has_birth_coords))
    paragraphs.append(_footer_paragraph(user, profile))
    return "\n\n".join(p for p in paragraphs if p)


async def build_portrait_text(session: AsyncSession, user, profile) -> str:  # noqa: ANN001
    """Посчитать карту и собрать текст карточки.

    Полная карта строится на каждое открытие раздела: kerykeion считает её за
    единицы миллисекунд, а кеш пришлось бы сбрасывать на каждой правке профиля.
    Упавший расчёт не должен закрывать человеку доступ к своим данным — тогда
    показываем карточку без портрета.
    """
    from astra.astro.calculator import moon_sign_bounds
    from astra.services.astro_service import birth_coordinates, build_full_chart_for_user

    chart: FullNatalChart | None
    moon_bounds: tuple[str, str] | None = None
    try:
        chart = await build_full_chart_for_user(session, user, profile)
        if chart.moon_sign_uncertain:
            lat, lon, tz = await birth_coordinates(session, profile)
            moon_bounds = moon_sign_bounds(profile.birth_date, lat=lat, lon=lon, timezone=tz)
    except Exception:
        log.exception(Event.PROFILE_PORTRAIT_FAILED, profile_id=profile.id)
        chart = None

    return format_portrait_card(
        user,
        profile,
        chart,
        has_birth_coords=profile.birth_place_id is not None,
        moon_bounds=moon_bounds,
    )
