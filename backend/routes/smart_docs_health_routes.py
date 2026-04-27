"""
Smart Docs V2 Health Check & Canary Deployment Routes

Provides health, readiness, liveness, and canary deployment endpoints:

    GET  /health             - Overall health (public, minimal response)
    GET  /health/detailed    - Per-component health (admin only)
    GET  /health/ready       - Readiness probe (public, minimal response)
    GET  /health/live        - Liveness probe (public, minimal response)
    GET  /version            - Version/git SHA/deployed_at (auth required)
    GET  /features           - Feature manifest (auth required)
    POST /health/smoke-test  - Run smoke test (admin only)
    GET  /health/deploy-metrics - Deployment metrics (admin only)

Mounted under /api/smart-docs via smart_docs_v2_registration.py.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Smart Docs Health"])


# =============================================================================
# Helpers
# =============================================================================

def _get_org_id(current_user) -> int:
    """Extract organization_id from the authenticated user."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")
    return org_id


def _require_admin(current_user) -> None:
    """Raise 403 if the user is not a platform or site admin."""
    role = getattr(current_user, "permission_role", "")
    if role not in ("admin", "site_admin"):
        raise HTTPException(
            status_code=403,
            detail="Admin access required for this endpoint",
        )


def _get_health_service():
    """Lazy import to avoid circular imports at module load."""
    from services.smart_docs.health_check_service import get_health_check_service
    return get_health_check_service()


# =============================================================================
# GET /health - Overall health (public, no auth)
# =============================================================================

@router.get("/health")
async def smart_docs_health(
    db: Session = Depends(get_db),
):
    """
    Overall health check for Smart Docs V2.

    Public endpoint suitable for load-balancer health probes.
    Returns ``status``: healthy | degraded | unhealthy.
    """
    try:
        svc = _get_health_service()

        db_health = await svc.check_database_health(db)
        circuit_health = await svc.check_circuit_breaker_status()

        # Quick aggregate: only DB and circuit breaker for the lightweight check
        statuses = [db_health.status, circuit_health.status]

        if "unhealthy" in statuses:
            overall = "unhealthy"
        elif "degraded" in statuses:
            overall = "degraded"
        else:
            overall = "healthy"

        return {"status": overall}
    except Exception as e:
        logger.error("Health check endpoint failed: %s", e)
        return {"status": "unhealthy"}


# =============================================================================
# GET /health/detailed - Per-component health (admin only)
# =============================================================================

@router.get("/health/detailed")
async def smart_docs_health_detailed(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Detailed per-component health check for Smart Docs V2.

    Admin only. Runs all component health checks and returns full details
    including latency, configuration state, and component-specific diagnostics.
    """
    _require_admin(current_user)

    svc = _get_health_service()
    report = await svc.check_all_components(db)

    # Include deployment metrics in the detailed report
    report["deployment"] = svc.get_deployment_metrics()
    report["version"] = svc.get_version_info()

    return report


# =============================================================================
# GET /health/ready - Readiness probe (public, for deployment)
# =============================================================================

@router.get("/health/ready")
async def smart_docs_readiness(
    db: Session = Depends(get_db),
):
    """
    Readiness probe for Smart Docs V2.

    Public endpoint for deployment orchestrator (Kubernetes, Railway).
    Returns ``status: healthy | unhealthy``.
    """
    try:
        svc = _get_health_service()
        result = await svc.check_readiness(db)

        if not result["ready"]:
            raise HTTPException(status_code=503, detail={"status": "unhealthy"})

        return {"status": "healthy"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Readiness probe failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy"},
        )


# =============================================================================
# GET /health/live - Liveness probe (public, for orchestrator)
# =============================================================================

@router.get("/health/live")
async def smart_docs_liveness():
    """
    Liveness probe for Smart Docs V2.

    Public endpoint for deployment orchestrator.
    Returns ``status: healthy | unhealthy``.
    """
    try:
        svc = _get_health_service()
        result = await svc.check_liveness()

        if not result["alive"]:
            raise HTTPException(status_code=503, detail={"status": "unhealthy"})

        return {"status": "healthy"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Liveness probe failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy"},
        )


# =============================================================================
# GET /version - Version info
# =============================================================================

@router.get("/version")
async def smart_docs_version(
    current_user=Depends(get_current_user),
):
    """
    Smart Docs V2 version information.

    Authenticated endpoint. Returns version, git SHA, and deployment timestamp.
    """
    svc = _get_health_service()
    return svc.get_version_info()


# =============================================================================
# GET /features - Feature manifest
# =============================================================================

@router.get("/features")
async def smart_docs_features(
    current_user=Depends(get_current_user),
):
    """
    Smart Docs V2 feature manifest.

    Authenticated endpoint. Returns list of all registered features.
    """
    svc = _get_health_service()
    return svc.get_feature_manifest()


# =============================================================================
# POST /health/smoke-test - Smoke test (admin only)
# =============================================================================

@router.post("/health/smoke-test")
async def smart_docs_smoke_test(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Run a mini integration smoke test for Smart Docs V2.

    Admin only. Exercises the critical path:
    database -> classify -> extract -> encrypt -> search -> cleanup.

    Returns pass/fail with step-by-step timing.
    """
    _require_admin(current_user)

    org_id = _get_org_id(current_user)

    svc = _get_health_service()
    result = await svc.run_smoke_test(db, org_id=org_id)

    response = result.to_dict()
    response["version"] = svc.get_version_info()

    return response


# =============================================================================
# GET /health/deploy-metrics - Deployment metrics (admin only)
# =============================================================================

@router.get("/health/deploy-metrics")
async def smart_docs_deploy_metrics(
    current_user=Depends(get_current_user),
):
    """
    Deployment metrics for Smart Docs V2.

    Admin only. Returns request counts, error rates, and auto-rollback signal
    since the current deployment started.

    If ``rollback_signal`` is true, the error rate has exceeded the configured
    threshold (default 5%) within the sliding window.
    """
    _require_admin(current_user)

    svc = _get_health_service()
    metrics = svc.get_deployment_metrics()
    metrics["version"] = svc.get_version_info()

    return metrics
