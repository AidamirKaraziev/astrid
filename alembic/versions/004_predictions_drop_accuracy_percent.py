"""predictions: drop accuracy_percent, text stores body only

Revision ID: 004
Revises: 003
Create Date: 2026-05-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("predictions", "accuracy_percent")


def downgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("accuracy_percent", sa.Integer(), nullable=False, server_default="33"),
    )
    op.alter_column("predictions", "accuracy_percent", server_default=None)
