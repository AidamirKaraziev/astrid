"""Карта дня: прогноз по кнопке в tarot_draws

Revision ID: 017
Revises: 016
Create Date: 2026-07-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tarot_draws", sa.Column("forecast", sa.Text(), nullable=True))
    op.add_column(
        "tarot_draws",
        sa.Column("forecast_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tarot_draws", "forecast_sent_at")
    op.drop_column("tarot_draws", "forecast")
