"""Кнопки выбора места: регион, потом сам населённый пункт.

## Почему в два шага

«Красных» в справочнике 171 штука в 62 регионах, «Ивановок» — 488 в 96.
Плоский список из пяти строк показывал первые пять и предлагал «ввести
другой запрос» — остальные 166 были недостижимы, как ни переформулируй.
А пять строк выглядели одинаково: «Красное, Липецкая область» пять раз,
и человек с вероятностью четыре к одному выбирал не своё село. Молча.

Поэтому: много тёзок — сначала спрашиваем регион, там их единицы, и уже
внутри показываем места с ориентиром.

## Почему «Устюжна, 12 км», а не «12 км от Устюжны»

Родительный падеж пробовали: pymorphy3 на реальных названиях выдаёт «от
Шексна», «от Улана Удэ», «от Минеральных Воды», «от Санкта Петербурга».
Грамматическая ошибка на кнопке ничем не лучше орфографической, поэтому
название стоит в именительном, а расстояние отделено запятой.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from astra.places.crud import RegionHit
from astra.places.models import Place

# Сколько мест влезает на экран, чтобы список не приходилось прокручивать.
PAGE_SIZE = 8
# Больше этого — сначала спрашиваем регион. Меньше — показываем сразу места:
# лишний шаг ради трёх вариантов только раздражает.
REGION_STEP_FROM = 8

# Telegram обрезает подпись кнопки; режем сами, чтобы обрыв был осмысленным.
BUTTON_LIMIT = 60

CB_PICK = "place:pick:"
CB_REGION = "place:region:"
CB_PAGE = "place:page:"
CB_REGIONS = "place:regions"
CB_RETRY = "place:retry"
CB_MISSING = "place:missing"
CB_DESCRIBE = "place:describe"

BTN_MISSING = "💜 Не нашла свой город"
BTN_DESCRIBE = "💜 Рассказать, какого места не хватает"
BTN_RETRY = "🔍 Ввести другой запрос"


def _tail_rows() -> list[list[InlineKeyboardButton]]:
    """Две последние строки любого списка мест: переспросить и пожаловаться.

    Кнопка «не нашла» стоит всегда, а не только на пустой выдаче: тупик чаще
    выглядит как восемь чужих сёл на экране, чем как пустота.
    """
    return [
        [InlineKeyboardButton(text=BTN_RETRY, callback_data=CB_RETRY)],
        [InlineKeyboardButton(text=BTN_MISSING, callback_data=CB_MISSING)],
    ]


def nothing_found_keyboard() -> InlineKeyboardMarkup:
    """Совсем ничего не нашлось — выход всё равно должен быть на экране."""
    return InlineKeyboardMarkup(inline_keyboard=_tail_rows())


def missing_place_keyboard() -> InlineKeyboardMarkup:
    """Экран «маленьких сёл нет не всегда»: вернуться к поиску или рассказать."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Выбрать город", callback_data=CB_RETRY)],
            [InlineKeyboardButton(text=BTN_DESCRIBE, callback_data=CB_DESCRIBE)],
        ],
    )


def _clip(text: str) -> str:
    return text if len(text) <= BUTTON_LIMIT else f"{text[: BUTTON_LIMIT - 1]}…"


def landmark_hint(place: Place) -> str:
    """«Устюжна, 12 км» — по какому городу человек узнаёт своё село."""
    if not place.nearest_city or place.nearest_city_km is None:
        return ""
    return f"{place.nearest_city}, {place.nearest_city_km} км"


def place_label(place: Place, *, with_region: bool, with_landmark: bool) -> str:
    """Подпись кнопки места.

    Регион не повторяем, когда человек его только что выбрал, а ориентир
    показываем только там, где без него строки неразличимы.
    """
    head = place.display_name if with_region else place.name
    hint = landmark_hint(place) if with_landmark else ""
    return _clip(f"{head} · {hint}" if hint else head)


def has_namesakes(places: list[Place]) -> bool:
    """Есть ли в выдаче строки, которые без ориентира выглядят одинаково."""
    seen = [place.display_name for place in places]
    return len(set(seen)) != len(seen)


def places_pick_keyboard(
    places: list[Place],
    *,
    with_region: bool = True,
    offset: int = 0,
    total: int | None = None,
    inside_region: bool = False,
) -> InlineKeyboardMarkup:
    with_landmark = has_namesakes(places) or inside_region
    rows = [
        [
            InlineKeyboardButton(
                text=place_label(place, with_region=with_region, with_landmark=with_landmark),
                callback_data=f"{CB_PICK}{place.id}",
            ),
        ]
        for place in places
    ]

    navigation: list[InlineKeyboardButton] = []
    if total is not None and offset + len(places) < total:
        remaining = total - offset - len(places)
        navigation.append(
            InlineKeyboardButton(
                text=f"Ещё {min(remaining, PAGE_SIZE)} из {remaining}",
                callback_data=f"{CB_PAGE}{offset + len(places)}",
            ),
        )
    if inside_region:
        navigation.append(
            InlineKeyboardButton(text="Другой регион", callback_data=CB_REGIONS),
        )
    if navigation:
        rows.append(navigation)

    rows.extend(_tail_rows())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def regions_pick_keyboard(
    regions: list[RegionHit],
    *,
    offset: int = 0,
    total: int | None = None,
) -> InlineKeyboardMarkup:
    """Первый шаг: в каком регионе искать."""
    rows = [
        [
            InlineKeyboardButton(
                text=_clip(f"{hit.title} · {hit.count}"),
                callback_data=f"{CB_REGION}{offset + index}",
            ),
        ]
        for index, hit in enumerate(regions)
    ]

    if total is not None and offset + len(regions) < total:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Ещё регионы ({total - offset - len(regions)})",
                    callback_data=f"{CB_PAGE}{offset + len(regions)}",
                ),
            ],
        )

    rows.extend(_tail_rows())
    return InlineKeyboardMarkup(inline_keyboard=rows)
