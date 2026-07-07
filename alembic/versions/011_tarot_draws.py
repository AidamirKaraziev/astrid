"""tarot_draws

Revision ID: 011
Revises: 010
Create Date: 2026-07-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tarot_draws",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("context_kind", sa.String(length=32), nullable=False),
        sa.Column("card_id", sa.String(length=32), nullable=False),
        sa.Column("reversed", sa.Boolean(), nullable=False),
        sa.Column("conflict_text", sa.Text(), nullable=True),
        sa.Column("interpretation", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", "context_kind", name="uq_tarot_draw_user_date_kind"),
    )
    op.create_index("ix_tarot_draws_user_id", "tarot_draws", ["user_id"])
    op.create_index("ix_tarot_draws_date", "tarot_draws", ["date"])


def downgrade() -> None:
    op.drop_index("ix_tarot_draws_date", table_name="tarot_draws")
    op.drop_index("ix_tarot_draws_user_id", table_name="tarot_draws")
    op.drop_table("tarot_draws")
