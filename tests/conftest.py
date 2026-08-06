import os
import random
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

# Defaults for tests without real Telegram/DB when only hitting /health
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0000000000:TEST_TOKEN_FOR_TESTS")
os.environ.setdefault("TELEGRAM_BOT_USERNAME", "TestAstraBot")
os.environ.setdefault("TELEGRAM_MODE", "polling")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://astra:astra@localhost:5432/astra",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

# Регистрируем все ORM-модели, как это делает init_engine на старте приложения:
# создание любой mapped-модели настраивает мапперы целиком, и без полного
# реестра ссылки в relationship («NatalChart») не резолвятся.
import astra.db.models_registry  # noqa: E402,F401


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def api_client() -> AsyncClient:
    from astra.main import create_app

    app = create_app(with_lifespan=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# --------------------------------------------------------------------------
# Настоящие Postgres и Redis для интеграционных тестов
#
# Регистрация ломалась в слое БД (сессия, ленивая подгрузка профиля), а все
# тесты работали с `AsyncMock` — и потому были зелёными. Поэтому воронка
# «/start → онбординг» проверяется на живой базе, без подмены сессии.
# --------------------------------------------------------------------------

# Диапазон telegram_id, зарезервированный за тестами: настоящие id сейчас
# меньше 8·10⁹, так что в чужие данные мы не попадём даже на dev-базе.
TEST_TELEGRAM_ID_MIN = 9_000_000_000
TEST_TELEGRAM_ID_MAX = 9_999_999_999

_infra_status: dict[str, str | None] = {}


def new_test_telegram_id() -> int:
    return random.randrange(TEST_TELEGRAM_ID_MIN, TEST_TELEGRAM_ID_MAX)


async def _infra_problem() -> str | None:
    """None — инфраструктура на месте; иначе текст проблемы."""
    if "problem" in _infra_status:
        return _infra_status["problem"]

    problem: str | None = None
    from astra.core.config import get_settings

    settings = get_settings()
    try:
        import asyncpg

        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn, timeout=5)
        try:
            await conn.fetchval("select count(*) from users")
        finally:
            await conn.close()
    except Exception as exc:
        problem = f"Postgres недоступен ({type(exc).__name__}: {exc})"

    if problem is None:
        try:
            from redis.asyncio import Redis

            client = Redis.from_url(settings.redis_url, socket_connect_timeout=3)
            try:
                await client.ping()
            finally:
                await client.aclose()
        except Exception as exc:
            problem = f"Redis недоступен ({type(exc).__name__}: {exc})"

    _infra_status["problem"] = problem
    return problem


@pytest.fixture
async def live_infra() -> None:
    """Гарантия, что тест реально прогнался, а не тихо пропустился.

    Локально без `make infra` тест пропускается с понятной подсказкой; в CI
    (переменная `CI`) — падает: молча пропущенный тест регистрации ничем не
    лучше отсутствующего.
    """
    problem = await _infra_problem()
    if problem is None:
        return
    hint = "подними инфраструктуру: make infra && uv run alembic upgrade head"
    if os.getenv("CI"):
        pytest.fail(f"{problem}. В CI это ошибка, а не повод пропустить тест.")
    pytest.skip(f"{problem}. {hint}")


@pytest.fixture
async def db_engine(live_infra: None) -> AsyncIterator[object]:
    """Боевой движок на живой базе; поднимается заново на каждый тест.

    Свой движок на тест, потому что pytest-asyncio даёт каждому тесту свой
    event loop, а пул asyncpg к чужому циклу не привязывается.
    """
    from astra.core.config import get_settings
    from astra.db import session as db_session

    # debug=False — иначе echo движка топит вывод упавшего теста в SQL.
    engine = db_session.init_engine(get_settings().model_copy(update={"debug": False}))
    try:
        yield engine
    finally:
        await engine.dispose()
        db_session._engine = None
        db_session.async_session_factory = None


@pytest.fixture
async def session_factory(db_engine: object):
    from astra.db.session import get_session_factory

    return get_session_factory()


@pytest.fixture
async def db_session(session_factory) -> AsyncIterator[object]:
    """Отдельная сессия для подготовки данных и проверок в тестах."""
    async with session_factory() as session:
        yield session


# Городов хватает ровно на онбординг. Настоящий справочник — 200 тысяч строк
# из GeoNames; качать его в CI нельзя (минуты и внешняя сеть), а без единого
# города онбординг обрывается на выборе места рождения.
_SEED_PLACES = (
    {
        "geoname_id": 990_000_001,
        "name": "Москва",
        "name_normalized": "москва",
        "display_name": "Москва, Россия",
        "search_text": "москва moskva moscow",
        "admin1_code": "48",
        "admin1_name": "Москва",
        "feature_code": "PPLC",
        "latitude": Decimal("55.755826"),
        "longitude": Decimal("37.617300"),
        "timezone": "Europe/Moscow",
        "population": 10_381_222,
    },
    {
        "geoname_id": 990_000_002,
        "name": "Санкт-Петербург",
        "name_normalized": "санкт-петербург",
        "display_name": "Санкт-Петербург, Россия",
        "search_text": "санкт-петербург sankt-peterburg saint petersburg питер",
        "admin1_code": "66",
        "admin1_name": "Санкт-Петербург",
        "feature_code": "PPLA",
        "latitude": Decimal("59.939039"),
        "longitude": Decimal("30.315785"),
        "timezone": "Europe/Moscow",
        "population": 5_351_935,
    },
    {
        "geoname_id": 990_000_003,
        "name": "Владивосток",
        "name_normalized": "владивосток",
        "display_name": "Владивосток, Приморский край, Россия",
        "search_text": "владивосток vladivostok приморский край",
        "admin1_code": "59",
        "admin1_name": "Приморский край",
        "feature_code": "PPLA",
        "latitude": Decimal("43.116667"),
        "longitude": Decimal("131.900000"),
        "timezone": "Asia/Vladivostok",
        "population": 604_901,
    },
)


@pytest.fixture
async def places_catalog(session_factory) -> AsyncIterator[None]:
    """Справочник городов, на котором можно пройти онбординг.

    На машине разработчика справочник уже импортирован — тогда ничего не
    трогаем и проверяем на настоящих данных. На пустой базе (CI) досеиваем
    несколько городов вместо похода в GeoNames.
    """
    from sqlalchemy import delete, func, select

    from astra.places.models import Place

    async with session_factory() as session:
        already = (await session.execute(select(func.count()).select_from(Place))).scalar_one()
        if already:
            yield
            return

        for row in _SEED_PLACES:
            session.add(Place(country_code="RU", **row))
        await session.commit()

    try:
        yield
    finally:
        async with session_factory() as session:
            await session.execute(
                delete(Place).where(
                    Place.geoname_id.in_([row["geoname_id"] for row in _SEED_PLACES]),
                ),
            )
            await session.commit()


@pytest.fixture
async def full_catalog(session_factory, places_catalog) -> None:
    """Тест требует настоящий справочник, а не три засеянных города.

    Приёмка на контрольном списке городов возможна только на полном
    справочнике. В CI его нет осознанно: качать 200 МБ GeoNames на каждый
    прогон незачем, и та же проверка выполняется при импорте
    (`scripts/import_geonames.py` падает, если хоть один город не находится).
    """
    from astra.places.crud import count_places

    async with session_factory() as session:
        total = await count_places(session)
    if total < 100_000:
        pytest.skip(
            f"в справочнике {total} мест: приёмка на контрольном списке идёт "
            "при импорте, а не здесь (uv run python scripts/import_geonames.py)",
        )


@pytest.fixture
async def purge_test_users(session_factory) -> AsyncIterator[None]:
    """Чистит тестовый диапазон telegram_id до и после теста.

    До — чтобы упавший прогон не отравил следующий; после — чтобы dev-база не
    зарастала. Всё связанное с пользователем удаляется каскадом.
    """
    from sqlalchemy import text

    async def sweep() -> None:
        async with session_factory() as session:
            await session.execute(
                text("delete from users where telegram_id between :lo and :hi"),
                {"lo": TEST_TELEGRAM_ID_MIN, "hi": TEST_TELEGRAM_ID_MAX},
            )
            await session.commit()

    await sweep()
    try:
        yield
    finally:
        await sweep()
