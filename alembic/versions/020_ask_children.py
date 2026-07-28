"""Спроси Астрид: вопрос про детей + контекст калибрующих вопросов

Revision ID: 020
Revises: 019
Create Date: 2026-07-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRODUCT_CODE = "ask_love_kids"


def upgrade() -> None:
    # Ответ на калибрующий вопрос свой у каждого продукта: держим в JSONB,
    # а не заводим колонку на каждый вопрос раздела.
    op.add_column(
        "ask_readings",
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO products (code, kind, title, is_active, created_at, updated_at)
            VALUES (:code, 'ask_answer', 'Будут ли у меня дети', true, now(), now())
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
    op.drop_column("ask_readings", "context")
