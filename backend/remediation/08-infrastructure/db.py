"""
08-infrastructure/db.py

Async SQLAlchemy engine + session factory. Uses pooled URL (Supavisor) for
app runtime, direct URL for migrations (Alembic writes DDL which needs
session-mode, not transaction-mode pooling).

Drop-in: backend/app/core/db.py
Replaces whatever scattered engine creation was in main.py.
"""

from __future__ import annotations

import logging
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, QueuePool

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def _normalize_url(url: str) -> str:
    """Coerce Railway-style postgres:// into asyncpg-compatible URL."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # Supavisor adds ?pgbouncer=true which asyncpg doesn't recognize — strip it.
    # asyncpg handles pooler-mode via statement_cache_size=0 instead.
    if "pgbouncer=true" in url:
        url = url.replace("?pgbouncer=true", "").replace("&pgbouncer=true", "")
    return url


def _make_engine():
    pooled = os.environ.get("DATABASE_POOLED_URL")
    direct = os.environ.get("DATABASE_URL")
    url = pooled or direct
    if not url:
        raise RuntimeError("DATABASE_URL or DATABASE_POOLED_URL must be set")

    url = _normalize_url(url)
    using_supavisor = bool(pooled)

    # When going through Supavisor transaction-mode, disable statement caching
    # on asyncpg — the cache doesn't survive connection handoff between txns.
    connect_args: dict = {}
    if using_supavisor:
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0

    return create_async_engine(
        url,
        echo=False,
        # Per-replica pool
        pool_size=int(os.environ.get("DB_POOL_SIZE", "20")),
        max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "10")),
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


engine = _make_engine()

# Session factory. expire_on_commit=False so objects remain usable after commit
# (important for async — lazy attribute loads after commit would re-query).
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session, rolls back on exception, always closes."""
    async with async_session_factory() as session:
        try:
            yield session
            # If the route didn't commit, rollback to release locks
            if session.in_transaction():
                await session.rollback()
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            await session.rollback()
            raise
        finally:
            await session.close()
