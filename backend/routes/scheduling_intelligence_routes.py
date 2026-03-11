"""
Scheduling Intelligence Routes
================================
Endpoints exposing the continuous learning system for scheduling optimization.

Prefix: /api/v1/scheduler/intelligence

Auth: Bearer token via auth.dependencies.get_current_user
DB:   SQLAlchemy session via db.get_db
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scheduler/intelligence", tags=["Scheduling Intelligence"])


def _get_org_id(current_user) -> int:
    """Extract organization_id from the authenticated user."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")
    return org_id


# ---------------------------------------------------------------------------
# 1. Weekly Insights Digest
# ---------------------------------------------------------------------------

@router.get("/insights")
async def get_scheduling_insights(
    days: int = Query(default=30, ge=7, le=365, description="Analysis period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get weekly scheduling intelligence insights.

    Returns human-readable insights like:
    - "Tuesday 10am has 85% show rate vs 60% for Friday 4pm"
    - "Referral leads convert 3x better with LO Sarah"
    - "Pre-appointment SMS reduces no-shows by 40%"
    """
    from services.scheduling_intelligence import generate_insights

    org_id = _get_org_id(current_user)

    try:
        result = await generate_insights(org_id=org_id, db=db, days=days)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.exception(f"Error generating scheduling insights for org {org_id}")
        raise HTTPException(status_code=500, detail="Failed to generate insights")


# ---------------------------------------------------------------------------
# 2. Optimal Times for a Specific Lead
# ---------------------------------------------------------------------------

@router.get("/optimal-times/{lead_id}")
async def get_optimal_times(
    lead_id: int,
    lo_id: Optional[int] = Query(default=None, description="Loan officer ID (defaults to current user)"),
    days_ahead: int = Query(default=14, ge=1, le=60, description="Days to look ahead"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get the best appointment time slots for a specific lead,
    ranked by predicted conversion probability.
    """
    from services.scheduling_intelligence import suggest_optimal_time

    org_id = _get_org_id(current_user)
    effective_lo_id = lo_id or current_user.id

    try:
        result = await suggest_optimal_time(
            lead_id=lead_id, lo_id=effective_lo_id, db=db, days_ahead=days_ahead
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.exception(f"Error suggesting optimal times for lead {lead_id}")
        raise HTTPException(status_code=500, detail="Failed to compute optimal times")


# ---------------------------------------------------------------------------
# 3. Best LO Match for a Lead
# ---------------------------------------------------------------------------

@router.get("/lo-match/{lead_id}")
async def get_lo_match(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Find the best loan officer for a lead based on historical
    conversion data, source matching, and show rates.
    """
    from services.scheduling_intelligence import optimize_lo_matching

    org_id = _get_org_id(current_user)

    try:
        result = await optimize_lo_matching(lead_id=lead_id, org_id=org_id, db=db)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.exception(f"Error computing LO match for lead {lead_id}")
        raise HTTPException(status_code=500, detail="Failed to compute LO match")


# ---------------------------------------------------------------------------
# 4. No-Show Risk Score
# ---------------------------------------------------------------------------

@router.get("/no-show-risk/{appointment_id}")
async def get_no_show_risk(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Predict no-show probability for a specific appointment.

    Returns a risk score (0.0-1.0), risk level (low/medium/high),
    contributing factors, and mitigation suggestions.
    """
    from services.scheduling_intelligence import predict_no_show_risk

    try:
        result = await predict_no_show_risk(appointment_id=appointment_id, db=db)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.exception(f"Error predicting no-show risk for appointment {appointment_id}")
        raise HTTPException(status_code=500, detail="Failed to predict no-show risk")


# ---------------------------------------------------------------------------
# 5. Conversion Trends Over Time
# ---------------------------------------------------------------------------

@router.get("/trends")
async def get_conversion_trends_endpoint(
    days: int = Query(default=90, ge=7, le=365, description="Analysis period in days"),
    granularity: str = Query(default="week", regex="^(week|month)$", description="Trend granularity"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get appointment conversion trends over time (weekly or monthly).

    Includes show rate, no-show rate, and trend direction for each period.
    """
    from services.scheduling_intelligence import get_conversion_trends

    org_id = _get_org_id(current_user)

    try:
        result = await get_conversion_trends(org_id=org_id, db=db, days=days, granularity=granularity)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.exception(f"Error fetching conversion trends for org {org_id}")
        raise HTTPException(status_code=500, detail="Failed to fetch conversion trends")


# ---------------------------------------------------------------------------
# 6. Conversion Pattern Analysis
# ---------------------------------------------------------------------------

@router.get("/patterns")
async def get_conversion_patterns(
    days: int = Query(default=90, ge=7, le=365, description="Analysis period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Identify highest-converting time slots, days, and LO matches.

    Includes a day-hour heatmap of show rates and Wilson-score-ranked results
    to avoid sample-size bias.
    """
    from services.scheduling_intelligence import analyze_conversion_patterns

    org_id = _get_org_id(current_user)

    try:
        result = await analyze_conversion_patterns(org_id=org_id, db=db, days=days)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.exception(f"Error analyzing conversion patterns for org {org_id}")
        raise HTTPException(status_code=500, detail="Failed to analyze conversion patterns")


# ---------------------------------------------------------------------------
# 7. Script / Booking Method Performance
# ---------------------------------------------------------------------------

@router.get("/script-performance")
async def get_script_performance_endpoint(
    days: int = Query(default=90, ge=7, le=365, description="Analysis period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Compare show rates across booking methods (AI vs manual),
    meeting types, and meeting modes (video vs phone vs in-person).
    """
    from services.scheduling_intelligence import get_script_performance

    org_id = _get_org_id(current_user)

    try:
        result = await get_script_performance(org_id=org_id, db=db, days=days)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.exception(f"Error fetching script performance for org {org_id}")
        raise HTTPException(status_code=500, detail="Failed to fetch script performance")


# ---------------------------------------------------------------------------
# 8. Appointment Duration Prediction
# ---------------------------------------------------------------------------

@router.get("/predict-duration")
async def predict_duration(
    appointment_type: str = Query(..., description="Appointment type key (e.g. discovery_call)"),
    lo_id: Optional[int] = Query(default=None, description="Specific LO ID"),
    lead_source: Optional[str] = Query(default=None, description="Lead source filter"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Predict how long an appointment will actually take based on
    historical duration data.
    """
    from services.scheduling_intelligence import predict_appointment_duration

    org_id = _get_org_id(current_user)

    try:
        result = await predict_appointment_duration(
            appointment_type=appointment_type, db=db,
            org_id=org_id, lo_id=lo_id, lead_source=lead_source,
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.exception(f"Error predicting duration for type {appointment_type}")
        raise HTTPException(status_code=500, detail="Failed to predict duration")


# ---------------------------------------------------------------------------
# 9. Follow-Up Timing Recommendation
# ---------------------------------------------------------------------------

@router.get("/followup-timing/{appointment_id}")
async def get_followup_timing(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get the optimal number of days to wait before following up
    after an appointment, based on historical conversion patterns.
    """
    from services.scheduling_intelligence import calculate_followup_timing

    try:
        result = await calculate_followup_timing(appointment_id=appointment_id, db=db)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.exception(f"Error calculating followup timing for appointment {appointment_id}")
        raise HTTPException(status_code=500, detail="Failed to calculate followup timing")
