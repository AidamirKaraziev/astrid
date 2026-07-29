"""Дни активности, учёт вызовов моделей и прайс на токены

Revision ID: 023
Revises: 022
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Прайс на день миграции, доллары за миллион токенов. Дальше правится из панели.
_SEED_PRICES = (
    ("deepseek-v4-flash", "0.28", "0.42", "актуально на 2026-07-29"),
    ("gpt-5.5", "1.25", "10.00", "актуально на 2026-07-29"),
    ("gemini-2.0-flash", "0.10", "0.40", "актуально на 2026-07-29"),
    ("grok-4-1-fast-non-reasoning", "0.20", "0.50", "актуально на 2026-07-29"),
)


def upgrade() -> None:
    op.create_table(
        "activity_days",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("day_msk", sa.Date(), nullable=False),
        sa.Column("day_local", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "day_msk", "day_local", name="uq_activity_days_user_day"),
    )
    op.create_index("ix_activity_days_user_id", "activity_days", ["user_id"])
    op.create_index("ix_activity_days_day_msk", "activity_days", ["day_msk"])

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("purpose", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_calls_purpose", "llm_calls", ["purpose"])
    op.create_index("ix_llm_calls_created_purpose", "llm_calls", ["created_at", "purpose"])

    op.create_table(
        "llm_prices",
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("input_per_million", sa.Numeric(10, 4), nullable=False),
        sa.Column("output_per_million", sa.Numeric(10, 4), nullable=False),
        sa.Column("note", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("model"),
        sa.CheckConstraint("input_per_million >= 0", name="ck_llm_prices_input_positive"),
        sa.CheckConstraint("output_per_million >= 0", name="ck_llm_prices_output_positive"),
    )

    for model, incoming, outgoing, note in _SEED_PRICES:
        op.execute(
            sa.text(
                """
                INSERT INTO llm_prices
                    (model, input_per_million, output_per_million, note, created_at, updated_at)
                VALUES (:model, CAST(:incoming AS numeric), CAST(:outgoing AS numeric), :note, now(), now())
                ON CONFLICT (model) DO NOTHING
                """,
            ).bindparams(model=model, incoming=incoming, outgoing=outgoing, note=note),
        )


def downgrade() -> None:
    op.drop_table("llm_prices")
    op.drop_index("ix_llm_calls_created_purpose", table_name="llm_calls")
    op.drop_index("ix_llm_calls_purpose", table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index("ix_activity_days_day_msk", table_name="activity_days")
    op.drop_index("ix_activity_days_user_id", table_name="activity_days")
    op.drop_table("activity_days")
