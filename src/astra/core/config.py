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
    # Публичный HTTPS URL API (для Web App геолокации на Desktop). Пример: https://xxx.ngrok-free.app
    webapp_base_url: str = ""

    points_daily_visit: int = 7
    referral_bonus_referrer: int = 50
    referral_bonus_invitee: int = 10

    notification_hour: int = 9
    notification_minute: int = 0

    rabbitmq_url: str = "amqp://astra:astra@localhost:5672/"
    rabbitmq_enabled: bool = True
    rabbitmq_prefetch: int = 8

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_enabled: bool = True
    ollama_timeout_seconds: float = 120.0

    sentry_dsn: str | None = None

    # Автозагрузка справочника GeoNames при старте, если таблица places пуста
    geonames_auto_import: bool = True

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
