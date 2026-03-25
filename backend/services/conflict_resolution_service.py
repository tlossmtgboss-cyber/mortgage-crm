"""
Conflict Resolution Service - Detect scheduling conflicts and suggest alternatives.

Provides:
  - detect_conflicts(db, user_id, start, end, org_id, exclude_id)
      Returns list of overlapping appointments with details.
  - suggest_alternatives(db, user_id, start, end, duration, org_id)
      Returns up to 5 nearest available slots.
  - get_conflict_severity(appointment_a, appointment_b)
      Returns "hard" (direct time overlap) or "soft" (buffer overlap only).
  - auto_resolve_soft_conflicts(conflicts)
      Adjusts times to eliminate buffer-only overlaps.
"""

from datetime import datetime, timedelta, date, time, timezone
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import logging

logger = logging.getLogger(__name__)

# Default buffer minutes (matches SchedulerConfig defaults in _helpers.py)
DEFAULT_BUFFER_BEFORE = 5
DEFAULT_BUFFER_AFTER = 5


def _get_scheduler_models():
    """Lazy import scheduler models to avoid circular import."""
    from routes.scheduler._helpers import get_models
    return get_models()


def _get_user_config(db: Session, user_id: int, org_id: int = None) -> dict:
    """Load SchedulerConfig for buffer/working hours settings."""
    models = _get_scheduler_models()
    SchedulerConfig = models.get('SchedulerConfig') if models else None
    if not SchedulerConfig:
        return {
            'buffer_before': DEFAULT_BUFFER_BEFORE,
            'buffer_after': DEFAULT_BUFFER_AFTER,
        }

    query = db.query(SchedulerConfig).filter(SchedulerConfig.user_id == user_id)
    if org_id:
        query = query.filter(SchedulerConfig.organization_id == org_id)
    config = query.first()

    if config:
        return {
            'buffer_before': getattr(config, 'buffer_before_minutes', DEFAULT_BUFFER_BEFORE) or DEFAULT_BUFFER_BEFORE,
            'buffer_after': getattr(config, 'buffer_after_minutes', DEFAULT_BUFFER_AFTER) or DEFAULT_BUFFER_AFTER,
        }
    return {
        'buffer_before': DEFAULT_BUFFER_BEFORE,
        'buffer_after': DEFAULT_BUFFER_AFTER,
    }


def _appointment_to_dict(appt) -> dict:
    """Serialize an Appointment model to a dict for API responses."""
    return {
        'id': appt.id,
        'title': appt.title,
        'attendee_name': appt.attendee_name,
        'attendee_email': appt.attendee_email,
        'scheduled_start': appt.scheduled_start.isoformat() if appt.scheduled_start else None,
        'scheduled_end': appt.scheduled_end.isoformat() if appt.scheduled_end else None,
        'duration_minutes': appt.duration_minutes,
        'status': appt.status.value if hasattr(appt.status, 'value') else str(appt.status),
        'meeting_mode': appt.meeting_mode.value if hasattr(appt.meeting_mode, 'value') else str(appt.meeting_mode) if appt.meeting_mode else None,
    }


def detect_conflicts(
    db: Session,
    user_id: int,
    start: datetime,
    end: datetime,
    org_id: int = None,
    exclude_id: int = None,
) -> List[Dict[str, Any]]:
    """
    Detect appointments that overlap with the proposed [start, end) window.

    Returns a list of conflict dicts, each containing:
      - appointment: serialized appointment data
      - severity: "hard" or "soft"
      - overlap_minutes: number of minutes of direct overlap
    """
    models = _get_scheduler_models()
    if not models:
        logger.error("Scheduler models not available for conflict detection")
        return []

    Appointment = models.get('Appointment')
    if not Appointment:
        return []

    from smart_scheduler_models import AppointmentStatus

    config = _get_user_config(db, user_id, org_id)
    buffer_before = config['buffer_before']
    buffer_after = config['buffer_after']

    # Expand the search window to include buffer zones
    search_start = start - timedelta(minutes=buffer_after)  # an existing appt ending here + buffer overlaps
    search_end = end + timedelta(minutes=buffer_before)  # an existing appt starting here - buffer overlaps

    filters = [
        Appointment.assigned_user_id == user_id,
        # SEC-008: Use enum members consistently (AppointmentStatus is a str enum)
        Appointment.status.notin_([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
        Appointment.scheduled_start < search_end,
        Appointment.scheduled_end > search_start,
    ]

    if org_id is not None:
        filters.append(Appointment.organization_id == org_id)
    if exclude_id is not None:
        filters.append(Appointment.id != exclude_id)

    overlapping = db.query(Appointment).filter(and_(*filters)).all()

    conflicts = []
    for appt in overlapping:
        severity = get_conflict_severity_from_times(
            start, end,
            appt.scheduled_start, appt.scheduled_end,
            buffer_before, buffer_after,
        )

        # Calculate direct overlap minutes
        overlap_start = max(start, appt.scheduled_start)
        overlap_end = min(end, appt.scheduled_end)
        overlap_minutes = max(0, (overlap_end - overlap_start).total_seconds() / 60)

        conflicts.append({
            'appointment': _appointment_to_dict(appt),
            'severity': severity,
            'overlap_minutes': round(overlap_minutes, 1),
        })

    # Sort: hard conflicts first, then by overlap amount descending
    conflicts.sort(key=lambda c: (0 if c['severity'] == 'hard' else 1, -c['overlap_minutes']))

    return conflicts


def get_conflict_severity(appointment_a: dict, appointment_b: dict, buffer_before: int = DEFAULT_BUFFER_BEFORE, buffer_after: int = DEFAULT_BUFFER_AFTER) -> str:
    """
    Determine conflict severity between two appointment dicts.

    Returns:
      "hard" — the two appointments directly overlap in time (same LO, same time)
      "soft" — they only overlap in the buffer zone (adjacent/buffer overlap)
    """
    a_start = _parse_dt(appointment_a.get('scheduled_start'))
    a_end = _parse_dt(appointment_a.get('scheduled_end'))
    b_start = _parse_dt(appointment_b.get('scheduled_start'))
    b_end = _parse_dt(appointment_b.get('scheduled_end'))

    if not all([a_start, a_end, b_start, b_end]):
        return 'hard'  # Cannot determine, assume worst case

    return get_conflict_severity_from_times(a_start, a_end, b_start, b_end, buffer_before, buffer_after)


def get_conflict_severity_from_times(
    a_start: datetime, a_end: datetime,
    b_start: datetime, b_end: datetime,
    buffer_before: int = DEFAULT_BUFFER_BEFORE,
    buffer_after: int = DEFAULT_BUFFER_AFTER,
) -> str:
    """
    Determine conflict severity from raw datetime pairs.

    "hard" — direct time overlap (the meeting windows themselves intersect)
    "soft" — only buffer zones overlap (adjacent meetings too close together)
    """
    # Check for direct overlap: a_start < b_end AND a_end > b_start
    if a_start < b_end and a_end > b_start:
        return 'hard'

    # If we reach here, no direct overlap. Check buffer overlap.
    buffered_b_start = b_start - timedelta(minutes=buffer_before)
    buffered_b_end = b_end + timedelta(minutes=buffer_after)
    if a_start < buffered_b_end and a_end > buffered_b_start:
        return 'soft'

    return 'soft'  # Fallback (shouldn't be called if no overlap at all)


def suggest_alternatives(
    db: Session,
    user_id: int,
    start: datetime,
    end: datetime,
    duration: int,
    org_id: int = None,
    count: int = 5,
) -> List[Dict[str, str]]:
    """
    Suggest the nearest available slots to the requested time.

    Strategy: search in expanding windows around the requested time,
    alternating before and after, until we find `count` slots.
    Uses the unified slot generation engine from _helpers for consistency.
    """
    from routes.scheduler._helpers import _generate_available_slots

    results = []
    target_date = start.date()

    # Search within a 7-day window centered on the target date
    search_start = target_date - timedelta(days=3)
    search_end = target_date + timedelta(days=3)

    # Clamp search_start to today
    today = datetime.now(timezone.utc).replace(tzinfo=None).date()
    if search_start < today:
        search_start = today

    try:
        all_slots = _generate_available_slots(
            db=db,
            user_ids=[user_id],
            start_date=search_start,
            end_date=search_end,
            duration_minutes=duration,
            org_id=org_id,
            check_cross_source=True,
        )
    except Exception as e:
        logger.error(f"Failed to generate alternative slots: {e}")
        return []

    if not all_slots:
        return []

    # Sort slots by distance from the originally requested start time
    request_iso = start.isoformat()

    def distance_key(slot):
        slot_start_str = slot.get('start', '')
        try:
            slot_dt = datetime.fromisoformat(slot_start_str)
            return abs((slot_dt - start).total_seconds())
        except (ValueError, TypeError):
            return float('inf')

    all_slots.sort(key=distance_key)

    # Return the closest `count` slots
    for slot in all_slots[:count]:
        results.append({
            'start': slot.get('start', ''),
            'end': slot.get('end', ''),
            'date': slot.get('date', ''),
        })

    return results


def auto_resolve_soft_conflicts(
    conflicts: List[Dict[str, Any]],
    buffer_before: int = DEFAULT_BUFFER_BEFORE,
    buffer_after: int = DEFAULT_BUFFER_AFTER,
) -> List[Dict[str, Any]]:
    """
    For soft conflicts (buffer-only overlaps), suggest adjusted times that
    eliminate the buffer overlap.

    Returns a list of resolution suggestions, each containing:
      - conflict: the original conflict dict
      - suggested_start: adjusted start time ISO string
      - suggested_end: adjusted end time ISO string
      - adjustment_minutes: how many minutes the time was shifted
    """
    resolutions = []

    for conflict in conflicts:
        if conflict['severity'] != 'soft':
            continue

        appt = conflict['appointment']
        appt_end = _parse_dt(appt.get('scheduled_end'))
        appt_start = _parse_dt(appt.get('scheduled_start'))

        if not appt_end or not appt_start:
            continue

        # The soft conflict means the proposed time is within the buffer zone.
        # Suggest moving to just after the existing appointment's buffer.
        suggested_start = appt_end + timedelta(minutes=buffer_after)
        duration_minutes = appt.get('duration_minutes', 30)

        # Use the duration from the proposed meeting if available in the conflict context,
        # otherwise approximate from the conflicting appointment's duration
        suggested_end = suggested_start + timedelta(minutes=duration_minutes)

        # Calculate how much we shifted
        # We don't know the original proposed start here, so just report the gap
        adjustment = (suggested_start - appt_end).total_seconds() / 60

        resolutions.append({
            'conflict': conflict,
            'suggested_start': suggested_start.isoformat(),
            'suggested_end': suggested_end.isoformat(),
            'adjustment_minutes': round(adjustment, 1),
        })

    return resolutions


def list_user_conflicts(
    db: Session,
    user_id: int,
    org_id: int = None,
    start_date: date = None,
    end_date: date = None,
) -> List[Dict[str, Any]]:
    """
    List all current conflicts for a user within a date range.

    Scans existing appointments and finds all pairs that overlap.
    """
    models = _get_scheduler_models()
    if not models:
        return []

    Appointment = models.get('Appointment')
    if not Appointment:
        return []

    from smart_scheduler_models import AppointmentStatus

    if start_date is None:
        start_date = datetime.now(timezone.utc).replace(tzinfo=None).date()
    if end_date is None:
        end_date = start_date + timedelta(days=30)

    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)

    filters = [
        Appointment.assigned_user_id == user_id,
        # SEC-008: Use enum members consistently (AppointmentStatus is a str enum)
        Appointment.status.notin_([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
        Appointment.scheduled_start >= start_dt,
        Appointment.scheduled_start <= end_dt,
    ]
    if org_id is not None:
        filters.append(Appointment.organization_id == org_id)

    appointments = db.query(Appointment).filter(
        and_(*filters)
    ).order_by(Appointment.scheduled_start).all()

    config = _get_user_config(db, user_id, org_id)
    buffer_before = config['buffer_before']
    buffer_after = config['buffer_after']

    conflict_pairs = []
    seen_pairs = set()

    for i, appt_a in enumerate(appointments):
        for appt_b in appointments[i + 1:]:
            # Check if these two overlap (including buffers)
            buffered_b_start = appt_b.scheduled_start - timedelta(minutes=buffer_before)
            buffered_b_end = appt_b.scheduled_end + timedelta(minutes=buffer_after)

            if appt_a.scheduled_start < buffered_b_end and appt_a.scheduled_end > buffered_b_start:
                pair_key = (min(appt_a.id, appt_b.id), max(appt_a.id, appt_b.id))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                severity = get_conflict_severity_from_times(
                    appt_a.scheduled_start, appt_a.scheduled_end,
                    appt_b.scheduled_start, appt_b.scheduled_end,
                    buffer_before, buffer_after,
                )

                overlap_start = max(appt_a.scheduled_start, appt_b.scheduled_start)
                overlap_end = min(appt_a.scheduled_end, appt_b.scheduled_end)
                overlap_minutes = max(0, (overlap_end - overlap_start).total_seconds() / 60)

                conflict_pairs.append({
                    'appointment_a': _appointment_to_dict(appt_a),
                    'appointment_b': _appointment_to_dict(appt_b),
                    'severity': severity,
                    'overlap_minutes': round(overlap_minutes, 1),
                })

    return conflict_pairs


def _parse_dt(value) -> Optional[datetime]:
    """Parse a datetime from string or return as-is if already datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00').replace('+00:00', ''))
    except (ValueError, TypeError):
        return None
