"""places catalog and profile place FKs

Revision ID: 002
Revises: 001
Create Date: 2026-05-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "places",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("geoname_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_normalized", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False, server_default="RU"),
        sa.Column("admin1_code", sa.String(length=10), nullable=True),
        sa.Column("admin1_name", sa.String(length=128), nullable=True),
        sa.Column("feature_code", sa.String(length=10), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("population", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("geoname_id"),
    )
    op.create_index("ix_places_geoname_id", "places", ["geoname_id"])
    op.create_index("ix_places_name_normalized", "places", ["name_normalized"])
    op.create_index("ix_places_country_population", "places", ["country_code", "population"])
    op.execute(
        """
        CREATE INDEX ix_places_name_normalized_trgm
        ON places USING gin (name_normalized gin_trgm_ops)
        """
    )

    op.add_column("profiles", sa.Column("birth_place_id", sa.UUID(), nullable=True))
    op.add_column("profiles", sa.Column("notification_place_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_profiles_birth_place_id",
        "profiles",
        "places",
        ["birth_place_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_profiles_notification_place_id",
        "profiles",
        "places",
        ["notification_place_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_profiles_notification_place_id", "profiles", type_="foreignkey")
    op.drop_constraint("fk_profiles_birth_place_id", "profiles", type_="foreignkey")
    op.drop_column("profiles", "notification_place_id")
    op.drop_column("profiles", "birth_place_id")
    op.drop_table("places")
