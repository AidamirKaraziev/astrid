from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from astra.compatibility import crud as compatibility_crud
from astra.telegram.button_texts import (
    CB_PEOPLE_CARD_PREFIX,
    CB_PEOPLE_DELETE_CANCEL_PREFIX,
    CB_PEOPLE_DELETE_CONFIRM_PREFIX,
    CB_PEOPLE_EDIT_PREFIX,
    CB_PEOPLE_LIST,
    CB_PERSON_PICK_PREFIX,
)
from astra.telegram.handlers.people import format_people_card
from astra.telegram.keyboards_people import (
    CB_PEOPLE_GENDER_PREFIX,
    people_card_keyboard,
    people_delete_confirm_keyboard,
    people_gender_keyboard,
    people_list_keyboard,
    person_pick_keyboard,
)


def _profile(**overrides):
    base = dict(
        id=uuid4(),
        label="Анжела",
        gender="женщина",
        birth_date=date(1995, 6, 20),
        birth_time=datetime(1995, 6, 20, 14, 30, tzinfo=timezone.utc),
        birth_place="Москва, Россия",
        birth_place_id=uuid4(),
        timezone="Europe/Moscow",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_person_pick_keyboard_callback_and_label() -> None:
    profile = _profile()
    keyboard = person_pick_keyboard([profile])
    button = keyboard.inline_keyboard[0][0]
    assert button.callback_data == f"{CB_PERSON_PICK_PREFIX}{profile.id}"
    assert "Анжела" in button.text
    assert "20.06.1995" in button.text


def test_people_list_keyboard_has_back_button() -> None:
    profile = _profile()
    keyboard = people_list_keyboard([profile])
    assert keyboard.inline_keyboard[0][0].callback_data == f"{CB_PEOPLE_CARD_PREFIX}{profile.id}"
    assert keyboard.inline_keyboard[-1][0].callback_data == "profile:back"


def test_people_card_keyboard_callbacks() -> None:
    pid = "00000000-0000-0000-0000-000000000042"
    keyboard = people_card_keyboard(pid)
    flat = [btn for row in keyboard.inline_keyboard for btn in row]
    callbacks = {btn.callback_data for btn in flat}
    assert f"{CB_PEOPLE_EDIT_PREFIX}name:{pid}" in callbacks
    assert f"{CB_PEOPLE_EDIT_PREFIX}gender:{pid}" in callbacks
    assert f"{CB_PEOPLE_EDIT_PREFIX}date:{pid}" in callbacks
    assert f"{CB_PEOPLE_EDIT_PREFIX}time:{pid}" in callbacks
    assert f"{CB_PEOPLE_EDIT_PREFIX}place:{pid}" in callbacks
    assert f"people:del:{pid}" in callbacks
    assert CB_PEOPLE_LIST in callbacks


def test_people_gender_keyboard_callbacks() -> None:
    pid = "00000000-0000-0000-0000-000000000042"
    keyboard = people_gender_keyboard(pid)
    row = keyboard.inline_keyboard[0]
    assert row[0].callback_data == f"{CB_PEOPLE_GENDER_PREFIX}male:{pid}"
    assert row[1].callback_data == f"{CB_PEOPLE_GENDER_PREFIX}female:{pid}"


def test_people_delete_confirm_keyboard_callbacks() -> None:
    pid = "00000000-0000-0000-0000-000000000042"
    keyboard = people_delete_confirm_keyboard(pid)
    row = keyboard.inline_keyboard[0]
    assert row[0].callback_data == f"{CB_PEOPLE_DELETE_CONFIRM_PREFIX}{pid}"
    assert row[1].callback_data == f"{CB_PEOPLE_DELETE_CANCEL_PREFIX}{pid}"


def test_format_people_card_full() -> None:
    text = format_people_card(_profile())
    assert "👤 <b>Анжела</b>" in text
    assert "👩 Женщина" in text
    assert "📅 20.06.1995" in text
    assert "🕐 18:30" in text  # 14:30 UTC → Europe/Moscow (лето 1995 = +4)
    assert "📍 Москва" in text


def test_format_people_card_missing_optional_fields() -> None:
    profile = _profile(gender=None, birth_time=None, birth_place="")
    text = format_people_card(profile)
    assert "пол не указан" in text
    assert "время не указано" in text
    assert "место не указано" in text


@pytest.mark.asyncio
async def test_update_natal_profile_resets_chart_on_birth_change() -> None:
    profile = MagicMock()
    profile.chart_data = {"cached": True}
    session = AsyncMock()
    await compatibility_crud.update_natal_profile(
        session,
        profile,
        birth_date=date(2000, 1, 1),
    )
    assert profile.birth_date == date(2000, 1, 1)
    assert profile.chart_data is None
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_natal_profile_keeps_chart_on_label_change() -> None:
    profile = MagicMock()
    profile.chart_data = {"cached": True}
    session = AsyncMock()
    await compatibility_crud.update_natal_profile(session, profile, label="Новое имя")
    assert profile.label == "Новое имя"
    assert profile.chart_data == {"cached": True}


@pytest.mark.asyncio
async def test_delete_natal_profile_scopes_by_owner() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.rowcount = 1
    session.execute.return_value = result
    ok = await compatibility_crud.delete_natal_profile(session, uuid4(), uuid4())
    assert ok is True
    session.flush.assert_awaited_once()


def test_normalize_profile_label_collapses_case_and_space() -> None:
    n = compatibility_crud.normalize_profile_label
    assert n("Анжела") == n("анжела") == n("  Анжела  ") == n("АНЖЕЛА")
    # ник и транслит остаются разными — безопасно не сливаем
    assert n("анж") != n("анжела")
    assert n("Anzhela") != n("анжела")


@pytest.mark.asyncio
async def test_find_by_identity_matches_case_variant_same_date() -> None:
    owner = uuid4()
    existing = _profile(label="Анжела", birth_date=date(2001, 12, 2))
    result = MagicMock()
    result.scalars.return_value.all.return_value = [existing]
    session = AsyncMock()
    session.execute.return_value = result

    found = await compatibility_crud.find_natal_profile_by_identity(
        session, owner, "  анжела ", date(2001, 12, 2),
    )
    assert found is existing


@pytest.mark.asyncio
async def test_upsert_updates_case_variant_instead_of_duplicating() -> None:
    owner = uuid4()
    existing = _profile(label="Анжела", birth_date=date(2001, 12, 2), gender=None)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [existing]
    session = AsyncMock()
    session.execute.return_value = result

    row = await compatibility_crud.upsert_natal_profile(
        session,
        owner_user_id=owner,
        label="анжела",
        gender="женщина",
        birth_date=date(2001, 12, 2),
        birth_time=None,
        birth_place="Москва",
        birth_place_id=None,
        timezone="Europe/Moscow",
    )
    # обновили существующий, а не создали новый
    assert row is existing
    assert existing.gender == "женщина"
    session.add.assert_not_called()
