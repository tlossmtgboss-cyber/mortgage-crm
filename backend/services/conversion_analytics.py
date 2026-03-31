"""
Booking Conversion Analytics

Tracks the full funnel:
Appointment Booked -> Showed Up -> Lead Created -> Application -> Funded Loan

Metrics:
- Show rate (booked vs. attended)
- Lead conversion rate (attended -> became lead)
- Application rate (lead -> application submitted)
- Pull-through rate (application -> funded)
- Revenue per appointment (funded volume / total appointments)
- Time-to-conversion (appointment date -> funded date)
- Source attribution (which booking source converts best: AI, public page, manual)
- LO comparison (which LOs have best appointment conversion)
"""

import logging
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy import text, func, case, and_, or_, extract
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from services.workflow_constants import TERMINAL_LOAN_STAGES as TERMINAL_STAGES

APPLICATION_STAGES = (
    "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED", "UNDERWRITING",
    "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED", "SUSPENDED",
    "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
)


# ============================================================================
# Helpers
# ============================================================================

def _safe_rate(numerator: int, denominator: int) -> float:
    """Calculate a percentage rate, returning 0.0 when denominator is zero."""
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _parse_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
    default_days: int = 90,
) -> Tuple[date, date]:
    """Parse start/end date strings into date objects with fallback defaults."""
    today = date.today()
    if end_date:
        end_dt = datetime.fromisoformat(end_date).date()
    else:
        end_dt = today
    if start_date:
        start_dt = datetime.fromisoformat(start_date).date()
    else:
        start_dt = end_dt - timedelta(days=default_days)
    return start_dt, end_dt


def _get_models(db: Session) -> Dict[str, Any]:
    """Lazily import scheduler + CRM models so the module has no import-time deps."""
    from smart_scheduler_models import create_smart_scheduler_models
    from db import Base

    models = create_smart_scheduler_models(Base)

    from database.models.lead_loan import Lead, Loan
    models["Lead"] = Lead
    models["Loan"] = Loan
    return models


# ============================================================================
# Core tracking mutations
# ============================================================================

async def track_appointment_outcome(
    appointment_id: int,
    outcome: str,
    db: Session,
) -> Dict[str, Any]:
    """
    Record an appointment outcome: showed, no_show, cancelled, rescheduled.

    Updates the Appointment row's status and associated timestamp columns.
    """
    models = _get_models(db)
    Appointment = models["Appointment"]

    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        return {"error": f"Appointment {appointment_id} not found"}

    now = datetime.now(timezone.utc)
    outcome_lower = outcome.lower()

    status_map = {
        "showed": "completed",
        "completed": "completed",
        "no_show": "no_show",
        "cancelled": "cancelled",
        "rescheduled": "rescheduled",
    }

    new_status = status_map.get(outcome_lower)
    if not new_status:
        return {"error": f"Invalid outcome '{outcome}'. Use: showed, no_show, cancelled, rescheduled"}

    appt.status = new_status
    appt.status_changed_at = now

    if outcome_lower in ("showed", "completed"):
        appt.completed_at = now
    elif outcome_lower == "no_show":
        appt.no_show_at = now
    elif outcome_lower == "cancelled":
        appt.cancelled_at = now

    db.commit()
    db.refresh(appt)

    return {
        "appointment_id": appointment_id,
        "new_status": new_status,
        "updated_at": now.isoformat(),
    }


async def link_appointment_to_lead(
    appointment_id: int,
    lead_id: int,
    db: Session,
) -> Dict[str, Any]:
    """Associate an appointment with a lead for conversion tracking."""
    models = _get_models(db)
    Appointment = models["Appointment"]

    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        return {"error": f"Appointment {appointment_id} not found"}

    appt.lead_id = lead_id
    db.commit()

    return {
        "appointment_id": appointment_id,
        "lead_id": lead_id,
        "linked": True,
    }


async def link_appointment_to_loan(
    appointment_id: int,
    loan_id: int,
    db: Session,
) -> Dict[str, Any]:
    """Associate an appointment with a loan for revenue attribution."""
    models = _get_models(db)
    Appointment = models["Appointment"]

    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        return {"error": f"Appointment {appointment_id} not found"}

    appt.loan_id = loan_id
    db.commit()

    return {
        "appointment_id": appointment_id,
        "loan_id": loan_id,
        "linked": True,
    }


# ============================================================================
# Read-only analytics queries
# ============================================================================

async def get_conversion_funnel(
    org_id: int,
    start_date: Optional[str],
    end_date: Optional[str],
    db: Session,
) -> Dict[str, Any]:
    """
    Full conversion funnel:
    Booked -> Showed -> Lead Created -> Application -> Funded
    """
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    row = db.execute(text("""
        SELECT
            COUNT(*)                                                             AS total_booked,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END)                 AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END)                   AS no_show,
            COUNT(CASE WHEN sa.status = 'cancelled' THEN 1 END)                 AS cancelled,
            COUNT(CASE WHEN sa.status = 'rescheduled' THEN 1 END)               AS rescheduled,
            COUNT(CASE WHEN sa.lead_id IS NOT NULL THEN 1 END)                  AS linked_lead,
            COUNT(CASE WHEN sa.loan_id IS NOT NULL THEN 1 END)                  AS linked_loan,
            COUNT(CASE WHEN lo.application_date IS NOT NULL THEN 1 END)         AS application,
            COUNT(CASE WHEN lo.stage = 'FUNDED' THEN 1 END)                     AS funded,
            COALESCE(SUM(CASE WHEN lo.stage = 'FUNDED' THEN lo.amount END), 0)  AS funded_volume
        FROM scheduler_appointments sa
        LEFT JOIN loans lo ON lo.id = sa.loan_id
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= :start_dt
          AND sa.scheduled_start < :end_dt + INTERVAL '1 day'
    """), {"org_id": org_id, "start_dt": start_dt, "end_dt": end_dt}).fetchone()

    booked = row.total_booked or 0
    showed = row.showed or 0
    linked_lead = row.linked_lead or 0
    application = row.application or 0
    funded = row.funded or 0
    funded_volume = float(row.funded_volume or 0)

    return {
        "period": {"start": str(start_dt), "end": str(end_dt)},
        "funnel": {
            "booked": booked,
            "showed": showed,
            "no_show": row.no_show or 0,
            "cancelled": row.cancelled or 0,
            "rescheduled": row.rescheduled or 0,
            "linked_lead": linked_lead,
            "linked_loan": row.linked_loan or 0,
            "application": application,
            "funded": funded,
            "funded_volume": funded_volume,
            "funded_volume_formatted": f"${funded_volume:,.2f}",
        },
        "rates": {
            "show_rate": _safe_rate(showed, booked),
            "no_show_rate": _safe_rate(row.no_show or 0, booked),
            "lead_conversion_rate": _safe_rate(linked_lead, showed),
            "application_rate": _safe_rate(application, linked_lead),
            "pull_through_rate": _safe_rate(funded, application),
            "overall_rate": _safe_rate(funded, booked),
            "revenue_per_appointment": round(funded_volume / booked, 2) if booked else 0,
        },
    }


async def get_source_performance(
    org_id: int,
    start_date: Optional[str],
    end_date: Optional[str],
    db: Session,
) -> Dict[str, Any]:
    """Conversion rates grouped by booking source (external_source column)."""
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    rows = db.execute(text("""
        SELECT
            COALESCE(sa.external_source, 'direct') AS source,
            COUNT(*)                                                              AS booked,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END)                  AS showed,
            COUNT(CASE WHEN sa.lead_id IS NOT NULL THEN 1 END)                   AS leads,
            COUNT(CASE WHEN lo.application_date IS NOT NULL THEN 1 END)          AS applications,
            COUNT(CASE WHEN lo.stage = 'FUNDED' THEN 1 END)                      AS funded,
            COALESCE(SUM(CASE WHEN lo.stage = 'FUNDED' THEN lo.amount END), 0)   AS funded_volume
        FROM scheduler_appointments sa
        LEFT JOIN loans lo ON lo.id = sa.loan_id
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= :start_dt
          AND sa.scheduled_start < :end_dt + INTERVAL '1 day'
        GROUP BY COALESCE(sa.external_source, 'direct')
        ORDER BY funded_volume DESC
    """), {"org_id": org_id, "start_dt": start_dt, "end_dt": end_dt}).fetchall()

    sources = []
    for r in rows:
        booked = r.booked or 0
        showed = r.showed or 0
        sources.append({
            "source": r.source,
            "booked": booked,
            "showed": showed,
            "leads": r.leads or 0,
            "applications": r.applications or 0,
            "funded": r.funded or 0,
            "funded_volume": float(r.funded_volume or 0),
            "show_rate": _safe_rate(showed, booked),
            "overall_rate": _safe_rate(r.funded or 0, booked),
            "revenue_per_appointment": round(float(r.funded_volume or 0) / booked, 2) if booked else 0,
        })

    return {
        "period": {"start": str(start_dt), "end": str(end_dt)},
        "sources": sources,
    }


async def get_lo_conversion_rates(
    org_id: int,
    start_date: Optional[str],
    end_date: Optional[str],
    db: Session,
) -> Dict[str, Any]:
    """Per-LO conversion metrics based on assigned_user_id."""
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    rows = db.execute(text("""
        SELECT
            sa.assigned_user_id                                                   AS lo_id,
            CONCAT(u.first_name, ' ', u.last_name)                               AS lo_name,
            COUNT(*)                                                              AS booked,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END)                  AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END)                    AS no_show,
            COUNT(CASE WHEN sa.lead_id IS NOT NULL THEN 1 END)                   AS leads,
            COUNT(CASE WHEN lo.application_date IS NOT NULL THEN 1 END)          AS applications,
            COUNT(CASE WHEN lo.stage = 'FUNDED' THEN 1 END)                      AS funded,
            COALESCE(SUM(CASE WHEN lo.stage = 'FUNDED' THEN lo.amount END), 0)   AS funded_volume
        FROM scheduler_appointments sa
        LEFT JOIN users u ON u.id = sa.assigned_user_id
        LEFT JOIN loans lo ON lo.id = sa.loan_id
        WHERE sa.organization_id = :org_id
          AND sa.assigned_user_id IS NOT NULL
          AND sa.scheduled_start >= :start_dt
          AND sa.scheduled_start < :end_dt + INTERVAL '1 day'
        GROUP BY sa.assigned_user_id, u.first_name, u.last_name
        ORDER BY funded_volume DESC
    """), {"org_id": org_id, "start_dt": start_dt, "end_dt": end_dt}).fetchall()

    los = []
    for r in rows:
        booked = r.booked or 0
        showed = r.showed or 0
        los.append({
            "lo_id": r.lo_id,
            "lo_name": r.lo_name or "Unknown",
            "booked": booked,
            "showed": showed,
            "no_show": r.no_show or 0,
            "leads": r.leads or 0,
            "applications": r.applications or 0,
            "funded": r.funded or 0,
            "funded_volume": float(r.funded_volume or 0),
            "show_rate": _safe_rate(showed, booked),
            "lead_rate": _safe_rate(r.leads or 0, showed),
            "pull_through": _safe_rate(r.funded or 0, r.applications or 0),
            "overall_rate": _safe_rate(r.funded or 0, booked),
            "revenue_per_appointment": round(float(r.funded_volume or 0) / booked, 2) if booked else 0,
        })

    return {
        "period": {"start": str(start_dt), "end": str(end_dt)},
        "loan_officers": los,
    }


async def get_time_analytics(
    org_id: int,
    start_date: Optional[str],
    end_date: Optional[str],
    db: Session,
) -> Dict[str, Any]:
    """
    Day-of-week x hour-of-day heatmap showing appointment volume,
    show rates, and conversion rates.
    """
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    rows = db.execute(text("""
        SELECT
            EXTRACT(DOW FROM sa.scheduled_start)::int  AS dow,
            EXTRACT(HOUR FROM sa.scheduled_start)::int AS hour,
            COUNT(*)                                                   AS booked,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END)       AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END)         AS no_show,
            COUNT(CASE WHEN lo.stage = 'FUNDED' THEN 1 END)           AS funded
        FROM scheduler_appointments sa
        LEFT JOIN loans lo ON lo.id = sa.loan_id
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= :start_dt
          AND sa.scheduled_start < :end_dt + INTERVAL '1 day'
        GROUP BY dow, hour
        ORDER BY dow, hour
    """), {"org_id": org_id, "start_dt": start_dt, "end_dt": end_dt}).fetchall()

    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    heatmap = []
    best_slot = {"booked": 0, "day": "", "hour": 0}
    best_conversion_slot = {"rate": 0.0, "day": "", "hour": 0}

    for r in rows:
        booked = r.booked or 0
        showed = r.showed or 0
        funded = r.funded or 0
        show_rate = _safe_rate(showed, booked)
        conversion_rate = _safe_rate(funded, booked)

        slot = {
            "day_index": r.dow,
            "day": day_names[r.dow],
            "hour": r.hour,
            "hour_label": f"{r.hour:02d}:00",
            "booked": booked,
            "showed": showed,
            "no_show": r.no_show or 0,
            "funded": funded,
            "show_rate": show_rate,
            "conversion_rate": conversion_rate,
        }
        heatmap.append(slot)

        if booked > best_slot["booked"]:
            best_slot = {"booked": booked, "day": day_names[r.dow], "hour": r.hour}
        if conversion_rate > best_conversion_slot["rate"] and booked >= 3:
            best_conversion_slot = {"rate": conversion_rate, "day": day_names[r.dow], "hour": r.hour}

    return {
        "period": {"start": str(start_dt), "end": str(end_dt)},
        "heatmap": heatmap,
        "insights": {
            "busiest_slot": best_slot,
            "best_conversion_slot": best_conversion_slot,
        },
    }


async def get_revenue_attribution(
    org_id: int,
    start_date: Optional[str],
    end_date: Optional[str],
    db: Session,
) -> Dict[str, Any]:
    """Revenue traced back to appointments that originated the loan."""
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    row = db.execute(text("""
        SELECT
            COUNT(DISTINCT sa.id)                                                AS total_appointments,
            COUNT(DISTINCT CASE WHEN lo.stage = 'FUNDED' THEN sa.id END)         AS funded_appointments,
            COALESCE(SUM(CASE WHEN lo.stage = 'FUNDED' THEN lo.amount END), 0)   AS total_funded_volume,
            AVG(CASE WHEN lo.stage = 'FUNDED' THEN lo.amount END)                AS avg_funded_amount,
            AVG(
                CASE WHEN lo.funded_date IS NOT NULL
                     THEN EXTRACT(EPOCH FROM (lo.funded_date - sa.scheduled_start)) / 86400.0
                END
            ) AS avg_days_to_fund
        FROM scheduler_appointments sa
        LEFT JOIN loans lo ON lo.id = sa.loan_id
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= :start_dt
          AND sa.scheduled_start < :end_dt + INTERVAL '1 day'
    """), {"org_id": org_id, "start_dt": start_dt, "end_dt": end_dt}).fetchone()

    total_appts = row.total_appointments or 0
    funded_appts = row.funded_appointments or 0
    total_volume = float(row.total_funded_volume or 0)

    # Monthly trend of appointment-attributed revenue
    monthly = db.execute(text("""
        SELECT
            TO_CHAR(sa.scheduled_start, 'YYYY-MM') AS month,
            COUNT(DISTINCT sa.id)                                                AS appointments,
            COUNT(DISTINCT CASE WHEN lo.stage = 'FUNDED' THEN sa.id END)         AS funded,
            COALESCE(SUM(CASE WHEN lo.stage = 'FUNDED' THEN lo.amount END), 0)   AS volume
        FROM scheduler_appointments sa
        LEFT JOIN loans lo ON lo.id = sa.loan_id
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= :start_dt
          AND sa.scheduled_start < :end_dt + INTERVAL '1 day'
        GROUP BY TO_CHAR(sa.scheduled_start, 'YYYY-MM')
        ORDER BY month
    """), {"org_id": org_id, "start_dt": start_dt, "end_dt": end_dt}).fetchall()

    return {
        "period": {"start": str(start_dt), "end": str(end_dt)},
        "summary": {
            "total_appointments": total_appts,
            "funded_appointments": funded_appts,
            "total_funded_volume": total_volume,
            "total_funded_volume_formatted": f"${total_volume:,.2f}",
            "avg_funded_amount": round(float(row.avg_funded_amount or 0), 2),
            "avg_days_to_fund": round(float(row.avg_days_to_fund or 0), 1),
            "revenue_per_appointment": round(total_volume / total_appts, 2) if total_appts else 0,
            "conversion_rate": _safe_rate(funded_appts, total_appts),
        },
        "monthly_trend": [
            {
                "month": m.month,
                "appointments": m.appointments or 0,
                "funded": m.funded or 0,
                "volume": float(m.volume or 0),
            }
            for m in monthly
        ],
    }


async def get_ai_vs_manual_comparison(
    org_id: int,
    start_date: Optional[str],
    end_date: Optional[str],
    db: Session,
) -> Dict[str, Any]:
    """Compare AI-booked appointments vs manual bookings on key metrics."""
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    rows = db.execute(text("""
        SELECT
            sa.booked_by_ai,
            COUNT(*)                                                              AS booked,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END)                  AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END)                    AS no_show,
            COUNT(CASE WHEN sa.status = 'cancelled' THEN 1 END)                  AS cancelled,
            COUNT(CASE WHEN sa.lead_id IS NOT NULL THEN 1 END)                   AS leads,
            COUNT(CASE WHEN lo.application_date IS NOT NULL THEN 1 END)          AS applications,
            COUNT(CASE WHEN lo.stage = 'FUNDED' THEN 1 END)                      AS funded,
            COALESCE(SUM(CASE WHEN lo.stage = 'FUNDED' THEN lo.amount END), 0)   AS funded_volume,
            AVG(
                CASE WHEN lo.funded_date IS NOT NULL
                     THEN EXTRACT(EPOCH FROM (lo.funded_date - sa.scheduled_start)) / 86400.0
                END
            ) AS avg_days_to_fund
        FROM scheduler_appointments sa
        LEFT JOIN loans lo ON lo.id = sa.loan_id
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= :start_dt
          AND sa.scheduled_start < :end_dt + INTERVAL '1 day'
        GROUP BY sa.booked_by_ai
        ORDER BY sa.booked_by_ai DESC
    """), {"org_id": org_id, "start_dt": start_dt, "end_dt": end_dt}).fetchall()

    def _build(r):
        booked = r.booked or 0
        showed = r.showed or 0
        funded = r.funded or 0
        funded_vol = float(r.funded_volume or 0)
        return {
            "booked": booked,
            "showed": showed,
            "no_show": r.no_show or 0,
            "cancelled": r.cancelled or 0,
            "leads": r.leads or 0,
            "applications": r.applications or 0,
            "funded": funded,
            "funded_volume": funded_vol,
            "show_rate": _safe_rate(showed, booked),
            "lead_rate": _safe_rate(r.leads or 0, showed),
            "overall_conversion": _safe_rate(funded, booked),
            "revenue_per_appointment": round(funded_vol / booked, 2) if booked else 0,
            "avg_days_to_fund": round(float(r.avg_days_to_fund or 0), 1),
        }

    ai_stats = {"booked": 0, "showed": 0, "funded": 0, "funded_volume": 0}
    manual_stats = {"booked": 0, "showed": 0, "funded": 0, "funded_volume": 0}

    result = {"ai": None, "manual": None}
    for r in rows:
        if r.booked_by_ai:
            result["ai"] = _build(r)
        else:
            result["manual"] = _build(r)

    # Build comparison insights
    ai = result.get("ai") or {}
    manual = result.get("manual") or {}

    winner_show = "ai" if (ai.get("show_rate", 0) > manual.get("show_rate", 0)) else "manual"
    winner_conv = "ai" if (ai.get("overall_conversion", 0) > manual.get("overall_conversion", 0)) else "manual"
    winner_rev = "ai" if (ai.get("revenue_per_appointment", 0) > manual.get("revenue_per_appointment", 0)) else "manual"

    return {
        "period": {"start": str(start_dt), "end": str(end_dt)},
        "ai": result["ai"],
        "manual": result["manual"],
        "insights": {
            "higher_show_rate": winner_show,
            "higher_conversion": winner_conv,
            "higher_revenue_per_appt": winner_rev,
        },
    }


async def get_weekly_trends(
    org_id: int,
    start_date: Optional[str],
    end_date: Optional[str],
    db: Session,
) -> Dict[str, Any]:
    """Week-over-week trend data for appointments, show rate, conversions."""
    start_dt, end_dt = _parse_date_range(start_date, end_date, default_days=180)

    rows = db.execute(text("""
        SELECT
            DATE_TRUNC('week', sa.scheduled_start)::date                          AS week_start,
            COUNT(*)                                                              AS booked,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END)                  AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END)                    AS no_show,
            COUNT(CASE WHEN sa.lead_id IS NOT NULL THEN 1 END)                   AS leads,
            COUNT(CASE WHEN lo.stage = 'FUNDED' THEN 1 END)                      AS funded,
            COALESCE(SUM(CASE WHEN lo.stage = 'FUNDED' THEN lo.amount END), 0)   AS funded_volume
        FROM scheduler_appointments sa
        LEFT JOIN loans lo ON lo.id = sa.loan_id
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= :start_dt
          AND sa.scheduled_start < :end_dt + INTERVAL '1 day'
        GROUP BY DATE_TRUNC('week', sa.scheduled_start)::date
        ORDER BY week_start
    """), {"org_id": org_id, "start_dt": start_dt, "end_dt": end_dt}).fetchall()

    weeks = []
    for r in rows:
        booked = r.booked or 0
        showed = r.showed or 0
        weeks.append({
            "week_start": str(r.week_start),
            "booked": booked,
            "showed": showed,
            "no_show": r.no_show or 0,
            "leads": r.leads or 0,
            "funded": r.funded or 0,
            "funded_volume": float(r.funded_volume or 0),
            "show_rate": _safe_rate(showed, booked),
            "conversion_rate": _safe_rate(r.funded or 0, booked),
        })

    # Compute week-over-week deltas
    for i in range(1, len(weeks)):
        prev = weeks[i - 1]
        curr = weeks[i]
        curr["booked_delta"] = curr["booked"] - prev["booked"]
        curr["show_rate_delta"] = round(curr["show_rate"] - prev["show_rate"], 1)
        curr["conversion_rate_delta"] = round(curr["conversion_rate"] - prev["conversion_rate"], 1)
    if weeks:
        weeks[0]["booked_delta"] = 0
        weeks[0]["show_rate_delta"] = 0.0
        weeks[0]["conversion_rate_delta"] = 0.0

    return {
        "period": {"start": str(start_dt), "end": str(end_dt)},
        "weeks": weeks,
    }
