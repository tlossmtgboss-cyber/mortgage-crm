"""
Calendar Invite Service (backward-compatibility wrapper)

All ICS generation logic has been consolidated into ``utils.ics_generator``.
This class delegates to those functions so that existing call sites using
``calendar_invite_service.generate_ics(...)`` continue to work unchanged.
"""

import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from utils.ics_generator import (
    generate_meeting_ics,
    generate_meeting_ics_bytes,
    format_datetime_utc,
    _escape_ics_text,
    _fold_line,
)

logger = logging.getLogger(__name__)


class CalendarInviteService:
    """Generates .ics calendar invite files for video meetings.

    This class now delegates to :mod:`utils.ics_generator` for all ICS
    generation.  It is retained for backward compatibility and for the
    higher-level ``create_meeting_invite`` and ``attach_ics_to_email``
    convenience methods.
    """

    # Kept for any code that references these class attributes directly.
    PRODID = "-//Perennia AI//Video Meeting Platform//EN"
    CALSCALE = "GREGORIAN"
    VERSION = "2.0"

    # Expose the consolidated helpers as instance methods for backward compat.
    @staticmethod
    def _escape_ics_text(text: str) -> str:
        return _escape_ics_text(text)

    @staticmethod
    def _format_datetime(dt: datetime) -> str:
        return format_datetime_utc(dt)

    @staticmethod
    def _fold_line(line: str) -> str:
        return _fold_line(line)

    def generate_ics(
        self,
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
        """Generate an ICS calendar invite string following RFC 5545.

        Delegates to :func:`utils.ics_generator.generate_meeting_ics`.
        """
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
        )

    def generate_ics_bytes(
        self,
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
        """Generate ICS as UTF-8 bytes for email attachment.

        Delegates to :func:`utils.ics_generator.generate_meeting_ics_bytes`.
        """
        return generate_meeting_ics_bytes(
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
        )

    def create_meeting_invite(
        self,
        room: Any,
        host_user: Any,
        attendee_list: List[Dict[str, str]],
        base_url: str,
    ) -> str:
        """Generate an ICS invite from a meeting room object.

        Args:
            room: Meeting room object with ``room_name``, ``room_description``,
                ``scheduled_start``, ``scheduled_end``, ``room_code``.
            host_user: User object with ``email`` and ``name`` (or
                ``first_name``/``last_name``).
            attendee_list: List of dicts with ``email`` and ``name``.
            base_url: Application base URL.

        Returns:
            The ICS file content as a string.
        """
        clean_base = base_url.rstrip("/")
        room_code = getattr(room, "room_code", "")
        join_url = f"{clean_base}/meeting/{room_code}"

        host_name = getattr(host_user, "name", None)
        if not host_name:
            first = getattr(host_user, "first_name", "")
            last = getattr(host_user, "last_name", "")
            host_name = f"{first} {last}".strip() or "Meeting Host"

        host_email = getattr(host_user, "email", "noreply@perenniaai.com")

        room_description = getattr(room, "room_description", "") or ""
        description_parts = []
        if room_description:
            description_parts.append(room_description)
        description_parts.append(f"Join the meeting: {join_url}")
        full_description = "\n\n".join(description_parts)

        uid = f"{room_code}@perenniaai.com"

        return self.generate_ics(
            meeting_name=getattr(room, "room_name", "Perennia AI Meeting"),
            description=full_description,
            start_time=getattr(room, "scheduled_start", datetime.now(timezone.utc)),
            end_time=getattr(room, "scheduled_end", datetime.now(timezone.utc) + timedelta(hours=1)),
            organizer_email=host_email,
            organizer_name=host_name,
            attendees=attendee_list,
            join_url=join_url,
            uid=uid,
        )

    def attach_ics_to_email(
        self,
        email_html: str,
        ics_content: str,
        meeting_name: str,
    ) -> Dict[str, Any]:
        """Prepare email data with an ICS attachment.

        Args:
            email_html: HTML body of the email.
            ics_content: ICS file content string.
            meeting_name: Meeting name for the attachment filename.

        Returns:
            Dict with ``html`` and ``attachments`` keys.
        """
        safe_name = "".join(
            c if c.isalnum() or c in (" ", "-", "_") else "_"
            for c in meeting_name
        ).strip().replace(" ", "_")
        if not safe_name:
            safe_name = "meeting_invite"
        filename = f"{safe_name}.ics"

        ics_bytes = ics_content.encode("utf-8")
        ics_base64 = base64.b64encode(ics_bytes).decode("ascii")

        return {
            "html": email_html,
            "attachments": [
                {
                    "filename": filename,
                    "content": ics_base64,
                    "content_type": "text/calendar; method=REQUEST",
                }
            ],
        }


# Global singleton instance
calendar_invite_service = CalendarInviteService()
