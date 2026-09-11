"""Подарочные разборы: один человек дарит другому за счёт бота

Даритель выбирает продукт из каталога и получает ссылку `?start=gift_<код>`.
Активировать её может только человек, которого в боте ещё нет, и только один
раз от этого дарителя — обе проверки живут в services/gift_service.

Уникальность кода — на уровне базы: код попадает в ссылку, которую пересылают
дальше, и коллизия означала бы чужой подарок.

Revision ID: 031
Revises: 030
Create Date: 2026-08-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    gift_status = sa.Enum("issued", "redeemed", "revoked", name="gift_status")

    op.create_table(
        "gifts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "giver_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("status", gift_status, nullable=False),
        sa.Column(
            "redeemed_by",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_gifts_giver_id", "gifts", ["giver_id"])
    op.create_index("ix_gifts_status", "gifts", ["status"])
    op.create_index("ix_gifts_code", "gifts", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_gifts_code", table_name="gifts")
    op.drop_index("ix_gifts_status", table_name="gifts")
    op.drop_index("ix_gifts_giver_id", table_name="gifts")
    op.drop_table("gifts")
    sa.Enum(name="gift_status").drop(op.get_bind(), checkfirst=True)
