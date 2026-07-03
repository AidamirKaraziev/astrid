import asyncio

from astra.core.config import get_settings
from astra.core.observability import configure_observability
from astra.core.sentry import init_sentry
from astra.workers.consumer import run_consumer


def run() -> None:
    settings = get_settings()
    configure_observability(settings)
    init_sentry(settings)
    asyncio.run(run_consumer(settings))


if __name__ == "__main__":
    run()
