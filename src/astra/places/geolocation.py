"""Определение населённого пункта по координатам (ближайший в справочнике GeoNames)."""

import math

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.places.models import Place

EARTH_RADIUS_KM = 6371.0


def _bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Приближённый bbox для предфильтрации в БД."""
    delta_lat = radius_km / 111.0
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    delta_lon = radius_km / (111.0 * cos_lat)
    return (
        lat - delta_lat,
        lat + delta_lat,
        lon - delta_lon,
        lon + delta_lon,
    )


def _distance_km_expression(lat: float, lon: float):
    lat_r = func.radians(lat)
    lon_r = func.radians(lon)
    plat = func.radians(cast(Place.latitude, Float))
    plon = func.radians(cast(Place.longitude, Float))
    cos_angle = (
        func.cos(lat_r) * func.cos(plat) * func.cos(plon - lon_r)
        + func.sin(lat_r) * func.sin(plat)
    )
    clamped = func.least(1.0, func.greatest(-1.0, cos_angle))
    return EARTH_RADIUS_KM * func.acos(clamped)


async def find_nearest_places(
    session: AsyncSession,
    latitude: float,
    longitude: float,
    *,
    limit: int = 5,
    max_distance_km: float = 80.0,
    country_code: str = "RU",
) -> list[tuple[Place, float]]:
    """
    Ближайшие населённые пункты из нашей БД.
    Возвращает [(Place, distance_km), ...].
    """
    min_lat, max_lat, min_lon, max_lon = _bounding_box(latitude, longitude, max_distance_km)
    distance_km = _distance_km_expression(latitude, longitude).label("distance_km")

    stmt = (
        select(Place, distance_km)
        .where(
            Place.country_code == country_code,
            cast(Place.latitude, Float) >= min_lat,
            cast(Place.latitude, Float) <= max_lat,
            cast(Place.longitude, Float) >= min_lon,
            cast(Place.longitude, Float) <= max_lon,
        )
        .order_by(distance_km)
        .limit(limit * 3)
    )
    result = await session.execute(stmt)
    rows = result.all()

    places: list[tuple[Place, float]] = []
    for place, dist in rows:
        dist_f = float(dist)
        if dist_f <= max_distance_km:
            places.append((place, dist_f))
        if len(places) >= limit:
            break
    return places
