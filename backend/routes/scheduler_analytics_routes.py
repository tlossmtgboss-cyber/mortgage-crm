"""
Scheduler Analytics Routes - Appointment-to-Funded-Loan Conversion Tracking

Endpoints:
- GET /api/v1/scheduler/analytics/funnel       - Conversion funnel
- GET /api/v1/scheduler/analytics/sources       - Source performance
- GET /api/v1/scheduler/analytics/lo-performance - LO comparison
- GET /api/v1/scheduler/analytics/time-heatmap  - Day/hour heatmap
- GET /api/v1/scheduler/analytics/revenue       - Revenue attribution
- GET /api/v1/scheduler/analytics/ai-performance - AI vs manual bookings
- GET /api/v1/scheduler/analytics/trends        - Week-over-week trends
- POST /api/v1/scheduler/analytics/track-outcome - Record appointment outcome
- POST /api/v1/scheduler/analytics/link-lead     - Link appointment to lead
- POST /api/v1/scheduler/analytics/link-loan     - Link appointment to loan
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_async_db
from routes.auth_deps import require_auth, current_user_dep

from services.conversion_analytics import (
    track_appointment_outcome,
    link_appointment_to_lead,
    link_appointment_to_loan,
    get_conversion_funnel,
    get_source_performance,
    get_lo_conversion_rates,
    get_time_analytics,
    get_revenue_attribution,
    get_ai_vs_manual_comparison,
    get_weekly_trends,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/scheduler/analytics",
    tags=["Scheduler Analytics"],
    dependencies=[Depends(require_auth)],
)


# ============================================================================
# Request/Response Schemas
# ============================================================================

class TrackOutcomeRequest(BaseModel):
    appointment_id: int
    outcome: str = Field(..., description="showed | no_show | cancelled | rescheduled")


class LinkLeadRequest(BaseModel):
    appointment_id: int
    lead_id: int


class LinkLoanRequest(BaseModel):
    appointment_id: int
    loan_id: int


# ============================================================================
# Helpers
# ============================================================================

def _get_org_id(user) -> int:
    """Extract organization_id from the authenticated user, raise 403 if missing."""
    org_id = getattr(user, "organization_id", None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


# ============================================================================
# Mutation endpoints
# ============================================================================

@router.post("/track-outcome")
async def api_track_outcome(
    body: TrackOutcomeRequest,
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Record an appointment outcome (showed, no_show, cancelled, rescheduled)."""
    result = await track_appointment_outcome(body.appointment_id, body.outcome, db)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/link-lead")
async def api_link_lead(
    body: LinkLeadRequest,
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Associate an appointment with a lead for conversion tracking."""
    result = await link_appointment_to_lead(body.appointment_id, body.lead_id, db)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/link-loan")
async def api_link_loan(
    body: LinkLoanRequest,
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Associate an appointment with a loan for revenue attribution."""
    result = await link_appointment_to_loan(body.appointment_id, body.loan_id, db)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ============================================================================
# Analytics read endpoints
# ============================================================================

@router.get("/funnel")
async def api_conversion_funnel(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Full booking-to-funded conversion funnel."""
    org_id = _get_org_id(current_user)
    return await get_conversion_funnel(org_id, start_date, end_date, db)


@router.get("/sources")
async def api_source_performance(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Conversion metrics broken down by booking source."""
    org_id = _get_org_id(current_user)
    return await get_source_performance(org_id, start_date, end_date, db)


@router.get("/lo-performance")
async def api_lo_performance(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Per-LO appointment conversion leaderboard."""
    org_id = _get_org_id(current_user)
    return await get_lo_conversion_rates(org_id, start_date, end_date, db)


@router.get("/time-heatmap")
async def api_time_heatmap(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Day-of-week x hour-of-day appointment performance heatmap."""
    org_id = _get_org_id(current_user)
    return await get_time_analytics(org_id, start_date, end_date, db)


@router.get("/revenue")
async def api_revenue_attribution(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Revenue attributed to appointments with monthly trend."""
    org_id = _get_org_id(current_user)
    return await get_revenue_attribution(org_id, start_date, end_date, db)


@router.get("/ai-performance")
async def api_ai_performance(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Compare AI-booked vs manually-booked appointment performance."""
    org_id = _get_org_id(current_user)
    return await get_ai_vs_manual_comparison(org_id, start_date, end_date, db)


@router.get("/trends")
async def api_weekly_trends(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Week-over-week appointment and conversion trends."""
    org_id = _get_org_id(current_user)
    return await get_weekly_trends(org_id, start_date, end_date, db)
