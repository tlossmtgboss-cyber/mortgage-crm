"""
Outlook Calendar Sync — push CRM appointments to Outlook via .ics email invite.

CMG's Azure AD blocks direct OAuth from the Perennia app, so we send an .ics
calendar invite to the LO's Outlook address via SendGrid. Outlook auto-accepts
the .ics attachment and the event appears on their calendar.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _build_ics(
    uid: str,
    summary: str,
    dtstart: datetime,
    dtend: datetime,
    description: str = "",
    location: str = "",
    organizer_email: str = "",
    attendee_email: str = "",
    method: str = "REQUEST",
) -> str:
    fmt = "%Y%m%dT%H%M%SZ"

    def _utc(dt: datetime) -> str:
        if dt.tzinfo is None:
            return dt.strftime(fmt)
        return dt.astimezone(timezone.utc).strftime(fmt)

    now = _utc(datetime.now(timezone.utc))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Perennia AI//Smart Calendar//EN",
        f"METHOD:{method}",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now}",
        f"DTSTART:{_utc(dtstart)}",
        f"DTEND:{_utc(dtend)}",
        f"SUMMARY:{summary}",
    ]
    if description:
        escaped = description.replace("\n", "\\n").replace(",", "\\,")
        lines.append(f"DESCRIPTION:{escaped}")
    if location:
        lines.append(f"LOCATION:{location}")
    if organizer_email:
        lines.append(f"ORGANIZER;CN=Perennia Calendar:mailto:{organizer_email}")
    if attendee_email:
        lines.append(
            f"ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=ACCEPTED;RSVP=FALSE:"
            f"mailto:{attendee_email}"
        )
    lines.append("SEQUENCE:0")
    lines.append("STATUS:CONFIRMED")
    lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


async def push_appointment_to_outlook(
    db: Session,
    appointment,
    outlook_email: str,
) -> dict:
    """Send an .ics invite to the LO's Outlook so the event appears on their calendar.

    Uses SendGrid (no Microsoft tokens needed). The .ics attachment triggers
    Outlook's calendar processing and auto-adds the event.
    """
    try:
        from email_service import EmailService
        email_svc = EmailService()
    except Exception as exc:
        return {"success": False, "error": f"Email service unavailable: {exc}"}

    ics_uid = f"perennia-appt-{appointment.id}@perenniaai.com"

    location = ""
    if getattr(appointment, "video_link", None):
        location = appointment.video_link
    elif getattr(appointment, "location", None):
        location = appointment.location

    attendee = getattr(appointment, "attendee_email", "") or ""

    ics_content = _build_ics(
        uid=ics_uid,
        summary=getattr(appointment, "title", "Appointment") or "Appointment",
        dtstart=appointment.scheduled_start,
        dtend=appointment.scheduled_end,
        description=getattr(appointment, "description", "") or "",
        location=location,
        organizer_email=outlook_email,
        attendee_email=attendee,
    )

    title = getattr(appointment, "title", "Appointment") or "Appointment"
    start_fmt = appointment.scheduled_start.strftime("%B %d, %Y at %I:%M %p") if appointment.scheduled_start else ""

    body_html = (
        f"<p>A new appointment has been added to your calendar from Perennia Smart Calendar.</p>"
        f"<p><strong>{title}</strong><br>{start_fmt}</p>"
    )
    attendee_name = getattr(appointment, "attendee_name", None)
    if attendee_name:
        body_html += f"<p>With: {attendee_name}"
        if attendee:
            body_html += f" ({attendee})"
        body_html += "</p>"
    if location:
        body_html += f"<p>Location: {location}</p>"

    ics_bytes = ics_content.encode("utf-8")

    try:
        sent = email_svc.send_html_email(
            to_email=outlook_email,
            subject=f"Smart Calendar: {title}",
            html_body=body_html,
            attachments=[{
                "content": ics_bytes,
                "filename": "invite.ics",
                "type": "text/calendar; method=REQUEST",
            }],
        )
        if sent:
            logger.info("Outlook sync: sent .ics invite for appointment %s to %s", appointment.id, outlook_email)
            return {"success": True}
        return {"success": False, "error": "SendGrid send_html_email returned False"}
    except Exception as exc:
        logger.error("Outlook sync exception: %s", exc)
        return {"success": False, "error": str(exc)}
