from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.db.models import Base


def create_engine_and_factory(settings: Settings) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
    )

    if settings.database_url.startswith("sqlite"):
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    return engine, session_factory


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.url.drivername.startswith("sqlite"):
            await _apply_sqlite_event_columns_migration(conn)


async def _apply_sqlite_event_columns_migration(conn) -> None:
    result = await conn.execute(text("PRAGMA table_info(events)"))
    columns = {row[1] for row in result.fetchall()}
    if "start_notified" not in columns:
        await conn.execute(
            text(
                "ALTER TABLE events ADD COLUMN start_notified BOOLEAN NOT NULL DEFAULT 0"
            )
        )
    if "reminder_24h_notified" not in columns:
        await conn.execute(
            text(
                "ALTER TABLE events ADD COLUMN reminder_24h_notified BOOLEAN NOT NULL DEFAULT 0"
            )
        )


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
