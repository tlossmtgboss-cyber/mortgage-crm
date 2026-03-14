"""
iCalendar Feed Service — Generates RFC 5545-compliant ICS feeds.

Produces VCALENDAR output from a user's scheduler appointments.
No external dependency required — ICS is plain text with a well-defined format.

Public interface:
  - generate_ical_feed(db, user_id, org_id, days_ahead, include_details)
  - appointment_to_vevent(appointment, include_details, user_tz)

References:
  - RFC 5545: Internet Calendaring and Scheduling (iCalendar)
  - RFC 7986: New Properties for iCalendar (NAME, REFRESH-INTERVAL)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ============================================================================
# ICS FORMATTING HELPERS
# ============================================================================

def _fold_line(line: str) -> str:
    """
    RFC 5545 Section 3.1: Lines longer than 75 octets SHOULD be folded.
    Continuation lines start with a single space.
    """
    if len(line.encode("utf-8")) <= 75:
        return line
    result = []
    current = ""
    for char in line:
        # Check byte length after adding this char
        test = current + char
        if len(test.encode("utf-8")) > 75:
            result.append(current)
            current = " " + char  # continuation line starts with space
        else:
            current = test
    if current:
        result.append(current)
    return "\r\n".join(result)


def _escape_text(text: str) -> str:
    """Escape text values per RFC 5545 Section 3.3.11."""
    if not text:
        return ""
    return (
        text
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
        .replace("\r", "")
    )


def _format_dt(dt: datetime) -> str:
    """
    Format a datetime as an ICS DATETIME value in UTC.
    Appointments are stored as naive UTC datetimes in the DB.
    """
    if dt is None:
        return ""
    # Ensure we're working with UTC
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _status_to_ics(status_value: str) -> str:
    """Map appointment status to ICS VEVENT STATUS."""
    status_str = str(status_value).lower()
    if status_str in ("cancelled", "rescheduled"):
        return "CANCELLED"
    if status_str in ("tentative",):
        return "TENTATIVE"
    return "CONFIRMED"


# ============================================================================
# VEVENT BUILDER
# ============================================================================

def appointment_to_vevent(appointment, include_details: bool = True, user_email: str = "") -> str:
    """
    Convert a single Appointment ORM object into a VEVENT component string.

    Args:
        appointment: Appointment model instance
        include_details: If False, mask title/description (busy/free mode)
        user_email: Email of the calendar owner (for ORGANIZER)

    Returns:
        A VEVENT block as a string (with CRLF line endings).
    """
    lines = ["BEGIN:VEVENT"]

    # UID — globally unique per RFC 5545; use appointment ID + domain
    uid = f"appointment-{appointment.id}@perenniaai.com"
    lines.append(_fold_line(f"UID:{uid}"))

    # Timestamps
    lines.append(f"DTSTAMP:{_format_dt(datetime.now(timezone.utc).replace(tzinfo=None))}")
    lines.append(f"DTSTART:{_format_dt(appointment.scheduled_start)}")
    lines.append(f"DTEND:{_format_dt(appointment.scheduled_end)}")

    # Created / Last Modified
    if appointment.created_at:
        lines.append(f"CREATED:{_format_dt(appointment.created_at)}")
    if appointment.updated_at:
        lines.append(f"LAST-MODIFIED:{_format_dt(appointment.updated_at)}")

    # Summary / Description
    if include_details:
        title = _escape_text(appointment.title or "Appointment")
        lines.append(_fold_line(f"SUMMARY:{title}"))

        # Build a rich description
        desc_parts = []
        if appointment.description:
            desc_parts.append(appointment.description)
        if appointment.attendee_name:
            desc_parts.append(f"Client: {appointment.attendee_name}")
        if appointment.attendee_phone:
            desc_parts.append(f"Phone: {appointment.attendee_phone}")
        if appointment.video_link:
            desc_parts.append(f"Video link: {appointment.video_link}")
        if appointment.internal_notes:
            desc_parts.append(f"Notes: {appointment.internal_notes}")

        if desc_parts:
            lines.append(_fold_line(f"DESCRIPTION:{_escape_text(chr(10).join(desc_parts))}"))
    else:
        # Busy/free mode — hide details
        lines.append("SUMMARY:Busy")

    # Location
    if include_details and appointment.location:
        lines.append(_fold_line(f"LOCATION:{_escape_text(appointment.location)}"))
    elif include_details and appointment.video_link:
        lines.append(_fold_line(f"LOCATION:{_escape_text(appointment.video_link)}"))

    # Status
    status_val = getattr(appointment.status, "value", str(appointment.status)) if appointment.status else "booked"
    lines.append(f"STATUS:{_status_to_ics(status_val)}")

    # Transparency: OPAQUE means the time is blocked ("busy")
    lines.append("TRANSP:OPAQUE")

    # ORGANIZER (the calendar owner / assigned LO)
    if include_details and user_email:
        lines.append(_fold_line(f"ORGANIZER;CN=Loan Officer:mailto:{user_email}"))

    # ATTENDEE (the client)
    if include_details and appointment.attendee_email:
        attendee_cn = _escape_text(appointment.attendee_name or "Client")
        lines.append(_fold_line(
            f"ATTENDEE;CN={attendee_cn};ROLE=REQ-PARTICIPANT;"
            f"PARTSTAT=ACCEPTED:mailto:{appointment.attendee_email}"
        ))

    # Sequence number (for rescheduled appointments)
    seq = appointment.reschedule_count or 0
    if seq > 0:
        lines.append(f"SEQUENCE:{seq}")

    lines.append("END:VEVENT")
    return "\r\n".join(lines)


# ============================================================================
# FULL FEED GENERATOR
# ============================================================================

def generate_ical_feed(
    db: Session,
    user_id: int,
    org_id: int,
    days_ahead: int = 90,
    include_details: bool = True,
) -> str:
    """
    Generate a complete iCalendar feed for a user's appointments.

    Args:
        db: SQLAlchemy session
        user_id: The user whose calendar to export
        org_id: Organization ID for tenant isolation
        days_ahead: How many days into the future to include (also includes 30 days in the past)
        include_details: If False, only show busy/free blocks

    Returns:
        A complete VCALENDAR string with Content-Type: text/calendar
    """
    from smart_scheduler_models import AppointmentStatus

    # Lazy import to avoid circular dependency at module load
    _models = _get_scheduler_models()
    if not _models:
        logger.error("Scheduler models not available for iCal feed generation")
        return _empty_calendar("Perennia AI Calendar")

    Appointment = _models["Appointment"]

    # Look up user email for ORGANIZER field
    user_email = ""
    try:
        from database.models.core import User
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user_email = getattr(user, "email", "") or ""
    except Exception as e:
        logger.warning(f"Could not look up user email for iCal ORGANIZER: {e}")

    # Query range: 30 days back + days_ahead forward
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    range_start = now - timedelta(days=30)
    range_end = now + timedelta(days=days_ahead)

    # Fetch active/completed appointments (exclude cancelled)
    active_statuses = [
        AppointmentStatus.BOOKED,
        AppointmentStatus.TENTATIVE,
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.REMINDED,
        AppointmentStatus.CHECKED_IN,
        AppointmentStatus.COMPLETED,
    ]

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.assigned_user_id == user_id,
            Appointment.organization_id == org_id,
            Appointment.status.in_(active_statuses),
            Appointment.scheduled_start >= range_start,
            Appointment.scheduled_start <= range_end,
        )
        .order_by(Appointment.scheduled_start)
        .all()
    )

    # Build the calendar
    cal_name = "Perennia AI - Appointments"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//Perennia AI//Mortgage CRM Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        _fold_line(f"X-WR-CALNAME:{cal_name}"),
        # Suggest a 15-minute refresh interval (RFC 7986)
        "REFRESH-INTERVAL;VALUE=DURATION:PT15M",
        "X-PUBLISHED-TTL:PT15M",
    ]

    # Add VTIMEZONE for America/Chicago (the default user timezone)
    # Most clients handle UTC fine, but including a VTIMEZONE is good practice
    lines.append(_vtimezone_utc())

    # Add each appointment as a VEVENT
    for appt in appointments:
        lines.append(appointment_to_vevent(appt, include_details, user_email))

    lines.append("END:VCALENDAR")

    return "\r\n".join(lines)


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

_cached_models = None


def _get_scheduler_models():
    """Lazy-load scheduler models to avoid circular imports."""
    global _cached_models
    if _cached_models is not None:
        return _cached_models

    try:
        from routes.scheduler._helpers import get_models
        models = get_models()
        if models and "Appointment" in models:
            _cached_models = models
            return models
    except Exception as e:
        logger.debug(f"Could not load scheduler models via _helpers: {e}")

    # Fallback: try direct import from the factory
    try:
        from db import Base
        from smart_scheduler_models import create_smart_scheduler_models
        all_models = create_smart_scheduler_models(Base)
        # create_smart_scheduler_models returns via class scope; the Appointment class
        # is accessible as a local in the factory. We need the dict pattern used elsewhere.
        # The models dict is set via set_dependencies() in _helpers.py, so we rely on that.
        logger.warning("Scheduler models not yet initialized via set_dependencies; feed may be empty")
        return None
    except Exception as e:
        logger.error(f"Failed to load scheduler models for iCal feed: {e}")
        return None


def _vtimezone_utc() -> str:
    """Minimal VTIMEZONE component for UTC (most clients handle Z suffix natively)."""
    return "\r\n".join([
        "BEGIN:VTIMEZONE",
        "TZID:UTC",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0000",
        "TZOFFSETTO:+0000",
        "TZNAME:UTC",
        "END:STANDARD",
        "END:VTIMEZONE",
    ])


def _empty_calendar(name: str = "Perennia AI Calendar") -> str:
    """Return a valid but empty VCALENDAR."""
    return "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Perennia AI//Mortgage CRM Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        _fold_line(f"X-WR-CALNAME:{name}"),
        "END:VCALENDAR",
    ])
