from astra.core.config import Settings
from astra.core.sentry import init_sentry


def test_init_sentry_without_dsn_is_noop() -> None:
    settings = Settings(sentry_dsn=None, sentry_enabled=True)
    init_sentry(settings)


def test_init_sentry_disabled() -> None:
    settings = Settings(
        sentry_dsn="https://example@o0.ingest.sentry.io/0",
        sentry_enabled=False,
    )
    init_sentry(settings)
