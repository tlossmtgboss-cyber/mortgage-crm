"""
Outlook Calendar Sync — push CRM appointments to Outlook via .ics email invite.

CMG's Azure AD blocks direct OAuth from the Perennia app, so we use the
existing DRE email integration (MicrosoftOAuthToken) to send an .ics
calendar invite to the LO's own Outlook address. Outlook auto-adds the
event to their calendar.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
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
    lines.append(f"SEQUENCE:0")
    lines.append("STATUS:CONFIRMED")
    lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


async def _get_token_for_user(user_id: int, db: Session) -> Optional[str]:
    from database.models.microsoft import MicrosoftOAuthToken
    from services.dre_helpers import validate_microsoft_token

    record = db.query(MicrosoftOAuthToken).filter(
        MicrosoftOAuthToken.user_id == user_id,
    ).first()
    if not record:
        return None

    result = await validate_microsoft_token(record, db)
    if not result.get("valid"):
        logger.warning("Outlook sync: token invalid for user %s: %s", user_id, result.get("error"))
        return None
    return result["access_token"]


async def push_appointment_to_outlook(
    db: Session,
    appointment,
    user_email: str,
) -> dict:
    """Send an .ics invite to the LO's Outlook so the event appears on their calendar."""
    user_id = appointment.assigned_user_id or appointment.created_by_user_id
    if not user_id:
        return {"success": False, "error": "No user associated with appointment"}

    access_token = await _get_token_for_user(user_id, db)
    if not access_token:
        return {"success": False, "error": "No valid Microsoft token — connect Outlook email first"}

    ics_uid = f"perennia-appt-{appointment.id}@perenniaai.com"

    location = ""
    if appointment.video_link:
        location = appointment.video_link
    elif appointment.location:
        location = appointment.location

    attendee_line = ""
    if appointment.attendee_email:
        attendee_line = appointment.attendee_email

    ics_content = _build_ics(
        uid=ics_uid,
        summary=appointment.title or "Appointment",
        dtstart=appointment.scheduled_start,
        dtend=appointment.scheduled_end,
        description=appointment.description or "",
        location=location,
        organizer_email=user_email,
        attendee_email=attendee_line,
    )

    import base64
    ics_b64 = base64.b64encode(ics_content.encode("utf-8")).decode("ascii")

    subject = f"📅 {appointment.title or 'Appointment'}"
    body_html = (
        f"<p>A new appointment has been added to your calendar from Perennia Smart Calendar.</p>"
        f"<p><strong>{appointment.title}</strong><br>"
        f"{appointment.scheduled_start.strftime('%B %d, %Y at %I:%M %p') if appointment.scheduled_start else ''}"
        f"</p>"
    )
    if appointment.attendee_name:
        body_html += f"<p>With: {appointment.attendee_name}"
        if appointment.attendee_email:
            body_html += f" ({appointment.attendee_email})"
        body_html += "</p>"
    if location:
        body_html += f"<p>Location: {location}</p>"

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [{"emailAddress": {"address": user_email}}],
            "attachments": [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": "invite.ics",
                    "contentType": "text/calendar; method=REQUEST",
                    "contentBytes": ics_b64,
                }
            ],
        },
        "saveToSentItems": False,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://graph.microsoft.com/v1.0/me/sendMail",
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
        if resp.status_code == 202:
            logger.info("Outlook sync: sent .ics invite for appointment %s to %s", appointment.id, user_email)
            return {"success": True}

        error_text = resp.text[:300]
        logger.error("Outlook sync failed: %d — %s", resp.status_code, error_text)
        return {"success": False, "error": f"Graph API {resp.status_code}: {error_text}"}
    except Exception as exc:
        logger.error("Outlook sync exception: %s", exc)
        return {"success": False, "error": str(exc)}
