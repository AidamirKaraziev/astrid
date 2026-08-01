"""Одноразовый скрипт: доставить разборы «Спроси Астрид», которые не дошли.

Зачем: доставка падала с `400 Bad Request` (текст длиннее 4096 знаков), при
этом разбор уже был собран и лежит в базе со статусом `ready`. Человек
заплатил и ничего не увидел. После правки отправки такие разборы можно
доставить заново — генерировать и платить второй раз не нужно.

Факта доставки в базе нет (`ask_readings` не отмечает отправку), поэтому
скрипт ничего не угадывает: он показывает кандидатов и шлёт только тех,
кого назвали явно.

    # посмотреть, что вообще есть за последние сутки (ничего не отправляет)
    uv run python scripts/resend_ask_answers.py --since-hours 24

    # доставить конкретные разборы
    uv run python scripts/resend_ask_answers.py --id <uuid> --id <uuid> --send

По умолчанию — сухой прогон: сообщения людям уходят только с `--send`.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from astra.ask.enums import AskStatus
from astra.ask.models import AskReading
from astra.db.session import get_session_factory
from astra.services.ask_service import deliver_ask_answer
from astra.telegram.message_split import split_html_message


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--id",
        dest="ids",
        action="append",
        default=[],
        help="id разбора; можно повторять",
    )
    parser.add_argument(
        "--since-hours",
        type=int,
        default=24,
        help="окно для показа кандидатов (по умолчанию 24)",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="действительно отправить; без него — только показать",
    )
    return parser.parse_args()


async def _candidates(session, since_hours: int) -> list[AskReading]:  # noqa: ANN001
    since = datetime.now(UTC) - timedelta(hours=since_hours)
    rows = await session.execute(
        select(AskReading)
        .where(AskReading.status == AskStatus.READY, AskReading.updated_at >= since)
        .order_by(AskReading.updated_at.desc()),
    )
    return list(rows.scalars())


async def _load(session, ids: list[str]) -> list[AskReading]:  # noqa: ANN001
    rows = await session.execute(
        select(AskReading).where(AskReading.id.in_([UUID(value) for value in ids])),
    )
    return list(rows.scalars())


def _describe(reading: AskReading) -> str:
    html = (reading.answer or {}).get("html") or ""
    parts = len(split_html_message(html))
    return (
        f"{reading.id}  {reading.question_key:22} {reading.updated_at:%Y-%m-%d %H:%M}  "
        f"{len(html):5} знаков → {parts} сообщ."
    )


async def main() -> None:
    args = _parse_args()
    session_factory = get_session_factory()

    async with session_factory() as session:
        readings = await _load(session, args.ids) if args.ids else await _candidates(
            session,
            args.since_hours,
        )
        if not readings:
            print("нечего доставлять")
            return

        for reading in readings:
            print(_describe(reading))

        if not args.send:
            print(f"\nсухой прогон: {len(readings)} шт. Отправить — добавь --send")
            return

        delivered = 0
        for reading in readings:
            try:
                if await deliver_ask_answer(session, reading):
                    delivered += 1
                    print(f"отправлено: {reading.id}")
                else:
                    print(f"пропущено (нет ответа или человека): {reading.id}")
            except Exception as error:  # noqa: BLE001 — один сбой не должен рвать остальных
                print(f"не отправилось: {reading.id} — {error}")
        await session.commit()
        print(f"\nдоставлено: {delivered} из {len(readings)}")


if __name__ == "__main__":
    asyncio.run(main())
