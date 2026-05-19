"""
Scheduler Metrics - Observability endpoints for scheduler operations.

Endpoints:
  - GET /metrics              JSON metrics summary (admin only)
  - GET /metrics/prometheus   Prometheus text exposition format (admin only)
  - POST /metrics/reset       Reset all counters (platform admin only)

All endpoints require authentication and admin role.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
import logging

from db import get_db
from routes.scheduler._helpers import get_current_user, _is_scheduler_admin
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# JSON METRICS
# ============================================================================

@router.get("/metrics")
async def get_scheduler_metrics(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Return current scheduler metrics as JSON.

    Requires admin role. Returns counters, timing percentiles, and
    derived rates (conversion, cancellation, etc.).
    """
    user = await get_current_user(request, db)
    if not _is_scheduler_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    from services.scheduler_metrics_service import scheduler_metrics

    return scheduler_metrics.get_summary()


# ============================================================================
# PROMETHEUS FORMAT
# ============================================================================

@router.get("/metrics/prometheus")
async def get_scheduler_metrics_prometheus(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Return scheduler metrics in Prometheus text exposition format.

    Suitable for scraping by a Prometheus server at a /metrics endpoint.
    Requires admin role.
    """
    user = await get_current_user(request, db)
    if not _is_scheduler_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    from services.scheduler_metrics_service import scheduler_metrics

    return PlainTextResponse(
        content=scheduler_metrics.get_prometheus_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


# ============================================================================
# RESET (Platform Admin only)
# ============================================================================

@router.post("/metrics/reset")
async def reset_scheduler_metrics(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Reset all scheduler metrics counters and timings.

    Restricted to platform_admin role. Typically called after metrics
    have been exported to an external system.
    """
    user = await get_current_user(request, db)
    role = getattr(user, 'permission_role', '') or getattr(user, 'role', '') or ''
    if role.lower() != 'platform_admin':
        raise HTTPException(status_code=403, detail="Platform admin access required")

    from services.scheduler_metrics_service import scheduler_metrics

    scheduler_metrics.reset()
    logger.info(f"Scheduler metrics reset by user {user.id}")

    return {"message": "Scheduler metrics reset", "reset_by": user.id}
