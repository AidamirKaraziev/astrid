"""zodiac_daily_horoscopes

Revision ID: 010
Revises: 009
Create Date: 2026-07-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "zodiac_daily_horoscopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sign", sa.String(length=32), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("moon_note", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sign", "date", name="uq_zodiac_daily_sign_date"),
    )
    op.create_index("ix_zodiac_daily_horoscopes_sign", "zodiac_daily_horoscopes", ["sign"])
    op.create_index("ix_zodiac_daily_horoscopes_date", "zodiac_daily_horoscopes", ["date"])


def downgrade() -> None:
    op.drop_index("ix_zodiac_daily_horoscopes_date", table_name="zodiac_daily_horoscopes")
    op.drop_index("ix_zodiac_daily_horoscopes_sign", table_name="zodiac_daily_horoscopes")
    op.drop_table("zodiac_daily_horoscopes")
