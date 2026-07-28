"""Спроси Астрид: вопрос про отношения с детьми

Revision ID: 021
Revises: 020
Create Date: 2026-07-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRODUCT_CODE = "ask_love_kids_bond"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO products (code, kind, title, is_active, created_at, updated_at)
            VALUES (:code, 'ask_answer', 'Какими будут отношения с детьми', true, now(), now())
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
