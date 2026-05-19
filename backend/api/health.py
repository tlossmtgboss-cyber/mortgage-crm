"""
Health Check API Endpoints

Provides Kubernetes-compatible health probes:
- /health - Basic health check with database connectivity
- /health/ready - Readiness probe (can accept traffic?)
- /health/live - Liveness probe (is process alive?)
- /health/detailed - Comprehensive health check
- /health/cache - Redis cache status

These endpoints are used by:
- Kubernetes for pod lifecycle management
- Load balancers for traffic routing
- Monitoring systems for alerting
"""

from datetime import datetime, timezone
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


def get_health_router(
    get_db,
    SessionLocal,
    health_checker=None,
    is_production_func=None,
):
    """
    Create health router with dependencies injected.

    Args:
        get_db: Database session dependency
        SessionLocal: Session factory for direct connections
        health_checker: Optional health checker instance from production_hardening
        is_production_func: Function to check if running in production

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/health", tags=["Health"])

    @router.get("")
    async def health_check(db: AsyncSession = Depends(get_async_db)):
        """
        Basic health check endpoint.

        Returns database connectivity status and basic metadata.
        """
        try:
            await db.execute(text("SELECT 1"))
            return {
                "status": "healthy",
                "database": "connected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "database": "disconnected",
                    "error": "Internal server error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

    @router.get("/ready")
    async def readiness_check():
        """
        Kubernetes readiness probe - can accept traffic?

        Checks:
        - Database connectivity
        - Redis connectivity (required in production)
        """
        checks = {"database": False, "redis": False}
        errors = []

        # Check database
        try:
            db = SessionLocal()
            await db.execute(text("SELECT 1"))
            db.close()
            checks["database"] = True
        except Exception as e:
            errors.append(f"Database: {str(e)}")

        # Check Redis (required in production)
        try:
            from tasks.celery_app import check_redis_health
            redis_status = check_redis_health()
            checks["redis"] = redis_status.get("status") == "healthy"
            if not checks["redis"]:
                errors.append(f"Redis: {redis_status.get('error', 'unhealthy')}")
        except ImportError:
            # Celery module not available, try direct Redis check
            try:
                import redis as redis_lib
                from config import settings
                r = redis_lib.from_url(settings.REDIS_URL)
                r.ping()
                checks["redis"] = True
            except Exception as e:
                errors.append(f"Redis: {str(e)}")

        # Determine readiness based on environment
        is_prod = is_production_func() if is_production_func else False
        if is_prod:
            # In production, both database and Redis must be healthy
            is_ready = all(checks.values())
        else:
            # In development, only database is required
            is_ready = checks["database"]

        if is_ready:
            return {"status": "ready", "checks": checks}
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": checks, "errors": errors},
        )

    @router.get("/live")
    async def liveness_check():
        """Kubernetes liveness probe - is process alive?"""
        return {"status": "alive"}

    @router.get("/detailed")
    async def health_check_detailed():
        """Comprehensive health check with all dependencies."""
        if health_checker:
            results = await health_checker.check_all()
            status_code = 200 if results["status"] == "healthy" else 503
            return JSONResponse(status_code=status_code, content=results)
        else:
            return {
                "status": "healthy",
                "message": "Basic health check (detailed checks not configured)",
            }

    @router.get("/cache")
    async def cache_health():
        """Check Redis cache status."""
        try:
            from tasks.celery_app import check_redis_health
            redis_status = check_redis_health()
            return {
                "status": "healthy" if redis_status.get("status") == "healthy" else "degraded",
                "redis": redis_status,
            }
        except ImportError:
            return {"status": "disabled", "message": "Redis module not available"}
        except Exception as e:
            return {"status": "error", "error": "Internal server error"}

    return router


# Standalone router for simple imports (uses defaults)
standalone_router = APIRouter(prefix="/health", tags=["Health"])


@standalone_router.get("/live")
async def liveness():
    """Simple liveness check - always returns alive if server is running."""
    return {"status": "alive"}
