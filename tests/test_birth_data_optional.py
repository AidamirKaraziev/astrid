"""Профиль без астроданных: человек в базе есть, даты рождения нет.

Короткий онбординг спрашивает имя и пол, поэтому профиль без даты рождения —
не сбой, а нормальное состояние. Здесь проверяется, что оно нигде не роняет
бота и что продукты честно говорят, чего им не хватает.

Отдельно проверяется ежедневная рассылка: предсказание строится от знака
Солнца, и человек без даты рождения не должен ни получать пустое
предсказание, ни ронять обход всех пользователей.
"""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from astra.telegram.birth_data_gate import ensure_birth_data, missing_data_text
from astra.telegram.profile_portrait import format_portrait_card
from astra.telegram.profile_text import format_profile_card
from astra.users.birth_data import (
    BirthField,
    Product,
    blocked_by,
    has_birth_data,
    missing_for,
)
from astra.users.getters import calculate_profile_accuracy


def _profile(**kwargs: object) -> SimpleNamespace:
    """Профиль сразу после короткого онбординга: имя и пол, больше ничего."""
    defaults: dict[str, object] = {
        "id": uuid4(),
        "display_name": "Анна",
        "gender": "женщина",
        "birth_date": None,
        "birth_time": None,
        "birth_place": None,
        "birth_place_id": None,
        "notification_place_id": None,
        "city": "не указан",
        "timezone": "Europe/Moscow",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _full_profile(**kwargs: object) -> SimpleNamespace:
    filled: dict[str, object] = {
        "birth_date": date(1990, 6, 15),
        "birth_time": datetime(1990, 6, 15, 14, 30),
        "birth_place": "Москва, Россия",
        "birth_place_id": uuid4(),
    }
    filled.update(kwargs)
    return _profile(**filled)


def _user() -> SimpleNamespace:
    return SimpleNamespace(points=0, streak_current=0)


# ── Что кому нужно ──────────────────────────────────────────────────────────


def test_empty_profile_blocks_every_product_that_needs_date() -> None:
    profile = _profile()
    for product in Product:
        assert BirthField.DATE in blocked_by(product, profile), product


def test_full_profile_blocks_nothing() -> None:
    profile = _full_profile()
    for product in Product:
        assert blocked_by(product, profile) == (), product


def test_missing_time_does_not_block_natal_but_is_asked() -> None:
    """Время необязательно: без него карта считается на полдень."""
    profile = _full_profile(birth_time=None)
    assert blocked_by(Product.NATAL_REPORT, profile) == ()
    assert missing_for(Product.NATAL_REPORT, profile) == (BirthField.TIME,)


def test_missing_place_blocks_natal() -> None:
    """Место обязательно: без него дома считались бы от Москвы — это неправда."""
    profile = _full_profile(birth_place_id=None)
    assert blocked_by(Product.NATAL_REPORT, profile) == (BirthField.PLACE,)


def test_place_written_by_hand_does_not_count() -> None:
    """Текст без ссылки на справочник координат не даёт."""
    profile = _full_profile(birth_place_id=None, birth_place="Череповец")
    assert BirthField.PLACE in blocked_by(Product.NATAL_REPORT, profile)


def test_missing_for_asks_required_before_optional() -> None:
    order = missing_for(Product.NATAL_REPORT, _profile())
    assert order.index(BirthField.DATE) < order.index(BirthField.TIME)


def test_no_profile_at_all_needs_everything() -> None:
    assert blocked_by(Product.NATAL_REPORT, None) == (BirthField.DATE, BirthField.PLACE)
    assert has_birth_data(None) is False


# ── Что видит человек ───────────────────────────────────────────────────────


def test_profile_card_survives_empty_date() -> None:
    card = format_profile_card(_user(), _profile())
    assert "Анна" in card
    assert "Дата рождения пока не указана" in card


def test_portrait_says_what_is_needed_not_that_it_broke() -> None:
    """«Загляни позже» здесь было бы враньём: ждут не бота, а человека."""
    card = format_portrait_card(_user(), _profile(), None, has_birth_coords=False)
    assert "нужна дата рождения" in card
    assert "посчитать не получилось" not in card


def test_portrait_without_date_does_not_nag_about_time_and_place() -> None:
    card = format_portrait_card(_user(), _profile(), None, has_birth_coords=False)
    assert "время рождения" not in card.lower()


def test_accuracy_is_zero_without_date() -> None:
    percent, hint = calculate_profile_accuracy(_profile())
    assert percent == 0
    assert "дату рождения" in hint


def test_missing_data_text_lists_everything_at_once() -> None:
    text = missing_data_text(
        Product.NATAL_REPORT,
        (BirthField.DATE, BirthField.PLACE),
    )
    assert "дата и место рождения" in text  # слово «рождения» не повторяется трижды


@pytest.mark.asyncio
async def test_gate_stops_product_and_explains() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    allowed = await ensure_birth_data(message, Product.NATAL_REPORT, _profile())
    assert allowed is False
    message.answer.assert_awaited_once()
    assert "дата рождения" in message.answer.await_args.args[0].replace(" и место", "")


@pytest.mark.asyncio
async def test_daily_prediction_skips_user_without_birth_date() -> None:
    """Обход рассылки не должен ни падать, ни слать предсказание в пустоту."""
    from astra.notifications import scheduler

    user = SimpleNamespace(id=uuid4(), profile=_profile())
    rows = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [user]))
    session = SimpleNamespace(execute=AsyncMock(return_value=rows))

    with (
        patch.object(scheduler, "_is_notification_due", return_value=True),
        patch.object(scheduler, "enqueue_prediction_pipeline", new=AsyncMock()) as enqueue,
    ):
        enqueued = await scheduler.process_scheduled_notifications(session, None)

    assert enqueued == 0
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_gate_lets_full_profile_through_silently() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    allowed = await ensure_birth_data(message, Product.NATAL_REPORT, _full_profile())
    assert allowed is True
    message.answer.assert_not_awaited()
