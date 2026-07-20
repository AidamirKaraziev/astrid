"""payments: справочник товаров, мультивалютные цены, платежи

Revision ID: 013
Revises: 012
Create Date: 2026-07-20
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRODUCT_KIND_TAROT = "tarot_reading"

# Сид каталога: три расклада + стартовые цены в Stars.
_SEED_PRODUCTS = (
    ("tarot_wish", "Загадай желание"),
    ("tarot_three_cards", "Три карты"),
    ("tarot_relationship", "Расклад на отношения"),
)
_SEED_PRICE_XTR = 50


def upgrade() -> None:
    products = op.create_table(
        "products",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )

    prices = op.create_table(
        "product_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("discount_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_code"], ["products.code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_code", "currency", name="uq_product_prices_product_currency"),
        sa.CheckConstraint("amount > 0", name="ck_product_prices_amount_positive"),
        sa.CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 99",
            name="ck_product_prices_discount_range",
        ),
    )

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("reading_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        # Снапшот цены в момент оплаты: отчётность не зависит от будущих правок цен.
        sa.Column("base_amount", sa.Integer(), nullable=False),
        sa.Column("discount_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_charge_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        # RESTRICT: товар с платежами удалить нельзя — финансовая история неприкосновенна.
        sa.ForeignKeyConstraint(["product_code"], ["products.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reading_id"], ["tarot_readings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        # Идемпотентность: повторный successful_payment не создаёт вторую запись.
        sa.UniqueConstraint("provider", "provider_charge_id", name="uq_payments_provider_charge"),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 99",
            name="ck_payments_discount_range",
        ),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_reading_id", "payments", ["reading_id"])
    op.create_index("ix_product_prices_product_code", "product_prices", ["product_code"])

    op.bulk_insert(
        products,
        [
            {"code": code, "kind": _PRODUCT_KIND_TAROT, "title": title, "is_active": True}
            for code, title in _SEED_PRODUCTS
        ],
    )
    op.bulk_insert(
        prices,
        [
            {
                "id": str(uuid.uuid4()),
                "product_code": code,
                "currency": "XTR",
                "amount": _SEED_PRICE_XTR,
                "discount_percent": 0,
                "is_active": True,
            }
            for code, _ in _SEED_PRODUCTS
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_payments_reading_id", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_product_prices_product_code", table_name="product_prices")
    op.drop_table("product_prices")
    op.drop_table("products")
