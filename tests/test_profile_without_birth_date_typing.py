"""Профиль без даты рождения: время рождения без даты — 422, а не 500.

После короткого онбординга профиль заводится без даты, времени и места.
PATCH с одним `birth_time` звал `datetime.combine(None, …)` и падал 500.
"""

from contextlib import asynccontextmanager
from datetime import date, datetime

import pytest

from astra.astro.birth_time import BirthDateMissingError, require_birth_date
from astra.users import crud as users_crud
from astra.users.models import Profile

from conftest import new_test_telegram_id


async def _profile_without_birth_date(session) -> Profile:
    user = await users_crud.create_user(
        session,
        telegram_id=new_test_telegram_id(),
        username=None,
        language_code="ru",
    )
    profile = Profile(user_id=user.id, display_name="Без даты", city="Москва")
    session.add(profile)
    await session.flush()
    assert profile.birth_date is None
    return profile


@asynccontextmanager
async def _client_on(db_session):
    """API на той же сессии, что и тест."""
    from httpx import ASGITransport, AsyncClient

    from astra.db.session import get_session
    from astra.main import create_app

    app = create_app(with_lifespan=False)

    async def _session():
        yield db_session

    app.dependency_overrides[get_session] = _session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.anyio
async def test_birth_time_without_birth_date_is_422(db_session) -> None:
    profile = await _profile_without_birth_date(db_session)

    async with _client_on(db_session) as client:
        response = await client.patch(
            f"/v1/users/me/{profile.user_id}/profile",
            json={"birth_time": "14:30:00"},
        )

    assert response.status_code == 422
    assert "дат" in response.json()["detail"].lower()
    await db_session.refresh(profile)
    assert profile.birth_time is None
    await db_session.rollback()


@pytest.mark.anyio
async def test_birth_time_with_birth_date_in_same_request_is_saved(
    db_session,
) -> None:
    profile = await _profile_without_birth_date(db_session)

    async with _client_on(db_session) as client:
        response = await client.patch(
            f"/v1/users/me/{profile.user_id}/profile",
            json={"birth_date": "1990-03-15", "birth_time": "14:30:00"},
        )

    assert response.status_code == 200
    await db_session.refresh(profile)
    assert profile.birth_time == datetime(1990, 3, 15, 14, 30)
    await db_session.rollback()


def test_require_birth_date_explains_instead_of_failing_deep_in_the_calculation() -> None:
    assert require_birth_date(date(1990, 3, 15)) == date(1990, 3, 15)
    with pytest.raises(BirthDateMissingError, match="Дата рождения"):
        require_birth_date(None)
