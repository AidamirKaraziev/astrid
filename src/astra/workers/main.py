import asyncio
import logging

from astra.core.config import get_settings
from astra.workers.consumer import run_consumer


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def run() -> None:
    settings = get_settings()
    _configure_logging(settings.log_level)
    asyncio.run(run_consumer(settings))


if __name__ == "__main__":
    run()
