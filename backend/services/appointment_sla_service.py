"""
Appointment SLA Service - Track and enforce appointment scheduling SLAs.

Metrics tracked:
  - time_to_first_appointment_hours: Lead creation -> first scheduled appointment
  - appointment_confirmation_minutes: Booking created -> confirmation sent
  - reminder_lead_time_hours: Reminder sent before appointment start
  - reschedule_response_hours: Reschedule request -> new time offered
  - post_appointment_followup_hours: Appointment completed -> follow-up activity

All queries are scoped by organization_id for tenant isolation.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_, or_, extract
import logging

from smart_scheduler_models import AppointmentStatus

logger = logging.getLogger(__name__)

# Statuses that count as "completed" (appointment happened)
_COMPLETED_STATUSES = {
    AppointmentStatus.COMPLETED.value,
    AppointmentStatus.CHECKED_IN.value,
}

# Statuses that count as "did not happen"
_NEGATIVE_STATUSES = {
    AppointmentStatus.CANCELLED.value,
    AppointmentStatus.NO_SHOW.value,
}


# =============================================================================
# DEFAULT SLA TARGETS
# =============================================================================

DEFAULT_SLA_TARGETS = {
    "time_to_first_appointment_hours": 48,       # New lead -> first scheduled appointment
    "appointment_confirmation_minutes": 30,      # Booking -> confirmation sent
    "reminder_lead_time_hours": 24,              # Reminder sent before appointment
    "reschedule_response_hours": 4,              # Reschedule request -> new time offered
    "post_appointment_followup_hours": 24,       # Appointment completed -> follow-up sent
}


def _resolve_date_range(period_days: int) -> Tuple[datetime, datetime]:
    """Return (start, end) datetimes for a given number of lookback days."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start = now - timedelta(days=period_days)
    return start, now


def _get_appointment_model(models: dict):
    """Get Appointment model from models dict."""
    return models.get("Appointment")


# =============================================================================
# SLA TARGET RESOLUTION
# =============================================================================

def get_sla_targets(
    db: Session,
    models: dict,
    organization_id: int,
    appointment_type_id: Optional[int] = None,
) -> dict:
    """
    Get SLA targets for an organization, with optional per-appointment-type overrides.

    Priority (highest to lowest):
      1. Per-type overrides (AppointmentType.sla_targets) — only when appointment_type_id is given
      2. Org-level overrides (SchedulerConfig.sla_targets for user_id IS NULL)
      3. DEFAULT_SLA_TARGETS system defaults

    Checks SchedulerConfig for org-level overrides in the `sla_targets` JSON
    field.  Falls back to DEFAULT_SLA_TARGETS for any missing keys.
    """
    SchedulerConfig = models.get("SchedulerConfig")
    AppointmentType = models.get("AppointmentType")
    custom_targets = {}

    if SchedulerConfig:
        # Look for an org-level config (user_id IS NULL) that has sla_targets
        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.organization_id == organization_id,
            SchedulerConfig.user_id.is_(None),
        ).first()
        if config and hasattr(config, "sla_targets") and config.sla_targets:
            custom_targets = config.sla_targets

    # Merge: org overrides take precedence over defaults
    merged = {**DEFAULT_SLA_TARGETS, **custom_targets}

    # Per-type overrides are the highest priority
    if appointment_type_id and AppointmentType:
        appt_type = db.query(AppointmentType).filter(
            AppointmentType.id == appointment_type_id,
            AppointmentType.organization_id == organization_id,
        ).first()
        if appt_type and hasattr(appt_type, "sla_targets") and appt_type.sla_targets:
            merged.update(appt_type.sla_targets)

    return merged


# =============================================================================
# TIME TO FIRST APPOINTMENT
# =============================================================================

def get_time_to_first_appointment(
    db: Session,
    models: dict,
    organization_id: int,
    lead_id: Optional[int] = None,
    days: int = 30,
) -> dict:
    """
    Measure hours from lead creation to first scheduled appointment.

    If lead_id is provided, returns the specific metric for that lead.
    Otherwise returns aggregate stats for the org over the given period.
    """
    Appointment = _get_appointment_model(models)
    if not Appointment:
        return {"error": "Appointment model not available"}

    try:
        from database.models.lead_loan import Lead
    except ImportError:
        return {"error": "Lead model not available"}

    if lead_id:
        # Single lead lookup
        lead = db.query(Lead.id, Lead.created_at).filter(
            Lead.id == lead_id,
            Lead.organization_id == organization_id,
        ).first()
        if not lead or not lead.created_at:
            return {"lead_id": lead_id, "hours": None, "message": "Lead not found or no creation date"}

        first_appt = db.query(
            func.min(Appointment.created_at).label("first_booked"),
        ).filter(
            Appointment.organization_id == organization_id,
            Appointment.lead_id == lead_id,
        ).first()

        if not first_appt or not first_appt.first_booked:
            return {"lead_id": lead_id, "hours": None, "message": "No appointment found for lead"}

        delta = first_appt.first_booked - lead.created_at
        hours = round(delta.total_seconds() / 3600, 1)
        return {"lead_id": lead_id, "hours": hours}

    # Aggregate: average time-to-first-appointment over the period
    start, end = _resolve_date_range(days)

    # Subquery: for each lead created in the period, find the earliest appointment
    from sqlalchemy import literal_column
    first_appt_sub = (
        db.query(
            Appointment.lead_id,
            func.min(Appointment.created_at).label("first_booked"),
        )
        .filter(
            Appointment.organization_id == organization_id,
            Appointment.lead_id.isnot(None),
        )
        .group_by(Appointment.lead_id)
        .subquery("first_appt")
    )

    rows = (
        db.query(
            Lead.id.label("lead_id"),
            Lead.created_at.label("lead_created"),
            first_appt_sub.c.first_booked,
        )
        .join(first_appt_sub, first_appt_sub.c.lead_id == Lead.id)
        .filter(
            Lead.organization_id == organization_id,
            Lead.created_at >= start,
            Lead.created_at <= end,
        )
        .all()
    )

    if not rows:
        return {
            "period_days": days,
            "total_leads_with_appointments": 0,
            "avg_hours": None,
            "median_hours": None,
            "p90_hours": None,
        }

    hours_list = []
    for row in rows:
        if row.lead_created and row.first_booked:
            delta = row.first_booked - row.lead_created
            hours_list.append(round(delta.total_seconds() / 3600, 1))

    if not hours_list:
        return {
            "period_days": days,
            "total_leads_with_appointments": 0,
            "avg_hours": None,
            "median_hours": None,
            "p90_hours": None,
        }

    hours_list.sort()
    avg_hours = round(sum(hours_list) / len(hours_list), 1)
    median_idx = len(hours_list) // 2
    median_hours = hours_list[median_idx]
    p90_idx = min(int(len(hours_list) * 0.9), len(hours_list) - 1)
    p90_hours = hours_list[p90_idx]

    return {
        "period_days": days,
        "total_leads_with_appointments": len(hours_list),
        "avg_hours": avg_hours,
        "median_hours": median_hours,
        "p90_hours": p90_hours,
    }


# =============================================================================
# APPOINTMENT COMPLETION RATE
# =============================================================================

def get_appointment_completion_rate(
    db: Session,
    models: dict,
    organization_id: int,
    lo_id: Optional[int] = None,
    days: int = 30,
) -> dict:
    """
    Percentage of scheduled appointments that were completed (not cancelled/no-show).

    Only considers appointments whose scheduled_start is in the past.
    """
    Appointment = _get_appointment_model(models)
    if not Appointment:
        return {"error": "Appointment model not available"}

    start, end = _resolve_date_range(days)

    filters = [
        Appointment.organization_id == organization_id,
        Appointment.scheduled_start >= start,
        Appointment.scheduled_start <= end,
    ]
    if lo_id:
        filters.append(Appointment.assigned_user_id == lo_id)

    row = db.query(
        func.count(Appointment.id).label("total"),
        func.count(case(
            (Appointment.status.in_(list(_COMPLETED_STATUSES)), 1),
        )).label("completed"),
        func.count(case(
            (Appointment.status == AppointmentStatus.CANCELLED.value, 1),
        )).label("cancelled"),
        func.count(case(
            (Appointment.status == AppointmentStatus.NO_SHOW.value, 1),
        )).label("no_shows"),
    ).filter(and_(*filters)).first()

    total = row.total or 0
    completed = row.completed or 0
    cancelled = row.cancelled or 0
    no_shows = row.no_shows or 0

    completion_rate = round((completed / total) * 100, 1) if total > 0 else 0.0
    cancellation_rate = round((cancelled / total) * 100, 1) if total > 0 else 0.0
    no_show_rate = round((no_shows / total) * 100, 1) if total > 0 else 0.0

    return {
        "period_days": days,
        "lo_id": lo_id,
        "total": total,
        "completed": completed,
        "cancelled": cancelled,
        "no_shows": no_shows,
        "completion_rate": completion_rate,
        "cancellation_rate": cancellation_rate,
        "no_show_rate": no_show_rate,
    }


# =============================================================================
# NO-SHOW RATE
# =============================================================================

def get_no_show_rate(
    db: Session,
    models: dict,
    organization_id: int,
    lo_id: Optional[int] = None,
    days: int = 30,
) -> dict:
    """
    No-show rate for an LO or org, with trend comparison to prior period.
    """
    Appointment = _get_appointment_model(models)
    if not Appointment:
        return {"error": "Appointment model not available"}

    def _rate_for_period(period_start: datetime, period_end: datetime) -> dict:
        filters = [
            Appointment.organization_id == organization_id,
            Appointment.scheduled_start >= period_start,
            Appointment.scheduled_start <= period_end,
        ]
        if lo_id:
            filters.append(Appointment.assigned_user_id == lo_id)

        row = db.query(
            func.count(Appointment.id).label("total"),
            func.count(case(
                (Appointment.status == AppointmentStatus.NO_SHOW.value, 1),
            )).label("no_shows"),
        ).filter(and_(*filters)).first()

        total = row.total or 0
        no_shows = row.no_shows or 0
        rate = round((no_shows / total) * 100, 1) if total > 0 else 0.0
        return {"total": total, "no_shows": no_shows, "rate": rate}

    # Current period
    start, end = _resolve_date_range(days)
    current = _rate_for_period(start, end)

    # Prior period for trend
    prior_start = start - timedelta(days=days)
    prior = _rate_for_period(prior_start, start)

    trend = "stable"
    if current["rate"] > prior["rate"] + 2:
        trend = "worsening"
    elif current["rate"] < prior["rate"] - 2:
        trend = "improving"

    return {
        "period_days": days,
        "lo_id": lo_id,
        "current": current,
        "prior_period": prior,
        "trend": trend,
    }


# =============================================================================
# SLA BREACH DETECTION
# =============================================================================

def get_sla_breaches(
    db: Session,
    models: dict,
    organization_id: int,
    days: int = 7,
) -> list:
    """
    List recent SLA breaches with details.

    Checks:
    1. time_to_first_appointment: leads created in the period without a timely appointment
    2. post_appointment_followup: completed appointments without timely follow-up activity
    3. no_show_rate: LOs whose no-show rate exceeds a threshold
    """
    Appointment = _get_appointment_model(models)
    if not Appointment:
        return []

    targets = get_sla_targets(db, models, organization_id)
    start, end = _resolve_date_range(days)
    breaches = []

    # -------------------------------------------------------------------------
    # Breach type 1: Time to first appointment exceeded
    # -------------------------------------------------------------------------
    ttfa_target_hours = targets.get("time_to_first_appointment_hours", 48)

    try:
        from database.models.lead_loan import Lead

        # Find leads created in the period that still have no appointment
        # or whose first appointment was booked after the SLA target
        first_appt_sub = (
            db.query(
                Appointment.lead_id,
                func.min(Appointment.created_at).label("first_booked"),
            )
            .filter(
                Appointment.organization_id == organization_id,
                Appointment.lead_id.isnot(None),
            )
            .group_by(Appointment.lead_id)
            .subquery("first_appt")
        )

        # Leads with no appointment at all (and SLA window has passed)
        cutoff = end - timedelta(hours=ttfa_target_hours)
        no_appt_leads = (
            db.query(Lead.id, Lead.first_name, Lead.last_name, Lead.created_at)
            .outerjoin(first_appt_sub, first_appt_sub.c.lead_id == Lead.id)
            .filter(
                Lead.organization_id == organization_id,
                Lead.created_at >= start,
                Lead.created_at <= cutoff,
                first_appt_sub.c.first_booked.is_(None),
            )
            .limit(50)
            .all()
        )

        for lead in no_appt_leads:
            hours_elapsed = round((end - lead.created_at).total_seconds() / 3600, 1) if lead.created_at else 0
            breaches.append({
                "breach_type": "time_to_first_appointment",
                "severity": "critical" if hours_elapsed > ttfa_target_hours * 2 else "warning",
                "entity_type": "lead",
                "entity_id": lead.id,
                "entity_name": f"{lead.first_name or ''} {lead.last_name or ''}".strip(),
                "target_hours": ttfa_target_hours,
                "actual_hours": hours_elapsed,
                "message": f"Lead has no appointment after {hours_elapsed}h (target: {ttfa_target_hours}h)",
                "detected_at": end.isoformat(),
            })

        # Leads whose first appointment was booked late
        late_appt_leads = (
            db.query(
                Lead.id,
                Lead.first_name,
                Lead.last_name,
                Lead.created_at,
                first_appt_sub.c.first_booked,
            )
            .join(first_appt_sub, first_appt_sub.c.lead_id == Lead.id)
            .filter(
                Lead.organization_id == organization_id,
                Lead.created_at >= start,
                Lead.created_at <= end,
            )
            .limit(100)
            .all()
        )

        for lead in late_appt_leads:
            if lead.created_at and lead.first_booked:
                delta_hours = round((lead.first_booked - lead.created_at).total_seconds() / 3600, 1)
                if delta_hours > ttfa_target_hours:
                    breaches.append({
                        "breach_type": "time_to_first_appointment",
                        "severity": "warning",
                        "entity_type": "lead",
                        "entity_id": lead.id,
                        "entity_name": f"{lead.first_name or ''} {lead.last_name or ''}".strip(),
                        "target_hours": ttfa_target_hours,
                        "actual_hours": delta_hours,
                        "message": f"First appointment booked after {delta_hours}h (target: {ttfa_target_hours}h)",
                        "detected_at": end.isoformat(),
                    })

    except ImportError:
        logger.debug("Lead model not available for time-to-first-appointment breach check")

    # -------------------------------------------------------------------------
    # Breach type 2: Post-appointment follow-up exceeded
    # -------------------------------------------------------------------------
    followup_target_hours = targets.get("post_appointment_followup_hours", 24)

    completed_appts = (
        db.query(
            Appointment.id,
            Appointment.title,
            Appointment.assigned_user_id,
            Appointment.lead_id,
            Appointment.completed_at,
            Appointment.attendee_name,
        )
        .filter(
            Appointment.organization_id == organization_id,
            Appointment.status.in_(list(_COMPLETED_STATUSES)),
            Appointment.completed_at.isnot(None),
            Appointment.completed_at >= start,
            Appointment.completed_at <= end,
        )
        .limit(200)
        .all()
    )

    # Check each completed appointment for a follow-up activity
    try:
        from database.models.core import Activity
        for appt in completed_appts:
            if not appt.completed_at:
                continue

            followup_deadline = appt.completed_at + timedelta(hours=followup_target_hours)

            # Skip if the deadline hasn't passed yet
            if followup_deadline > end:
                continue

            # Look for any activity on this lead after completion
            has_followup = False
            if appt.lead_id:
                followup_count = db.query(func.count(Activity.id)).filter(
                    Activity.lead_id == appt.lead_id,
                    Activity.created_at > appt.completed_at,
                    Activity.created_at <= followup_deadline,
                ).scalar() or 0
                has_followup = followup_count > 0

            if not has_followup:
                hours_since = round((end - appt.completed_at).total_seconds() / 3600, 1)
                breaches.append({
                    "breach_type": "post_appointment_followup",
                    "severity": "warning",
                    "entity_type": "appointment",
                    "entity_id": appt.id,
                    "entity_name": appt.attendee_name or appt.title,
                    "lo_id": appt.assigned_user_id,
                    "target_hours": followup_target_hours,
                    "actual_hours": hours_since,
                    "message": f"No follow-up {hours_since}h after completion (target: {followup_target_hours}h)",
                    "detected_at": end.isoformat(),
                })
    except ImportError:
        logger.debug("Activity model not available for follow-up breach check")

    # Sort: critical first, then by actual_hours descending
    breaches.sort(key=lambda b: (0 if b["severity"] == "critical" else 1, -(b.get("actual_hours") or 0)))

    return breaches


# =============================================================================
# SLA COMPLIANCE DASHBOARD
# =============================================================================

def check_sla_compliance(
    db: Session,
    models: dict,
    organization_id: int,
    days: int = 30,
) -> dict:
    """
    Check current SLA compliance across all metrics.

    Returns a dashboard-style dict with each SLA metric, its target,
    current measured value, and pass/fail status.
    """
    targets = get_sla_targets(db, models, organization_id)

    # Time to first appointment
    ttfa = get_time_to_first_appointment(db, models, organization_id, days=days)
    ttfa_target = targets.get("time_to_first_appointment_hours", 48)
    ttfa_avg = ttfa.get("avg_hours")
    ttfa_compliant = ttfa_avg is not None and ttfa_avg <= ttfa_target

    # Appointment completion rate (org-wide)
    completion = get_appointment_completion_rate(db, models, organization_id, days=days)

    # No-show rate
    no_show = get_no_show_rate(db, models, organization_id, days=days)

    # SLA breaches (last 7 days)
    recent_breaches = get_sla_breaches(db, models, organization_id, days=7)

    metrics = [
        {
            "metric": "time_to_first_appointment",
            "display_name": "Time to First Appointment",
            "target": f"{ttfa_target}h",
            "current_value": f"{ttfa_avg}h" if ttfa_avg is not None else "N/A",
            "compliant": ttfa_compliant,
            "details": {
                "median_hours": ttfa.get("median_hours"),
                "p90_hours": ttfa.get("p90_hours"),
                "sample_size": ttfa.get("total_leads_with_appointments", 0),
            },
        },
        {
            "metric": "appointment_completion_rate",
            "display_name": "Appointment Completion Rate",
            "target": "80%",
            "current_value": f"{completion.get('completion_rate', 0)}%",
            "compliant": completion.get("completion_rate", 0) >= 80,
            "details": {
                "total": completion.get("total", 0),
                "completed": completion.get("completed", 0),
                "cancelled": completion.get("cancelled", 0),
                "no_shows": completion.get("no_shows", 0),
            },
        },
        {
            "metric": "no_show_rate",
            "display_name": "No-Show Rate",
            "target": "<15%",
            "current_value": f"{no_show.get('current', {}).get('rate', 0)}%",
            "compliant": no_show.get("current", {}).get("rate", 0) <= 15,
            "details": {
                "current_rate": no_show.get("current", {}).get("rate", 0),
                "prior_rate": no_show.get("prior_period", {}).get("rate", 0),
                "trend": no_show.get("trend", "stable"),
            },
        },
        {
            "metric": "post_appointment_followup",
            "display_name": "Post-Appointment Follow-up",
            "target": f"{targets.get('post_appointment_followup_hours', 24)}h",
            "current_value": "See breaches",
            "compliant": len([b for b in recent_breaches if b["breach_type"] == "post_appointment_followup"]) == 0,
            "details": {
                "breaches_last_7d": len([b for b in recent_breaches if b["breach_type"] == "post_appointment_followup"]),
            },
        },
    ]

    total_metrics = len(metrics)
    compliant_count = sum(1 for m in metrics if m["compliant"])
    overall_score = round((compliant_count / total_metrics) * 100, 1) if total_metrics > 0 else 0

    return {
        "organization_id": organization_id,
        "period_days": days,
        "overall_compliance_score": overall_score,
        "compliant_count": compliant_count,
        "total_metrics": total_metrics,
        "metrics": metrics,
        "recent_breach_count": len(recent_breaches),
        "targets": targets,
    }


# =============================================================================
# PER-LO SLA METRICS
# =============================================================================

def get_lo_sla_metrics(
    db: Session,
    models: dict,
    organization_id: int,
    lo_id: int,
    days: int = 30,
) -> dict:
    """
    Get comprehensive SLA metrics for a specific loan officer.
    """
    Appointment = _get_appointment_model(models)
    if not Appointment:
        return {"error": "Appointment model not available"}

    targets = get_sla_targets(db, models, organization_id)
    start, end = _resolve_date_range(days)

    # Completion/no-show rates
    completion = get_appointment_completion_rate(
        db, models, organization_id, lo_id=lo_id, days=days,
    )
    no_show = get_no_show_rate(
        db, models, organization_id, lo_id=lo_id, days=days,
    )

    # Time-to-first-appointment for leads assigned to this LO
    # Use appointments assigned to this LO to find their leads
    ttfa_data = {"avg_hours": None, "total_leads_with_appointments": 0}
    try:
        from database.models.lead_loan import Lead

        first_appt_sub = (
            db.query(
                Appointment.lead_id,
                func.min(Appointment.created_at).label("first_booked"),
            )
            .filter(
                Appointment.organization_id == organization_id,
                Appointment.assigned_user_id == lo_id,
                Appointment.lead_id.isnot(None),
            )
            .group_by(Appointment.lead_id)
            .subquery("first_appt")
        )

        rows = (
            db.query(
                Lead.id,
                Lead.created_at.label("lead_created"),
                first_appt_sub.c.first_booked,
            )
            .join(first_appt_sub, first_appt_sub.c.lead_id == Lead.id)
            .filter(
                Lead.organization_id == organization_id,
                Lead.created_at >= start,
                Lead.created_at <= end,
            )
            .all()
        )

        hours_list = []
        for row in rows:
            if row.lead_created and row.first_booked:
                delta = row.first_booked - row.lead_created
                hours_list.append(round(delta.total_seconds() / 3600, 1))

        if hours_list:
            hours_list.sort()
            ttfa_data = {
                "avg_hours": round(sum(hours_list) / len(hours_list), 1),
                "median_hours": hours_list[len(hours_list) // 2],
                "total_leads_with_appointments": len(hours_list),
            }
    except ImportError:
        logger.debug("Lead model not available for LO TTFA calculation")

    # Average response time for rescheduled appointments
    # (time between rescheduled_from appointment's status change and new appointment creation)
    avg_reschedule_hours = None
    rescheduled_appts = (
        db.query(
            Appointment.id,
            Appointment.created_at,
            Appointment.rescheduled_from_id,
        )
        .filter(
            Appointment.organization_id == organization_id,
            Appointment.assigned_user_id == lo_id,
            Appointment.rescheduled_from_id.isnot(None),
            Appointment.created_at >= start,
            Appointment.created_at <= end,
        )
        .limit(100)
        .all()
    )

    if rescheduled_appts:
        original_ids = [a.rescheduled_from_id for a in rescheduled_appts]
        originals = {
            a.id: a.status_changed_at
            for a in db.query(Appointment.id, Appointment.status_changed_at)
            .filter(Appointment.id.in_(original_ids))
            .all()
        }

        reschedule_deltas = []
        for appt in rescheduled_appts:
            original_changed = originals.get(appt.rescheduled_from_id)
            if original_changed and appt.created_at:
                delta = (appt.created_at - original_changed).total_seconds() / 3600
                if delta >= 0:
                    reschedule_deltas.append(round(delta, 1))

        if reschedule_deltas:
            avg_reschedule_hours = round(sum(reschedule_deltas) / len(reschedule_deltas), 1)

    # Fetch LO name
    lo_name = f"User {lo_id}"
    try:
        from database.models.core import User
        user = db.query(User.first_name, User.last_name).filter(User.id == lo_id).first()
        if user:
            lo_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or lo_name
    except ImportError:
        pass

    ttfa_target = targets.get("time_to_first_appointment_hours", 48)
    reschedule_target = targets.get("reschedule_response_hours", 4)

    return {
        "lo_id": lo_id,
        "lo_name": lo_name,
        "period_days": days,
        "time_to_first_appointment": {
            **ttfa_data,
            "target_hours": ttfa_target,
            "compliant": (ttfa_data.get("avg_hours") or 0) <= ttfa_target if ttfa_data.get("avg_hours") is not None else True,
        },
        "completion_rate": {
            "rate": completion.get("completion_rate", 0),
            "total": completion.get("total", 0),
            "completed": completion.get("completed", 0),
        },
        "no_show_rate": {
            "rate": no_show.get("current", {}).get("rate", 0),
            "total": no_show.get("current", {}).get("total", 0),
            "no_shows": no_show.get("current", {}).get("no_shows", 0),
            "trend": no_show.get("trend", "stable"),
        },
        "reschedule_response": {
            "avg_hours": avg_reschedule_hours,
            "target_hours": reschedule_target,
            "compliant": (avg_reschedule_hours or 0) <= reschedule_target if avg_reschedule_hours is not None else True,
        },
    }
