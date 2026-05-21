from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from astra.astro.models import NatalChart
from astra.astro.schemas import NatalChartData


async def get_natal_chart(session: AsyncSession, user_id: UUID) -> NatalChart | None:
    result = await session.execute(select(NatalChart).where(NatalChart.user_id == user_id))
    return result.scalar_one_or_none()


async def upsert_natal_chart(
    session: AsyncSession,
    user_id: UUID,
    data: NatalChartData,
) -> NatalChart:
    row = await get_natal_chart(session, user_id)
    payload = data.model_dump(mode="json")
    now = datetime.now(timezone.utc)
    if row is None:
        row = NatalChart(
            user_id=user_id,
            chart_data=payload,
            accuracy_tier=data.accuracy_tier,
            computed_at=now,
        )
        session.add(row)
    else:
        row.chart_data = payload
        flag_modified(row, "chart_data")
        row.accuracy_tier = data.accuracy_tier
        row.computed_at = now
    await session.flush()
    return row


def chart_data_from_row(row: NatalChart) -> NatalChartData:
    return NatalChartData.model_validate(row.chart_data)
