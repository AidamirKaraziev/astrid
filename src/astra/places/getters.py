from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from astra.places import crud
from astra.places.schemas import PlaceRead


def format_place_confirm(place: PlaceRead) -> str:
    lat = float(place.latitude)
    lon = float(place.longitude)
    lat_s = f"{abs(lat):.2f}°{'N' if lat >= 0 else 'S'}"
    lon_s = f"{abs(lon):.2f}°{'E' if lon >= 0 else 'W'}"
    return (
        f"<b>{place.display_name}</b>\n"
        f"📍 {lat_s}, {lon_s}\n"
        f"🕐 Часовой пояс: <code>{place.timezone}</code>"
    )


async def get_place_read(session: AsyncSession, place_id: UUID) -> PlaceRead | None:
    row = await crud.get_place_by_id(session, place_id)
    if row is None:
        return None
    return PlaceRead.model_validate(row)
