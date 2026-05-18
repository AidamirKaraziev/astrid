"""GIN index on places.search_text for trgm search

Revision ID: 003
Revises: 002
Create Date: 2026-05-16

"""

from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_places_search_text_trgm
        ON places USING gin (search_text gin_trgm_ops)
        """,
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_places_search_text_trgm")
