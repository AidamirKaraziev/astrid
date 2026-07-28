"""Спроси Астрид: купленные ответы по натальной карте

Revision ID: 019
Revises: 018
Create Date: 2026-07-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRODUCT_CODE = "ask_love_fated_count"


def upgrade() -> None:
    op.create_table(
        "ask_readings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending_payment", nullable=False),
        sa.Column("in_relationship", sa.Boolean(), nullable=True),
        sa.Column("computed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("methodology_version", sa.Integer(), nullable=True),
        sa.Column("answer", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("card_file_id", sa.String(length=256), nullable=True),
        sa.Column("paid_amount", sa.Integer(), nullable=True),
        sa.Column("charge_id", sa.String(length=128), nullable=True),
        sa.Column("refunded", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ask_readings_user_id", "ask_readings", ["user_id"])
    op.create_index("ix_ask_readings_question_key", "ask_readings", ["question_key"])
    op.create_index("ix_ask_readings_user_question", "ask_readings", ["user_id", "question_key"])

    # Товар и цена: правится в БД без релиза.
    op.execute(
        sa.text(
            """
            INSERT INTO products (code, kind, title, is_active, created_at, updated_at)
            VALUES (:code, 'ask_answer', 'Сколько судьбоносных партнёров', true, now(), now())
            ON CONFLICT (code) DO NOTHING
            """,
        ).bindparams(code=_PRODUCT_CODE),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO product_prices
                (id, product_code, currency, amount, discount_percent, is_active,
                 created_at, updated_at)
            VALUES (gen_random_uuid(), :code, 'XTR', 1, 0, true, now(), now())
            ON CONFLICT (product_code, currency) DO NOTHING
            """,
        ).bindparams(code=_PRODUCT_CODE),
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM product_prices WHERE product_code = :code").bindparams(
            code=_PRODUCT_CODE,
        ),
    )
    op.execute(
        sa.text("DELETE FROM products WHERE code = :code").bindparams(code=_PRODUCT_CODE),
    )
    op.drop_index("ix_ask_readings_user_question", table_name="ask_readings")
    op.drop_index("ix_ask_readings_question_key", table_name="ask_readings")
    op.drop_index("ix_ask_readings_user_id", table_name="ask_readings")
    op.drop_table("ask_readings")
