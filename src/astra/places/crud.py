from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.places.models import Place
from astra.places.normalize import normalize_place_query

# Административные центры — выше в выдаче при нечётком запросе
_PRIORITY_FEATURES = ("PPLC", "PPLA", "PPLA2", "PPLA3", "PPLA4")


async def get_place_by_id(session: AsyncSession, place_id: UUID) -> Place | None:
    result = await session.execute(select(Place).where(Place.id == place_id))
    return result.scalar_one_or_none()


async def get_place_by_geoname_id(session: AsyncSession, geoname_id: int) -> Place | None:
    result = await session.execute(select(Place).where(Place.geoname_id == geoname_id))
    return result.scalar_one_or_none()


async def search_places(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 5,
    country_code: str = "RU",
) -> list[Place]:
    """
    Поиск по name_normalized и search_text (pg_trgm).
    Приоритет: точное совпадение имени → крупный город → схожесть.
    """
    normalized = normalize_place_query(query)
    if len(normalized) < 2:
        return []

    name_similarity = func.similarity(Place.name_normalized, normalized)
    text_similarity = func.similarity(Place.search_text, normalized)

    exact_name = case((Place.name_normalized == normalized, 1), else_=0)
    is_admin_center = case(
        (Place.feature_code.in_(_PRIORITY_FEATURES), 1),
        else_=0,
    )

    stmt = (
        select(Place)
        .where(
            Place.country_code == country_code,
            or_(
                Place.name_normalized.op("%")(normalized),
                Place.search_text.op("%")(normalized),
            ),
        )
        .order_by(
            exact_name.desc(),
            is_admin_center.desc(),
            Place.population.desc(),
            name_similarity.desc(),
            text_similarity.desc(),
        )
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_places(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(Place))
    return int(result.scalar_one())
