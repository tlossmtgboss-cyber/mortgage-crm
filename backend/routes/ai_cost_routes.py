"""
AI Cost Tracking Routes

Admin endpoints for viewing AI cost breakdowns, daily trends, per-agent
costs, budget alerts, circuit breaker management, and per-org budget
configuration.

Endpoints:
    GET  /api/v1/ai/costs/summary            — Platform-wide cost summary
    GET  /api/v1/ai/costs/org/{id}           — Org-level cost breakdown
    GET  /api/v1/ai/costs/daily              — Daily cost trend (last N days)
    GET  /api/v1/ai/costs/by-agent           — Cost broken down by agent type
    GET  /api/v1/ai/costs/budget-status      — Current spend vs budget for all orgs
    PUT  /api/v1/ai/costs/org/{id}/budget    — Set daily budget for an org
    GET  /api/v1/ai/costs/alerts             — Recent budget alerts/warnings
    POST /api/v1/ai/costs/reset-circuit/{id} — Manual circuit breaker reset

Registration:
    Called from router_registry.py via register_ai_cost_routes(app, get_db, get_current_user).
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================

class DailyEntry(BaseModel):
    date: str
    cost: float
    tokens: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    requests: int


class AgentCostEntry(BaseModel):
    agent_type: str
    cost: float
    input_tokens: int
    output_tokens: int
    requests: int
    avg_duration_ms: int


class OrgCostEntry(BaseModel):
    organization_id: int
    cost: float
    requests: int


class ModelCostEntry(BaseModel):
    model: str
    cost: float
    requests: int


class PlatformSummaryResponse(BaseModel):
    period_days: int
    total_cost: float
    total_requests: int
    total_tokens: int
    by_org: List[OrgCostEntry]
    by_model: List[ModelCostEntry]
    by_agent: List[Dict[str, Any]]
    daily_trend: List[DailyEntry]


class OrgCostResponse(BaseModel):
    org_id: int
    start_date: str
    end_date: str
    total_cost: float
    total_tokens: int
    request_count: int
    daily_breakdown: List[DailyEntry]
    budget_alert: Optional[str] = None


class AgentCostResponse(BaseModel):
    org_id: int
    period_days: int
    total_cost: float
    agents: List[AgentCostEntry]


class DailyTrendResponse(BaseModel):
    period_days: int
    org_id: Optional[int] = None
    daily: List[DailyEntry]


class OrgBudgetStatusEntry(BaseModel):
    organization_id: int
    org_name: str
    spent_today: float
    daily_budget: float
    usage_pct: float
    circuit_breaker_state: str


class BudgetStatusResponse(BaseModel):
    orgs: List[OrgBudgetStatusEntry]
    total_platform_spend: float


class SetBudgetRequest(BaseModel):
    daily_budget_usd: Optional[float] = Field(
        None,
        description="Daily AI budget in USD. NULL means unlimited.",
        ge=0,
    )


class SetBudgetResponse(BaseModel):
    organization_id: int
    daily_budget_usd: Optional[float]
    message: str


class AlertEntry(BaseModel):
    organization_id: int
    org_name: str
    level: str
    spent_today: float
    daily_budget: float
    usage_pct: float
    message: str


class AlertsResponse(BaseModel):
    alerts: List[AlertEntry]
    count: int


class CircuitResetResponse(BaseModel):
    organization_id: int
    message: str
    previous_state: str


# =============================================================================
# Route Registration
# =============================================================================

def register_ai_cost_routes(app, get_db, get_current_user):
    """Register AI cost tracking routes on the FastAPI app.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.
    get_db : callable
        Dependency that yields a SQLAlchemy Session.
    get_current_user : callable
        Dependency that returns the authenticated user.
    """

    def _require_admin(user):
        """Raise 403 if user is not a platform admin or site admin."""
        role = getattr(user, "role", None) or ""
        is_platform_admin = getattr(user, "is_platform_admin", False)
        if role not in ("Platform Admin", "Site Admin") and not is_platform_admin:
            raise HTTPException(
                status_code=403,
                detail="Admin access required for AI cost data",
            )

    @app.get(
        "/api/v1/ai/costs/summary",
        response_model=PlatformSummaryResponse,
        tags=["AI Cost Tracking"],
        summary="Platform-wide AI cost summary",
    )
    async def get_ai_cost_summary(
        period_days: int = Query(30, ge=1, le=365),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Return platform-wide AI cost summary (admin only).

        Includes total spend, top orgs, model breakdown, agent breakdown,
        and daily trend.
        """
        _require_admin(current_user)

        from services.ai_cost_tracker import AICostTracker
        tracker = AICostTracker(db)
        return tracker.get_platform_cost_summary(period_days=period_days)

    @app.get(
        "/api/v1/ai/costs/org/{org_id}",
        response_model=OrgCostResponse,
        tags=["AI Cost Tracking"],
        summary="Organization AI cost breakdown",
    )
    async def get_ai_cost_by_org(
        org_id: int,
        start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
        end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Return cost breakdown for a specific organization.

        Admins can view any org. Non-admins can only view their own org.
        """
        user_org_id = getattr(current_user, "organization_id", None)
        role = getattr(current_user, "role", None) or ""
        is_platform_admin = getattr(current_user, "is_platform_admin", False)

        # Non-admins can only see their own org
        if (
            role not in ("Platform Admin", "Site Admin")
            and not is_platform_admin
            and user_org_id != org_id
        ):
            raise HTTPException(
                status_code=403,
                detail="You can only view costs for your own organization",
            )

        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        from services.ai_cost_tracker import AICostTracker
        tracker = AICostTracker(db)
        result = tracker.get_org_cost_period(org_id, start_date, end_date)

        # Include budget alert
        alert = tracker.check_budget_alert(org_id)
        result["budget_alert"] = alert

        return result

    @app.get(
        "/api/v1/ai/costs/daily",
        response_model=DailyTrendResponse,
        tags=["AI Cost Tracking"],
        summary="Daily AI cost trend",
    )
    async def get_ai_cost_daily_trend(
        period_days: int = Query(30, ge=1, le=365),
        org_id: Optional[int] = Query(None, description="Filter by org (admin only for cross-org)"),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Return daily cost trend for the last N days.

        Platform admins can view any org or the whole platform.
        Non-admins are restricted to their own org.
        """
        user_org_id = getattr(current_user, "organization_id", None)
        role = getattr(current_user, "role", None) or ""
        is_platform_admin = getattr(current_user, "is_platform_admin", False)

        # Non-admins are scoped to their own org
        if role not in ("Platform Admin", "Site Admin") and not is_platform_admin:
            org_id = user_org_id

        from services.ai_cost_tracker import AICostTracker
        tracker = AICostTracker(db)
        daily = tracker.get_daily_trend(org_id=org_id, period_days=period_days)

        return {
            "period_days": period_days,
            "org_id": org_id,
            "daily": daily,
        }

    @app.get(
        "/api/v1/ai/costs/by-agent",
        response_model=AgentCostResponse,
        tags=["AI Cost Tracking"],
        summary="AI cost by agent type",
    )
    async def get_ai_cost_by_agent(
        org_id: Optional[int] = Query(None, description="Organization ID"),
        period_days: int = Query(30, ge=1, le=365),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Return cost breakdown by agent type for an organization.

        Platform admins can view any org. Non-admins see their own org.
        """
        user_org_id = getattr(current_user, "organization_id", None)
        role = getattr(current_user, "role", None) or ""
        is_platform_admin = getattr(current_user, "is_platform_admin", False)

        # Default to user's own org if not specified
        if org_id is None:
            org_id = user_org_id

        # Non-admins can only see their own org
        if (
            role not in ("Platform Admin", "Site Admin")
            and not is_platform_admin
            and user_org_id != org_id
        ):
            raise HTTPException(
                status_code=403,
                detail="You can only view costs for your own organization",
            )

        if org_id is None:
            raise HTTPException(
                status_code=400,
                detail="org_id is required",
            )

        from services.ai_cost_tracker import AICostTracker
        tracker = AICostTracker(db)
        return tracker.get_cost_by_agent(org_id=org_id, period_days=period_days)

    # ------------------------------------------------------------------
    # Budget Status (all orgs)
    # ------------------------------------------------------------------

    @app.get(
        "/api/v1/ai/costs/budget-status",
        response_model=BudgetStatusResponse,
        tags=["AI Cost Tracking"],
        summary="Budget status for all orgs",
    )
    async def get_ai_budget_status(
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Return current spend vs budget for all organizations (admin only).

        Includes circuit breaker state for each org.
        """
        _require_admin(current_user)

        from services.ai_cost_tracker import AICostTracker
        tracker = AICostTracker(db)
        orgs = tracker.get_all_budget_status()
        total_spend = sum(o["spent_today"] for o in orgs)

        return {
            "orgs": orgs,
            "total_platform_spend": round(total_spend, 2),
        }

    # ------------------------------------------------------------------
    # Set Org Budget
    # ------------------------------------------------------------------

    @app.put(
        "/api/v1/ai/costs/org/{org_id}/budget",
        response_model=SetBudgetResponse,
        tags=["AI Cost Tracking"],
        summary="Set daily AI budget for an org",
    )
    async def set_ai_org_budget(
        org_id: int,
        body: SetBudgetRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Set or remove the daily AI budget for an organization (admin only).

        Set ``daily_budget_usd`` to a positive number to enforce a limit,
        or to ``null`` to remove the cap (unlimited).
        """
        _require_admin(current_user)

        from sqlalchemy import text as sql_text

        # Verify org exists
        org_row = await db.execute(sql_text(
            "SELECT id, name FROM organizations WHERE id = :org_id"
        ), {"org_id": org_id}).fetchone()

        if not org_row:
            raise HTTPException(status_code=404, detail=f"Organization {org_id} not found")

        budget_value = body.daily_budget_usd
        await db.execute(sql_text(
            "UPDATE organizations SET ai_daily_budget_usd = :budget WHERE id = :org_id"
        ), {"budget": budget_value, "org_id": org_id})
        await db.commit()

        # Also update the in-memory budget tracker
        try:
            from middleware.ai_cost_tracker import get_ai_budget_tracker
            tracker = get_ai_budget_tracker()
            if budget_value is not None:
                tracker.set_org_budget(org_id, budget_value)
        except Exception as e:
            logger.debug("Failed to update in-memory budget tracker: %s", e)

        budget_str = f"${budget_value:.2f}" if budget_value is not None else "unlimited"
        logger.info(
            "AI budget updated: org=%d budget=%s by user=%s",
            org_id, budget_str, getattr(current_user, "id", "?"),
        )

        return {
            "organization_id": org_id,
            "daily_budget_usd": budget_value,
            "message": f"Daily AI budget set to {budget_str} for {org_row[1]}",
        }

    # ------------------------------------------------------------------
    # Budget Alerts
    # ------------------------------------------------------------------

    @app.get(
        "/api/v1/ai/costs/alerts",
        response_model=AlertsResponse,
        tags=["AI Cost Tracking"],
        summary="Recent budget alerts across platform",
    )
    async def get_ai_budget_alerts(
        limit: int = Query(50, ge=1, le=200),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Return recent budget alerts/warnings across all orgs (admin only).

        Lists all orgs that have crossed the 75% warning threshold today.
        """
        _require_admin(current_user)

        from services.ai_cost_tracker import AICostTracker
        tracker = AICostTracker(db)
        alerts = tracker.get_recent_alerts(limit=limit)

        return {
            "alerts": alerts,
            "count": len(alerts),
        }

    # ------------------------------------------------------------------
    # Circuit Breaker Reset
    # ------------------------------------------------------------------

    @app.post(
        "/api/v1/ai/costs/reset-circuit/{org_id}",
        response_model=CircuitResetResponse,
        tags=["AI Cost Tracking"],
        summary="Reset circuit breaker for an org",
    )
    async def reset_ai_circuit_breaker(
        org_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Manually reset the circuit breaker for an organization (admin only).

        Use this when an org's budget has been exceeded but needs to be
        unblocked immediately (e.g., after increasing their budget).
        """
        _require_admin(current_user)

        from services.ai_cost_tracker import (
            _get_circuit_breaker_state,
            reset_circuit_breaker,
        )

        previous_state = _get_circuit_breaker_state(org_id)
        reset_circuit_breaker(org_id)

        logger.info(
            "Circuit breaker reset: org=%d previous_state=%s by user=%s",
            org_id, previous_state, getattr(current_user, "id", "?"),
        )

        return {
            "organization_id": org_id,
            "message": f"Circuit breaker reset for organization {org_id}",
            "previous_state": previous_state,
        }

    logger.info("AI cost tracking routes registered (8 endpoints)")
