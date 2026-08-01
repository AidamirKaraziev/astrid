"""Спроси Астрид: вопрос про повторяющийся сценарий в отношениях

Revision ID: 027
Revises: 026
Create Date: 2026-08-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRODUCT_CODE = "ask_love_pain_loop"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO products (code, kind, title, is_active, created_at, updated_at)
            VALUES (:code, 'ask_answer', 'Почему я снова и снова обжигаюсь', true, now(), now())
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
