from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    # plain — console renderer (dev); json — stdout JSON (prod / Loki)
    log_format: str = "plain"
    # OpenTelemetry traces (этап 3); пока только флаг в конфиге
    otel_enabled: bool = False
    otel_traces_sample_rate: float = 0.1
    # true — Bot API через telegram_proxy_url; false — прямое подключение, proxy игнорируется
    use_vpn: bool = False

    database_url: str = Field(
        default="postgresql+asyncpg://astra:astra@localhost:5432/astra",
    )
    redis_url: str = "redis://localhost:6379/0"
    # FSM aiogram: redis | memory (memory — если Redis не запущен)
    fsm_storage: str = "redis"

    telegram_bot_token: str = ""
    telegram_bot_username: str = "AstraBot"
    # Личный аккаунт Astrid для поддержки (без @)
    telegram_support_username: str = ""
    telegram_mode: str = "polling"
    telegram_webhook_url: str | None = None
    telegram_webhook_secret: str | None = None
    # SOCKS5 или HTTP(S) proxy только для Bot API (не MTProto tg://proxy)
    # Пример: socks5://user:pass@host:1080
    telegram_proxy_url: str = ""

    points_daily_visit: int = 7
    referral_bonus_referrer: int = 50
    referral_bonus_invitee: int = 10

    notification_hour: int = 9
    notification_minute: int = 0

    rabbitmq_url: str = "amqp://astra:astra@localhost:5672/"
    rabbitmq_prefetch: int = 8

    # true — всем персональные предсказания; false — общий гороскоп по знаку
    personal_predictions_enabled: bool = True

    # xAI Grok — платные продукты (совместимость и др.)
    grok_enabled: bool = False
    xai_api_key: str = ""
    # Дешёвая модель для тестов на бесплатных кредитах console.x.ai ($25 при регистрации)
    grok_model: str = "grok-4-1-fast-non-reasoning"
    grok_base_url: str = "https://api.x.ai/v1"
    grok_timeout_seconds: float = 120.0

    # Google Gemini (AI Studio) — платные продукты / A-B тесты
    gemini_enabled: bool = False
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_seconds: float = 120.0

    # OpenRouter — единый API к разным LLM (OpenAI-compatible)
    openrouter_enabled: bool = False
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Qwen3 Next 80B Instruct — сильный instruct, RU, 262K ctx, :free на OpenRouter
    openrouter_model: str = "qwen/qwen3-next-80b-a3b-instruct:free"
    # Через запятую — fallback при 429/даунтайме upstream (см. openrouter.ai/docs/guides/routing/model-fallbacks)
    openrouter_fallback_models: str = (
        "google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free,"
        "mistralai/mistral-small-3.1-24b-instruct:free"
    )
    openrouter_timeout_seconds: float = 120.0

    # OpenAI — платные продукты (совместимость, GPT-5.5)
    openai_enabled: bool = False
    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: float = 180.0

    # DeepSeek — совместимость (V4-Flash non-thinking по умолчанию)
    # Ключ: https://platform.deepseek.com/api_keys
    deepseek_enabled: bool = False
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_timeout_seconds: float = 120.0

    # AI-чат Astrid (прототип feature/ai-chat-astrid) — свободный текст вместо кнопок.
    # Ловит сообщения вне FSM и ведёт разговор через LLM. По умолчанию выключен.
    ai_chat_enabled: bool = False
    ai_chat_provider: str = "deepseek"

    # PDF совместимости на volume (Docker: /data/compatibility)
    compatibility_pdf_dir: str = "data/compatibility_pdfs"

    # PDF разбора натала на volume (Docker: /data/natal)
    natal_pdf_dir: str = "data/natal_pdfs"

    # Sentry — ошибки и (опционально) трейсы; стенд: local | dev | prod
    sentry_dsn: str | None = None
    sentry_enabled: bool = True
    sentry_environment: str = "local"
    sentry_send_default_pii: bool = False
    sentry_traces_sample_rate: float = 0.0
    sentry_profiles_sample_rate: float = 0.0
    sentry_release: str | None = None
    # Компонент в одном репо: api (FastAPI + polling) | worker (RabbitMQ consumer)
    sentry_service: str = "api"
    # Heartbeat в Sentry Crons: замена uptime-монитору без статического IP.
    # Слаг задаётся только на проде; пустой = выключено.
    sentry_heartbeat_slug: str | None = None
    sentry_heartbeat_interval_minutes: int = 5

    # Автозагрузка справочника GeoNames при старте, если таблица places пуста
    geonames_auto_import: bool = True

    @property
    def app_version(self) -> str:
        from importlib.metadata import version

        try:
            return version("astra")
        except Exception:
            return "0.0.0"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def telegram_proxy_url_effective(self) -> str | None:
        """URL proxy для Bot API, если use_vpn=true и URL задан; иначе None."""
        if not self.use_vpn:
            return None
        url = self.telegram_proxy_url.strip()
        return url or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
