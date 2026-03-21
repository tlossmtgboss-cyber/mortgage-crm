"""
Scheduler Outcome Tracking - Appointment-to-funding conversion analytics.

Endpoints:
  - GET /analytics/appointment-outcomes     AI vs manual appointment funding conversion
  - GET /analytics/appointment-type-effectiveness  Conversion rates by appointment type

Measures whether AI-scheduled appointments lead to funded loans by joining
scheduler_appointments with loans via the loan_id foreign key.

All endpoints require authentication and are scoped to the user's organization.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from db import get_db
from middleware.feature_gate import require_feature_tier
from routes.scheduler._helpers import (
    get_current_user, _get_org_id, _is_scheduler_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# PYDANTIC RESPONSE MODELS
# =============================================================================

class BookingChannelMetrics(BaseModel):
    """Metrics for a single booking channel (AI or manual)."""
    total_appointments: int = Field(0, description="Total appointments in period")
    linked_to_loan: int = Field(0, description="Appointments with a loan_id")
    funded_count: int = Field(0, description="Linked loans that reached FUNDED stage")
    funded_volume: float = Field(0.0, description="Total dollar volume of funded loans")
    funded_volume_formatted: str = Field("$0.00", description="Formatted funded volume")
    no_show_count: int = Field(0, description="Appointments marked no-show")
    cancelled_count: int = Field(0, description="Appointments cancelled")
    completed_count: int = Field(0, description="Appointments completed")
    conversion_rate: float = Field(0.0, description="Funded / linked-to-loan as percentage")
    no_show_rate: float = Field(0.0, description="No-show / total as percentage")
    avg_days_to_fund: Optional[float] = Field(None, description="Avg days from appointment to funding")


class OutcomeComparison(BaseModel):
    """Comparison metrics between AI and manual scheduling."""
    conversion_rate_diff: float = Field(0.0, description="AI conversion rate minus manual rate (pp)")
    no_show_rate_diff: float = Field(0.0, description="AI no-show rate minus manual rate (pp)")
    avg_days_to_fund_diff: Optional[float] = Field(None, description="AI avg days minus manual avg days")
    ai_advantage: str = Field("neutral", description="'ai_better', 'manual_better', or 'neutral'")


class AppointmentOutcomesResponse(BaseModel):
    """Full appointment outcomes response."""
    period_days: int = Field(90, description="Lookback period in days")
    ai_scheduled: BookingChannelMetrics = Field(default_factory=BookingChannelMetrics)
    manually_scheduled: BookingChannelMetrics = Field(default_factory=BookingChannelMetrics)
    comparison: OutcomeComparison = Field(default_factory=OutcomeComparison)

    class Config:
        from_attributes = True


class TypeEffectivenessEntry(BaseModel):
    """Conversion metrics for a single appointment type."""
    type_id: Optional[int] = Field(None, description="Appointment type ID")
    type_name: str = Field("Unknown", description="Appointment type name")
    total_appointments: int = Field(0)
    linked_to_loan: int = Field(0)
    funded_count: int = Field(0)
    funded_volume: float = Field(0.0)
    funded_volume_formatted: str = Field("$0.00")
    conversion_rate: float = Field(0.0, description="Funded / linked as percentage")
    avg_days_to_fund: Optional[float] = Field(None)
    avg_loan_amount: Optional[float] = Field(None, description="Average funded loan amount")
    completed_count: int = Field(0)
    no_show_count: int = Field(0)


class TypeEffectivenessResponse(BaseModel):
    """Appointment type effectiveness response."""
    period_days: int = Field(90)
    types: List[TypeEffectivenessEntry] = Field(default_factory=list)

    class Config:
        from_attributes = True


# =============================================================================
# HELPERS
# =============================================================================

def _format_currency(amount: float) -> str:
    """Format amount as USD currency string."""
    return f"${amount:,.2f}"


def _calc_rate(numerator: int, denominator: int) -> float:
    """Calculate percentage rate, returning 0.0 if denominator is zero."""
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _resolve_effective_user_id(
    current_user, user_id: Optional[int], require_admin_for_all: bool = False,
) -> Optional[int]:
    """Resolve effective user_id, enforcing permission checks.

    Returns None if admin is viewing all users, or the specific user_id to filter by.
    """
    if user_id and user_id != current_user.id and not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can view other users' analytics")
    if require_admin_for_all and not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required for team analytics")
    if not _is_scheduler_admin(current_user):
        return current_user.id
    return user_id


# =============================================================================
# APPOINTMENT OUTCOMES (AI vs Manual)
# =============================================================================

@router.get("/analytics/appointment-outcomes", response_model=AppointmentOutcomesResponse)
@require_feature_tier("scheduler_analytics")
async def get_appointment_outcomes(
    request: Request,
    days: int = Query(90, ge=7, le=365, description="Lookback period in days"),
    user_id: Optional[int] = Query(None, description="Filter by specific LO (admin only)"),
    db: Session = Depends(get_db),
):
    """
    Get appointment-to-funding conversion metrics, comparing AI-scheduled
    vs manually-scheduled appointments.

    Joins scheduler_appointments with loans via loan_id to determine
    which appointments ultimately resulted in funded loans.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    effective_user_id = _resolve_effective_user_id(current_user, user_id)

    user_filter = ""
    params = {"org_id": org_id, "days": days}
    if effective_user_id:
        user_filter = "AND a.assigned_user_id = :user_id"
        params["user_id"] = effective_user_id

    try:
        rows = db.execute(text(f"""
            SELECT
                a.booked_by_ai,
                COUNT(*) as total_appointments,
                COUNT(a.loan_id) as linked_to_loan,
                COUNT(CASE WHEN l.stage = 'FUNDED' THEN 1 END) as funded_count,
                COALESCE(SUM(CASE WHEN l.stage = 'FUNDED' THEN l.amount END), 0) as funded_volume,
                COUNT(CASE WHEN a.status = 'no_show' THEN 1 END) as no_show_count,
                COUNT(CASE WHEN a.status = 'cancelled' THEN 1 END) as cancelled_count,
                COUNT(CASE WHEN a.status = 'completed' THEN 1 END) as completed_count,
                AVG(CASE WHEN l.funded_date IS NOT NULL
                    THEN EXTRACT(EPOCH FROM (l.funded_date - a.scheduled_start)) / 86400
                END) as avg_days_to_fund
            FROM scheduler_appointments a
            LEFT JOIN loans l ON l.id = a.loan_id
            WHERE a.organization_id = :org_id
                AND a.scheduled_start >= CURRENT_DATE - :days
                {user_filter}
            GROUP BY a.booked_by_ai
        """), params).fetchall()

        ai_data = BookingChannelMetrics()
        manual_data = BookingChannelMetrics()

        for row in rows:
            row_dict = row._mapping
            booked_by_ai = row_dict["booked_by_ai"]
            linked = int(row_dict["linked_to_loan"] or 0)
            funded = int(row_dict["funded_count"] or 0)
            total = int(row_dict["total_appointments"] or 0)
            volume = float(row_dict["funded_volume"] or 0)
            avg_dtf = float(row_dict["avg_days_to_fund"]) if row_dict["avg_days_to_fund"] is not None else None

            metrics = BookingChannelMetrics(
                total_appointments=total,
                linked_to_loan=linked,
                funded_count=funded,
                funded_volume=volume,
                funded_volume_formatted=_format_currency(volume),
                no_show_count=int(row_dict["no_show_count"] or 0),
                cancelled_count=int(row_dict["cancelled_count"] or 0),
                completed_count=int(row_dict["completed_count"] or 0),
                conversion_rate=_calc_rate(funded, linked),
                no_show_rate=_calc_rate(int(row_dict["no_show_count"] or 0), total),
                avg_days_to_fund=round(avg_dtf, 1) if avg_dtf is not None else None,
            )

            if booked_by_ai:
                ai_data = metrics
            else:
                manual_data = metrics

        # Build comparison
        conv_diff = round(ai_data.conversion_rate - manual_data.conversion_rate, 1)
        ns_diff = round(ai_data.no_show_rate - manual_data.no_show_rate, 1)
        dtf_diff = None
        if ai_data.avg_days_to_fund is not None and manual_data.avg_days_to_fund is not None:
            dtf_diff = round(ai_data.avg_days_to_fund - manual_data.avg_days_to_fund, 1)

        # Determine advantage: AI is better if higher conversion and lower no-show
        if conv_diff > 2 and ns_diff <= 0:
            advantage = "ai_better"
        elif conv_diff < -2 and ns_diff >= 0:
            advantage = "manual_better"
        else:
            advantage = "neutral"

        comparison = OutcomeComparison(
            conversion_rate_diff=conv_diff,
            no_show_rate_diff=ns_diff,
            avg_days_to_fund_diff=dtf_diff,
            ai_advantage=advantage,
        )

        return AppointmentOutcomesResponse(
            period_days=days,
            ai_scheduled=ai_data,
            manually_scheduled=manual_data,
            comparison=comparison,
        )
    except Exception as e:
        logger.exception(f"Appointment outcomes query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute appointment outcomes")


# =============================================================================
# APPOINTMENT TYPE EFFECTIVENESS
# =============================================================================

@router.get("/analytics/appointment-type-effectiveness", response_model=TypeEffectivenessResponse)
@require_feature_tier("scheduler_analytics")
async def get_appointment_type_effectiveness(
    request: Request,
    days: int = Query(90, ge=7, le=365, description="Lookback period in days"),
    user_id: Optional[int] = Query(None, description="Filter by specific LO (admin only)"),
    db: Session = Depends(get_db),
):
    """
    Get which appointment types have the highest conversion to funded loans.

    Groups by appointment_type and calculates conversion rates, funded volume,
    and average time-to-fund for each type.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    effective_user_id = _resolve_effective_user_id(current_user, user_id)

    user_filter = ""
    params = {"org_id": org_id, "days": days}
    if effective_user_id:
        user_filter = "AND a.assigned_user_id = :user_id"
        params["user_id"] = effective_user_id

    try:
        rows = db.execute(text(f"""
            SELECT
                at.id as type_id,
                COALESCE(at.type_name, 'Unassigned') as type_name,
                COUNT(*) as total_appointments,
                COUNT(a.loan_id) as linked_to_loan,
                COUNT(CASE WHEN l.stage = 'FUNDED' THEN 1 END) as funded_count,
                COALESCE(SUM(CASE WHEN l.stage = 'FUNDED' THEN l.amount END), 0) as funded_volume,
                AVG(CASE WHEN l.funded_date IS NOT NULL
                    THEN EXTRACT(EPOCH FROM (l.funded_date - a.scheduled_start)) / 86400
                END) as avg_days_to_fund,
                AVG(CASE WHEN l.stage = 'FUNDED' THEN l.amount END) as avg_loan_amount,
                COUNT(CASE WHEN a.status = 'completed' THEN 1 END) as completed_count,
                COUNT(CASE WHEN a.status = 'no_show' THEN 1 END) as no_show_count
            FROM scheduler_appointments a
            LEFT JOIN appointment_types at ON at.id = a.appointment_type_id
            LEFT JOIN loans l ON l.id = a.loan_id
            WHERE a.organization_id = :org_id
                AND a.scheduled_start >= CURRENT_DATE - :days
                {user_filter}
            GROUP BY at.id, at.type_name
            ORDER BY funded_count DESC, total_appointments DESC
        """), params).fetchall()

        types = []
        for row in rows:
            m = row._mapping
            linked = int(m["linked_to_loan"] or 0)
            funded = int(m["funded_count"] or 0)
            volume = float(m["funded_volume"] or 0)
            avg_dtf = float(m["avg_days_to_fund"]) if m["avg_days_to_fund"] is not None else None
            avg_amt = float(m["avg_loan_amount"]) if m["avg_loan_amount"] is not None else None

            types.append(TypeEffectivenessEntry(
                type_id=m["type_id"],
                type_name=m["type_name"],
                total_appointments=int(m["total_appointments"] or 0),
                linked_to_loan=linked,
                funded_count=funded,
                funded_volume=volume,
                funded_volume_formatted=_format_currency(volume),
                conversion_rate=_calc_rate(funded, linked),
                avg_days_to_fund=round(avg_dtf, 1) if avg_dtf is not None else None,
                avg_loan_amount=round(avg_amt, 2) if avg_amt is not None else None,
                completed_count=int(m["completed_count"] or 0),
                no_show_count=int(m["no_show_count"] or 0),
            ))

        return TypeEffectivenessResponse(
            period_days=days,
            types=types,
        )
    except Exception as e:
        logger.exception(f"Appointment type effectiveness query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute type effectiveness")


