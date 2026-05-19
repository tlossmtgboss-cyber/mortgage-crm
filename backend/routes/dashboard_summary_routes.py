"""
Dashboard Summary Routes

GET /api/v1/dashboard/summary — Pipeline summary for iOS background sync.
POST /api/v1/dashboard/summary/invalidate — Clear cached summary for the
    authenticated user's org (call after mutations like creating a loan).

Returns camelCase JSON matching the DashboardData Codable struct in
BackgroundSyncManager.swift (which does NOT use convertFromSnakeCase).

Response shape:
{
    "urgentTaskCount": 3,
    "activeLoanCount": 12,
    "rateAlertCount": 0,
    "newLeadCount": 5,
    "todayAppointmentCount": 2,
    "pipelineSummary": {
        "applicationCount": 4,
        "processingCount": 3,
        "underwritingCount": 2,
        "clearToCloseCount": 3
    }
}
"""

import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, cast, Date
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import require_auth, current_user_dep
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache — Redis-backed via cache_service, with in-memory fallback
# ---------------------------------------------------------------------------
_CACHE_TTL_SECONDS = 30

# In-memory fallback when Redis is unavailable
_CACHE_MAX_SIZE = 100
_cache: dict[int, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def _cache_get(org_id: int) -> dict | None:
    """Return cached response — tries Redis first, falls back to in-memory."""
    try:
        from services.cache_service import cache_get
        redis_val = cache_get(f"pipeline:dashboard:org:{org_id}:summary")
        if redis_val is not None:
            return redis_val
    except Exception as _exc:  # noqa: BLE001
        pass
    # In-memory fallback
    with _cache_lock:
        entry = _cache.get(org_id)
        if entry is None:
            return None
        ts, data = entry
        if time.monotonic() - ts > _CACHE_TTL_SECONDS:
            del _cache[org_id]
            return None
        return data


def _cache_set(org_id: int, data: dict) -> None:
    """Store response in both Redis and in-memory."""
    try:
        from services.cache_service import cache_set
        cache_set(f"pipeline:dashboard:org:{org_id}:summary", data, ttl=_CACHE_TTL_SECONDS)
    except Exception as _exc:  # noqa: BLE001
        pass
    # In-memory fallback
    with _cache_lock:
        if org_id in _cache:
            _cache[org_id] = (time.monotonic(), data)
            return
        if len(_cache) >= _CACHE_MAX_SIZE:
            oldest_key = min(_cache, key=lambda k: _cache[k][0])
            del _cache[oldest_key]
        _cache[org_id] = (time.monotonic(), data)


def _cache_invalidate(org_id: int) -> bool:
    """Remove a single org's cache entry from both Redis and in-memory."""
    try:
        from services.cache_service import cache_delete
        cache_delete(f"pipeline:dashboard:org:{org_id}:summary")
    except Exception as _exc:  # noqa: BLE001
        pass
    with _cache_lock:
        return _cache.pop(org_id, None) is not None


router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
    dependencies=[Depends(require_auth)],
)

# Stages considered terminal — loans in these stages are excluded from "active"
_TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD",
    "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
})

# Stages that count as "closing soon"
_CLOSING_STAGES = frozenset({
    "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT",
})


@router.get("/summary")
async def get_dashboard_summary(
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Pipeline summary consumed by BackgroundSyncManager.swift (iOS background
    fetch) and the Perennia widget extension.

    All counts are scoped to the authenticated user's organization_id.
    Results are cached in-memory for 60 seconds per org.
    """
    from database.models.lead_loan import Lead, Loan
    from database.models.task import Task

    org_id = getattr(current_user, "organization_id", None)
    if org_id is None:
        return _empty_response()

    # Check cache first
    cached = _cache_get(org_id)
    if cached is not None:
        return cached

    try:
        # ------------------------------------------------------------------
        # Active loans (non-terminal) — with stage breakdown in one query
        # ------------------------------------------------------------------
        stage_rows = (
            db.query(Loan.stage, func.count(Loan.id))
            .filter(
                Loan.organization_id == org_id,
                ~Loan.stage.in_(_TERMINAL_STAGES),
            )
            .group_by(Loan.stage)
            .all()
        )

        stage_counts: dict[str, int] = {}
        active_loan_count = 0
        for stage, cnt in stage_rows:
            stage_upper = (stage or "").upper()
            stage_counts[stage_upper] = cnt
            active_loan_count += cnt

        application_count = stage_counts.get("APPLICATION", 0)
        processing_count = (
            stage_counts.get("PROCESSING", 0)
            + stage_counts.get("SUBMITTED", 0)
        )
        underwriting_count = (
            stage_counts.get("UNDERWRITING", 0)
            + stage_counts.get("UW_RECEIVED", 0)
            + stage_counts.get("CONDITIONAL_APPROVAL", 0)
        )
        clear_to_close_count = sum(
            stage_counts.get(s, 0) for s in _CLOSING_STAGES
        )

        # ------------------------------------------------------------------
        # Tasks due today (pending, for this org)
        # ------------------------------------------------------------------
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        today_end = today_start + timedelta(days=1)

        urgent_task_count = (
            db.query(func.count(Task.id))
            .filter(
                Task.organization_id == org_id,
                Task.status.in_(["pending", "in_progress"]),
                Task.due_date < today_end,
            )
            .scalar()
        ) or 0

        # ------------------------------------------------------------------
        # New leads (created in the last 7 days)
        # ------------------------------------------------------------------
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        new_lead_count = (
            db.query(func.count(Lead.id))
            .filter(
                Lead.organization_id == org_id,
                Lead.created_at >= seven_days_ago,
            )
            .scalar()
        ) or 0

        # ------------------------------------------------------------------
        # Rate alerts — RateMonitorAlert has no organization_id column,
        # so we count via the related target's user/mum_client chain.
        # For now return 0; a future join-based query can populate this.
        # ------------------------------------------------------------------
        rate_alert_count = 0

        # ------------------------------------------------------------------
        # Today's appointments — from scheduler_appointments table
        # ------------------------------------------------------------------
        today_appointment_count = 0
        try:
            from database.models.scheduler import Appointment
            today_appointment_count = (
                db.query(func.count(Appointment.id))
                .filter(
                    Appointment.organization_id == org_id,
                    cast(Appointment.scheduled_start, Date) == date.today(),
                    Appointment.status.notin_(["cancelled", "rescheduled"]),
                )
                .scalar()
            ) or 0
        except Exception as _exc:  # noqa: BLE001
            pass

        result = {
            "urgentTaskCount": urgent_task_count,
            "activeLoanCount": active_loan_count,
            "rateAlertCount": rate_alert_count,
            "newLeadCount": new_lead_count,
            "todayAppointmentCount": today_appointment_count,
            "pipelineSummary": {
                "applicationCount": application_count,
                "processingCount": processing_count,
                "underwritingCount": underwriting_count,
                "clearToCloseCount": clear_to_close_count,
            },
        }
        _cache_set(org_id, result)
        return result

    except Exception as e:
        logger.exception(f"Error building dashboard summary: {e}")
        return _empty_response()


@router.post("/summary/invalidate")
async def invalidate_dashboard_cache(
    current_user=Depends(current_user_dep),
):
    """
    Clear the cached dashboard summary for the authenticated user's org.
    Call after mutations (e.g., creating a loan or lead) to force a fresh
    query on the next GET /summary request.
    """
    org_id = getattr(current_user, "organization_id", None)
    if org_id is None:
        return {"invalidated": False}
    removed = _cache_invalidate(org_id)
    return {"invalidated": removed}


def _empty_response() -> dict:
    """Return a valid but zeroed-out dashboard payload."""
    return {
        "urgentTaskCount": 0,
        "activeLoanCount": 0,
        "rateAlertCount": 0,
        "newLeadCount": 0,
        "todayAppointmentCount": 0,
        "pipelineSummary": {
            "applicationCount": 0,
            "processingCount": 0,
            "underwritingCount": 0,
            "clearToCloseCount": 0,
        },
    }
