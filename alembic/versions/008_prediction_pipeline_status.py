"""predictions.status and nullable text for pipeline drafts

Revision ID: 008
Revises: 007
Create Date: 2026-07-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="text_ready",
        ),
    )
    op.alter_column("predictions", "text", existing_type=sa.Text(), nullable=True)

    op.execute(
        sa.text(
            "UPDATE predictions SET status = 'sent' WHERE sent_at IS NOT NULL",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE predictions SET status = 'text_ready' "
            "WHERE sent_at IS NULL AND text IS NOT NULL",
        ),
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE predictions SET text = '' WHERE text IS NULL"))
    op.alter_column("predictions", "text", existing_type=sa.Text(), nullable=False)
    op.drop_column("predictions", "status")
