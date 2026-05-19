"""
Admin Scheduler Status Routes

Provides admin endpoints to inspect the unified scheduler:
  GET /api/v1/admin/scheduler/status  — List all jobs with last run, next run, status
  GET /api/v1/admin/scheduler/jobs    — Detailed job listing grouped by domain

Requires ADMIN_API_KEY authentication via X-API-Key header.
"""

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/scheduler", tags=["Admin Scheduler"])

_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


def _verify_admin_key(request: Request) -> None:
    """Validate admin API key from X-API-Key header. Fail-closed if not configured."""
    if not _ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin key not configured")
    provided = request.headers.get("X-API-Key", "")
    if not provided or not secrets.compare_digest(provided, _ADMIN_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid admin key")


@router.get("/status")
async def scheduler_status(request: Request):
    """Get scheduler status with all registered jobs.

    Returns:
      - scheduler_running: whether APScheduler is running
      - advisory_lock_held: whether this replica holds the PostgreSQL advisory lock
      - total_jobs: number of registered jobs
      - jobs: list of job status dicts with next_run, last_run, duration, status
    """
    _verify_admin_key(request)

    try:
        from services.scheduler_service import scheduler_service, _advisory_lock_conn
    except ImportError:
        return JSONResponse(
            status_code=503,
            content={"error": "scheduler_service not available"},
        )

    try:
        running = scheduler_service.scheduler.running
    except Exception as _exc:  # noqa: BLE001
        logger.exception("unhandled exception")
        running = False

    jobs = scheduler_service.get_job_status()

    # Check advisory lock status
    advisory_lock_held = _advisory_lock_conn is not None

    # Check Redis lock service availability
    redis_available = False
    try:
        from services.distributed_lock import get_lock_service
        lock_svc = get_lock_service()
        redis = lock_svc._get_redis()
        redis_available = redis is not None
    except Exception as _exc:  # noqa: BLE001
        pass

    return {
        "scheduler_running": running,
        "advisory_lock_held": advisory_lock_held,
        "redis_available": redis_available,
        "total_jobs": len(jobs),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "jobs": jobs,
    }


@router.get("/jobs")
async def scheduler_jobs(request: Request):
    """Get detailed job listing grouped by domain.

    Returns registry entries enriched with runtime status:
      - name, domain, description, trigger info
      - next_run time
      - last_run info (start, end, duration_ms, status, error)
      - lock_ttl setting
    """
    _verify_admin_key(request)

    try:
        from services.scheduler_service import scheduler_service
    except ImportError:
        return JSONResponse(
            status_code=503,
            content={"error": "scheduler_service not available"},
        )

    all_jobs = scheduler_service.list_jobs()

    # Group by domain
    by_domain: Dict[str, List[Dict[str, Any]]] = {}
    for job in all_jobs:
        domain = job.get("domain", "unknown")
        by_domain.setdefault(domain, []).append(job)

    return {
        "total_jobs": len(all_jobs),
        "domains": list(by_domain.keys()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "by_domain": by_domain,
    }
