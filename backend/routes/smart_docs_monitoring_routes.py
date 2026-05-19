"""
Smart Docs Monitoring & Health Check Routes

Provides observability endpoints for the Smart Docs V2 subsystem:
    GET /monitoring/health       - System health (lightweight, for load balancers)
    GET /monitoring/metrics      - Processing metrics (admin only)
    GET /monitoring/sla          - SLA compliance report
    GET /monitoring/costs        - AI cost report (admin only)
    GET /monitoring/errors       - Error report (admin only)
    GET /monitoring/dashboard    - Combined dashboard data

All endpoints except /health require authentication. Admin-only endpoints
require platform admin or site admin role.

Mounted under /api/smart-docs via smart_docs_v2_registration.py.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_async_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Smart Docs Monitoring"])


# =============================================================================
# Helpers
# =============================================================================

def _get_org_id(current_user) -> Optional[int]:
    """Extract organization_id from the authenticated user."""
    return getattr(current_user, "organization_id", None)


def _require_admin(current_user) -> None:
    """Raise 403 if the user is not a platform or site admin."""
    role = getattr(current_user, "permission_role", "")
    if role not in ("admin", "site_admin"):
        raise HTTPException(
            status_code=403,
            detail="Admin access required for this endpoint",
        )


def _get_monitoring_service():
    """Lazy import to avoid circular imports at module load."""
    from services.smart_docs.monitoring_service import get_monitoring_service
    return get_monitoring_service()


# =============================================================================
# GET /monitoring/health — System health (lightweight)
# =============================================================================

@router.get("/monitoring/health")
async def smart_docs_health(
    db: AsyncSession = Depends(get_async_db),
):
    """
    System health check for Smart Docs V2.

    Lightweight endpoint suitable for load-balancer health probes.
    Does not require authentication.

    Returns status: healthy | degraded | unhealthy with component details.
    """
    try:
        svc = _get_monitoring_service()
        health = svc.get_system_health(db)
        return health
    except Exception as e:
        logger.error("Health check endpoint failed: %s", e)
        return {
            "status": "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": "Health check failed",
        }


# =============================================================================
# GET /monitoring/metrics — Processing metrics (admin only)
# =============================================================================

@router.get("/monitoring/metrics")
async def smart_docs_metrics(
    hours: int = Query(24, ge=1, le=720, description="Lookback period in hours"),
    org_id: Optional[int] = Query(None, description="Filter by org (admin only, default: all)"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """
    Processing metrics for Smart Docs V2.

    Admin only. Returns operation counts, latency percentiles, success
    rates, estimated AI costs, and cache statistics.
    """
    _require_admin(current_user)

    # Non-admins can only see their own org
    effective_org_id = org_id
    if effective_org_id is None:
        user_role = getattr(current_user, "permission_role", "")
        if user_role != "admin":
            effective_org_id = _get_org_id(current_user)

    svc = _get_monitoring_service()
    return svc.get_processing_metrics(org_id=effective_org_id, hours=hours)


# =============================================================================
# GET /monitoring/sla — SLA compliance report
# =============================================================================

@router.get("/monitoring/sla")
async def smart_docs_sla(
    hours: int = Query(24, ge=1, le=720, description="Lookback period in hours"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """
    SLA compliance metrics for Smart Docs V2.

    Shows per-operation compliance against SLA targets:
    - Document classification: < 30 seconds
    - Document review: < 2 minutes
    - Follow-up send: < 1 hour after trigger
    - Income calculation: < 5 minutes
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    svc = _get_monitoring_service()
    return svc.get_sla_metrics(org_id=org_id, hours=hours)


# =============================================================================
# GET /monitoring/costs — AI cost report (admin only)
# =============================================================================

@router.get("/monitoring/costs")
async def smart_docs_costs(
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    org_id: Optional[int] = Query(None, description="Filter by org (admin only)"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """
    AI cost report for Smart Docs V2.

    Admin only. Shows cost breakdown by operation, daily trend, projected
    monthly cost, top consumers, and cache savings estimate.
    """
    _require_admin(current_user)

    effective_org_id = org_id
    if effective_org_id is None:
        user_role = getattr(current_user, "permission_role", "")
        if user_role != "admin":
            effective_org_id = _get_org_id(current_user)

    svc = _get_monitoring_service()
    return svc.get_ai_cost_report(org_id=effective_org_id, days=days)


# =============================================================================
# GET /monitoring/errors — Error report (admin only)
# =============================================================================

@router.get("/monitoring/errors")
async def smart_docs_errors(
    hours: int = Query(24, ge=1, le=720, description="Lookback period in hours"),
    org_id: Optional[int] = Query(None, description="Filter by org (admin only)"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """
    Error report for Smart Docs V2.

    Admin only. Shows error counts by service, most common error types,
    recent failed operations, and circuit breaker trip history.
    """
    _require_admin(current_user)

    effective_org_id = org_id
    if effective_org_id is None:
        user_role = getattr(current_user, "permission_role", "")
        if user_role != "admin":
            effective_org_id = _get_org_id(current_user)

    svc = _get_monitoring_service()
    return svc.get_error_report(org_id=effective_org_id, hours=hours)


# =============================================================================
# GET /monitoring/dashboard — Combined dashboard data
# =============================================================================

@router.get("/monitoring/dashboard")
async def smart_docs_monitoring_dashboard(
    hours: int = Query(24, ge=1, le=720, description="Lookback period in hours"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """
    Combined monitoring dashboard for Smart Docs V2.

    Returns health, metrics, SLA, and error data in a single response
    to minimize frontend round-trips.

    Non-admin users see their own org only. Admins see all orgs.
    """
    org_id = _get_org_id(current_user)
    is_admin = getattr(current_user, "permission_role", "") in ("admin", "site_admin")

    svc = _get_monitoring_service()

    dashboard: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Health (available to all)
    try:
        dashboard["health"] = svc.get_system_health(db)
    except Exception as e:
        logger.error("Dashboard: health check failed: %s", e)
        dashboard["health"] = {"status": "unknown", "error": str(e)[:200]}

    # SLA (scoped to user's org)
    if org_id:
        try:
            dashboard["sla"] = svc.get_sla_metrics(org_id=org_id, hours=hours)
        except Exception as e:
            logger.error("Dashboard: SLA metrics failed: %s", e)
            dashboard["sla"] = {"error": str(e)[:200]}
    else:
        dashboard["sla"] = {"message": "No organization context"}

    # Metrics and errors (admin only gets full view)
    if is_admin:
        try:
            dashboard["metrics"] = svc.get_processing_metrics(
                org_id=None, hours=hours,
            )
        except Exception as e:
            logger.error("Dashboard: metrics failed: %s", e)
            dashboard["metrics"] = {"error": str(e)[:200]}

        try:
            dashboard["errors"] = svc.get_error_report(
                org_id=None, hours=hours,
            )
        except Exception as e:
            logger.error("Dashboard: error report failed: %s", e)
            dashboard["errors"] = {"error": str(e)[:200]}
    else:
        # Non-admins get scoped metrics, no error details
        if org_id:
            try:
                dashboard["metrics"] = svc.get_processing_metrics(
                    org_id=org_id, hours=hours,
                )
            except Exception as e:
                logger.error("Dashboard: metrics failed: %s", e)
                dashboard["metrics"] = {"error": str(e)[:200]}

    return dashboard
