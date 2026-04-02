"""
Scheduling Optimizer - AI-Powered Scheduling Decision Engine

Learns from historical appointment data to optimize scheduling decisions:
1. Rank available slots by predicted conversion/show probability
2. Predict no-show risk for specific attendees by email
3. Generate org-level booking insights (best hours, best days, lead time, etc.)
4. Recommend best times for the upcoming week

Uses pure SQL aggregations against the scheduler_appointments table.
No external ML libraries required.

Data signals used:
- Hour-of-day show/no-show rates
- Day-of-week show/no-show rates
- Meeting type performance
- Booking source (AI vs manual vs website)
- Attendee history (repeat no-shows)
- Lead time (days between booking and appointment)
- Cancellation patterns
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Day name lookup (PostgreSQL DOW: 0=Sunday)
_DOW_NAMES = [
    "Sunday", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday",
]

# Default business hours for slot generation
_DEFAULT_START_HOUR = 9
_DEFAULT_END_HOUR = 17
_LUNCH_HOUR = 12


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def _pct(numerator: int, denominator: int) -> float:
    """Safe percentage calculation."""
    return round((numerator / denominator) * 100, 1) if denominator > 0 else 0.0


def _safe_float(val, default: float = 0.0) -> float:
    """Safely convert a DB value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _wilson_lower_bound(pos: int, total: int, z: float = 1.96) -> float:
    """
    Wilson score confidence interval lower bound.
    Handles small sample sizes gracefully: a 1/1 (100%) item
    ranks below a 95/100 (95%) item, as expected.
    z=1.96 = 95% confidence.
    """
    if total == 0:
        return 0.0
    p = pos / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return round((centre - spread) / denominator, 4)


# ---------------------------------------------------------------------------
# Core Optimizer
# ---------------------------------------------------------------------------

class SchedulingOptimizer:
    """
    Learns from historical scheduler_appointments data to optimize scheduling.

    All methods are static/classmethod and accept a DB session, making them
    easy to call from route handlers without instantiation state.
    """

    # ------------------------------------------------------------------
    # 1. Hourly show rates
    # ------------------------------------------------------------------

    @staticmethod
    def get_hourly_show_rates(
        db: Session, org_id: int, user_id: Optional[int] = None, days: int = 90,
    ) -> Dict[int, Dict[str, Any]]:
        """
        Calculate show rate by hour of day from the last N days.

        Returns: {hour_int: {"total": N, "completed": N, "no_shows": N, "show_rate": 0.xx}}
        """
        params: Dict[str, Any] = {"org_id": org_id, "days": days}
        user_filter = ""
        if user_id is not None:
            user_filter = "AND sa.assigned_user_id = :user_id"
            params["user_id"] = user_id

        query = (
            "SELECT"
            " EXTRACT(HOUR FROM sa.scheduled_start)::int AS hour,"
            " COUNT(*) AS total,"
            " COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS completed,"
            " COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_shows"
            " FROM scheduler_appointments sa"
            " WHERE sa.organization_id = :org_id"
            " " + user_filter
            + " AND sa.scheduled_start >= CURRENT_DATE - :days"
            " AND sa.status IN ('completed', 'no_show', 'cancelled')"
            " GROUP BY EXTRACT(HOUR FROM sa.scheduled_start)"
            " ORDER BY hour"
        )
        rows = db.execute(text(query), params).fetchall()

        result: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            total = r.total or 0
            completed = r.completed or 0
            result[int(r.hour)] = {
                "total": total,
                "completed": completed,
                "no_shows": r.no_shows or 0,
                "show_rate": round(completed / total, 4) if total > 0 else 0.5,
                "wilson_score": _wilson_lower_bound(completed, total),
            }
        return result

    # ------------------------------------------------------------------
    # 2. Day-of-week show rates
    # ------------------------------------------------------------------

    @staticmethod
    def get_dow_show_rates(
        db: Session, org_id: int, user_id: Optional[int] = None, days: int = 90,
    ) -> Dict[int, Dict[str, Any]]:
        """
        Calculate show rate by day of week (PostgreSQL DOW: 0=Sunday..6=Saturday).

        Returns: {dow_int: {"total": N, "completed": N, "no_shows": N, "show_rate": 0.xx, "day_name": "..."}}
        """
        params: Dict[str, Any] = {"org_id": org_id, "days": days}
        user_filter = ""
        if user_id is not None:
            user_filter = "AND sa.assigned_user_id = :user_id"
            params["user_id"] = user_id

        query = (
            "SELECT"
            " EXTRACT(DOW FROM sa.scheduled_start)::int AS dow,"
            " COUNT(*) AS total,"
            " COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS completed,"
            " COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_shows"
            " FROM scheduler_appointments sa"
            " WHERE sa.organization_id = :org_id"
            " " + user_filter
            + " AND sa.scheduled_start >= CURRENT_DATE - :days"
            " AND sa.status IN ('completed', 'no_show', 'cancelled')"
            " GROUP BY EXTRACT(DOW FROM sa.scheduled_start)"
            " ORDER BY dow"
        )
        rows = db.execute(text(query), params).fetchall()

        result: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            total = r.total or 0
            completed = r.completed or 0
            dow = int(r.dow)
            result[dow] = {
                "total": total,
                "completed": completed,
                "no_shows": r.no_shows or 0,
                "show_rate": round(completed / total, 4) if total > 0 else 0.5,
                "wilson_score": _wilson_lower_bound(completed, total),
                "day_name": _DOW_NAMES[dow] if 0 <= dow <= 6 else "Unknown",
            }
        return result

    # ------------------------------------------------------------------
    # 3. Slot scoring
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_slot_score(
        slot_hour: int,
        slot_dow: int,
        hourly_stats: Dict[int, Dict[str, Any]],
        dow_stats: Dict[int, Dict[str, Any]],
        meeting_type_stats: Optional[Dict[str, float]] = None,
        meeting_type: Optional[str] = None,
    ) -> float:
        """
        Score a candidate slot based on historical patterns.

        Weights:
        - 55% hour-of-day pattern (most predictive signal)
        - 30% day-of-week pattern
        - 10% meeting type performance
        - 5% baseline prior

        Returns a score between 0.0 and 1.0.
        """
        hour_data = hourly_stats.get(slot_hour, {})
        hour_rate = hour_data.get("wilson_score", 0.0) if hour_data.get("total", 0) >= 3 else 0.0
        # Fall back to raw show_rate for sparse data
        if hour_rate == 0.0:
            hour_rate = hour_data.get("show_rate", 0.5)

        dow_data = dow_stats.get(slot_dow, {})
        dow_rate = dow_data.get("wilson_score", 0.0) if dow_data.get("total", 0) >= 3 else 0.0
        if dow_rate == 0.0:
            dow_rate = dow_data.get("show_rate", 0.5)

        # Meeting type bonus
        mt_score = 0.5  # neutral default
        if meeting_type_stats and meeting_type and meeting_type in meeting_type_stats:
            mt_score = meeting_type_stats[meeting_type]

        # Weighted combination
        score = hour_rate * 0.55 + dow_rate * 0.30 + mt_score * 0.10 + 0.5 * 0.05
        return round(min(max(score, 0.0), 1.0), 4)

    # ------------------------------------------------------------------
    # 4. Optimal slots
    # ------------------------------------------------------------------

    @staticmethod
    async def get_optimal_slots(
        db: Session,
        org_id: int,
        user_id: int,
        target_date: date,
        count: int = 5,
        duration_minutes: int = 30,
        meeting_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return available time slots for `target_date` ranked by predicted
        conversion probability.

        Generates candidate slots from business hours, filters out booked
        slots, then scores and ranks remaining candidates.
        """
        # Gather historical stats
        hourly_stats = SchedulingOptimizer.get_hourly_show_rates(db, org_id, user_id)
        dow_stats = SchedulingOptimizer.get_dow_show_rates(db, org_id, user_id)

        # Meeting type show rates (optional enrichment)
        mt_stats: Optional[Dict[str, float]] = None
        if meeting_type:
            mt_rows = db.execute(text("""
                SELECT
                    sa.meeting_type,
                    COUNT(*) AS total,
                    COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS completed
                FROM scheduler_appointments sa
                WHERE sa.organization_id = :org_id
                    AND sa.assigned_user_id = :user_id
                    AND sa.scheduled_start >= CURRENT_DATE - 90
                    AND sa.status IN ('completed', 'no_show')
                    AND sa.meeting_type IS NOT NULL
                GROUP BY sa.meeting_type
                HAVING COUNT(*) >= 3
            """), {"org_id": org_id, "user_id": user_id}).fetchall()
            mt_stats = {}
            for r in mt_rows:
                t = r.total or 0
                c = r.completed or 0
                mt_stats[r.meeting_type] = _wilson_lower_bound(c, t)

        # Get already-booked slots for this user on target_date
        start_dt = datetime.combine(target_date, time.min)
        end_dt = datetime.combine(target_date, time.max)

        booked_rows = db.execute(text("""
            SELECT
                EXTRACT(HOUR FROM scheduled_start)::int AS hour,
                EXTRACT(MINUTE FROM scheduled_start)::int AS minute
            FROM scheduler_appointments
            WHERE assigned_user_id = :user_id
                AND organization_id = :org_id
                AND scheduled_start >= :start_dt
                AND scheduled_start <= :end_dt
                AND status NOT IN ('cancelled', 'no_show')
        """), {
            "user_id": user_id,
            "org_id": org_id,
            "start_dt": start_dt,
            "end_dt": end_dt,
        }).fetchall()

        booked_hours = {(int(r.hour), int(r.minute)) for r in booked_rows}

        # Python weekday (Mon=0) -> PostgreSQL DOW (Sun=0)
        target_dow = (target_date.weekday() + 1) % 7

        # Generate candidate slots
        scored_slots: List[Dict[str, Any]] = []
        for hour in range(_DEFAULT_START_HOUR, _DEFAULT_END_HOUR):
            if hour == _LUNCH_HOUR:
                continue
            # Generate slots at 30-minute intervals
            for minute in (0, 30):
                if (hour, minute) in booked_hours:
                    continue

                score = SchedulingOptimizer.calculate_slot_score(
                    slot_hour=hour,
                    slot_dow=target_dow,
                    hourly_stats=hourly_stats,
                    dow_stats=dow_stats,
                    meeting_type_stats=mt_stats,
                    meeting_type=meeting_type,
                )

                slot_start = datetime.combine(target_date, time(hour, minute))
                slot_end = slot_start + timedelta(minutes=duration_minutes)

                scored_slots.append({
                    "start": slot_start.isoformat(),
                    "end": slot_end.isoformat(),
                    "hour": hour,
                    "minute": minute,
                    "display": f"{hour:02d}:{minute:02d}",
                    "day_name": _DOW_NAMES[target_dow],
                    "score": score,
                    "predicted_show_rate_pct": round(score * 100, 1),
                })

        # Sort by score descending and take top N
        scored_slots.sort(key=lambda x: x["score"], reverse=True)
        top_slots = scored_slots[:count]

        return {
            "date": target_date.isoformat(),
            "user_id": user_id,
            "org_id": org_id,
            "meeting_type": meeting_type,
            "total_available": len(scored_slots),
            "returned_count": len(top_slots),
            "slots": top_slots,
            "data_quality": {
                "hourly_data_points": sum(v.get("total", 0) for v in hourly_stats.values()),
                "dow_data_points": sum(v.get("total", 0) for v in dow_stats.values()),
            },
            "recommendation": (
                f"Best slot: {top_slots[0]['display']} "
                f"({top_slots[0]['predicted_show_rate_pct']}% predicted show rate)"
                if top_slots else "No available slots"
            ),
        }

    # ------------------------------------------------------------------
    # 5. No-show risk by attendee email
    # ------------------------------------------------------------------

    @staticmethod
    async def get_no_show_risk(
        db: Session, attendee_email: str, org_id: int,
    ) -> Dict[str, Any]:
        """
        Predict no-show risk for a specific attendee based on their
        historical appointment record within the organization.

        Returns risk level (low/medium/high/unknown), score, and
        actionable recommendation.
        """
        rows = db.execute(text("""
            SELECT status, COUNT(*) AS count
            FROM scheduler_appointments
            WHERE attendee_email = :email
                AND organization_id = :org_id
                AND status IN ('completed', 'no_show', 'cancelled')
            GROUP BY status
        """), {"email": attendee_email, "org_id": org_id}).fetchall()

        stats: Dict[str, int] = {r.status: r.count for r in rows}
        total = sum(stats.values())
        no_show_count = stats.get("no_show", 0)
        completed_count = stats.get("completed", 0)
        cancelled_count = stats.get("cancelled", 0)

        if total == 0:
            return {
                "attendee_email": attendee_email,
                "risk": "unknown",
                "score": 0.5,
                "history_count": 0,
                "no_show_count": 0,
                "completed_count": 0,
                "cancelled_count": 0,
                "recommendation": "New attendee - no history available. Consider sending an extra reminder.",
            }

        # Risk score: weight no-shows heavily, cancellations less so
        attended_total = completed_count + no_show_count
        if attended_total > 0:
            risk_score = no_show_count / attended_total
        else:
            # Only cancellations, no actual attendance records
            risk_score = 0.4  # moderate baseline

        # Adjust for sample size using Wilson lower bound for more stable estimates
        if attended_total >= 3:
            risk_score = 1.0 - _wilson_lower_bound(completed_count, attended_total)

        risk_score = round(min(max(risk_score, 0.0), 1.0), 3)

        if risk_score > 0.3:
            risk_level = "high"
        elif risk_score > 0.15:
            risk_level = "medium"
        else:
            risk_level = "low"

        recommendation = _get_no_show_recommendation(
            risk_level, no_show_count, total, cancelled_count,
        )

        return {
            "attendee_email": attendee_email,
            "risk": risk_level,
            "score": risk_score,
            "history_count": total,
            "no_show_count": no_show_count,
            "completed_count": completed_count,
            "cancelled_count": cancelled_count,
            "recommendation": recommendation,
        }

    # ------------------------------------------------------------------
    # 6. Org-level booking insights
    # ------------------------------------------------------------------

    @staticmethod
    async def get_booking_insights(
        db: Session, org_id: int, days: int = 90,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive scheduling insights for the organization.

        Includes: best hours, best days, average lead time, popular
        appointment types, conversion by booking source, and overall
        show/no-show/cancel rates.
        """
        params = {"org_id": org_id, "days": days}

        # -- Overall stats --
        overall = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) AS completed,
                COUNT(CASE WHEN status = 'no_show' THEN 1 END) AS no_shows,
                COUNT(CASE WHEN status = 'cancelled' THEN 1 END) AS cancelled,
                AVG(EXTRACT(EPOCH FROM (scheduled_start - created_at)) / 86400) AS avg_lead_time_days,
                AVG(duration_minutes) AS avg_duration_minutes
            FROM scheduler_appointments
            WHERE organization_id = :org_id
                AND scheduled_start >= CURRENT_DATE - :days
        """), params).fetchone()

        total = overall.total or 0
        completed = overall.completed or 0
        no_shows = overall.no_shows or 0
        cancelled = overall.cancelled or 0

        # -- Best hours (top 5 by Wilson score) --
        best_hours_rows = db.execute(text("""
            SELECT
                EXTRACT(HOUR FROM scheduled_start)::int AS hour,
                COUNT(*) AS total,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) AS completed
            FROM scheduler_appointments
            WHERE organization_id = :org_id
                AND scheduled_start >= CURRENT_DATE - :days
                AND status IN ('completed', 'no_show')
            GROUP BY EXTRACT(HOUR FROM scheduled_start)
            HAVING COUNT(*) >= 3
            ORDER BY COUNT(CASE WHEN status = 'completed' THEN 1 END)::float
                     / NULLIF(COUNT(*), 0) DESC
            LIMIT 5
        """), params).fetchall()

        best_hours = [
            {
                "hour": int(r.hour),
                "display": f"{int(r.hour):02d}:00",
                "total": r.total,
                "show_rate_pct": _pct(r.completed, r.total),
                "wilson_score": _wilson_lower_bound(r.completed, r.total),
            }
            for r in best_hours_rows
        ]

        # -- Best days (top 3 by Wilson score) --
        best_days_rows = db.execute(text("""
            SELECT
                EXTRACT(DOW FROM scheduled_start)::int AS dow,
                COUNT(*) AS total,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) AS completed
            FROM scheduler_appointments
            WHERE organization_id = :org_id
                AND scheduled_start >= CURRENT_DATE - :days
                AND status IN ('completed', 'no_show')
            GROUP BY EXTRACT(DOW FROM scheduled_start)
            HAVING COUNT(*) >= 3
            ORDER BY COUNT(CASE WHEN status = 'completed' THEN 1 END)::float
                     / NULLIF(COUNT(*), 0) DESC
            LIMIT 3
        """), params).fetchall()

        best_days = [
            {
                "day_of_week": int(r.dow),
                "day_name": _DOW_NAMES[int(r.dow)] if 0 <= int(r.dow) <= 6 else "Unknown",
                "total": r.total,
                "show_rate_pct": _pct(r.completed, r.total),
                "wilson_score": _wilson_lower_bound(r.completed, r.total),
            }
            for r in best_days_rows
        ]

        # -- Popular meeting types --
        type_rows = db.execute(text("""
            SELECT
                COALESCE(meeting_type, 'custom') AS meeting_type,
                COUNT(*) AS total,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) AS completed,
                COUNT(CASE WHEN status = 'no_show' THEN 1 END) AS no_shows
            FROM scheduler_appointments
            WHERE organization_id = :org_id
                AND scheduled_start >= CURRENT_DATE - :days
            GROUP BY COALESCE(meeting_type, 'custom')
            ORDER BY COUNT(*) DESC
            LIMIT 10
        """), params).fetchall()

        meeting_types = [
            {
                "type": r.meeting_type,
                "total": r.total,
                "show_rate_pct": _pct(r.completed, r.completed + (r.no_shows or 0)),
                "no_show_rate_pct": _pct(r.no_shows or 0, r.completed + (r.no_shows or 0)),
            }
            for r in type_rows
        ]

        # -- Conversion by booking source --
        source_rows = db.execute(text("""
            SELECT
                CASE
                    WHEN booked_by_ai = true THEN 'ai'
                    WHEN external_source IS NOT NULL THEN external_source
                    ELSE 'manual'
                END AS booking_source,
                COUNT(*) AS total,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) AS completed,
                COUNT(CASE WHEN status = 'no_show' THEN 1 END) AS no_shows
            FROM scheduler_appointments
            WHERE organization_id = :org_id
                AND scheduled_start >= CURRENT_DATE - :days
                AND status IN ('completed', 'no_show')
            GROUP BY booking_source
            ORDER BY COUNT(*) DESC
        """), params).fetchall()

        by_source = [
            {
                "source": r.booking_source,
                "total": r.total,
                "show_rate_pct": _pct(r.completed, r.total),
            }
            for r in source_rows
        ]

        return {
            "org_id": org_id,
            "period_days": days,
            "summary": {
                "total_appointments": total,
                "completed": completed,
                "no_shows": no_shows,
                "cancelled": cancelled,
                "show_rate_pct": _pct(completed, completed + no_shows),
                "no_show_rate_pct": _pct(no_shows, completed + no_shows),
                "cancel_rate_pct": _pct(cancelled, total),
                "avg_lead_time_days": round(_safe_float(overall.avg_lead_time_days), 1),
                "avg_duration_minutes": round(_safe_float(overall.avg_duration_minutes), 0),
            },
            "best_hours": best_hours,
            "best_days": best_days,
            "meeting_types": meeting_types,
            "by_booking_source": by_source,
            "recommendation": _build_insights_recommendation(best_hours, best_days, total),
        }

    # ------------------------------------------------------------------
    # 7. Best times for next week
    # ------------------------------------------------------------------

    @staticmethod
    async def get_best_times_next_week(
        db: Session,
        org_id: int,
        user_id: int,
        count: int = 10,
    ) -> Dict[str, Any]:
        """
        Return the best available time slots over the next 7 business days,
        ranked by historical show rate.
        """
        hourly_stats = SchedulingOptimizer.get_hourly_show_rates(db, org_id, user_id)
        dow_stats = SchedulingOptimizer.get_dow_show_rates(db, org_id, user_id)

        # Get booked slots for the next 7 days
        today = date.today()
        end_date = today + timedelta(days=8)

        booked_rows = db.execute(text("""
            SELECT
                DATE(scheduled_start) AS appt_date,
                EXTRACT(HOUR FROM scheduled_start)::int AS hour,
                EXTRACT(MINUTE FROM scheduled_start)::int AS minute
            FROM scheduler_appointments
            WHERE assigned_user_id = :user_id
                AND organization_id = :org_id
                AND scheduled_start >= :start_dt
                AND scheduled_start < :end_dt
                AND status NOT IN ('cancelled', 'no_show')
        """), {
            "user_id": user_id,
            "org_id": org_id,
            "start_dt": datetime.combine(today, time.min),
            "end_dt": datetime.combine(end_date, time.min),
        }).fetchall()

        booked_set = {
            (r.appt_date, int(r.hour), int(r.minute))
            for r in booked_rows
        }

        candidates: List[Dict[str, Any]] = []

        for day_offset in range(1, 8):  # Next 7 days, starting tomorrow
            check_date = today + timedelta(days=day_offset)
            # Skip weekends
            if check_date.weekday() >= 5:
                continue

            target_dow = (check_date.weekday() + 1) % 7  # Python -> PG DOW

            for hour in range(_DEFAULT_START_HOUR, _DEFAULT_END_HOUR):
                if hour == _LUNCH_HOUR:
                    continue
                for minute in (0, 30):
                    if (check_date, hour, minute) in booked_set:
                        continue

                    score = SchedulingOptimizer.calculate_slot_score(
                        slot_hour=hour,
                        slot_dow=target_dow,
                        hourly_stats=hourly_stats,
                        dow_stats=dow_stats,
                    )

                    candidates.append({
                        "date": check_date.isoformat(),
                        "day_name": _DOW_NAMES[target_dow],
                        "hour": hour,
                        "minute": minute,
                        "display": f"{_DOW_NAMES[target_dow]}, {check_date.strftime('%b %d')} at {hour:02d}:{minute:02d}",
                        "score": score,
                        "predicted_show_rate_pct": round(score * 100, 1),
                    })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        top = candidates[:count]

        return {
            "user_id": user_id,
            "org_id": org_id,
            "period": f"{today.isoformat()} to {end_date.isoformat()}",
            "total_available": len(candidates),
            "returned_count": len(top),
            "best_times": top,
            "recommendation": (
                f"Top slot: {top[0]['display']} "
                f"({top[0]['predicted_show_rate_pct']}% predicted show rate)"
                if top else "No available slots in the next week"
            ),
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_no_show_recommendation(
    risk_level: str, no_show_count: int, total: int, cancelled_count: int,
) -> str:
    """Generate actionable recommendation based on no-show risk level."""
    if risk_level == "high":
        parts = [
            f"High risk: {no_show_count} no-shows out of {total} appointments.",
            "Send SMS reminder 2 hours before.",
            "Consider requiring confirmation or calling to confirm.",
        ]
        if cancelled_count > 2:
            parts.append(
                f"Also {cancelled_count} cancellations - offer flexible rescheduling."
            )
        return " ".join(parts)

    if risk_level == "medium":
        return (
            f"Moderate risk: {no_show_count} no-show(s) in {total} appointments. "
            "Ensure automated reminders are enabled (24h + 2h before)."
        )

    return (
        f"Low risk: {no_show_count} no-show(s) in {total} appointments. "
        "Standard reminder schedule is sufficient."
    )


def _build_insights_recommendation(
    best_hours: List[Dict], best_days: List[Dict], total: int,
) -> str:
    """Build a human-readable recommendation from insights data."""
    if total < 10:
        return (
            f"Only {total} appointments in the analysis period. "
            "Need more data for reliable recommendations."
        )

    parts = []
    if best_hours:
        top_hour = best_hours[0]
        parts.append(
            f"Best hour: {top_hour['display']} "
            f"({top_hour['show_rate_pct']}% show rate, n={top_hour['total']})"
        )
    if best_days:
        top_day = best_days[0]
        parts.append(
            f"Best day: {top_day['day_name']} "
            f"({top_day['show_rate_pct']}% show rate, n={top_day['total']})"
        )

    return ". ".join(parts) if parts else "Insufficient data for recommendations."
