"""Внутренний кошелёк в звёздах и перенос в него накопленных баллов

Настоящие Telegram Stars бот на баланс человека положить не может, поэтому
награда за приглашённого живёт своим леджером в тех же единицах, что и цены
каталога. Баланс — сумма `delta`; отдельной колонки с балансом нет намеренно.

Баллы (`points_ledger`) до сих пор было негде потратить — счётчик ради
счётчика. Переносим накопленное в звёзды по курсу 10 баллов = 1 ⭐ и убираем
баллы из интерфейса. Сам `points_ledger` остаётся: по нему считается серия
ежедневных визитов и часть аналитики.

Курс округляется вниз, нулевые начисления не создаются. Downgrade сносит
таблицу целиком — восстанавливать в баллы нечего, их никто не отнимал.

Revision ID: 030
Revises: 029
Create Date: 2026-08-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POINTS_PER_STAR = 10


def upgrade() -> None:
    # Тип создаётся самим create_table: отдельный .create() до него ронял
    # миграцию на DuplicateObject.
    wallet_reason = sa.Enum(
        "referral_reward",
        "points_migration",
        "hold",
        "purchase",
        "released",
        "refund",
        "manual",
        name="wallet_reason",
    )

    op.create_table(
        "star_wallet_entries",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", wallet_reason, nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.String(length=128), nullable=True),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_star_wallet_entries_user_id",
        "star_wallet_entries",
        ["user_id"],
    )
    op.create_index(
        "ix_star_wallet_entries_payload",
        "star_wallet_entries",
        ["payload"],
    )

    # Накопленные баллы переезжают в звёзды: человек, у которого их было 250,
    # обнаруживает на счету 25 ⭐, а не ноль.
    op.execute(
        f"""
        INSERT INTO star_wallet_entries (id, user_id, delta, reason, description)
        SELECT gen_random_uuid(), id, points / {POINTS_PER_STAR},
               'points_migration', 'Перенос накопленных баллов'
        FROM users
        WHERE points >= {POINTS_PER_STAR}
        """,
    )


def downgrade() -> None:
    op.drop_index("ix_star_wallet_entries_payload", table_name="star_wallet_entries")
    op.drop_index("ix_star_wallet_entries_user_id", table_name="star_wallet_entries")
    op.drop_table("star_wallet_entries")
    sa.Enum(name="wallet_reason").drop(op.get_bind(), checkfirst=True)
