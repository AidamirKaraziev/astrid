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
    rabbitmq_enabled: bool = True
    rabbitmq_prefetch: int = 8

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:e2b"
    ollama_enabled: bool = True
    ollama_timeout_seconds: float = 300.0

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
