"""
Calendar Invite Service - Generates RFC 5545 compliant ICS calendar invites
for Perennia AI video meeting platform.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CalendarInviteService:
    """Generates .ics calendar invite files for video meetings."""

    PRODID = "-//Perennia AI//Video Meeting Platform//EN"
    CALSCALE = "GREGORIAN"
    VERSION = "2.0"

    def _escape_ics_text(self, text: str) -> str:
        """Escape special characters per RFC 5545 Section 3.3.11.

        Backslashes must be escaped first to avoid double-escaping.
        Commas, semicolons, and newlines all require escaping in TEXT values.
        """
        if not text:
            return ""
        text = text.replace("\\", "\\\\")
        text = text.replace(";", "\\;")
        text = text.replace(",", "\\,")
        text = text.replace("\r\n", "\\n")
        text = text.replace("\r", "\\n")
        text = text.replace("\n", "\\n")
        return text

    def _format_datetime(self, dt: datetime) -> str:
        """Format a datetime as an ICS UTC timestamp (YYYYMMDDTHHMMSSZ)."""
        return dt.strftime("%Y%m%dT%H%M%SZ")

    def _fold_line(self, line: str) -> str:
        """Fold long lines per RFC 5545 Section 3.1.

        Content lines should be no longer than 75 octets. Lines that exceed
        this limit are folded by inserting a CRLF followed by a single
        whitespace character.
        """
        if len(line.encode("utf-8")) <= 75:
            return line
        result = []
        current = ""
        for char in line:
            test = current + char
            if len(test.encode("utf-8")) > 75 if not result else len(test.encode("utf-8")) > 74:
                result.append(current)
                current = char
            else:
                current = test
        if current:
            result.append(current)
        return "\r\n ".join(result)

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

        Args:
            meeting_name: Title/summary of the meeting.
            description: Meeting description or agenda text.
            start_time: Meeting start in UTC.
            end_time: Meeting end in UTC.
            organizer_email: Email address of the organizer.
            organizer_name: Display name of the organizer.
            attendees: List of dicts with "email" and "name" keys.
            join_url: Video meeting join URL.
            location: Optional physical or virtual location string.
            uid: Optional unique event identifier. Generated if not provided.

        Returns:
            The complete ICS file content as a string.
        """
        if uid is None:
            uid = f"{uuid.uuid4()}@perenniaai.com"

        dtstamp = self._format_datetime(datetime.utcnow())
        dtstart = self._format_datetime(start_time)
        dtend = self._format_datetime(end_time)

        escaped_name = self._escape_ics_text(meeting_name)
        escaped_description = self._escape_ics_text(description)
        escaped_organizer = self._escape_ics_text(organizer_name)

        # Build the effective location: prefer explicit location, fall back to join URL
        effective_location = self._escape_ics_text(location) if location else join_url

        lines = [
            "BEGIN:VCALENDAR",
            f"PRODID:{self.PRODID}",
            f"VERSION:{self.VERSION}",
            f"CALSCALE:{self.CALSCALE}",
            "METHOD:REQUEST",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:{escaped_name}",
            f"DESCRIPTION:{escaped_description}",
            f"LOCATION:{effective_location}",
            f"URL:{join_url}",
            f"ORGANIZER;CN={escaped_organizer}:mailto:{organizer_email}",
            "SEQUENCE:0",
            "STATUS:CONFIRMED",
            "TRANSP:OPAQUE",
        ]

        # Add attendees
        for attendee in attendees:
            attendee_name = self._escape_ics_text(attendee.get("name", ""))
            attendee_email = attendee.get("email", "")
            if attendee_email:
                lines.append(
                    f"ATTENDEE;CN={attendee_name};ROLE=REQ-PARTICIPANT;"
                    f"PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{attendee_email}"
                )

        # Add a 15-minute reminder alarm
        lines.extend([
            "BEGIN:VALARM",
            "TRIGGER:-PT15M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:Reminder: {escaped_name} starts in 15 minutes",
            "END:VALARM",
            "END:VEVENT",
            "END:VCALENDAR",
        ])

        # Fold long lines and join with CRLF per RFC 5545
        folded_lines = [self._fold_line(line) for line in lines]
        return "\r\n".join(folded_lines) + "\r\n"

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
        """Generate an ICS calendar invite as bytes for email attachment.

        Accepts the same parameters as generate_ics. Returns UTF-8 encoded
        bytes suitable for attaching to an email message.
        """
        ics_string = self.generate_ics(
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
        return ics_string.encode("utf-8")

    def create_meeting_invite(
        self,
        room: Any,
        host_user: Any,
        attendee_list: List[Dict[str, str]],
        base_url: str,
    ) -> str:
        """High-level method to generate an ICS invite from a meeting room object.

        Args:
            room: Meeting room object with attributes:
                - room_name (str): Name of the meeting room / meeting title.
                - room_description (str): Description or agenda.
                - scheduled_start (datetime): Start time in UTC.
                - scheduled_end (datetime): End time in UTC.
                - room_code (str): Unique room code for the join URL.
            host_user: User object with attributes:
                - email (str): Host's email address.
                - name (str) or first_name/last_name: Host's display name.
            attendee_list: List of dicts with "email" and "name" keys.
            base_url: Application base URL (e.g. "https://app.perenniaai.com").

        Returns:
            The ICS file content as a string.
        """
        # Build join URL from base_url and room code
        clean_base = base_url.rstrip("/")
        room_code = getattr(room, "room_code", "")
        join_url = f"{clean_base}/meeting/{room_code}"

        # Resolve host name from various possible attribute patterns
        host_name = getattr(host_user, "name", None)
        if not host_name:
            first = getattr(host_user, "first_name", "")
            last = getattr(host_user, "last_name", "")
            host_name = f"{first} {last}".strip() or "Meeting Host"

        host_email = getattr(host_user, "email", "noreply@perenniaai.com")

        # Build description including the join link
        room_description = getattr(room, "room_description", "") or ""
        description_parts = []
        if room_description:
            description_parts.append(room_description)
        description_parts.append(f"Join the meeting: {join_url}")
        full_description = "\n\n".join(description_parts)

        # Generate a stable UID from the room code
        uid = f"{room_code}@perenniaai.com"

        return self.generate_ics(
            meeting_name=getattr(room, "room_name", "Perennia AI Meeting"),
            description=full_description,
            start_time=getattr(room, "scheduled_start", datetime.utcnow()),
            end_time=getattr(room, "scheduled_end", datetime.utcnow() + timedelta(hours=1)),
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
        """Prepare email data with an ICS calendar invite attachment.

        Args:
            email_html: The HTML body of the email.
            ics_content: The ICS file content string (from generate_ics).
            meeting_name: Meeting name used to derive the attachment filename.

        Returns:
            A dict with email data suitable for use with email_service:
                - html: The email HTML body.
                - attachments: List containing the ICS attachment dict with
                  filename, content (base64), and content_type fields.
        """
        import base64

        # Sanitize meeting name for use as a filename
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
