"""Клиент Ollama для генерации ежедневного инсайта Astrid."""

from __future__ import annotations

from astra.astro.schemas import AstroContext, NatalChartData
from astra.core.config import Settings, get_settings
from astra.llm.astrid_generate import generate_astrid_body
from astra.llm.factory import get_ollama_provider
from astra.llm.prompts.astrid import QuestionArchetype
from astra.users.models import Profile


async def generate_prediction_body(
    ctx: AstroContext,
    profile: Profile,
    chart: NatalChartData,
    settings: Settings | None = None,
    *,
    archetype: QuestionArchetype | None = None,
) -> tuple[str | None, str]:
    """Сгенерировать текст инсайта на день через Ollama."""
    cfg = settings or get_settings()
    return await generate_astrid_body(
        ctx,
        profile,
        chart,
        get_ollama_provider(cfg),
        cfg,
        archetype=archetype,
    )
