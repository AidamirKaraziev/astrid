"""natal_profiles and compatibility_reports

Revision ID: 007
Revises: 006
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "natal_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("gender", sa.String(length=16), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("birth_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("birth_place", sa.String(length=255), nullable=False),
        sa.Column("birth_place_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("chart_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.ForeignKeyConstraint(["birth_place_id"], ["places.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_natal_profiles_owner_user_id", "natal_profiles", ["owner_user_id"])
    op.create_index("ix_natal_profiles_label", "natal_profiles", ["label"])

    op.create_table(
        "compatibility_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_context", sa.String(length=32), nullable=False),
        sa.Column("pair_mode", sa.String(length=32), nullable=False),
        sa.Column("person_a_natal_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("person_b_natal_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("person_a_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("person_b_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("llm_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("astro_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pdf_path", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["person_a_natal_profile_id"],
            ["natal_profiles.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["person_b_natal_profile_id"],
            ["natal_profiles.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compatibility_reports_owner_user_id",
        "compatibility_reports",
        ["owner_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_compatibility_reports_owner_user_id", table_name="compatibility_reports")
    op.drop_table("compatibility_reports")
    op.drop_index("ix_natal_profiles_label", table_name="natal_profiles")
    op.drop_index("ix_natal_profiles_owner_user_id", table_name="natal_profiles")
    op.drop_table("natal_profiles")
