"""
RFC 5545-compliant ICS calendar generator.

Consolidated utility for generating ICS calendar events across the Perennia AI
platform. Provides low-level RFC-correct primitives (escaping, line folding,
datetime formatting) and high-level helpers for mortgage appointments, loan
officer calendars, milestone calendars, and video meetings.

References:
    - RFC 5545: https://tools.ietf.org/html/rfc5545
    - Section 3.1: Content Lines (line folding)
    - Section 3.3.11: TEXT value type (escaping)
"""

from datetime import datetime, timedelta, date, timezone
from typing import Any, Dict, List, Optional
import uuid


# =============================================================================
# Constants
# =============================================================================

PRODID_MORTGAGE = "-//Perennia AI//Mortgage CRM//EN"
PRODID_VIDEO = "-//Perennia AI//Video Meeting Platform//EN"
PRODID_MILESTONES = "-//Perennia AI//Mortgage CRM Milestone Calendar//EN"

try:
    from routes.scheduler.constants import DEFAULT_ORGANIZER_EMAIL
except ImportError:
    import os
    DEFAULT_ORGANIZER_EMAIL = os.environ.get("SCHEDULER_ORGANIZER_EMAIL", "sarah@reply.perenniaai.com")
DEFAULT_ORGANIZER_NAME = "Sarah - Perennia AI"

# Appointment type display titles (shared between borrower and LO invite generators)
APPOINTMENT_TYPE_TITLES: Dict[str, str] = {
    "consultation": "Mortgage Consultation",
    "discovery": "Discovery Call",
    "pre_approval": "Pre-Approval Review",
    "document_review": "Document Review",
    "rate_lock": "Rate Lock Discussion",
    "closing_prep": "Closing Preparation",
}


# =============================================================================
# Low-level RFC 5545 helpers
# =============================================================================

def _escape_ics_text(text: str) -> str:
    """Escape special characters per RFC 5545 Section 3.3.11.

    Backslashes MUST be escaped first to avoid double-escaping characters
    introduced by later replacements.  Then semicolons, commas, and newlines.
    """
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    # Normalise all newline variants to the ICS literal ``\\n``
    text = text.replace("\r\n", "\\n")
    text = text.replace("\r", "\\n")
    text = text.replace("\n", "\\n")
    return text


def _fold_line(line: str) -> str:
    """Fold long content lines per RFC 5545 Section 3.1.

    Content lines SHOULD be no longer than 75 octets (bytes in UTF-8).
    Lines that exceed this limit are split by inserting a CRLF immediately
    followed by a single whitespace character (space or tab).  Continuation
    lines therefore have a 74-octet payload (75 minus the leading space).
    """
    if len(line.encode("utf-8")) <= 75:
        return line

    result: List[str] = []
    current = ""
    for char in line:
        candidate = current + char
        # First segment: 75-octet limit.  Continuations: 74 octets + 1 leading space.
        limit = 75 if not result else 74
        if len(candidate.encode("utf-8")) > limit:
            result.append(current)
            current = char
        else:
            current = candidate
    if current:
        result.append(current)

    return "\r\n ".join(result)


def format_datetime_utc(dt: datetime) -> str:
    """Format a datetime as an ICS UTC timestamp ``YYYYMMDDTHHMMSSZ``.

    The trailing ``Z`` designates UTC.  Callers must ensure *dt* represents
    UTC; no timezone conversion is performed here.
    """
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _format_date(d: date) -> str:
    """Format a date (or datetime) as ``YYYYMMDD`` for all-day events."""
    return d.strftime("%Y%m%d")


def _make_uid(prefix: str = "") -> str:
    """Generate a globally-unique event UID in the ``value@domain`` form."""
    if prefix:
        return f"{prefix}-{uuid.uuid4()}@perenniaai.com"
    return f"{uuid.uuid4()}@perenniaai.com"


# =============================================================================
# Core ICS event generators
# =============================================================================

def generate_ics_event(
    summary: str,
    description: str,
    start: datetime,
    end: datetime,
    location: str = "",
    organizer_email: str = "",
    organizer_name: str = "",
    attendees: Optional[List[Dict[str, str]]] = None,
    uid: Optional[str] = None,
    reminder_minutes: int = 15,
    url: Optional[str] = None,
    prodid: str = PRODID_MORTGAGE,
    method: str = "REQUEST",
) -> str:
    """Generate a complete single-event ICS calendar string.

    All ``DTSTART`` / ``DTEND`` values are emitted with the ``Z`` suffix
    (UTC) to avoid the floating-time ambiguity bug.

    Args:
        summary: Event title / summary.
        description: Event description (plain text; will be escaped).
        start: Event start datetime (UTC).
        end: Event end datetime (UTC).
        location: Optional location string (physical address or URL).
        organizer_email: Organizer email address.
        organizer_name: Organizer display name.
        attendees: List of dicts, each with ``email`` and optional ``name``.
        uid: Unique event identifier.  Auto-generated if *None*.
        reminder_minutes: Minutes before the event to trigger a reminder.
            Set to 0 or negative to suppress the VALARM.
        url: Optional URL property (e.g. a join link).
        prodid: PRODID value for the VCALENDAR wrapper.
        method: METHOD property (REQUEST, PUBLISH, etc.).

    Returns:
        The complete ICS file content as a string with CRLF line endings.
    """
    if uid is None:
        uid = _make_uid()
    if attendees is None:
        attendees = []

    dtstamp = format_datetime_utc(datetime.now(timezone.utc))
    dtstart = format_datetime_utc(start)
    dtend = format_datetime_utc(end)

    escaped_summary = _escape_ics_text(summary)
    escaped_description = _escape_ics_text(description)
    escaped_location = _escape_ics_text(location) if location else ""

    lines: List[str] = [
        "BEGIN:VCALENDAR",
        f"PRODID:{prodid}",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        f"METHOD:{method}",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{escaped_summary}",
    ]

    if escaped_description:
        lines.append(f"DESCRIPTION:{escaped_description}")

    if escaped_location:
        lines.append(f"LOCATION:{escaped_location}")

    if url:
        lines.append(f"URL:{url}")

    if organizer_email:
        escaped_org_name = _escape_ics_text(organizer_name) if organizer_name else ""
        if escaped_org_name:
            lines.append(f"ORGANIZER;CN={escaped_org_name}:mailto:{organizer_email}")
        else:
            lines.append(f"ORGANIZER:mailto:{organizer_email}")

    lines.extend([
        "SEQUENCE:0",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
    ])

    # Attendees
    for att in attendees:
        att_email = att.get("email", "")
        if not att_email:
            continue
        att_name = _escape_ics_text(att.get("name", ""))
        if att_name:
            lines.append(
                f"ATTENDEE;CN={att_name};ROLE=REQ-PARTICIPANT;"
                f"PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{att_email}"
            )
        else:
            lines.append(
                f"ATTENDEE;ROLE=REQ-PARTICIPANT;"
                f"PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{att_email}"
            )

    # Reminder alarm
    if reminder_minutes and reminder_minutes > 0:
        lines.extend([
            "BEGIN:VALARM",
            f"TRIGGER:-PT{reminder_minutes}M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:Reminder: {escaped_summary} starts in {reminder_minutes} minutes",
            "END:VALARM",
        ])

    lines.extend([
        "END:VEVENT",
        "END:VCALENDAR",
    ])

    # Fold long lines and join with CRLF per RFC 5545
    folded = [_fold_line(line) for line in lines]
    return "\r\n".join(folded) + "\r\n"


def generate_ics_multi_event(
    events: List[Dict[str, Any]],
    prodid: str = PRODID_MILESTONES,
    method: str = "PUBLISH",
    calendar_name: Optional[str] = None,
) -> str:
    """Generate an ICS calendar containing multiple VEVENT blocks.

    Each entry in *events* is a dict with the following keys:

    For timed events:
        - ``summary`` (str): Event title.
        - ``description`` (str): Event description.
        - ``start`` (datetime): Start time (UTC).
        - ``end`` (datetime): End time (UTC).

    For all-day events:
        - ``summary`` (str): Event title.
        - ``description`` (str): Event description.
        - ``start_date`` (date): Start date.
        - ``end_date`` (date, optional): Exclusive end date; defaults to
          ``start_date + 1 day``.

    Common optional keys:
        - ``uid`` (str): Unique identifier.
        - ``location`` (str): Location.
        - ``transp`` (str): TRANSPARENT or OPAQUE.
        - ``alarms`` (list of dict): Each with ``trigger`` (str, e.g.
          ``-PT15M``, ``-P1D``) and ``description`` (str).

    Returns:
        Complete ICS string with CRLF endings.
    """
    dtstamp = format_datetime_utc(datetime.now(timezone.utc))

    lines: List[str] = [
        "BEGIN:VCALENDAR",
        f"PRODID:{prodid}",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        f"METHOD:{method}",
    ]

    if calendar_name:
        lines.append(f"X-WR-CALNAME:{_escape_ics_text(calendar_name)}")

    for evt in events:
        uid = evt.get("uid") or _make_uid()
        escaped_summary = _escape_ics_text(evt.get("summary", ""))
        escaped_desc = _escape_ics_text(evt.get("description", ""))
        transp = evt.get("transp", "OPAQUE")

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
        ])

        # All-day vs timed
        if "start_date" in evt:
            start_d = evt["start_date"]
            end_d = evt.get("end_date") or (start_d + timedelta(days=1))
            lines.append(f"DTSTART;VALUE=DATE:{_format_date(start_d)}")
            lines.append(f"DTEND;VALUE=DATE:{_format_date(end_d)}")
        else:
            lines.append(f"DTSTART:{format_datetime_utc(evt['start'])}")
            lines.append(f"DTEND:{format_datetime_utc(evt['end'])}")

        lines.append(f"SUMMARY:{escaped_summary}")

        if escaped_desc:
            lines.append(f"DESCRIPTION:{escaped_desc}")

        location = evt.get("location")
        if location:
            lines.append(f"LOCATION:{_escape_ics_text(location)}")

        lines.append(f"TRANSP:{transp}")

        # Alarms
        for alarm in evt.get("alarms", []):
            lines.extend([
                "BEGIN:VALARM",
                f"TRIGGER:{alarm['trigger']}",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{_escape_ics_text(alarm.get('description', 'Reminder'))}",
                "END:VALARM",
            ])

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    folded = [_fold_line(line) for line in lines]
    return "\r\n".join(folded) + "\r\n"


# =============================================================================
# Mortgage appointment helpers
# =============================================================================

def generate_appointment_ics(
    appointment_id: str,
    contact_name: str,
    contact_email: str,
    start_time: datetime,
    duration_minutes: int = 30,
    appointment_type: str = "consultation",
    meeting_link: Optional[str] = None,
    loan_officer_name: Optional[str] = None,
    loan_officer_email: Optional[str] = None,
) -> str:
    """Generate ICS content for a mortgage appointment (borrower-facing).

    Args:
        appointment_id: Unique appointment ID.
        contact_name: Client's name.
        contact_email: Client's email.
        start_time: Appointment start time (UTC).
        duration_minutes: Duration in minutes.
        appointment_type: Key from :data:`APPOINTMENT_TYPE_TITLES`.
        meeting_link: Optional video meeting link.
        loan_officer_name: Assigned loan officer's name.
        loan_officer_email: Assigned loan officer's email.

    Returns:
        ICS file content as a string.
    """
    end_time = start_time + timedelta(minutes=duration_minutes)

    title = APPOINTMENT_TYPE_TITLES.get(appointment_type, "Mortgage Consultation")
    if loan_officer_name:
        title = f"{title} with {loan_officer_name}"
    else:
        title = f"{title} with {contact_name}"

    lo_info = f"\nYour Loan Officer: {loan_officer_name}" if loan_officer_name else ""
    description = (
        f"Thank you for scheduling your mortgage consultation with The Tim Loss Team!"
        f"{lo_info}\n"
        f"\nAppointment Details:\n"
        f"- Date: {start_time.strftime('%A, %B %d, %Y')}\n"
        f"- Time: {start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}\n"
        f"- Duration: {duration_minutes} minutes\n"
        f"\nWhat to Prepare:\n"
        f"- Recent pay stubs (last 30 days)\n"
        f"- Bank statements (last 2 months)\n"
        f"- Any questions you have about the mortgage process\n"
        f"\nIf you need to reschedule, please reply to this email.\n"
        f"\nReference: {appointment_id}"
    )

    if meeting_link:
        description += f"\n\nJoin the meeting: {meeting_link}"

    location = meeting_link or ""

    return generate_ics_event(
        summary=title,
        description=description,
        start=start_time,
        end=end_time,
        location=location,
        organizer_email=loan_officer_email or DEFAULT_ORGANIZER_EMAIL,
        organizer_name=loan_officer_name or DEFAULT_ORGANIZER_NAME,
        attendees=[{"email": contact_email, "name": contact_name}],
        url=meeting_link,
    )


def generate_lo_appointment_ics(
    appointment_id: str,
    contact_name: str,
    contact_email: str,
    contact_phone: Optional[str],
    start_time: datetime,
    duration_minutes: int = 30,
    appointment_type: str = "consultation",
    meeting_link: Optional[str] = None,
    loan_officer_name: str = "",
    loan_officer_email: str = "",
    notes: Optional[str] = None,
) -> str:
    """Generate ICS content for a loan officer's calendar.

    Args:
        appointment_id: Unique appointment ID.
        contact_name: Client's name.
        contact_email: Client's email.
        contact_phone: Client's phone number.
        start_time: Appointment start time (UTC).
        duration_minutes: Duration in minutes.
        appointment_type: Key from :data:`APPOINTMENT_TYPE_TITLES`.
        meeting_link: Optional video meeting link.
        loan_officer_name: Loan officer's name.
        loan_officer_email: Loan officer's email.
        notes: Additional notes about the appointment.

    Returns:
        ICS file content as a string.
    """
    end_time = start_time + timedelta(minutes=duration_minutes)

    title = APPOINTMENT_TYPE_TITLES.get(appointment_type, "Mortgage Consultation")
    title = f"{title} - {contact_name}"

    phone_info = f"\n- Phone: {contact_phone}" if contact_phone else ""
    notes_info = f"\n\nNotes:\n{notes}" if notes else ""

    description = (
        f"New appointment scheduled via AI Assistant\n"
        f"\nClient Information:\n"
        f"- Name: {contact_name}\n"
        f"- Email: {contact_email}{phone_info}\n"
        f"\nAppointment Details:\n"
        f"- Date: {start_time.strftime('%A, %B %d, %Y')}\n"
        f"- Time: {start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}\n"
        f"- Duration: {duration_minutes} minutes\n"
        f"- Type: {appointment_type.replace('_', ' ').title()}"
        f"{notes_info}\n"
        f"\nReference: {appointment_id}"
    )

    location = meeting_link or ""

    return generate_ics_event(
        summary=title,
        description=description,
        start=start_time,
        end=end_time,
        location=location,
        organizer_email=DEFAULT_ORGANIZER_EMAIL,
        organizer_name=DEFAULT_ORGANIZER_NAME,
        attendees=[{"email": loan_officer_email, "name": loan_officer_name}],
        url=meeting_link,
    )


def generate_milestone_calendar_ics(
    loan_number: str,
    borrower_name: str,
    property_address: Optional[str],
    milestones: List[Dict[str, Any]],
    target_close_date: Optional[date] = None,
    loan_officer_name: Optional[str] = None,
) -> str:
    """Generate an ICS calendar with all loan milestones as all-day events.

    Args:
        loan_number: The loan number for reference.
        borrower_name: Borrower's name.
        property_address: Property address (optional).
        milestones: List of milestone dicts with keys ``name``, ``description``,
            ``due_date`` (date), and ``status`` (pending/completed/overdue).
        target_close_date: Target closing date (optional).
        loan_officer_name: LO name for reference (optional).

    Returns:
        ICS file content as a string with multiple VEVENT blocks.
    """
    # Build shared context block for descriptions
    context_parts = [f"Loan: {loan_number}", f"Borrower: {borrower_name}"]
    if property_address:
        context_parts.append(f"Property: {property_address}")
    if loan_officer_name:
        context_parts.append(f"Loan Officer: {loan_officer_name}")
    context_info = "\n".join(context_parts)

    events: List[Dict[str, Any]] = []

    for milestone in milestones:
        milestone_name = milestone.get("name", "Milestone")
        milestone_desc = milestone.get("description", "")
        due_date = milestone.get("due_date")
        status = milestone.get("status", "pending")

        if not due_date:
            continue

        # Status indicator in title
        status_indicator = ""
        if status == "completed":
            status_indicator = "\u2713 "
        elif status == "overdue":
            status_indicator = "\u26a0\ufe0f "

        summary = f"{status_indicator}[Loan {loan_number}] {milestone_name}"

        desc_parts = []
        if milestone_desc:
            desc_parts.append(milestone_desc)
        desc_parts.append("")
        desc_parts.append(context_info)
        full_desc = "\n".join(desc_parts)

        events.append({
            "uid": _make_uid(f"milestone-{loan_number}"),
            "summary": summary,
            "description": full_desc,
            "start_date": due_date if isinstance(due_date, date) and not isinstance(due_date, datetime) else due_date,
            "end_date": (due_date + timedelta(days=1)),
            "transp": "TRANSPARENT",
            "alarms": [
                {
                    "trigger": "-P1D",
                    "description": f"Reminder: {milestone_name} is due tomorrow",
                },
            ],
        })

    # Target closing date as a special event
    if target_close_date:
        close_desc = f"Target closing date for {borrower_name}\n\n{context_info}"
        events.append({
            "uid": _make_uid(f"closing-{loan_number}"),
            "summary": f"\U0001f389 [Loan {loan_number}] TARGET CLOSING DAY",
            "description": close_desc,
            "start_date": target_close_date,
            "end_date": target_close_date + timedelta(days=1),
            "transp": "OPAQUE",
            "alarms": [
                {
                    "trigger": "-P7D",
                    "description": f"Reminder: Closing in 7 days for Loan {loan_number}",
                },
                {
                    "trigger": "-P3D",
                    "description": f"Reminder: Closing in 3 days for Loan {loan_number}",
                },
            ],
        })

    return generate_ics_multi_event(
        events=events,
        prodid=PRODID_MILESTONES,
        method="PUBLISH",
        calendar_name=f"Loan {loan_number} - Milestones",
    )


# =============================================================================
# Video meeting helper
# =============================================================================

def generate_meeting_ics(
    meeting_name: str,
    description: str,
    start_time: datetime,
    end_time: datetime,
    organizer_email: str,
    organizer_name: str,
    attendees: List[Dict[str, str]],
    join_url: str,
    location: Optional[str] = None,
    uid: Optional[str] = None,
) -> str:
    """Generate an ICS invite for a video meeting.

    This is the high-level entry point used by the video meeting platform.

    Args:
        meeting_name: Title / summary.
        description: Description or agenda.
        start_time: Start in UTC.
        end_time: End in UTC.
        organizer_email: Organizer email.
        organizer_name: Organizer display name.
        attendees: List of dicts with ``email`` and ``name``.
        join_url: Video meeting join URL.
        location: Optional explicit location (defaults to *join_url*).
        uid: Optional UID; auto-generated if omitted.

    Returns:
        Complete ICS file content as a string.
    """
    effective_location = location if location else join_url

    return generate_ics_event(
        summary=meeting_name,
        description=description,
        start=start_time,
        end=end_time,
        location=effective_location,
        organizer_email=organizer_email,
        organizer_name=organizer_name,
        attendees=attendees,
        uid=uid,
        url=join_url,
        prodid=PRODID_VIDEO,
    )


def generate_meeting_ics_bytes(
    meeting_name: str,
    description: str,
    start_time: datetime,
    end_time: datetime,
    organizer_email: str,
    organizer_name: str,
    attendees: List[Dict[str, str]],
    join_url: str,
    location: Optional[str] = None,
    uid: Optional[str] = None,
) -> bytes:
    """Generate ICS for a video meeting as UTF-8 bytes (for email attachment)."""
    return generate_meeting_ics(
        meeting_name=meeting_name,
        description=description,
        start_time=start_time,
        end_time=end_time,
        organizer_email=organizer_email,
        organizer_name=organizer_name,
        attendees=attendees,
        join_url=join_url,
        location=location,
        uid=uid,
    ).encode("utf-8")
