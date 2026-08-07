"""Профиль живёт без даты рождения: регистрация не требует астроданных

Онбординг сокращается до имени и пола, а дата, время и место рождения
спрашиваются в тот момент, когда человек открывает продукт, которому они
нужны. До сих пор `birth_date` был обязателен, и профиль нельзя было
создать вовсе — то есть человек либо проходил весь сбор данных, либо не
попадал в базу.

Обратно колонка сужается только после заполнения пустых дат: людей без
даты рождения на этот момент в базе может быть сколько угодно, и слепой
`nullable=False` в downgrade уронил бы миграцию. Поэтому downgrade сначала
удаляет профили без даты — терять там нечего, кроме имени и пола, но
делать это молча нельзя, потому и написано здесь прямо.

Revision ID: 029
Revises: 028
Create Date: 2026-08-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("profiles", "birth_date", existing_type=sa.Date(), nullable=True)


def downgrade() -> None:
    # Профили без даты рождения появились уже после 029 — вернуть колонку
    # в NOT NULL, не тронув их, невозможно.
    op.execute("DELETE FROM profiles WHERE birth_date IS NULL")
    op.alter_column("profiles", "birth_date", existing_type=sa.Date(), nullable=False)
