"""
08-infrastructure/health.py

Liveness and readiness probes. Railway should point:
  - Deployment healthcheck → /health/ready
  - Nothing else needed; there's no separate liveness probe on Railway.

Drop-in: backend/app/routes/health.py
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_session
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", status_code=200)
async def liveness():
    """Liveness — app process is alive. Does not hit DB/Redis."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    redis=Depends(get_redis),
):
    """
    Readiness — app can serve traffic. Exercises DB + Redis with short timeouts.
    Returns 503 if any dependency is unhealthy so Railway stops routing to us.
    """
    checks: dict[str, dict] = {}
    overall_ok = True

    # DB
    t0 = time.monotonic()
    try:
        async with asyncio.timeout(2.0):
            result = await db.execute(text("SELECT 1"))
            value = result.scalar()
            if value != 1:
                raise RuntimeError(f"unexpected value: {value}")
        checks["database"] = {"ok": True, "latency_ms": _ms(t0)}
    except Exception as e:
        overall_ok = False
        checks["database"] = {"ok": False, "error": str(e), "latency_ms": _ms(t0)}
        logger.error("Readiness: DB check failed: %s", e)

    # Redis
    t0 = time.monotonic()
    try:
        async with asyncio.timeout(2.0):
            pong = await redis.ping()
            if not pong:
                raise RuntimeError("ping returned falsy")
        checks["redis"] = {"ok": True, "latency_ms": _ms(t0)}
    except Exception as e:
        overall_ok = False
        checks["redis"] = {"ok": False, "error": str(e), "latency_ms": _ms(t0)}
        logger.error("Readiness: Redis check failed: %s", e)

    # Pool saturation visibility
    try:
        from app.core.db import engine
        pool = engine.pool
        checks["db_pool"] = {
            "size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    except Exception as _exc:  # noqa: BLE001
        pass

    response.status_code = (
        status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return {"status": "ok" if overall_ok else "degraded", "checks": checks}


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)
