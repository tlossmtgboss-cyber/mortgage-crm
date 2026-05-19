"""
Mobile Dashboard Routes

GET /api/v1/mobile/dashboard  — Pipeline summary for the iOS PerenniaWidget
GET /api/v1/mobile/pipeline   — Stage breakdown for the iOS PerenniaWidget

These proxy the existing dashboard_summary logic into the JSON shapes
expected by NetworkService.swift (fetchDashboard / fetchPipelineStages).

mobile/dashboard response:
{
    "pipeline": { "active": 12, "closing_soon": 3, "volume": 4250000.0 },
    "tasks_due_today": 3,
    "recent_activity": [
        { "summary": "New lead: Jane Doe", "type": "lead", "time": "2026-04-10T..." }
    ]
}

mobile/pipeline response:
{
    "stage_counts": { "APPLICATION": 4, "PROCESSING": 3, ... },
    "total_count": 12,
    "total_volume": 4250000.0
}
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import require_auth, current_user_dep

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache — Redis-backed via cache_service, with in-memory fallback
# ---------------------------------------------------------------------------
_dashboard_cache: dict[int, dict] = {}
_pipeline_cache: dict[int, dict] = {}

_DASHBOARD_TTL = 30   # seconds
_PIPELINE_TTL = 30    # seconds


def _get_cached(cache: dict, user_id: int, redis_prefix: str = "") -> dict | None:
    """Return cached data — tries Redis first, falls back to in-memory."""
    if redis_prefix and user_id is not None:
        try:
            from services.cache_service import cache_get
            redis_val = cache_get(f"{redis_prefix}:{user_id}")
            if redis_val is not None:
                return redis_val
        except Exception as _exc:  # noqa: BLE001
            pass
    # In-memory fallback
    entry = cache.get(user_id)
    if entry and entry["expires"] > time.time():
        return entry["data"]
    cache.pop(user_id, None)
    return None


def _set_cached(cache: dict, user_id: int, data: dict, ttl: int, redis_prefix: str = "") -> None:
    """Store data in both Redis and in-memory cache."""
    if redis_prefix and user_id is not None:
        try:
            from services.cache_service import cache_set
            cache_set(f"{redis_prefix}:{user_id}", data, ttl=ttl)
        except Exception as _exc:  # noqa: BLE001
            pass
    cache[user_id] = {"data": data, "expires": time.time() + ttl}


def _json_with_cache_control(data: dict, max_age: int) -> JSONResponse:
    """Wrap a dict in a JSONResponse with a Cache-Control header."""
    return JSONResponse(
        content=data,
        headers={"Cache-Control": f"private, max-age={max_age}"},
    )

router = APIRouter(
    prefix="/api/v1/mobile",
    tags=["Mobile Dashboard"],
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


@router.get("/dashboard")
async def mobile_dashboard(
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """
    Pipeline summary consumed by PerenniaWidget's NetworkService.fetchDashboard().

    Returns pipeline counts, tasks due today, and recent activity — all scoped
    to the authenticated user's organization.
    """
    from database.models.lead_loan import Lead, Loan
    from database.models.task import Task

    user_id = getattr(current_user, "id", None)
    org_id = getattr(current_user, "organization_id", None)
    if org_id is None:
        return _empty_dashboard()

    # Check cache
    if user_id is not None:
        cached = _get_cached(_dashboard_cache, user_id, redis_prefix=f"pipeline:mobile_dash:org:{org_id}")
        if cached is not None:
            return _json_with_cache_control(cached, _DASHBOARD_TTL)

    try:
        # ----------------------------------------------------------------------
        # Active loans with stage breakdown
        # ----------------------------------------------------------------------
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

        closing_soon = sum(stage_counts.get(s, 0) for s in _CLOSING_STAGES)

        # ----------------------------------------------------------------------
        # Total pipeline volume (amount for active loans)
        # ----------------------------------------------------------------------
        volume = (
            db.query(func.coalesce(func.sum(Loan.amount), 0))
            .filter(
                Loan.organization_id == org_id,
                ~Loan.stage.in_(_TERMINAL_STAGES),
            )
            .scalar()
        ) or 0
        volume = float(volume)

        # ----------------------------------------------------------------------
        # Tasks due today
        # ----------------------------------------------------------------------
        today_end = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        ) + timedelta(days=1)

        tasks_due_today = (
            db.query(func.count(Task.id))
            .filter(
                Task.organization_id == org_id,
                Task.status.in_(["pending", "in_progress"]),
                Task.due_date < today_end,
            )
            .scalar()
        ) or 0

        # ----------------------------------------------------------------------
        # Recent activity — latest leads created in the last 7 days
        # ----------------------------------------------------------------------
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent_leads = (
            db.query(Lead)
            .filter(
                Lead.organization_id == org_id,
                Lead.created_at >= seven_days_ago,
            )
            .order_by(Lead.created_at.desc())
            .limit(5)
            .all()
        )

        recent_activity = []
        for lead in recent_leads:
            name_parts = [
                getattr(lead, "first_name", None) or "",
                getattr(lead, "last_name", None) or "",
            ]
            name = " ".join(p for p in name_parts if p).strip() or "Unknown"
            recent_activity.append({
                "summary": f"New lead: {name}",
                "type": "lead",
                "time": (
                    lead.created_at.isoformat()
                    if getattr(lead, "created_at", None)
                    else None
                ),
            })

        result = {
            "pipeline": {
                "active": active_loan_count,
                "closing_soon": closing_soon,
                "volume": volume,
            },
            "tasks_due_today": tasks_due_today,
            "recent_activity": recent_activity,
        }

        if user_id is not None:
            _set_cached(_dashboard_cache, user_id, result, _DASHBOARD_TTL, redis_prefix=f"pipeline:mobile_dash:org:{org_id}")

        return _json_with_cache_control(result, _DASHBOARD_TTL)

    except Exception as e:
        logger.exception(f"Error building mobile dashboard: {e}")
        return _empty_dashboard()


@router.get("/pipeline")
async def mobile_pipeline(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """
    Pipeline stage breakdown consumed by PerenniaWidget's
    NetworkService.fetchPipelineStages().

    Returns per-stage loan counts and totals, scoped to the authenticated
    user's organization.
    """
    from database.models.lead_loan import Loan

    user_id = getattr(current_user, "id", None)
    org_id = getattr(current_user, "organization_id", None)
    if org_id is None:
        return {"stage_counts": {}, "total_count": 0, "total_volume": 0}

    # Check cache (keyed by user_id only — limit/offset are informational,
    # the query itself ignores them for stage aggregation)
    if user_id is not None:
        cached = _get_cached(_pipeline_cache, user_id, redis_prefix=f"pipeline:mobile_pipe:org:{org_id}")
        if cached is not None:
            return _json_with_cache_control(cached, _PIPELINE_TTL)

    try:
        # Per-stage counts (non-terminal only)
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
        total_count = 0
        for stage, cnt in stage_rows:
            stage_upper = (stage or "").upper()
            stage_counts[stage_upper] = cnt
            total_count += cnt

        # Total volume
        total_volume = (
            db.query(func.coalesce(func.sum(Loan.amount), 0))
            .filter(
                Loan.organization_id == org_id,
                ~Loan.stage.in_(_TERMINAL_STAGES),
            )
            .scalar()
        ) or 0
        total_volume = float(total_volume)

        result = {
            "stage_counts": stage_counts,
            "total_count": total_count,
            "total_volume": total_volume,
        }

        if user_id is not None:
            _set_cached(_pipeline_cache, user_id, result, _PIPELINE_TTL, redis_prefix=f"pipeline:mobile_pipe:org:{org_id}")

        return _json_with_cache_control(result, _PIPELINE_TTL)

    except Exception as e:
        logger.exception(f"Error building mobile pipeline: {e}")
        return {"stage_counts": {}, "total_count": 0, "total_volume": 0}


def _empty_dashboard() -> dict:
    """Zeroed-out mobile dashboard payload."""
    return {
        "pipeline": {
            "active": 0,
            "closing_soon": 0,
            "volume": 0.0,
        },
        "tasks_due_today": 0,
        "recent_activity": [],
    }
