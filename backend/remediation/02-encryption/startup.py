"""
02-encryption/startup.py

FastAPI lifespan/startup hook that validates critical config BEFORE the app
accepts traffic. If anything is wrong, the app crashes at boot, which
Railway will surface as a failed deployment instead of serving broken requests.

Integrate into main.py:

    from contextlib import asynccontextmanager
    from app.security.startup import validate_startup_config

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await validate_startup_config()
        yield

    app = FastAPI(lifespan=lifespan)
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

from app.security.pii_encryption import (
    PIIEncryptionConfigError,
    validate_encryption_at_startup,
)

logger = logging.getLogger(__name__)


class StartupConfigError(RuntimeError):
    """Fatal config problem detected at boot."""


# Required env vars. Missing any of these means the app cannot function correctly.
# Grouped for clearer error messages.
REQUIRED_ENV_VARS: dict[str, Iterable[str]] = {
    "database": ["DATABASE_URL"],
    "redis": ["REDIS_URL"],
    "encryption": ["PII_ENCRYPTION_KEY"],
    "auth": ["JWT_PRIVATE_KEY", "JWT_PUBLIC_KEY", "COOKIE_DOMAIN"],
    "claude": ["ANTHROPIC_API_KEY"],
    "storage": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_S3_BUCKET"],
    "telephony": ["TELNYX_API_KEY", "TWILIO_AUTH_TOKEN"],
    "email": ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"],
}


async def validate_startup_config() -> None:
    """
    Validate all critical configuration. Raises StartupConfigError on the first
    problem so Railway marks the deploy failed.
    """
    logger.info("Running startup config validation")

    missing: dict[str, list[str]] = {}
    for group, keys in REQUIRED_ENV_VARS.items():
        absent = [k for k in keys if not os.environ.get(k)]
        if absent:
            missing[group] = absent

    if missing:
        lines = ["Required environment variables are missing:"]
        for group, keys in missing.items():
            lines.append(f"  [{group}] {', '.join(keys)}")
        raise StartupConfigError("\n".join(lines))

    # Encryption round-trip
    try:
        validate_encryption_at_startup()
    except PIIEncryptionConfigError as e:
        raise StartupConfigError(f"PII encryption is not usable: {e}") from e

    # DB connectivity
    await _verify_database_connection()

    # Redis connectivity
    await _verify_redis_connection()

    logger.info("Startup config validated successfully")


async def _verify_database_connection() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    url = os.environ["DATABASE_URL"]
    # Normalize Railway-style postgres:// → postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(url, pool_pre_ping=True, pool_size=1, max_overflow=0)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            if result.scalar() != 1:
                raise StartupConfigError("Database SELECT 1 did not return 1")
    except Exception as e:
        raise StartupConfigError(f"Cannot connect to database: {e}") from e
    finally:
        await engine.dispose()


async def _verify_redis_connection() -> None:
    import redis.asyncio as aioredis

    client = aioredis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=5)
    try:
        pong = await client.ping()
        if not pong:
            raise StartupConfigError("Redis PING did not return PONG")
    except Exception as e:
        raise StartupConfigError(f"Cannot connect to Redis: {e}") from e
    finally:
        await client.close()
