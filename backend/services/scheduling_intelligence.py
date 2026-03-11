"""
Scheduling Intelligence — Continuous Learning System

Learns from historical data to optimize:
1. Best time to contact (per lead profile)
2. Best appointment times for conversions
3. Optimal call scripts (A/B testing outcomes)
4. No-show prediction and prevention
5. LO matching (which LO converts which lead type best)
6. Appointment duration prediction
7. Follow-up timing optimization

Data sources:
- Appointment outcomes (showed, no-show, cancelled, converted)
- Call logs (duration, outcome, time of day)
- Lead attributes (source, credit score, loan amount, location)
- LO performance (conversion rates by lead type)
- Time patterns (which day/hour combinations convert best)

Implementation: Pure SQL aggregations and statistical analysis.
No external ML libraries required.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Day name lookup (PostgreSQL DOW: 0=Sunday)
_DOW_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


# ---------------------------------------------------------------------------
# Helpers
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
    Useful for ranking items with different sample sizes —
    avoids the problem of a 1/1 (100%) item ranking above 95/100 (95%).
    z=1.96 corresponds to 95% confidence.
    """
    if total == 0:
        return 0.0
    p = pos / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return round((centre - spread) / denominator, 4)


# ---------------------------------------------------------------------------
# 1. Conversion Pattern Analysis
# ---------------------------------------------------------------------------

async def analyze_conversion_patterns(
    org_id: int,
    db: Session,
    days: int = 90,
) -> Dict[str, Any]:
    """
    Identify highest-converting time slots, days, and LO matches.

    Returns a structured analysis of which day/hour combinations and which
    LOs produce the best appointment outcomes (showed + converted).
    """
    params = {"org_id": org_id, "days": days}

    # -- By hour of day --
    by_hour = db.execute(text("""
        SELECT
            EXTRACT(HOUR FROM sa.scheduled_start)::int AS hour,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_showed
        FROM scheduler_appointments sa
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
          AND sa.status IN ('completed', 'no_show')
        GROUP BY EXTRACT(HOUR FROM sa.scheduled_start)
        ORDER BY hour
    """), params).fetchall()

    # -- By day of week --
    by_day = db.execute(text("""
        SELECT
            EXTRACT(DOW FROM sa.scheduled_start)::int AS dow,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_showed
        FROM scheduler_appointments sa
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
          AND sa.status IN ('completed', 'no_show')
        GROUP BY EXTRACT(DOW FROM sa.scheduled_start)
        ORDER BY dow
    """), params).fetchall()

    # -- By LO (assigned_user_id) --
    by_lo = db.execute(text("""
        SELECT
            sa.assigned_user_id AS lo_id,
            CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_showed
        FROM scheduler_appointments sa
        JOIN users u ON u.id = sa.assigned_user_id
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
          AND sa.status IN ('completed', 'no_show')
        GROUP BY sa.assigned_user_id, u.first_name, u.last_name
        HAVING COUNT(*) >= 5
        ORDER BY COUNT(CASE WHEN sa.status = 'completed' THEN 1 END)::float / NULLIF(COUNT(*), 0) DESC
    """), params).fetchall()

    # -- Combined day+hour heatmap (top 10 slots) --
    heatmap = db.execute(text("""
        SELECT
            EXTRACT(DOW FROM sa.scheduled_start)::int AS dow,
            EXTRACT(HOUR FROM sa.scheduled_start)::int AS hour,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed
        FROM scheduler_appointments sa
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
          AND sa.status IN ('completed', 'no_show')
        GROUP BY EXTRACT(DOW FROM sa.scheduled_start), EXTRACT(HOUR FROM sa.scheduled_start)
        HAVING COUNT(*) >= 3
        ORDER BY COUNT(CASE WHEN sa.status = 'completed' THEN 1 END)::float / NULLIF(COUNT(*), 0) DESC
        LIMIT 10
    """), params).fetchall()

    def _build_hour(row) -> Dict:
        total = row.total or 0
        showed = row.showed or 0
        return {
            "hour": row.hour,
            "display": f"{row.hour:02d}:00",
            "total": total,
            "showed": showed,
            "show_rate_pct": _pct(showed, total),
            "wilson_score": _wilson_lower_bound(showed, total),
        }

    def _build_day(row) -> Dict:
        total = row.total or 0
        showed = row.showed or 0
        return {
            "day_of_week": row.dow,
            "day_name": _DOW_NAMES[row.dow] if 0 <= row.dow <= 6 else "Unknown",
            "total": total,
            "showed": showed,
            "show_rate_pct": _pct(showed, total),
            "wilson_score": _wilson_lower_bound(showed, total),
        }

    hour_data = [_build_hour(r) for r in by_hour]
    day_data = [_build_day(r) for r in by_day]
    lo_data = [
        {
            "lo_id": r.lo_id,
            "lo_name": r.lo_name,
            "total": r.total or 0,
            "showed": r.showed or 0,
            "show_rate_pct": _pct(r.showed or 0, r.total or 0),
        }
        for r in by_lo
    ]
    heatmap_data = [
        {
            "day_name": _DOW_NAMES[r.dow] if 0 <= r.dow <= 6 else "Unknown",
            "hour": f"{r.hour:02d}:00",
            "total": r.total or 0,
            "showed": r.showed or 0,
            "show_rate_pct": _pct(r.showed or 0, r.total or 0),
        }
        for r in heatmap
    ]

    # Pick best using Wilson score (handles low sample sizes)
    best_hour = max(hour_data, key=lambda x: x["wilson_score"]) if hour_data else None
    best_day = max(day_data, key=lambda x: x["wilson_score"]) if day_data else None

    return {
        "period_days": days,
        "by_hour": hour_data,
        "by_day": day_data,
        "by_lo": lo_data,
        "heatmap_top_slots": heatmap_data,
        "best_hour": best_hour,
        "best_day": best_day,
        "recommendation": (
            f"Best slot: {best_day['day_name']}s at {best_hour['display']} "
            f"({best_hour['show_rate_pct']}% show rate, n={best_hour['total']})"
            if best_hour and best_day else "Not enough data for recommendation"
        ),
    }


# ---------------------------------------------------------------------------
# 2. No-Show Risk Prediction
# ---------------------------------------------------------------------------

async def predict_no_show_risk(
    appointment_id: int,
    db: Session,
) -> Dict[str, Any]:
    """
    Predict no-show probability for a specific appointment (0.0-1.0).

    Risk factors evaluated:
    - Client's historical no-show rate
    - Day-of-week no-show rate for this org
    - Hour-of-day no-show rate
    - Lead source no-show rate
    - Time since booking (longer gap = higher risk)
    - Whether a reminder was sent
    - Reschedule history
    """
    # Get appointment details
    appt = db.execute(text("""
        SELECT
            sa.id, sa.organization_id, sa.assigned_user_id,
            sa.lead_id, sa.scheduled_start, sa.created_at,
            sa.reschedule_count, sa.booked_by_ai,
            sa.attendee_email,
            EXTRACT(HOUR FROM sa.scheduled_start)::int AS appt_hour,
            EXTRACT(DOW FROM sa.scheduled_start)::int AS appt_dow,
            l.source AS lead_source,
            l.ai_score AS lead_score
        FROM scheduler_appointments sa
        LEFT JOIN leads l ON l.id = sa.lead_id
        WHERE sa.id = :appointment_id
    """), {"appointment_id": appointment_id}).fetchone()

    if not appt:
        return {"appointment_id": appointment_id, "risk_score": 0.5, "error": "Appointment not found"}

    risk_factors: List[Dict[str, Any]] = []
    weights: List[Tuple[float, float]] = []  # (weight, risk_value)

    org_id = appt.organization_id

    # Factor 1: Client historical no-show rate (weight=0.30)
    if appt.lead_id:
        client_history = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(CASE WHEN status = 'no_show' THEN 1 END) AS no_shows
            FROM scheduler_appointments
            WHERE lead_id = :lead_id
              AND status IN ('completed', 'no_show')
              AND id != :appointment_id
        """), {"lead_id": appt.lead_id, "appointment_id": appointment_id}).fetchone()

        if client_history and client_history.total > 0:
            client_ns_rate = client_history.no_shows / client_history.total
            weights.append((0.30, client_ns_rate))
            risk_factors.append({
                "factor": "client_history",
                "description": f"Client no-showed {client_history.no_shows}/{client_history.total} past appointments",
                "risk_value": round(client_ns_rate, 3),
                "weight": 0.30,
            })
        else:
            # No history — use org average as baseline
            weights.append((0.10, 0.2))  # Assume 20% baseline, lower weight
            risk_factors.append({
                "factor": "client_history",
                "description": "No prior appointment history — using baseline",
                "risk_value": 0.2,
                "weight": 0.10,
            })
    else:
        weights.append((0.10, 0.25))  # Unknown client, slightly higher risk
        risk_factors.append({
            "factor": "client_history",
            "description": "No lead linked — elevated baseline",
            "risk_value": 0.25,
            "weight": 0.10,
        })

    # Factor 2: Day-of-week no-show rate (weight=0.15)
    dow_stats = db.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN status = 'no_show' THEN 1 END) AS no_shows
        FROM scheduler_appointments
        WHERE organization_id = :org_id
          AND EXTRACT(DOW FROM scheduled_start) = :dow
          AND status IN ('completed', 'no_show')
          AND scheduled_start >= CURRENT_DATE - 180
    """), {"org_id": org_id, "dow": appt.appt_dow}).fetchone()

    if dow_stats and dow_stats.total >= 5:
        dow_ns_rate = dow_stats.no_shows / dow_stats.total
        weights.append((0.15, dow_ns_rate))
        day_name = _DOW_NAMES[appt.appt_dow] if 0 <= appt.appt_dow <= 6 else "Unknown"
        risk_factors.append({
            "factor": "day_of_week",
            "description": f"{day_name}: {dow_stats.no_shows}/{dow_stats.total} no-shows historically",
            "risk_value": round(dow_ns_rate, 3),
            "weight": 0.15,
        })

    # Factor 3: Hour-of-day no-show rate (weight=0.15)
    hour_stats = db.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN status = 'no_show' THEN 1 END) AS no_shows
        FROM scheduler_appointments
        WHERE organization_id = :org_id
          AND EXTRACT(HOUR FROM scheduled_start) = :hour
          AND status IN ('completed', 'no_show')
          AND scheduled_start >= CURRENT_DATE - 180
    """), {"org_id": org_id, "hour": appt.appt_hour}).fetchone()

    if hour_stats and hour_stats.total >= 5:
        hour_ns_rate = hour_stats.no_shows / hour_stats.total
        weights.append((0.15, hour_ns_rate))
        risk_factors.append({
            "factor": "time_of_day",
            "description": f"{appt.appt_hour:02d}:00 slot: {hour_stats.no_shows}/{hour_stats.total} no-shows",
            "risk_value": round(hour_ns_rate, 3),
            "weight": 0.15,
        })

    # Factor 4: Lead source no-show rate (weight=0.10)
    if appt.lead_source:
        source_stats = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_shows
            FROM scheduler_appointments sa
            JOIN leads l ON l.id = sa.lead_id
            WHERE sa.organization_id = :org_id
              AND l.source = :source
              AND sa.status IN ('completed', 'no_show')
              AND sa.scheduled_start >= CURRENT_DATE - 180
        """), {"org_id": org_id, "source": appt.lead_source}).fetchone()

        if source_stats and source_stats.total >= 5:
            source_ns_rate = source_stats.no_shows / source_stats.total
            weights.append((0.10, source_ns_rate))
            risk_factors.append({
                "factor": "lead_source",
                "description": f"Source '{appt.lead_source}': {source_stats.no_shows}/{source_stats.total} no-shows",
                "risk_value": round(source_ns_rate, 3),
                "weight": 0.10,
            })

    # Factor 5: Days between booking and appointment (weight=0.10)
    if appt.created_at and appt.scheduled_start:
        booking_gap_days = (appt.scheduled_start - appt.created_at).total_seconds() / 86400
        # Longer gaps correlate with higher no-show risk
        if booking_gap_days > 14:
            gap_risk = 0.40
        elif booking_gap_days > 7:
            gap_risk = 0.25
        elif booking_gap_days > 3:
            gap_risk = 0.15
        else:
            gap_risk = 0.08
        weights.append((0.10, gap_risk))
        risk_factors.append({
            "factor": "booking_gap",
            "description": f"Booked {int(booking_gap_days)} days before appointment",
            "risk_value": round(gap_risk, 3),
            "weight": 0.10,
        })

    # Factor 6: Reschedule history (weight=0.10)
    reschedule_count = appt.reschedule_count or 0
    if reschedule_count > 0:
        resched_risk = min(0.5, reschedule_count * 0.15)
        weights.append((0.10, resched_risk))
        risk_factors.append({
            "factor": "reschedule_history",
            "description": f"Rescheduled {reschedule_count} time(s)",
            "risk_value": round(resched_risk, 3),
            "weight": 0.10,
        })

    # Factor 7: Reminder acknowledgement (weight=0.10)
    reminder_check = db.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN status IN ('delivered', 'acknowledged') THEN 1 END) AS delivered
        FROM scheduler_reminders
        WHERE appointment_id = :appointment_id
    """), {"appointment_id": appointment_id}).fetchone()

    if reminder_check and reminder_check.total > 0:
        if reminder_check.delivered > 0:
            weights.append((0.10, 0.10))  # Reminder delivered = lower risk
            risk_factors.append({
                "factor": "reminder_status",
                "description": "Reminder delivered successfully",
                "risk_value": 0.10,
                "weight": 0.10,
            })
        else:
            weights.append((0.10, 0.35))  # Reminder not delivered
            risk_factors.append({
                "factor": "reminder_status",
                "description": "Reminder not delivered",
                "risk_value": 0.35,
                "weight": 0.10,
            })
    else:
        weights.append((0.05, 0.25))  # No reminders set up
        risk_factors.append({
            "factor": "reminder_status",
            "description": "No reminders configured",
            "risk_value": 0.25,
            "weight": 0.05,
        })

    # Compute weighted risk score
    if not weights:
        risk_score = 0.2  # Baseline fallback
    else:
        total_weight = sum(w for w, _ in weights)
        risk_score = sum(w * r for w, r in weights) / total_weight if total_weight > 0 else 0.2

    risk_score = round(min(max(risk_score, 0.0), 1.0), 3)

    # Classify risk level
    if risk_score >= 0.6:
        risk_level = "high"
    elif risk_score >= 0.3:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Generate mitigation suggestions
    mitigations = []
    if risk_score >= 0.3:
        mitigations.append("Send additional SMS reminder 2 hours before appointment")
    if risk_score >= 0.5:
        mitigations.append("Consider calling the client to confirm attendance")
    if reschedule_count >= 2:
        mitigations.append("High reschedule count — offer a more convenient time")
    if not reminder_check or reminder_check.total == 0:
        mitigations.append("Enable automated reminders for this appointment")

    return {
        "appointment_id": appointment_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_factors": risk_factors,
        "mitigations": mitigations,
    }


# ---------------------------------------------------------------------------
# 3. Optimal Time Suggestion
# ---------------------------------------------------------------------------

async def suggest_optimal_time(
    lead_id: int,
    lo_id: int,
    db: Session,
    days_ahead: int = 14,
) -> Dict[str, Any]:
    """
    Suggest top 3 time slots ranked by predicted conversion probability.

    Combines:
    - Org-wide hour/day show rates
    - LO-specific show rates
    - Lead-source-specific show rates
    - LO calendar availability
    """
    # Get lead info for source-based weighting
    lead = db.execute(text("""
        SELECT id, source, ai_score FROM leads WHERE id = :lead_id
    """), {"lead_id": lead_id}).fetchone()

    lead_source = lead.source if lead else None

    # Get the LO's org
    lo = db.execute(text("""
        SELECT id, organization_id FROM users WHERE id = :lo_id
    """), {"lo_id": lo_id}).fetchone()

    if not lo:
        return {"lead_id": lead_id, "lo_id": lo_id, "slots": [], "error": "LO not found"}

    org_id = lo.organization_id

    # Get show rates by day+hour for this LO (180 days of data)
    lo_stats = db.execute(text("""
        SELECT
            EXTRACT(DOW FROM sa.scheduled_start)::int AS dow,
            EXTRACT(HOUR FROM sa.scheduled_start)::int AS hour,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed
        FROM scheduler_appointments sa
        WHERE sa.assigned_user_id = :lo_id
          AND sa.status IN ('completed', 'no_show')
          AND sa.scheduled_start >= CURRENT_DATE - 180
        GROUP BY EXTRACT(DOW FROM sa.scheduled_start), EXTRACT(HOUR FROM sa.scheduled_start)
    """), {"lo_id": lo_id}).fetchall()

    # Build a score lookup: (dow, hour) -> wilson_score
    slot_scores: Dict[Tuple[int, int], float] = {}
    for row in lo_stats:
        total = row.total or 0
        showed = row.showed or 0
        if total >= 2:
            slot_scores[(row.dow, row.hour)] = _wilson_lower_bound(showed, total)

    # If LO has sparse data, supplement with org-wide stats
    if len(slot_scores) < 10:
        org_stats = db.execute(text("""
            SELECT
                EXTRACT(DOW FROM sa.scheduled_start)::int AS dow,
                EXTRACT(HOUR FROM sa.scheduled_start)::int AS hour,
                COUNT(*) AS total,
                COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed
            FROM scheduler_appointments sa
            WHERE sa.organization_id = :org_id
              AND sa.status IN ('completed', 'no_show')
              AND sa.scheduled_start >= CURRENT_DATE - 180
            GROUP BY EXTRACT(DOW FROM sa.scheduled_start), EXTRACT(HOUR FROM sa.scheduled_start)
        """), {"org_id": org_id}).fetchall()

        for row in org_stats:
            key = (row.dow, row.hour)
            if key not in slot_scores:
                total = row.total or 0
                showed = row.showed or 0
                if total >= 3:
                    # Discount org-wide slightly vs LO-specific
                    slot_scores[key] = _wilson_lower_bound(showed, total) * 0.85

    # Lead source adjustment
    source_adjustment: Dict[Tuple[int, int], float] = {}
    if lead_source:
        source_stats = db.execute(text("""
            SELECT
                EXTRACT(DOW FROM sa.scheduled_start)::int AS dow,
                EXTRACT(HOUR FROM sa.scheduled_start)::int AS hour,
                COUNT(*) AS total,
                COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed
            FROM scheduler_appointments sa
            JOIN leads l ON l.id = sa.lead_id
            WHERE sa.organization_id = :org_id
              AND l.source = :source
              AND sa.status IN ('completed', 'no_show')
              AND sa.scheduled_start >= CURRENT_DATE - 180
            GROUP BY EXTRACT(DOW FROM sa.scheduled_start), EXTRACT(HOUR FROM sa.scheduled_start)
            HAVING COUNT(*) >= 3
        """), {"org_id": org_id, "source": lead_source}).fetchall()

        for row in source_stats:
            source_adjustment[(row.dow, row.hour)] = _wilson_lower_bound(
                row.showed or 0, row.total or 0
            )

    # Get LO's booked slots in the next N days
    booked = db.execute(text("""
        SELECT
            EXTRACT(DOW FROM scheduled_start)::int AS dow,
            EXTRACT(HOUR FROM scheduled_start)::int AS hour,
            DATE(scheduled_start) AS appt_date
        FROM scheduler_appointments
        WHERE assigned_user_id = :lo_id
          AND scheduled_start >= CURRENT_DATE
          AND scheduled_start < CURRENT_DATE + :days_ahead
          AND status NOT IN ('cancelled')
    """), {"lo_id": lo_id, "days_ahead": days_ahead}).fetchall()

    booked_set = set()
    for row in booked:
        booked_set.add((row.appt_date, row.hour))

    # Generate candidate slots for the next N days
    candidates = []
    today = date.today()

    for day_offset in range(days_ahead):
        check_date = today + timedelta(days=day_offset)
        dow = (check_date.weekday() + 1) % 7  # Python weekday (Mon=0) -> PG DOW (Sun=0)
        if check_date.weekday() >= 5:  # Skip weekends
            continue

        for hour in range(9, 17):  # Business hours 9-16
            if hour == 12:  # Skip lunch
                continue
            if (check_date, hour) in booked_set:
                continue

            # Compute combined score
            base_score = slot_scores.get((dow, hour), 0.3)  # Default 30% if no data
            source_bonus = source_adjustment.get((dow, hour), 0.0)
            # Blend: 70% base + 30% source bonus (when available)
            combined = base_score * 0.7 + source_bonus * 0.3 if source_bonus else base_score

            candidates.append({
                "date": check_date.isoformat(),
                "day_name": _DOW_NAMES[dow],
                "hour": hour,
                "display": f"{_DOW_NAMES[dow]}, {check_date.strftime('%b %d')} at {hour:02d}:00",
                "score": round(combined, 4),
                "show_rate_estimate_pct": round(combined * 100, 1),
            })

    # Sort by score descending, take top 3
    candidates.sort(key=lambda x: x["score"], reverse=True)
    top_slots = candidates[:3]

    return {
        "lead_id": lead_id,
        "lo_id": lo_id,
        "lead_source": lead_source,
        "data_points_used": len(slot_scores),
        "slots": top_slots,
        "recommendation": (
            f"Best: {top_slots[0]['display']} (est. {top_slots[0]['show_rate_estimate_pct']}% show rate)"
            if top_slots else "No available slots found"
        ),
    }


# ---------------------------------------------------------------------------
# 4. LO Matching Optimization
# ---------------------------------------------------------------------------

async def optimize_lo_matching(
    lead_id: int,
    org_id: int,
    db: Session,
) -> Dict[str, Any]:
    """
    Find the best LO for a lead based on historical conversion data.

    Matches on: lead source, loan type, loan amount range, and overall
    show/conversion rates per LO.
    """
    lead = db.execute(text("""
        SELECT id, source, loan_type, loan_amount, credit_score, ai_score
        FROM leads WHERE id = :lead_id
    """), {"lead_id": lead_id}).fetchone()

    if not lead:
        return {"lead_id": lead_id, "matches": [], "error": "Lead not found"}

    # Build LO performance by lead source
    lo_performance = db.execute(text("""
        SELECT
            sa.assigned_user_id AS lo_id,
            CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
            l.source AS lead_source,
            COUNT(*) AS total_appts,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_shows
        FROM scheduler_appointments sa
        JOIN users u ON u.id = sa.assigned_user_id
        LEFT JOIN leads l ON l.id = sa.lead_id
        WHERE sa.organization_id = :org_id
          AND sa.status IN ('completed', 'no_show')
          AND sa.scheduled_start >= CURRENT_DATE - 180
          AND u.is_active = true
        GROUP BY sa.assigned_user_id, u.first_name, u.last_name, l.source
        HAVING COUNT(*) >= 3
    """), {"org_id": org_id}).fetchall()

    # Also get loan conversion data (appointments that led to funded loans)
    lo_conversions = db.execute(text("""
        SELECT
            ao.lo_user_id AS lo_id,
            ao.lead_source,
            COUNT(*) AS total_outcomes,
            COUNT(CASE WHEN ao.conversion_stage IN ('application_started', 'submitted', 'approved', 'funded') THEN 1 END) AS converted,
            COUNT(CASE WHEN ao.conversion_stage = 'funded' THEN 1 END) AS funded,
            COALESCE(SUM(ao.revenue), 0) AS total_revenue
        FROM appointment_outcomes ao
        WHERE ao.organization_id = :org_id
          AND ao.appointment_date >= CURRENT_DATE - 180
        GROUP BY ao.lo_user_id, ao.lead_source
    """), {"org_id": org_id}).fetchall()

    # Build LO score map
    lo_scores: Dict[int, Dict] = {}

    for row in lo_performance:
        lo_id = row.lo_id
        if lo_id not in lo_scores:
            lo_scores[lo_id] = {
                "lo_id": lo_id,
                "lo_name": row.lo_name,
                "total_appts": 0,
                "showed": 0,
                "source_match_bonus": 0.0,
            }
        lo_scores[lo_id]["total_appts"] += row.total_appts
        lo_scores[lo_id]["showed"] += row.showed

        # Bonus for matching lead source
        if lead.source and row.lead_source == lead.source:
            source_show_rate = row.showed / row.total_appts if row.total_appts > 0 else 0
            lo_scores[lo_id]["source_match_bonus"] = max(
                lo_scores[lo_id]["source_match_bonus"],
                source_show_rate * 0.2,  # Up to 20% bonus
            )

    # Add conversion bonus
    for row in lo_conversions:
        lo_id = row.lo_id
        if lo_id in lo_scores:
            conversion_rate = row.converted / row.total_outcomes if row.total_outcomes > 0 else 0
            lo_scores[lo_id].setdefault("conversion_rate", 0.0)
            lo_scores[lo_id]["conversion_rate"] = max(
                lo_scores[lo_id].get("conversion_rate", 0.0), conversion_rate
            )
            lo_scores[lo_id].setdefault("funded_count", 0)
            lo_scores[lo_id]["funded_count"] += row.funded or 0

    # Compute final score for each LO
    results = []
    for lo_id, data in lo_scores.items():
        base_show_rate = _wilson_lower_bound(data["showed"], data["total_appts"])
        conversion_bonus = data.get("conversion_rate", 0.0) * 0.3
        source_bonus = data["source_match_bonus"]

        # Combined score: show rate (50%) + conversion bonus (30%) + source match (20%)
        combined_score = base_show_rate * 0.5 + conversion_bonus + source_bonus

        results.append({
            "lo_id": data["lo_id"],
            "lo_name": data["lo_name"],
            "total_appointments": data["total_appts"],
            "show_rate_pct": _pct(data["showed"], data["total_appts"]),
            "conversion_rate_pct": round(data.get("conversion_rate", 0.0) * 100, 1),
            "funded_count": data.get("funded_count", 0),
            "source_match": bool(data["source_match_bonus"] > 0),
            "match_score": round(combined_score, 4),
        })

    results.sort(key=lambda x: x["match_score"], reverse=True)

    return {
        "lead_id": lead_id,
        "lead_source": lead.source,
        "lead_loan_type": lead.loan_type,
        "matches": results[:5],
        "recommendation": (
            f"Best match: {results[0]['lo_name']} "
            f"(score: {results[0]['match_score']:.2f}, "
            f"show rate: {results[0]['show_rate_pct']}%)"
            if results else "No matching LOs found"
        ),
    }


# ---------------------------------------------------------------------------
# 5. Script Performance Analysis
# ---------------------------------------------------------------------------

async def get_script_performance(
    org_id: int,
    db: Session,
    days: int = 90,
) -> Dict[str, Any]:
    """
    Analyze which booking channels/methods have the highest show and
    conversion rates. Uses the booked_by_ai flag and ai_booking_context
    as proxy for different scripts/approaches.
    """
    params = {"org_id": org_id, "days": days}

    # Performance by booking channel
    by_channel = db.execute(text("""
        SELECT
            CASE
                WHEN sa.booked_by_ai = true THEN 'ai_booked'
                ELSE 'manual_booked'
            END AS booking_method,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_shows,
            COUNT(CASE WHEN sa.status = 'cancelled' THEN 1 END) AS cancelled
        FROM scheduler_appointments sa
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
        GROUP BY CASE WHEN sa.booked_by_ai = true THEN 'ai_booked' ELSE 'manual_booked' END
    """), params).fetchall()

    # Performance by meeting type
    by_type = db.execute(text("""
        SELECT
            COALESCE(sa.meeting_type, 'unknown') AS meeting_type,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_shows
        FROM scheduler_appointments sa
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
          AND sa.status IN ('completed', 'no_show')
        GROUP BY sa.meeting_type
        ORDER BY COUNT(*) DESC
    """), params).fetchall()

    # Performance by meeting mode (video vs phone vs in-person)
    by_mode = db.execute(text("""
        SELECT
            COALESCE(sa.meeting_mode, 'unknown') AS mode,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_shows
        FROM scheduler_appointments sa
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
          AND sa.status IN ('completed', 'no_show')
        GROUP BY sa.meeting_mode
        ORDER BY COUNT(*) DESC
    """), params).fetchall()

    def _build_row(row, name_field: str = "booking_method") -> Dict:
        total = row.total or 0
        showed = row.showed or 0
        resolved = showed + (row.no_shows or 0)
        return {
            "name": getattr(row, name_field, "unknown"),
            "total": total,
            "showed": showed,
            "no_shows": row.no_shows or 0,
            "show_rate_pct": _pct(showed, resolved),
            "wilson_score": _wilson_lower_bound(showed, resolved),
        }

    channel_data = [_build_row(r, "booking_method") for r in by_channel]
    type_data = [_build_row(r, "meeting_type") for r in by_type]
    mode_data = [_build_row(r, "mode") for r in by_mode]

    # Generate insights
    insights = []
    if len(channel_data) >= 2:
        sorted_channels = sorted(channel_data, key=lambda x: x["show_rate_pct"], reverse=True)
        best = sorted_channels[0]
        worst = sorted_channels[-1]
        if best["show_rate_pct"] - worst["show_rate_pct"] > 5:
            insights.append(
                f"{best['name']} has {best['show_rate_pct']}% show rate vs "
                f"{worst['show_rate_pct']}% for {worst['name']}"
            )

    if mode_data:
        best_mode = max(mode_data, key=lambda x: x["wilson_score"])
        insights.append(
            f"{best_mode['name']} meetings have the highest show rate "
            f"({best_mode['show_rate_pct']}%, n={best_mode['total']})"
        )

    return {
        "period_days": days,
        "by_booking_method": channel_data,
        "by_meeting_type": type_data,
        "by_meeting_mode": mode_data,
        "insights": insights,
    }


# ---------------------------------------------------------------------------
# 6. Appointment Duration Prediction
# ---------------------------------------------------------------------------

async def predict_appointment_duration(
    appointment_type: str,
    db: Session,
    org_id: Optional[int] = None,
    lo_id: Optional[int] = None,
    lead_source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Predict appointment duration based on historical patterns.

    Uses the appointment_outcomes table (actual_duration_minutes) and
    falls back to scheduled durations from scheduler_appointments.
    """
    params: Dict[str, Any] = {"appointment_type": appointment_type}
    filters = ["ao.appointment_type = :appointment_type", "ao.actual_duration_minutes IS NOT NULL"]

    if org_id:
        filters.append("ao.organization_id = :org_id")
        params["org_id"] = org_id
    if lo_id:
        filters.append("ao.lo_user_id = :lo_id")
        params["lo_id"] = lo_id
    if lead_source:
        filters.append("ao.lead_source = :lead_source")
        params["lead_source"] = lead_source

    where_sql = " AND ".join(filters)

    # Try outcomes table first (has actual duration)
    stats = db.execute(text(f"""
        SELECT
            COUNT(*) AS sample_count,
            AVG(ao.actual_duration_minutes) AS avg_duration,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ao.actual_duration_minutes) AS median_duration,
            MIN(ao.actual_duration_minutes) AS min_duration,
            MAX(ao.actual_duration_minutes) AS max_duration,
            STDDEV(ao.actual_duration_minutes) AS stddev_duration
        FROM appointment_outcomes ao
        WHERE {where_sql}
    """), params).fetchone()

    if stats and stats.sample_count and stats.sample_count >= 5:
        predicted = round(_safe_float(stats.median_duration, 30))
        confidence = min(0.95, 0.5 + (stats.sample_count / 200))

        return {
            "appointment_type": appointment_type,
            "predicted_minutes": predicted,
            "confidence": round(confidence, 2),
            "statistics": {
                "sample_count": stats.sample_count,
                "avg_minutes": round(_safe_float(stats.avg_duration), 1),
                "median_minutes": round(_safe_float(stats.median_duration), 1),
                "min_minutes": round(_safe_float(stats.min_duration), 0),
                "max_minutes": round(_safe_float(stats.max_duration), 0),
                "stddev_minutes": round(_safe_float(stats.stddev_duration), 1),
            },
            "recommendation": f"Schedule {predicted} minutes (based on {stats.sample_count} past appointments)",
        }

    # Fallback: use default durations from appointment_types table
    default_duration = 30  # Sensible fallback
    type_row = db.execute(text("""
        SELECT default_duration_minutes
        FROM appointment_types
        WHERE type_key = :appointment_type OR type_name = :appointment_type
        LIMIT 1
    """), {"appointment_type": appointment_type}).fetchone()

    if type_row:
        default_duration = type_row.default_duration_minutes or 30

    return {
        "appointment_type": appointment_type,
        "predicted_minutes": default_duration,
        "confidence": 0.3,
        "statistics": {"sample_count": 0},
        "recommendation": f"Using default of {default_duration} minutes (no historical data)",
    }


# ---------------------------------------------------------------------------
# 7. Follow-Up Timing Optimization
# ---------------------------------------------------------------------------

async def calculate_followup_timing(
    appointment_id: int,
    db: Session,
) -> Dict[str, Any]:
    """
    Determine optimal days to wait before following up after an appointment.

    Analyzes historical patterns: which follow-up intervals correlate with
    the highest conversion rates.
    """
    appt = db.execute(text("""
        SELECT
            sa.id, sa.organization_id, sa.assigned_user_id,
            sa.lead_id, sa.status, sa.scheduled_start,
            sa.meeting_type,
            l.source AS lead_source
        FROM scheduler_appointments sa
        LEFT JOIN leads l ON l.id = sa.lead_id
        WHERE sa.id = :appointment_id
    """), {"appointment_id": appointment_id}).fetchone()

    if not appt:
        return {"appointment_id": appointment_id, "error": "Appointment not found"}

    org_id = appt.organization_id

    # Analyze follow-up patterns for completed appointments that led to conversions
    # Look at time gap between appointment and next activity/appointment
    followup_patterns = db.execute(text("""
        SELECT
            ao.time_to_conversion_days,
            ao.conversion_stage,
            ao.outcome
        FROM appointment_outcomes ao
        WHERE ao.organization_id = :org_id
          AND ao.outcome = 'showed'
          AND ao.time_to_conversion_days IS NOT NULL
          AND ao.conversion_stage IS NOT NULL
          AND ao.conversion_stage != 'none'
        ORDER BY ao.time_to_conversion_days
    """), {"org_id": org_id}).fetchall()

    if followup_patterns:
        conversion_days = [r.time_to_conversion_days for r in followup_patterns if r.time_to_conversion_days is not None]

        if conversion_days:
            # Compute optimal window
            avg_days = sum(conversion_days) / len(conversion_days)
            sorted_days = sorted(conversion_days)
            median_days = sorted_days[len(sorted_days) // 2]

            # Most conversions happen in a specific window
            buckets = {"0-1": 0, "2-3": 0, "4-7": 0, "8-14": 0, "15+": 0}
            for d in conversion_days:
                if d <= 1:
                    buckets["0-1"] += 1
                elif d <= 3:
                    buckets["2-3"] += 1
                elif d <= 7:
                    buckets["4-7"] += 1
                elif d <= 14:
                    buckets["8-14"] += 1
                else:
                    buckets["15+"] += 1

            best_bucket = max(buckets, key=buckets.get)

            # Map bucket to recommended follow-up day
            bucket_to_followup = {
                "0-1": 1,
                "2-3": 2,
                "4-7": 3,
                "8-14": 5,
                "15+": 7,
            }
            recommended_days = bucket_to_followup.get(best_bucket, 3)

            return {
                "appointment_id": appointment_id,
                "meeting_type": appt.meeting_type,
                "recommended_followup_days": recommended_days,
                "confidence": min(0.9, 0.4 + len(conversion_days) / 100),
                "analysis": {
                    "sample_size": len(conversion_days),
                    "avg_days_to_conversion": round(avg_days, 1),
                    "median_days_to_conversion": median_days,
                    "conversion_timing_buckets": buckets,
                    "best_window": best_bucket,
                },
                "recommendation": (
                    f"Follow up in {recommended_days} day(s) — "
                    f"most conversions happen within the {best_bucket} day window"
                ),
            }

    # Fallback: meeting-type-based defaults
    defaults = {
        "discovery_call": 1,
        "pre_approval_review": 2,
        "application_walkthrough": 1,
        "document_review": 2,
        "rate_lock_discussion": 1,
        "closing_prep": 1,
        "post_close_review": 7,
        "referral_partner_meeting": 3,
    }

    meeting_type = appt.meeting_type or "custom"
    recommended = defaults.get(meeting_type, 3)

    return {
        "appointment_id": appointment_id,
        "meeting_type": meeting_type,
        "recommended_followup_days": recommended,
        "confidence": 0.3,
        "analysis": {"sample_size": 0},
        "recommendation": f"Follow up in {recommended} day(s) (default for {meeting_type})",
    }


# ---------------------------------------------------------------------------
# 8. Weekly Insights Digest
# ---------------------------------------------------------------------------

async def generate_insights(
    org_id: int,
    db: Session,
    days: int = 30,
) -> Dict[str, Any]:
    """
    Generate a digest of scheduling intelligence insights.

    Produces human-readable insights like:
    - "Tuesday 10am has 85% show rate vs 60% for Friday 4pm"
    - "Referral leads convert 3x better with LO Sarah"
    - "Pre-appointment SMS reduces no-shows by 40%"
    """
    params = {"org_id": org_id, "days": days}
    insights: List[Dict[str, Any]] = []

    # --- Insight 1: Best and worst time slots ---
    time_slots = db.execute(text("""
        SELECT
            EXTRACT(DOW FROM sa.scheduled_start)::int AS dow,
            EXTRACT(HOUR FROM sa.scheduled_start)::int AS hour,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_shows
        FROM scheduler_appointments sa
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
          AND sa.status IN ('completed', 'no_show')
        GROUP BY EXTRACT(DOW FROM sa.scheduled_start), EXTRACT(HOUR FROM sa.scheduled_start)
        HAVING COUNT(*) >= 3
        ORDER BY COUNT(CASE WHEN sa.status = 'completed' THEN 1 END)::float / NULLIF(COUNT(*), 0) DESC
    """), params).fetchall()

    if len(time_slots) >= 2:
        best = time_slots[0]
        worst = time_slots[-1]
        best_rate = _pct(best.showed, best.total)
        worst_rate = _pct(worst.showed, worst.total)
        best_name = f"{_DOW_NAMES[best.dow]} {best.hour:02d}:00"
        worst_name = f"{_DOW_NAMES[worst.dow]} {worst.hour:02d}:00"

        if best_rate - worst_rate >= 10:
            insights.append({
                "type": "time_slot_performance",
                "title": "Time slot impact on show rates",
                "description": f"{best_name} has {best_rate}% show rate vs {worst_rate}% for {worst_name}",
                "impact": "high" if best_rate - worst_rate >= 25 else "medium",
                "data": {
                    "best_slot": best_name,
                    "best_rate": best_rate,
                    "worst_slot": worst_name,
                    "worst_rate": worst_rate,
                },
            })

    # --- Insight 2: LO-source matching ---
    lo_source = db.execute(text("""
        SELECT
            sa.assigned_user_id AS lo_id,
            CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
            l.source AS lead_source,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed
        FROM scheduler_appointments sa
        JOIN users u ON u.id = sa.assigned_user_id
        JOIN leads l ON l.id = sa.lead_id
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
          AND sa.status IN ('completed', 'no_show')
          AND l.source IS NOT NULL
        GROUP BY sa.assigned_user_id, u.first_name, u.last_name, l.source
        HAVING COUNT(*) >= 5
        ORDER BY COUNT(CASE WHEN sa.status = 'completed' THEN 1 END)::float / NULLIF(COUNT(*), 0) DESC
    """), params).fetchall()

    if len(lo_source) >= 2:
        best_match = lo_source[0]
        best_rate = _pct(best_match.showed, best_match.total)
        avg_rate_all = _pct(
            sum(r.showed for r in lo_source),
            sum(r.total for r in lo_source),
        )

        if best_rate > avg_rate_all + 10:
            multiplier = round(best_rate / max(avg_rate_all, 1), 1)
            insights.append({
                "type": "lo_lead_match",
                "title": "LO-Source specialization opportunity",
                "description": (
                    f"{best_match.lead_source} leads convert {multiplier}x better "
                    f"with {best_match.lo_name} ({best_rate}% vs {avg_rate_all}% avg)"
                ),
                "impact": "high" if multiplier >= 2 else "medium",
                "data": {
                    "lo_name": best_match.lo_name,
                    "lead_source": best_match.lead_source,
                    "show_rate": best_rate,
                    "avg_rate": avg_rate_all,
                    "multiplier": multiplier,
                },
            })

    # --- Insight 3: Reminder effectiveness ---
    reminder_effect = db.execute(text("""
        SELECT
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM scheduler_reminders sr
                    WHERE sr.appointment_id = sa.id
                      AND sr.status IN ('delivered', 'acknowledged')
                ) THEN 'reminder_sent'
                ELSE 'no_reminder'
            END AS reminder_group,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_shows
        FROM scheduler_appointments sa
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
          AND sa.status IN ('completed', 'no_show')
        GROUP BY CASE
            WHEN EXISTS (
                SELECT 1 FROM scheduler_reminders sr
                WHERE sr.appointment_id = sa.id
                  AND sr.status IN ('delivered', 'acknowledged')
            ) THEN 'reminder_sent'
            ELSE 'no_reminder'
        END
    """), params).fetchall()

    reminder_data = {r.reminder_group: r for r in reminder_effect}
    if "reminder_sent" in reminder_data and "no_reminder" in reminder_data:
        with_reminder = reminder_data["reminder_sent"]
        without_reminder = reminder_data["no_reminder"]
        rate_with = _pct(with_reminder.showed, with_reminder.total)
        rate_without = _pct(without_reminder.showed, without_reminder.total)

        if rate_with > rate_without:
            reduction_pct = round(((rate_with - rate_without) / max(100 - rate_without, 1)) * 100, 0)
            insights.append({
                "type": "reminder_effectiveness",
                "title": "Reminder impact on attendance",
                "description": (
                    f"Pre-appointment reminders improve show rates by "
                    f"{round(rate_with - rate_without, 1)} percentage points "
                    f"({rate_with}% vs {rate_without}%)"
                ),
                "impact": "high" if rate_with - rate_without >= 15 else "medium",
                "data": {
                    "with_reminder_rate": rate_with,
                    "without_reminder_rate": rate_without,
                    "improvement_ppts": round(rate_with - rate_without, 1),
                },
            })

    # --- Insight 4: No-show trends (week over week) ---
    trend_data = db.execute(text("""
        SELECT
            DATE_TRUNC('week', sa.scheduled_start)::date AS week_start,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_shows
        FROM scheduler_appointments sa
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
          AND sa.status IN ('completed', 'no_show')
        GROUP BY DATE_TRUNC('week', sa.scheduled_start)
        ORDER BY week_start
    """), params).fetchall()

    if len(trend_data) >= 3:
        rates = [_pct(r.no_shows, r.total) for r in trend_data]
        recent_rate = rates[-1]
        avg_rate = sum(rates) / len(rates)

        if recent_rate > avg_rate + 5:
            insights.append({
                "type": "no_show_trend",
                "title": "Rising no-show trend",
                "description": (
                    f"No-show rate this week ({recent_rate}%) is above "
                    f"the {days}-day average ({round(avg_rate, 1)}%)"
                ),
                "impact": "high" if recent_rate > avg_rate + 15 else "medium",
                "data": {
                    "current_rate": recent_rate,
                    "avg_rate": round(avg_rate, 1),
                    "trend": "increasing",
                },
            })
        elif recent_rate < avg_rate - 5:
            insights.append({
                "type": "no_show_trend",
                "title": "Improving no-show trend",
                "description": (
                    f"No-show rate this week ({recent_rate}%) is below "
                    f"the {days}-day average ({round(avg_rate, 1)}%)"
                ),
                "impact": "low",
                "data": {
                    "current_rate": recent_rate,
                    "avg_rate": round(avg_rate, 1),
                    "trend": "decreasing",
                },
            })

    # --- Insight 5: AI vs manual booking comparison ---
    ai_vs_manual = db.execute(text("""
        SELECT
            sa.booked_by_ai,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_shows
        FROM scheduler_appointments sa
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
          AND sa.status IN ('completed', 'no_show')
        GROUP BY sa.booked_by_ai
    """), params).fetchall()

    ai_data = {r.booked_by_ai: r for r in ai_vs_manual}
    if True in ai_data and False in ai_data:
        ai_rate = _pct(ai_data[True].showed, ai_data[True].total)
        manual_rate = _pct(ai_data[False].showed, ai_data[False].total)
        if abs(ai_rate - manual_rate) >= 5:
            better = "AI-booked" if ai_rate > manual_rate else "Manually-booked"
            insights.append({
                "type": "booking_method_comparison",
                "title": "AI vs manual booking performance",
                "description": (
                    f"{better} appointments have higher show rates "
                    f"(AI: {ai_rate}%, Manual: {manual_rate}%)"
                ),
                "impact": "medium",
                "data": {
                    "ai_show_rate": ai_rate,
                    "manual_show_rate": manual_rate,
                    "ai_total": ai_data[True].total,
                    "manual_total": ai_data[False].total,
                },
            })

    # --- Overall metrics summary ---
    overall = db.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_shows,
            COUNT(CASE WHEN sa.status = 'cancelled' THEN 1 END) AS cancelled
        FROM scheduler_appointments sa
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
    """), params).fetchone()

    total = overall.total or 0
    showed = overall.showed or 0
    no_shows = overall.no_shows or 0
    resolved = showed + no_shows

    return {
        "period_days": days,
        "summary": {
            "total_appointments": total,
            "showed": showed,
            "no_shows": no_shows,
            "cancelled": overall.cancelled or 0,
            "show_rate_pct": _pct(showed, resolved),
            "no_show_rate_pct": _pct(no_shows, resolved),
        },
        "insights": insights,
        "insight_count": len(insights),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# 9. Conversion Trends Over Time
# ---------------------------------------------------------------------------

async def get_conversion_trends(
    org_id: int,
    db: Session,
    days: int = 90,
    granularity: str = "week",  # week or month
) -> Dict[str, Any]:
    """
    Show conversion metrics over time (week-by-week or month-by-month).
    """
    trunc = "week" if granularity == "week" else "month"
    params = {"org_id": org_id, "days": days}

    trends = db.execute(text(f"""
        SELECT
            DATE_TRUNC('{trunc}', sa.scheduled_start)::date AS period_start,
            COUNT(*) AS total,
            COUNT(CASE WHEN sa.status = 'completed' THEN 1 END) AS showed,
            COUNT(CASE WHEN sa.status = 'no_show' THEN 1 END) AS no_shows,
            COUNT(CASE WHEN sa.status = 'cancelled' THEN 1 END) AS cancelled,
            COUNT(CASE WHEN sa.status = 'booked' THEN 1 END) AS upcoming
        FROM scheduler_appointments sa
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start >= CURRENT_DATE - :days
        GROUP BY DATE_TRUNC('{trunc}', sa.scheduled_start)
        ORDER BY period_start
    """), params).fetchall()

    periods = []
    for row in trends:
        total = row.total or 0
        showed = row.showed or 0
        no_shows = row.no_shows or 0
        resolved = showed + no_shows
        periods.append({
            "period_start": row.period_start.isoformat() if row.period_start else None,
            "total": total,
            "showed": showed,
            "no_shows": no_shows,
            "cancelled": row.cancelled or 0,
            "upcoming": row.upcoming or 0,
            "show_rate_pct": _pct(showed, resolved),
            "no_show_rate_pct": _pct(no_shows, resolved),
        })

    # Calculate trend direction
    trend_direction = "stable"
    if len(periods) >= 3:
        recent_rates = [p["show_rate_pct"] for p in periods[-3:]]
        if all(recent_rates[i] <= recent_rates[i + 1] for i in range(len(recent_rates) - 1)):
            trend_direction = "improving"
        elif all(recent_rates[i] >= recent_rates[i + 1] for i in range(len(recent_rates) - 1)):
            trend_direction = "declining"

    return {
        "period_days": days,
        "granularity": granularity,
        "trend_direction": trend_direction,
        "periods": periods,
    }
