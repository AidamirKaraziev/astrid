"""Карточка «Обо мне»: портрет по натальной карте.

Фикстура пиненая — 1990-06-15 14:30 Москва, та же, что в test_full_natal_chart.
"""

import re
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from astra.astro.calculator import build_full_natal_chart, kerykeion_available
from astra.astro.constants import SIGN_EN_TO_RU
from astra.telegram.portrait_texts import (
    ASC_BY_SIGN,
    MARS_BY_SIGN,
    MERCURY_BY_SIGN,
    MOON_BY_SIGN,
    SUN_BY_SIGN,
    SUN_HOUSE_ACCENT,
    VENUS_BY_SIGN,
)
from astra.telegram.profile_portrait import build_portrait_text, format_portrait_card

_BIRTH = {
    "name": "Тест",
    "birth_date": date(1990, 6, 15),
    "lat": 55.7558,
    "lon": 37.6176,
    "timezone": "Europe/Moscow",
}

_ALL_SIGNS = set(SIGN_EN_TO_RU.values())

# «, 9 дом» в заголовке блока. Слово «дома» встречается и в подсказках.
_HOUSE_IN_HEADLINE = re.compile(r", \d+ дом")


def _user() -> SimpleNamespace:
    return SimpleNamespace(points=340, streak_current=12)


def _profile(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "display_name": "Анна",
        "gender": "женщина",
        "birth_date": date(1990, 6, 15),
        "birth_time": datetime(1990, 6, 15, 14, 30),
        "birth_place": "Москва, Россия",
        "birth_place_id": uuid4(),
        "notification_place_id": uuid4(),
        "city": "Краснодар, Краснодарский край, Россия",
        "timezone": "Europe/Moscow",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── Контент: без полного набора фраз портрет молча теряет блоки ──────────────


def test_every_sign_has_text() -> None:
    for name, texts in (
        ("асцендент", ASC_BY_SIGN),
        ("солнце", SUN_BY_SIGN),
        ("луна", MOON_BY_SIGN),
        ("меркурий", MERCURY_BY_SIGN),
        ("венера", VENUS_BY_SIGN),
        ("марс", MARS_BY_SIGN),
    ):
        assert set(texts) == _ALL_SIGNS, f"{name}: не все знаки"
        assert all(value.strip() for value in texts.values()), f"{name}: пустая фраза"


def test_every_house_has_accent() -> None:
    assert set(SUN_HOUSE_ACCENT) == set(range(1, 13))


def test_texts_are_not_gendered() -> None:
    """Фразы читают и женщины, и мужчины — форм с родом быть не должно."""
    banned = re.compile(
        r"\b(был|была|сам|сама|готов|готова|уверен|уверена|должен|должна|рад|рада"
        r"|решил|решила|начал|начала|сделал|сделала|хотел|хотела|смог|смогла)\b",
        re.IGNORECASE,
    )
    for texts in (ASC_BY_SIGN, SUN_BY_SIGN, MOON_BY_SIGN, MERCURY_BY_SIGN,
                  VENUS_BY_SIGN, MARS_BY_SIGN, SUN_HOUSE_ACCENT):
        for value in texts.values():
            found = banned.search(value)
            assert not found, f"форма с родом в {value!r}"


# ── Полные данные ───────────────────────────────────────────────────────────

# Пропускаем через фикстуры, а не через pytestmark: тесты самих текстов и
# устойчивости сборки нужны и там, где kerykeion не поставлен.


@pytest.fixture(scope="module")
def chart():
    if not kerykeion_available():
        pytest.skip("kerykeion not installed")
    return build_full_natal_chart(birth_time=datetime(1990, 6, 15, 14, 30), **_BIRTH)


@pytest.fixture(scope="module")
def chart_no_time():
    if not kerykeion_available():
        pytest.skip("kerykeion not installed")
    return build_full_natal_chart(birth_time=None, **_BIRTH)


def test_full_card_shows_asc_houses_and_prepositional_case(chart) -> None:
    text = format_portrait_card(_user(), _profile(), chart, has_birth_coords=True)

    assert text.startswith("✨ <b>Анна</b> · Близнецы")
    assert "15 июня 1990, 14:30" in text
    assert "🌅 <b>Асцендент — Весы</b>" in text
    assert "🌞 <b>Солнце — Близнецы</b>, 9 дом" in text
    assert "🌙 <b>Луна — Рыбы</b>, 6 дом" in text
    # предложный падеж, а не «в Близнецы»
    assert "в Близнецах" in text
    assert "Стихия — " in text
    assert "Крест — " in text
    assert "🔥 Серия 12 дн." in text
    # подсказок нет: данные полные
    assert "Время рождения покажет" not in text
    assert "справочнике городов" not in text


def test_house_number_is_not_repeated_in_prose(chart) -> None:
    text = format_portrait_card(_user(), _profile(), chart, has_birth_coords=True)
    assert "Девятый дом" not in text


# ── Деградация ──────────────────────────────────────────────────────────────


def test_no_time_hides_asc_and_houses(chart_no_time) -> None:
    text = format_portrait_card(
        _user(),
        _profile(birth_time=None),
        chart_no_time,
        has_birth_coords=True,
    )

    assert "Асцендент" not in text
    assert _HOUSE_IN_HEADLINE.search(text) is None
    assert "🌞 <b>Солнце — Близнецы</b>" in text
    assert "Время рождения покажет" in text
    assert "справочнике городов" not in text


def test_time_without_coords_hides_asc_and_asks_to_refine_place(chart) -> None:
    """Без координат дома считались бы от Москвы — показывать их нельзя."""
    text = format_portrait_card(
        _user(),
        _profile(birth_place="Джубга", birth_place_id=None),
        chart,
        has_birth_coords=False,
    )

    assert "Асцендент" not in text
    assert _HOUSE_IN_HEADLINE.search(text) is None
    assert "Не нашла «Джубга»" in text


def test_empty_place_asks_to_add_it(chart) -> None:
    text = format_portrait_card(
        _user(),
        _profile(birth_place="", birth_place_id=None),
        chart,
        has_birth_coords=False,
    )
    assert "Добавь место рождения" in text


def test_uncertain_moon_names_both_signs(chart_no_time) -> None:
    uncertain = chart_no_time.model_copy(update={"moon_sign_uncertain": True})
    text = format_portrait_card(
        _user(),
        _profile(birth_time=None),
        uncertain,
        has_birth_coords=True,
        moon_bounds=("Овен", "Телец"),
    )

    assert "🌙 <b>Луна — Овен или Телец</b>" in text
    assert "Луна меняла знак" in text


def test_missing_gender_and_city_are_hinted(chart) -> None:
    text = format_portrait_card(
        _user(),
        _profile(gender=None, notification_place_id=None),
        chart,
        has_birth_coords=True,
    )
    assert "Укажи пол" in text
    assert "город для уведомлений" in text.lower()


def test_card_without_chart_still_shows_data() -> None:
    """Расчёт упал — человек всё равно видит свои данные и меню."""
    text = format_portrait_card(_user(), _profile(), None, has_birth_coords=True)

    assert "✨ <b>Анна</b>" in text
    assert "15 июня 1990, 14:30" in text
    assert "посчитать не получилось" in text
    assert "🔥 Серия 12 дн." in text


def test_balanced_elements_get_their_own_line(chart) -> None:
    even = chart.model_copy(
        update={"element_balance": {"огонь": 3.0, "вода": 3.0, "земля": 3.0, "воздух": 3.0}},
    )
    text = format_portrait_card(_user(), _profile(), even, has_birth_coords=True)
    assert "Стихии разложены ровно" in text


# ── Сборка ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_build_portrait_text_survives_chart_failure() -> None:
    profile = _profile()
    with patch(
        "astra.services.astro_service.build_full_chart_for_user",
        new_callable=AsyncMock,
        side_effect=RuntimeError("kerykeion сломался"),
    ):
        text = await build_portrait_text(AsyncMock(), _user(), profile)

    assert "посчитать не получилось" in text


@pytest.mark.anyio
async def test_build_portrait_text_asks_moon_bounds_only_when_uncertain(
    chart_no_time,
) -> None:
    uncertain = chart_no_time.model_copy(update={"moon_sign_uncertain": True})
    profile = _profile(birth_time=None)

    with (
        patch(
            "astra.services.astro_service.build_full_chart_for_user",
            new_callable=AsyncMock,
            return_value=uncertain,
        ),
        patch(
            "astra.services.astro_service.birth_coordinates",
            new_callable=AsyncMock,
            return_value=(55.75, 37.62, "Europe/Moscow"),
        ),
        patch(
            "astra.astro.calculator.moon_sign_bounds",
            return_value=("Овен", "Телец"),
        ) as bounds,
    ):
        text = await build_portrait_text(AsyncMock(), _user(), profile)

    bounds.assert_called_once()
    assert "Овен или Телец" in text


# ── Экраны: портрет и правка данных ─────────────────────────────────────────


@pytest.mark.anyio
async def test_profile_button_shows_portrait() -> None:
    from astra.telegram.handlers.menu import show_profile
    from astra.telegram.keyboards import profile_menu_keyboard

    message = AsyncMock()
    message.from_user.id = 42
    user = SimpleNamespace(points=1, streak_current=1, profile=_profile())

    with (
        patch(
            "astra.telegram.handlers.menu._get_user",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "astra.telegram.handlers.menu.build_portrait_text",
            new_callable=AsyncMock,
            return_value="портрет",
        ) as build,
    ):
        await show_profile(message, AsyncMock())

    build.assert_awaited_once()
    assert message.answer.await_args.args[0] == "портрет"
    assert message.answer.await_args.kwargs["reply_markup"] == profile_menu_keyboard()


@pytest.mark.anyio
async def test_edit_button_opens_field_screen() -> None:
    from astra.telegram.handlers.menu import cb_profile_edit
    from astra.telegram.keyboards import profile_edit_keyboard

    callback = AsyncMock()
    callback.from_user.id = 42
    callback.message = AsyncMock()
    user = SimpleNamespace(points=1, streak_current=1, profile=_profile())

    with patch(
        "astra.telegram.handlers.menu._get_user",
        new_callable=AsyncMock,
        return_value=user,
    ):
        await cb_profile_edit(callback, AsyncMock())

    text = callback.message.answer.await_args.args[0]
    assert text.startswith("✏️ Твои данные")
    assert callback.message.answer.await_args.kwargs["reply_markup"] == profile_edit_keyboard()


@pytest.mark.anyio
async def test_back_from_edit_returns_to_portrait() -> None:
    from astra.telegram.handlers.menu import cb_profile_back
    from astra.telegram.keyboards import profile_menu_keyboard

    callback = AsyncMock()
    callback.from_user.id = 42
    callback.message = AsyncMock()
    user = SimpleNamespace(points=1, streak_current=1, profile=_profile())

    with (
        patch(
            "astra.telegram.handlers.menu._get_user",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "astra.telegram.handlers.menu.build_portrait_text",
            new_callable=AsyncMock,
            return_value="портрет",
        ),
    ):
        await cb_profile_back(callback, AsyncMock())

    assert callback.message.answer.await_args.args[0] == "портрет"
    assert callback.message.answer.await_args.kwargs["reply_markup"] == profile_menu_keyboard()


def test_edit_screen_has_all_fields_and_way_back() -> None:
    from astra.telegram.button_texts import CB_PROFILE_BACK
    from astra.telegram.keyboards import profile_edit_keyboard

    rows = profile_edit_keyboard().inline_keyboard
    callbacks = [button.callback_data for row in rows for button in row]
    assert callbacks == [
        "profile:name",
        "profile:gender",
        "profile:date",
        "profile:time",
        "profile:place",
        "profile:notification_city",
        CB_PROFILE_BACK,
    ]


def test_portrait_screen_leads_to_paid_natal_report() -> None:
    from astra.telegram.button_texts import CB_PROFILE_EDIT, CB_PROFILE_NATAL
    from astra.telegram.keyboards import profile_menu_keyboard

    callbacks = [b.callback_data for row in profile_menu_keyboard().inline_keyboard for b in row]
    assert callbacks[0] == CB_PROFILE_NATAL
    assert CB_PROFILE_EDIT in callbacks
    # поля профиля с портрета уехали
    assert "profile:time" not in callbacks


@pytest.mark.anyio
async def test_saving_birth_time_shows_updated_portrait() -> None:
    """Смысл правки виден сразу: вписал время — получил асцендент и дома."""
    from astra.telegram.handlers.menu import save_birth_time

    message = AsyncMock()
    message.text = "14:30"
    message.from_user.id = 42
    user = SimpleNamespace(points=1, streak_current=1, profile=_profile(birth_time=None))

    with (
        patch(
            "astra.telegram.handlers.menu._get_user",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "astra.telegram.handlers.menu.users_crud.update_profile",
            new_callable=AsyncMock,
        ),
        patch(
            "astra.telegram.handlers.menu._send_portrait",
            new_callable=AsyncMock,
        ) as send_portrait,
    ):
        await save_birth_time(message, AsyncMock(), AsyncMock())

    assert "Время сохранено" in message.answer.await_args.args[0]
    send_portrait.assert_awaited_once()
