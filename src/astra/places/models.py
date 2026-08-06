import uuid
from decimal import Decimal

from sqlalchemy import BigInteger, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from astra.db.base import Base, TimestampMixin


class Place(Base, TimestampMixin):
    """Населённый пункт РФ (GeoNames). Координаты и TZ — для астрологии и рассылки."""

    __tablename__ = "places"
    __table_args__ = (Index("ix_places_country_population", "country_code", "population"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    geoname_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    name_normalized: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(512))
    search_text: Mapped[str] = mapped_column(Text)
    # Латинский ключ: «Зябриково» и `Zyabrikovo` дают одно и то же значение.
    # У четверти мест СНГ русского имени в источнике нет вовсе, и найти их по
    # русскому запросу можно только так (astra.places.translit).
    name_latin: Mapped[str] = mapped_column(String(255), default="")
    search_latin: Mapped[str] = mapped_column(Text, default="")
    # Имена места через разделитель: «|санкт-петербург|ленинград|питер|».
    # По нему ищется целое бывшее название, а не слово внутри чужого имени.
    search_names: Mapped[str] = mapped_column(Text, default="")
    # Ориентир для тёзок: «Горка · 12 км от Устюжны». Район в GeoNames
    # заполнен у 1,3% записей, поэтому третий уровень адреса считаем сами.
    nearest_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nearest_city_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), default="RU")
    country_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    admin1_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    admin1_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feature_code: Mapped[str] = mapped_column(String(10))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    timezone: Mapped[str] = mapped_column(String(64))
    population: Mapped[int] = mapped_column(Integer, default=0)
