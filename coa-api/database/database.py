"""Async SQLite engine for the trace store. No migrations: create_all at boot."""

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from model import Base
from settings import get_settings

_engine: AsyncEngine | None = None
_sessions: async_sessionmaker[AsyncSession] | None = None


async def init_engine(url: str | None = None) -> AsyncEngine:
    global _engine, _sessions
    settings = get_settings()
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    _engine = create_async_engine(url or settings.trace_db_url)

    @event.listens_for(_engine.sync_engine, "connect")
    def _wal(dbapi_conn, _record):
        # WAL: the SSE tail reads while the run writes.
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _sessions = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def dispose_engine() -> None:
    global _engine, _sessions
    if _engine is not None:
        await _engine.dispose()
    _engine = _sessions = None


async def get_session() -> AsyncGenerator[AsyncSession]:
    if _sessions is None:
        raise RuntimeError("init_engine() has not run")
    async with _sessions() as session:
        yield session
