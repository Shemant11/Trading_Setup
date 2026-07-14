"""Async SQLAlchemy engine wrapper.

Sets SQLite WAL + reasonable pragmas on connect so we can withstand
concurrent reads while a write is in progress.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from trader.observability.logging import get_logger
from trader.storage.models import Base

logger = get_logger("trader.storage.db")


@dataclass
class Database:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def create_all(self) -> None:
        """Only used in tests / dev. Production goes through Alembic."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()


def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - conn callback
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
    finally:
        cur.close()


def create_database(url: str, *, echo: bool = False) -> Database:
    """Create a `Database` for the given URL.

    SQLite gets WAL mode automatically. Postgres/other backends are used as-is.
    """
    is_sqlite = url.startswith("sqlite")
    engine = create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=not is_sqlite,
        future=True,
    )
    if is_sqlite:
        # Attach sync PRAGMAs to the sync sub-engine.
        try:
            sync_engine = engine.sync_engine
            event.listen(sync_engine, "connect", _sqlite_pragmas)
        except Exception as e:  # noqa: BLE001
            logger.warning("sqlite_pragma_hook_failed", error=str(e))

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    logger.info("database_configured", url=_mask(url))
    return Database(engine=engine, session_factory=factory)


def _mask(url: str) -> str:
    # Never log full DSN with password.
    if "@" in url:
        head, tail = url.split("@", 1)
        if "://" in head:
            scheme, _ = head.split("://", 1)
            return f"{scheme}://***@{tail}"
    return url
