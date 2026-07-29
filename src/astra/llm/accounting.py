"""Запись вызова модели в базу: токены, длительность, себестоимость.

Живёт отдельно от обёртки-трейсера, потому что у записи свои правила:

* **своя сессия** — вызовы идут из воркера, из хендлеров и из пайплайнов,
  и тащить туда чужую транзакцию нельзя: откат генерации не должен стирать
  факт того, что модель мы уже подёргали (и заплатили);
* **своё молчание при ошибке** — если учёт упал, продукт всё равно должен
  дойти до человека. Аналитика никогда не важнее ответа.

Прайс кешируется в памяти процесса на несколько минут: цены правятся руками
раз в месяц, а вызовов бывают сотни в час.
"""

from __future__ import annotations

import time
from decimal import Decimal

from sqlalchemy import select

from astra.core.observability import get_logger
from astra.llm.models import LlmCall, LlmPrice
from astra.llm.types import TokenUsage

log = get_logger(__name__)

_PRICE_TTL_SECONDS = 300
_price_cache: dict[str, tuple[float, LlmPrice | None]] = {}


async def _price_for(session, model: str | None) -> LlmPrice | None:
    if not model:
        return None
    cached = _price_cache.get(model)
    if cached and time.monotonic() - cached[0] < _PRICE_TTL_SECONDS:
        return cached[1]

    price = (
        await session.execute(select(LlmPrice).where(LlmPrice.model == model))
    ).scalar_one_or_none()
    _price_cache[model] = (time.monotonic(), price)
    return price


def reset_price_cache() -> None:
    """Сбросить кеш прайса — зовётся после правки цен в панели."""
    _price_cache.clear()


async def record_call(
    *,
    provider: str,
    model: str | None,
    purpose: str,
    status: str,
    reason: str | None,
    duration_ms: int,
    usage: TokenUsage,
) -> None:
    """Записать факт вызова модели. Ошибки глотаем: продукт важнее отчёта."""
    from astra.db.session import get_session_factory

    try:
        async with get_session_factory()() as session:
            price = await _price_for(session, model)
            cost: Decimal | None = None
            if price is not None:
                cost = price.cost_usd(usage.prompt, usage.completion)

            session.add(
                LlmCall(
                    provider=provider,
                    model=model,
                    purpose=purpose,
                    status=status,
                    reason=(reason or None),
                    duration_ms=duration_ms,
                    prompt_tokens=usage.prompt,
                    completion_tokens=usage.completion,
                    cost_usd=cost,
                ),
            )
            await session.commit()
    except Exception:
        log.warning("llm.accounting_failed", provider=provider, purpose=purpose)
