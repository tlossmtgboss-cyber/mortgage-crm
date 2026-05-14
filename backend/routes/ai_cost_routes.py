"""
AI Cost Tracking Routes

Admin endpoints for viewing AI cost breakdowns, daily trends, per-agent
costs, and budget alerts. All endpoints require admin role.

Endpoints:
    GET /api/v1/ai/costs/summary     — Platform-wide cost summary
    GET /api/v1/ai/costs/org/{id}    — Org-level cost breakdown
    GET /api/v1/ai/costs/daily       — Daily cost trend (last N days)
    GET /api/v1/ai/costs/by-agent    — Cost broken down by agent type

Registration:
    Called from main.py via register_ai_cost_routes(app, get_db, get_current_user).
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
        db: Session = Depends(get_db),
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
        db: Session = Depends(get_db),
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
        db: Session = Depends(get_db),
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
        db: Session = Depends(get_db),
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

    logger.info("AI cost tracking routes registered (4 endpoints)")
