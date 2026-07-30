"""Время рождения — настенные часы: timestamptz → timestamp

Revision ID: 025
Revises: 024
Create Date: 2026-07-30

Колонка была `timestamptz`, а код клал наивный `datetime`. Драйвер трактует
такое значение в часовом поясе **процесса, который пишет**, поэтому смысл
строки зависел от того, где крутился бот:

* в Docker (TZ не задан, то есть UTC) `03:35` уезжало в базу как `03:35Z`;
* с ноутбука на MSK то же `03:35` уезжало как `00:35Z`.

На чтении `astimezone` сдвигал часы ещё раз — человек видел `06:35` вместо
`03:35`, и карта считалась на неверный час.

## Как накатывать

Разворот делается через `AT TIME ZONE <пояс процесса, который писал>`.
Автоматически его не определить: в одной таблице могут лежать строки,
записанные и из контейнера, и с ноутбука. По умолчанию берём `UTC` —
так пишет продакшен в Docker. Если база наполнялась ботом, запущенным
не в контейнере, поясом переопределяем:

    BIRTH_TIME_WRITER_TZ=Europe/Moscow alembic upgrade head

Проверить, что получилось, и найти строки, которые всё-таки разъехались
(время рождения — редко ровно полночь и редко после 23:00):

    SELECT display_name, birth_time FROM profiles WHERE birth_time IS NOT NULL;

Строку с неверным часом чинит сам человек: «Обо мне» → «Изменить данные» →
«Время рождения». Это надёжнее любой догадки на стороне базы.
"""

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("profiles", "natal_profiles")


def _writer_timezone() -> str:
    """Пояс процесса, который писал время. Продакшен — Docker, там UTC."""
    return os.getenv("BIRTH_TIME_WRITER_TZ", "UTC")


def upgrade() -> None:
    zone = _writer_timezone()
    for table in _TABLES:
        op.alter_column(
            table,
            "birth_time",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(timezone=False),
            existing_nullable=True,
            postgresql_using=f"birth_time AT TIME ZONE '{zone}'",
        )


def downgrade() -> None:
    zone = _writer_timezone()
    for table in _TABLES:
        op.alter_column(
            table,
            "birth_time",
            existing_type=sa.DateTime(timezone=False),
            type_=sa.DateTime(timezone=True),
            existing_nullable=True,
            postgresql_using=f"birth_time AT TIME ZONE '{zone}'",
        )
