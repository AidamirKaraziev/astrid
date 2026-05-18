from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PlaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    geoname_id: int
    display_name: str
    name: str
    admin1_name: str | None
    latitude: Decimal
    longitude: Decimal
    timezone: str
    population: int


class PlaceSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    latitude: Decimal
    longitude: Decimal
