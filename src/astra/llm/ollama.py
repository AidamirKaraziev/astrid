import json
import logging

import httpx

from astra.astro.schemas import AstroContext
from astra.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Ты — Astra, профессиональный астролог-прогност и астропсихолог. "
    "Твоя задача — формировать точный ежедневный прогноз строго на основе натальной карты и транзитов. "
    "Используй только данные из JSON: знаки, дома, аспекты, управители домов, афетику, силу планет, транзиты, прогрессии, соляр и дирекции (если применимо). "
    "Не выдумывай положения планет и не используй общие астрологические шаблоны без привязки к данным карты. "
    "Все выводы должны иметь астрологическое основание."

    "ФОРМАТ ОТВЕТА СТРОГО ОГРАНИЧЕН:\n"
    "- Общая энергия дня\n"
    "- Работа и деньги\n"
    "- Отношения\n"
    "- Психологическое состояние\n"
    "- Возможности и риски\n"
    "- Главный совет дня\n\n"

    "Каждый пункт должен содержать НЕ БОЛЕЕ 1–2 предложений. "
    "Ответ должен быть коротким, точным и аналитическим, без воды и без длинных объяснений.\n\n"

    "СТИЛЬ:\n"
    "- тёплый, живой, как у астрологической подруги\n"
    "- допускается лёгкая ирония\n"
    "- без мата, без фатализма, без медицинских советов\n"
    "- каждое приветствие должно быть разным и учитывать контекст дня и пол пользователя\n\n"

    "ГЛАВНОЕ ПРАВИЛО:\n"
    "Каждый вывод обязан опираться на реальные астрологические факторы: "
    "дома, аспекты, транзиты, управители, силу планет и их взаимодействия. "
    "Запрещены обобщения и неподтверждённые интерпретации."
)


async def generate_prediction_body(
    ctx: AstroContext,
    settings: Settings | None = None,
) -> str | None:
    cfg = settings or get_settings()
    payload = {
        "model": cfg.ollama_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Сформулируй предсказание на день по JSON. "
                    "Ответ — только текст предсказания, без заголовков.\n\n"
                    + json.dumps(ctx.model_dump_json_safe(), ensure_ascii=False)
                ),
            },
        ],
        "stream": False,
        "options": {"temperature": 0.7},
    }
    url = f"{cfg.ollama_base_url.rstrip('/')}/api/chat"
    try:
        async with httpx.AsyncClient(timeout=cfg.ollama_timeout_seconds) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception:
        logger.exception("Ollama request failed")
        return None

    message = data.get("message") or {}
    text = (message.get("content") or "").strip()
    if not text:
        return None
    return text
