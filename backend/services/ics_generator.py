"""
ICS (iCalendar) generation service for scheduler appointments.

Provides the ``generate_ics_content`` function used by scheduler_email_service
and other scheduler modules.  Delegates to the RFC 5545-compliant primitives in
``utils.ics_generator`` so there is a single, well-tested ICS implementation
across the entire codebase.

Also exposes ``create_ics_attachment`` which handles the common pattern of
generating ICS content and wrapping it in a base64-encoded SendGrid attachment
dict.

Typical usage::

    from services.ics_generator import generate_ics_content, create_ics_attachment

    ics = generate_ics_content(
        appointment_title="Consultation",
        start_datetime=dt,
        duration_minutes=30,
        attendee_email="client@example.com",
        attendee_name="Jane Doe",
        organizer_email="lo@company.com",
        organizer_name="John Smith",
    )

    attachment = create_ics_attachment(ics, filename="appointment.ics")
"""

import base64
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from utils.ics_generator import (
    generate_ics_event,
    _escape_ics_text,
    _make_uid,
    PRODID_MORTGAGE,
    DEFAULT_ORGANIZER_EMAIL,
)

logger = logging.getLogger(__name__)


def generate_ics_content(
    appointment_title: str,
    start_datetime: datetime,
    duration_minutes: int,
    attendee_email: str,
    attendee_name: str,
    organizer_email: str,
    organizer_name: str,
    description: str = "",
    location: str = "",
    video_link: Optional[str] = None,
    appointment_id: Optional[int] = None,
) -> str:
    """Generate ICS calendar file content for a scheduler appointment.

    This function preserves the call signature used throughout
    scheduler_email_service.py and related modules while delegating to the
    RFC 5545-compliant implementation in ``utils.ics_generator``.

    Args:
        appointment_title: Event summary / title.
        start_datetime: Event start time (should be UTC).
        duration_minutes: Duration of the appointment in minutes.
        attendee_email: Attendee's email address.
        attendee_name: Attendee's display name.
        organizer_email: Organizer's email address.
        organizer_name: Organizer's display name.
        description: Plain-text event description.
        location: Event location (physical address or URL).
        video_link: Optional video meeting join URL.  Appended to description
            and used as location if no explicit location is provided.
        appointment_id: If provided, used to generate a deterministic UID
            (``appt-<id>@perenniaai.com``) to prevent duplicate calendar
            entries on updates.

    Returns:
        Complete ICS file content as a string.
    """
    end_datetime = start_datetime + timedelta(minutes=duration_minutes)

    # Build description with video link (matches legacy behavior)
    full_description = description or ""
    if video_link:
        full_description += "\\nJoin Video Call: " + video_link
        if not location:
            location = video_link

    # Deterministic UID when appointment_id is available
    uid: Optional[str] = None
    if appointment_id:
        uid = f"appt-{appointment_id}@perenniaai.com"

    # Build attendees list
    attendees = []
    if attendee_email:
        attendees.append({
            "email": attendee_email.replace("\n", "").replace("\r", "").strip(),
            "name": attendee_name or "",
        })

    return generate_ics_event(
        summary=appointment_title,
        description=full_description,
        start=start_datetime,
        end=end_datetime,
        location=location,
        organizer_email=organizer_email.replace("\n", "").replace("\r", "").strip() if organizer_email else "",
        organizer_name=organizer_name or "",
        attendees=attendees,
        uid=uid,
        url=video_link,
        prodid=PRODID_MORTGAGE,
        method="REQUEST",
    )


def generate_appointment_ics(appointment_data: dict) -> bytes:
    """Generate ICS content for an appointment and return as UTF-8 bytes.

    This is a convenience wrapper that accepts a dict of appointment data
    (as commonly available from database models or API payloads) and returns
    bytes suitable for direct use as an email attachment payload.

    Expected keys in ``appointment_data``:
        - ``title`` (str): Appointment title.
        - ``scheduled_start`` (datetime or ISO str): Start time.
        - ``scheduled_end`` (datetime or ISO str, optional): End time.
        - ``duration_minutes`` (int, optional): Duration; defaults to 30.
        - ``attendee_email`` (str): Attendee email.
        - ``attendee_name`` (str): Attendee name.
        - ``organizer_email`` (str, optional): Organizer email.
        - ``organizer_name`` (str, optional): Organizer name.
        - ``description`` (str, optional): Description text.
        - ``location`` (str, optional): Location.
        - ``video_link`` (str, optional): Video meeting URL.
        - ``id`` (int, optional): Appointment ID for deterministic UID.

    Returns:
        ICS file content as UTF-8 encoded bytes.
    """
    start_dt = appointment_data.get("scheduled_start")
    end_dt = appointment_data.get("scheduled_end")

    # Parse ISO strings if necessary
    if isinstance(start_dt, str):
        start_dt = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
    if isinstance(end_dt, str):
        end_dt = datetime.fromisoformat(end_dt.replace("Z", "+00:00"))

    # Calculate duration
    duration_minutes = appointment_data.get("duration_minutes", 30)
    if end_dt and start_dt and not appointment_data.get("duration_minutes"):
        duration_minutes = int((end_dt - start_dt).total_seconds() / 60)

    ics_str = generate_ics_content(
        appointment_title=appointment_data.get("title", "Appointment"),
        start_datetime=start_dt,
        duration_minutes=duration_minutes,
        attendee_email=appointment_data.get("attendee_email", ""),
        attendee_name=appointment_data.get("attendee_name", ""),
        organizer_email=appointment_data.get("organizer_email", DEFAULT_ORGANIZER_EMAIL),
        organizer_name=appointment_data.get("organizer_name", "Perennia AI"),
        description=appointment_data.get("description", ""),
        location=appointment_data.get("location", "") or appointment_data.get("video_link", ""),
        video_link=appointment_data.get("video_link"),
        appointment_id=appointment_data.get("id"),
    )

    return ics_str.encode("utf-8")


def create_ics_attachment(
    ics_content: str,
    filename: str = "appointment.ics",
) -> Dict[str, str]:
    """Wrap ICS content string into a SendGrid-compatible attachment dict.

    Args:
        ics_content: The raw ICS string (as returned by ``generate_ics_content``).
        filename: Attachment filename.

    Returns:
        Dict with ``content`` (base64-encoded), ``filename``, and ``type`` keys,
        ready for inclusion in the ``attachments`` list passed to
        ``notification_service.send_email()``.
    """
    return {
        "content": base64.b64encode(ics_content.encode("utf-8")).decode("utf-8"),
        "filename": filename,
        "type": "text/calendar",
    }
