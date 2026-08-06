"""Проводка сессии БД: то, на чём молча умирает всё приложение.

Здесь нет бизнес-логики — только контракт «сессию можно открыть». Один
символ в `get_session` (`factory` вместо `factory()`) уронил все ручки
FastAPI в 500, и ни один из восьми сотен тестов этого не заметил, потому что
сессию везде подменял `AsyncMock`.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("db_engine")


async def test_get_session_yields_working_session() -> None:
    """Зависимость FastAPI отдаёт живую сессию, а не падает на входе."""
    from astra.db.session import get_session

    gen = get_session()
    session = await gen.__anext__()
    assert isinstance(session, AsyncSession)
    assert (await session.execute(text("select 1"))).scalar_one() == 1

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


async def test_get_session_rolls_back_on_error() -> None:
    """Исключение в ручке не оставляет полузаписанную транзакцию."""
    from astra.db.session import get_session

    gen = get_session()
    session = await gen.__anext__()
    await session.execute(text("select 1"))

    boom = RuntimeError("ручка упала")
    with pytest.raises(RuntimeError):
        await gen.athrow(boom)
    assert not session.in_transaction()


async def test_session_factory_opens_session() -> None:
    """Фабрику зовут со скобками — на ней держатся бот и воркер."""
    from astra.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        assert (await session.execute(text("select 1"))).scalar_one() == 1


async def test_api_route_with_db_dependency_does_not_500(api_client) -> None:
    """Живая ручка на `Depends(get_session)`: 404 — это ответ, 500 — поломка.

    Канарейка на весь класс ошибок: если зависимость сессии сломана, здесь
    будет 500 задолго до того, как это увидит человек в админке.
    """
    response = await api_client.get(f"/v1/users/me/{uuid4()}")
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "User not found"
