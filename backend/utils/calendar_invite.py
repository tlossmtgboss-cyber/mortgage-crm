"""
Calendar Invite Utility (backward-compatibility wrapper)

All ICS generation logic has been consolidated into ``utils.ics_generator``.
This module re-exports the public API so that existing ``from utils.calendar_invite
import ...`` statements continue to work unchanged.
"""

from datetime import datetime
from typing import Optional

from utils.ics_generator import (  # noqa: F401
    generate_ics_event,
    generate_appointment_ics,
    generate_lo_appointment_ics,
    generate_milestone_calendar_ics,
    APPOINTMENT_TYPE_TITLES,
)


def generate_ics_content(
    title: str,
    start_time: datetime,
    end_time: datetime,
    description: str = "",
    location: str = "",
    organizer_email: str = "sarah@reply.perenniaai.com",
    organizer_name: str = "Sarah - Perennia AI",
    attendee_email: Optional[str] = None,
    attendee_name: Optional[str] = None,
    meeting_link: Optional[str] = None,
) -> str:
    """Generate ICS content with the legacy single-attendee signature.

    Delegates to :func:`utils.ics_generator.generate_ics_event`, converting
    the single ``attendee_email``/``attendee_name`` parameters into the list
    format expected by the consolidated generator.
    """
    # Build description with meeting link (matches old behavior)
    full_description = description
    if meeting_link:
        full_description += f"\n\nJoin the meeting: {meeting_link}"
        if not location:
            location = meeting_link

    attendees = []
    if attendee_email:
        attendees.append({
            "email": attendee_email,
            "name": attendee_name or attendee_email.split("@")[0],
        })

    return generate_ics_event(
        summary=title,
        description=full_description,
        start=start_time,
        end=end_time,
        location=location,
        organizer_email=organizer_email,
        organizer_name=organizer_name,
        attendees=attendees,
        url=meeting_link,
    )


__all__ = [
    "generate_ics_content",
    "generate_appointment_ics",
    "generate_lo_appointment_ics",
    "generate_milestone_calendar_ics",
    "APPOINTMENT_TYPE_TITLES",
]
