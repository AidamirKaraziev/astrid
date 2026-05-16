import os

import pytest
from httpx import ASGITransport, AsyncClient

# Defaults for tests without real Telegram/DB when only hitting /health
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0000000000:TEST_TOKEN_FOR_TESTS")
os.environ.setdefault("TELEGRAM_BOT_USERNAME", "TestAstraBot")
os.environ.setdefault("TELEGRAM_MODE", "polling")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://astra:astra@localhost:5432/astra",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def api_client() -> AsyncClient:
    from astra.main import create_app

    app = create_app(with_lifespan=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
