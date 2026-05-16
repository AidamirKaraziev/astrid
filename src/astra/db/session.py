from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from astra.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine, async_session_factory
    cfg = settings or get_settings()
    _engine = create_async_engine(
        cfg.database_url,
        echo=cfg.debug,
        pool_pre_ping=True,
    )
    async_session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        return init_engine()
    return _engine


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if async_session_factory is None:
        init_engine()
    assert async_session_factory is not None
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
