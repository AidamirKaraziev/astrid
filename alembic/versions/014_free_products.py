"""discount_percent = 100 означает бесплатный товар

Revision ID: 014
Revises: 013
Create Date: 2026-07-21
"""

from typing import Sequence, Union

from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_product_prices_discount_range", "product_prices", type_="check")
    op.create_check_constraint(
        "ck_product_prices_discount_range",
        "product_prices",
        "discount_percent >= 0 AND discount_percent <= 100",
    )


def downgrade() -> None:
    op.drop_constraint("ck_product_prices_discount_range", "product_prices", type_="check")
    op.create_check_constraint(
        "ck_product_prices_discount_range",
        "product_prices",
        "discount_percent >= 0 AND discount_percent <= 99",
    )
