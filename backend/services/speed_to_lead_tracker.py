"""
Speed-to-Lead Tracker
=====================
Measures the end-to-end time from lead creation / stage change
to booking link delivery or appointment auto-booking.

Key metric: Time from trigger event to borrower receiving scheduling communication.

"78% of borrowers choose the first lender who responds."
This module quantifies how fast the actual end-to-end time is from
lead creation to booking link delivery, giving visibility into whether
the pipeline appointment trigger system is delivering competitive
response times.

Integration points:
    - PipelineAppointmentTrigger._log_trigger() — records delivery timing
    - Pipeline appointment routes — exposes metrics via API
    - Scheduler analytics — feeds into overall scheduling performance

Usage:
    from services.speed_to_lead_tracker import record_trigger_timing, get_speed_to_lead_metrics

    # After a booking link or auto-book completes:
    await record_trigger_timing(
        db=db,
        loan_id=loan.id,
        trigger_event="stage_change",
        trigger_time=stage_changed_at,
        delivery_time=datetime.now(timezone.utc),
        delivery_method="booking_link_sms",
        organization_id=org_id,
    )

    # Dashboard / analytics endpoint:
    metrics = await get_speed_to_lead_metrics(db, organization_id=org_id, days=30)
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# TIMING THRESHOLDS — competitive benchmarks for mortgage lead response
# =============================================================================

# Under 60 seconds: elite response time (AI-driven)
THRESHOLD_ELITE_SECONDS = 60
# Under 5 minutes: excellent (industry top-quartile)
THRESHOLD_EXCELLENT_SECONDS = 300
# Under 30 minutes: good (better than most)
THRESHOLD_GOOD_SECONDS = 1800
# Under 1 hour: acceptable
THRESHOLD_ACCEPTABLE_SECONDS = 3600
# Over 1 hour: needs improvement — borrower likely contacted a competitor


async def record_trigger_timing(
    db: Session,
    *,
    loan_id: int,
    trigger_event: str,  # "stage_change", "lead_created"
    trigger_time: datetime,
    delivery_time: datetime = None,
    delivery_method: str = None,  # "auto_booked", "booking_link_sms", "booking_link_email"
    organization_id: int = None,
    loan_officer_id: int = None,
    trigger_stage: str = None,
    extra_data: dict = None,
):
    """Record the timing of a trigger-to-delivery cycle.

    This is the core instrumentation function. Call it from the
    PipelineAppointmentTrigger after a booking link is sent or
    an appointment is auto-booked.

    Args:
        db: Active SQLAlchemy session (caller manages commit).
        loan_id: The loan that triggered the action.
        trigger_event: What caused the trigger ("stage_change" or "lead_created").
        trigger_time: When the triggering event occurred (stage change timestamp).
        delivery_time: When the borrower received the communication. Defaults to now.
        delivery_method: How the booking was delivered (auto_booked, booking_link_sms, etc.).
        organization_id: Tenant isolation.
        loan_officer_id: The LO assigned to the loan.
        trigger_stage: The loan stage that fired the trigger (e.g., "APPLICATION").
        extra_data: Any additional context to store as JSON.
    """
    if delivery_time is None:
        delivery_time = datetime.now(timezone.utc)

    # Normalize to UTC-aware for consistent elapsed calculation
    if trigger_time.tzinfo is None:
        trigger_time = trigger_time.replace(tzinfo=timezone.utc)
    if delivery_time.tzinfo is None:
        delivery_time = delivery_time.replace(tzinfo=timezone.utc)

    elapsed_seconds = (delivery_time - trigger_time).total_seconds()

    # Guard against negative elapsed (clock skew, data errors)
    if elapsed_seconds < 0:
        logger.warning(
            f"Negative elapsed time ({elapsed_seconds:.1f}s) for loan {loan_id} — "
            f"trigger_time={trigger_time.isoformat()}, delivery_time={delivery_time.isoformat()}. "
            f"Recording as 0."
        )
        elapsed_seconds = 0

    try:
        db.execute(text("""
            INSERT INTO speed_to_lead_metrics
            (loan_id, organization_id, loan_officer_id, trigger_event, trigger_stage,
             trigger_time, delivery_time, delivery_method, elapsed_seconds,
             extra_data, created_at)
            VALUES (:loan_id, :org_id, :lo_id, :trigger_event, :trigger_stage,
                    :trigger_time, :delivery_time, :delivery_method, :elapsed_seconds,
                    :extra_data, :now)
        """), {
            "loan_id": loan_id,
            "org_id": organization_id,
            "lo_id": loan_officer_id,
            "trigger_event": trigger_event,
            "trigger_stage": trigger_stage,
            "trigger_time": trigger_time,
            "delivery_time": delivery_time,
            "delivery_method": delivery_method,
            "elapsed_seconds": elapsed_seconds,
            "extra_data": _json_dumps(extra_data) if extra_data else None,
            "now": datetime.now(timezone.utc),
        })
    except Exception as e:
        # Non-fatal: never let metrics recording break the trigger flow
        logger.exception(f"Failed to record speed-to-lead metric for loan {loan_id}: {e}")
        return

    # Classify response time for logging
    if elapsed_seconds <= THRESHOLD_ELITE_SECONDS:
        tier = "ELITE"
    elif elapsed_seconds <= THRESHOLD_EXCELLENT_SECONDS:
        tier = "EXCELLENT"
    elif elapsed_seconds <= THRESHOLD_GOOD_SECONDS:
        tier = "GOOD"
    elif elapsed_seconds <= THRESHOLD_ACCEPTABLE_SECONDS:
        tier = "ACCEPTABLE"
    else:
        tier = "NEEDS_IMPROVEMENT"

    logger.info(
        f"Speed-to-lead: {elapsed_seconds:.1f}s ({tier}) for loan {loan_id} "
        f"via {delivery_method} | trigger={trigger_event} stage={trigger_stage}"
    )


async def get_speed_to_lead_metrics(
    db: Session,
    organization_id: int = None,
    loan_officer_id: int = None,
    days: int = 30,
) -> Dict[str, Any]:
    """Get aggregated speed-to-lead metrics with percentile breakdowns.

    Returns overall and per-delivery-method statistics including median,
    p95, and percentage of responses under key thresholds.

    Args:
        db: Active SQLAlchemy session.
        organization_id: Filter by organization (tenant isolation).
        loan_officer_id: Filter by specific loan officer.
        days: Look-back period in days.

    Returns:
        Dict with period info, totals, threshold percentages, and per-method breakdown.
    """
    params: Dict[str, Any] = {"days": days}
    filters = ["created_at >= CURRENT_DATE - :days", "elapsed_seconds IS NOT NULL"]

    if organization_id:
        filters.append("organization_id = :org_id")
        params["org_id"] = organization_id
    if loan_officer_id:
        filters.append("loan_officer_id = :lo_id")
        params["lo_id"] = loan_officer_id

    where_sql = " AND ".join(filters)

    # Per-method breakdown with percentiles
    try:
        method_query = (
            "SELECT"
            " delivery_method,"
            " COUNT(*) as count,"
            " AVG(elapsed_seconds) as avg_seconds,"
            " PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY elapsed_seconds) as median_seconds,"
            " PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY elapsed_seconds) as p95_seconds,"
            " MIN(elapsed_seconds) as min_seconds,"
            " MAX(elapsed_seconds) as max_seconds,"
            " COUNT(CASE WHEN elapsed_seconds <= " + str(THRESHOLD_ELITE_SECONDS) + " THEN 1 END) as under_60s,"
            " COUNT(CASE WHEN elapsed_seconds <= " + str(THRESHOLD_EXCELLENT_SECONDS) + " THEN 1 END) as under_5min,"
            " COUNT(CASE WHEN elapsed_seconds <= " + str(THRESHOLD_GOOD_SECONDS) + " THEN 1 END) as under_30min,"
            " COUNT(CASE WHEN elapsed_seconds <= " + str(THRESHOLD_ACCEPTABLE_SECONDS) + " THEN 1 END) as under_1hr"
            " FROM speed_to_lead_metrics"
            " WHERE " + where_sql
            + " GROUP BY delivery_method"
            " ORDER BY count DESC"
        )
        result = db.execute(text(method_query), params).fetchall()
    except Exception as e:
        logger.exception(f"Failed to query speed-to-lead metrics: {e}")
        return {
            "period_days": days,
            "total_triggers": 0,
            "error": str(e),
            "by_method": [],
        }

    total_count = sum(r.count for r in result) if result else 0
    total_under_60s = sum(r.under_60s for r in result) if result else 0
    total_under_5min = sum(r.under_5min for r in result) if result else 0
    total_under_30min = sum(r.under_30min for r in result) if result else 0
    total_under_1hr = sum(r.under_1hr for r in result) if result else 0

    by_method = []
    for r in result:
        by_method.append({
            "method": r.delivery_method,
            "count": r.count,
            "avg_seconds": round(float(r.avg_seconds or 0), 1),
            "median_seconds": round(float(r.median_seconds or 0), 1),
            "p95_seconds": round(float(r.p95_seconds or 0), 1),
            "min_seconds": round(float(r.min_seconds or 0), 1),
            "max_seconds": round(float(r.max_seconds or 0), 1),
            "pct_under_60s": _pct(r.under_60s, r.count),
            "pct_under_5min": _pct(r.under_5min, r.count),
            "pct_under_30min": _pct(r.under_30min, r.count),
        })

    return {
        "period_days": days,
        "total_triggers": total_count,
        "thresholds": {
            "pct_under_60s": _pct(total_under_60s, total_count),
            "pct_under_5min": _pct(total_under_5min, total_count),
            "pct_under_30min": _pct(total_under_30min, total_count),
            "pct_under_1hr": _pct(total_under_1hr, total_count),
        },
        "by_method": by_method,
    }


async def get_speed_to_lead_trend(
    db: Session,
    organization_id: int = None,
    days: int = 30,
    bucket: str = "day",  # "day" or "week"
) -> Dict[str, Any]:
    """Get speed-to-lead trend over time, bucketed by day or week.

    Useful for tracking whether response times are improving or degrading
    as pipeline volume changes.

    Args:
        db: Active SQLAlchemy session.
        organization_id: Filter by organization.
        days: Look-back period.
        bucket: Time bucket granularity ("day" or "week").

    Returns:
        Dict with trend data points ordered chronologically.
    """
    params: Dict[str, Any] = {"days": days}
    filters = ["created_at >= CURRENT_DATE - :days", "elapsed_seconds IS NOT NULL"]

    if organization_id:
        filters.append("organization_id = :org_id")
        params["org_id"] = organization_id

    where_sql = " AND ".join(filters)

    if bucket == "week":
        date_trunc = "DATE_TRUNC('week', created_at)"
    else:
        date_trunc = "DATE_TRUNC('day', created_at)"

    try:
        trend_query = (
            "SELECT"
            " " + date_trunc + " as period,"
            " COUNT(*) as count,"
            " AVG(elapsed_seconds) as avg_seconds,"
            " PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY elapsed_seconds) as median_seconds,"
            " COUNT(CASE WHEN elapsed_seconds <= " + str(THRESHOLD_ELITE_SECONDS) + " THEN 1 END) as under_60s"
            " FROM speed_to_lead_metrics"
            " WHERE " + where_sql
            + " GROUP BY " + date_trunc
            + " ORDER BY period ASC"
        )
        result = db.execute(text(trend_query), params).fetchall()
    except Exception as e:
        logger.exception(f"Failed to query speed-to-lead trend: {e}")
        return {"period_days": days, "bucket": bucket, "trend": [], "error": str(e)}

    trend = []
    for r in result:
        trend.append({
            "period": r.period.isoformat() if r.period else None,
            "count": r.count,
            "avg_seconds": round(float(r.avg_seconds or 0), 1),
            "median_seconds": round(float(r.median_seconds or 0), 1),
            "pct_under_60s": _pct(r.under_60s, r.count),
        })

    return {
        "period_days": days,
        "bucket": bucket,
        "trend": trend,
    }


async def get_lo_speed_leaderboard(
    db: Session,
    organization_id: int,
    days: int = 30,
    limit: int = 20,
) -> Dict[str, Any]:
    """Get loan officer speed-to-lead leaderboard.

    Ranks LOs by median response time within the organization,
    showing who is fastest at getting booking links to borrowers.

    Args:
        db: Active SQLAlchemy session.
        organization_id: Organization to query.
        days: Look-back period.
        limit: Max number of LOs to return.

    Returns:
        Dict with ranked LO list and org-wide average.
    """
    params: Dict[str, Any] = {"days": days, "org_id": organization_id, "limit": limit}

    try:
        lb_query = (
            "SELECT"
            " stl.loan_officer_id,"
            " CONCAT(u.first_name, ' ', u.last_name) as lo_name,"
            " COUNT(*) as count,"
            " AVG(stl.elapsed_seconds) as avg_seconds,"
            " PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY stl.elapsed_seconds) as median_seconds,"
            " COUNT(CASE WHEN stl.elapsed_seconds <= " + str(THRESHOLD_ELITE_SECONDS) + " THEN 1 END) as under_60s"
            " FROM speed_to_lead_metrics stl"
            " LEFT JOIN users u ON u.id = stl.loan_officer_id"
            " WHERE stl.organization_id = :org_id"
            "     AND stl.created_at >= CURRENT_DATE - :days"
            "     AND stl.elapsed_seconds IS NOT NULL"
            "     AND stl.loan_officer_id IS NOT NULL"
            " GROUP BY stl.loan_officer_id, u.first_name, u.last_name"
            " HAVING COUNT(*) >= 3"
            " ORDER BY median_seconds ASC"
            " LIMIT :limit"
        )
        result = db.execute(text(lb_query), params).fetchall()
    except Exception as e:
        logger.exception(f"Failed to query LO speed leaderboard: {e}")
        return {"organization_id": organization_id, "leaderboard": [], "error": str(e)}

    leaderboard = []
    for rank, r in enumerate(result, 1):
        leaderboard.append({
            "rank": rank,
            "loan_officer_id": r.loan_officer_id,
            "lo_name": r.lo_name or "Unknown",
            "count": r.count,
            "avg_seconds": round(float(r.avg_seconds or 0), 1),
            "median_seconds": round(float(r.median_seconds or 0), 1),
            "pct_under_60s": _pct(r.under_60s, r.count),
        })

    return {
        "organization_id": organization_id,
        "period_days": days,
        "leaderboard": leaderboard,
    }


# =============================================================================
# PRIVATE HELPERS
# =============================================================================

def _pct(numerator: int, denominator: int) -> float:
    """Calculate percentage, safe against division by zero."""
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _json_dumps(data: Any) -> Optional[str]:
    """Safely serialize to JSON string for the extra_data column."""
    if data is None:
        return None
    try:
        import json
        return json.dumps(data, default=str)
    except Exception as _exc:  # noqa: BLE001
        return None
