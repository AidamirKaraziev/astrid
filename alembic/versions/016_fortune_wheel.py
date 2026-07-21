"""Колесо фортуны: пул призов, выигрыши, товар wheel_spin

Revision ID: 016
Revises: 015
Create Date: 2026-07-21
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Товар «вращение колеса»: цена меняется UPDATE'ом в product_prices.
_WHEEL_SPIN_CODE = "wheel_spin"
_WHEEL_SPIN_PRICE_XTR = 5  # ≈ 10 ₽

# Стартовый пул: три расклада — бесплатно (редко) и −50% (чаще).
_SEED_PRIZES = (
    ("tarot_wish", 100, 10),
    ("tarot_three_cards", 100, 10),
    ("tarot_relationship", 100, 10),
    ("tarot_wish", 50, 30),
    ("tarot_three_cards", 50, 30),
    ("tarot_relationship", 50, 30),
)


def upgrade() -> None:
    prizes = op.create_table(
        "wheel_prizes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("discount_percent", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_code"], ["products.code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "discount_percent >= 1 AND discount_percent <= 100",
            name="ck_wheel_prizes_discount_range",
        ),
        sa.CheckConstraint("weight > 0", name="ck_wheel_prizes_weight_positive"),
    )
    op.create_index("ix_wheel_prizes_product_code", "wheel_prizes", ["product_code"])

    op.create_table(
        "wheel_wins",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prize_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Снапшот приза: правки пула не меняют уже выпавшие выигрыши.
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("discount_percent", sa.Integer(), nullable=False),
        sa.Column("spin_type", sa.String(length=8), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reading_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("won_on", sa.Date(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prize_id"], ["wheel_prizes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_code"], ["products.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reading_id"], ["tarot_readings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "discount_percent >= 1 AND discount_percent <= 100",
            name="ck_wheel_wins_discount_range",
        ),
    )
    op.create_index("ix_wheel_wins_user_id", "wheel_wins", ["user_id"])
    op.create_index("ix_wheel_wins_reading_id", "wheel_wins", ["reading_id"])
    # Одно бесплатное вращение в локальный день пользователя.
    op.create_index(
        "uq_wheel_wins_free_per_day",
        "wheel_wins",
        ["user_id", "won_on"],
        unique=True,
        postgresql_where=sa.text("spin_type = 'free'"),
    )

    products = sa.table(
        "products",
        sa.column("code", sa.String),
        sa.column("kind", sa.String),
        sa.column("title", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        products,
        [
            {
                "code": _WHEEL_SPIN_CODE,
                "kind": "wheel_spin",
                "title": "Вращение колеса фортуны",
                "is_active": True,
            },
        ],
    )
    product_prices = sa.table(
        "product_prices",
        sa.column("id", postgresql.UUID(as_uuid=False)),
        sa.column("product_code", sa.String),
        sa.column("currency", sa.String),
        sa.column("amount", sa.Integer),
        sa.column("discount_percent", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        product_prices,
        [
            {
                "id": str(uuid.uuid4()),
                "product_code": _WHEEL_SPIN_CODE,
                "currency": "XTR",
                "amount": _WHEEL_SPIN_PRICE_XTR,
                "discount_percent": 0,
                "is_active": True,
            },
        ],
    )
    op.bulk_insert(
        prizes,
        [
            {
                "id": str(uuid.uuid4()),
                "product_code": code,
                "discount_percent": discount,
                "weight": weight,
                "is_active": True,
            }
            for code, discount, weight in _SEED_PRIZES
        ],
    )


def downgrade() -> None:
    op.drop_index("uq_wheel_wins_free_per_day", table_name="wheel_wins")
    op.drop_index("ix_wheel_wins_reading_id", table_name="wheel_wins")
    op.drop_index("ix_wheel_wins_user_id", table_name="wheel_wins")
    op.drop_table("wheel_wins")
    op.drop_index("ix_wheel_prizes_product_code", table_name="wheel_prizes")
    op.drop_table("wheel_prizes")
    op.execute(f"DELETE FROM product_prices WHERE product_code = '{_WHEEL_SPIN_CODE}'")
    op.execute(f"DELETE FROM products WHERE code = '{_WHEEL_SPIN_CODE}'")
