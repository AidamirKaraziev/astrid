"""Справочник СНГ: ориентир для тёзок и поиск независимо от алфавита

Только добавление колонок и индексов. Существующие колонки не трогаем: из
справочника читают ещё девять модулей (совместимость, натал, профиль,
астро-расчёт), и переименование любой из них уронило бы их все.

Данные наполняет импортёр (`astra.places.geonames_import`), миграция готовит
под них место.

Revision ID: 028
Revises: 027
Create Date: 2026-08-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Латинский ключ: и «Зябриково», и `Zyabrikovo` приводятся к `zyabrikovo`.
    # Без него четверть мест СНГ, у которых русского имени в источнике нет,
    # не находится по русскому запросу.
    op.add_column(
        "places",
        sa.Column("name_latin", sa.String(255), nullable=False, server_default=""),
    )
    op.add_column(
        "places",
        sa.Column("search_latin", sa.Text(), nullable=False, server_default=""),
    )
    # Ориентир для различения тёзок: «Горка · 12 км от Устюжны». Района в
    # GeoNames нет у 98,7% записей, поэтому третий уровень адреса считаем сами.
    op.add_column("places", sa.Column("nearest_city", sa.String(255), nullable=True))
    op.add_column("places", sa.Column("nearest_city_km", sa.Integer(), nullable=True))
    # Страна словами: справочник перестал быть только российским.
    op.add_column("places", sa.Column("country_name", sa.String(64), nullable=True))

    op.execute("UPDATE places SET country_name = 'Россия' WHERE country_code = 'RU'")

    op.create_index(
        "ix_places_name_latin_trgm",
        "places",
        ["name_latin"],
        postgresql_using="gin",
        postgresql_ops={"name_latin": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_places_search_latin_trgm",
        "places",
        ["search_latin"],
        postgresql_using="gin",
        postgresql_ops={"search_latin": "gin_trgm_ops"},
    )
    # Точное совпадение имени внутри страны — первая ступень ранжирования,
    # она обязана быть мгновенной: по ней проходит каждый запрос.
    op.create_index(
        "ix_places_country_name_latin",
        "places",
        ["country_code", "name_latin"],
    )


def downgrade() -> None:
    op.drop_index("ix_places_country_name_latin", table_name="places")
    op.drop_index("ix_places_search_latin_trgm", table_name="places")
    op.drop_index("ix_places_name_latin_trgm", table_name="places")
    op.drop_column("places", "country_name")
    op.drop_column("places", "nearest_city_km")
    op.drop_column("places", "nearest_city")
    op.drop_column("places", "search_latin")
    op.drop_column("places", "name_latin")
