"""
Calendar Export Service - ICS file and PDF schedule generation.

Generates downloadable ICS files for calendar app import and printable
PDF/HTML schedule documents.  Leverages the RFC 5545-compliant primitives
in ``utils.ics_generator`` for ICS output.
"""

from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import html as html_mod
import logging

from utils.ics_generator import (
    generate_ics_multi_event,
    generate_ics_event,
    format_datetime_utc,
    _escape_ics_text,
    _make_uid,
    PRODID_MORTGAGE,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ICS status mapping
# =============================================================================

_ICS_STATUS_MAP = {
    "booked": "CONFIRMED",
    "confirmed": "CONFIRMED",
    "tentative": "TENTATIVE",
    "available": "TENTATIVE",
    "reminded": "CONFIRMED",
    "checked_in": "CONFIRMED",
    "completed": "CONFIRMED",
    "no_show": "CANCELLED",
    "cancelled": "CANCELLED",
    "rescheduled": "CANCELLED",
}


def _appointment_to_event_dict(appt) -> Dict[str, Any]:
    """Convert an Appointment ORM object into the dict format expected by
    ``generate_ics_multi_event``.
    """
    status_str = appt.status.value if hasattr(appt.status, "value") else str(appt.status)

    summary = appt.title or "Appointment"
    description_parts = []

    if appt.description:
        description_parts.append(appt.description)
    if appt.attendee_name:
        description_parts.append(f"Attendee: {appt.attendee_name}")
    if appt.attendee_email:
        description_parts.append(f"Email: {appt.attendee_email}")
    if appt.attendee_phone:
        description_parts.append(f"Phone: {appt.attendee_phone}")
    if appt.video_link:
        description_parts.append(f"Video: {appt.video_link}")
    if appt.internal_notes:
        description_parts.append(f"\nNotes: {appt.internal_notes}")

    location = appt.location or appt.video_link or ""

    return {
        "uid": _make_uid(f"appt-{appt.id}"),
        "summary": summary,
        "description": "\n".join(description_parts),
        "start": appt.scheduled_start,
        "end": appt.scheduled_end,
        "location": location,
    }


# =============================================================================
# CalendarExportService
# =============================================================================

class CalendarExportService:
    """Generates ICS and PDF exports for scheduler appointments."""

    @staticmethod
    def generate_ics(
        appointments: list,
        calendar_name: str = "Perennia Schedule",
    ) -> str:
        """Generate a multi-event ICS (iCalendar) string for a list of
        Appointment ORM objects.

        Args:
            appointments: List of Appointment model instances.
            calendar_name: Display name embedded in the ICS X-WR-CALNAME header.

        Returns:
            Complete ICS file content (RFC 5545) with CRLF line endings.
        """
        events = [_appointment_to_event_dict(appt) for appt in appointments]

        return generate_ics_multi_event(
            events=events,
            prodid=PRODID_MORTGAGE,
            method="PUBLISH",
            calendar_name=calendar_name,
        )

    @staticmethod
    def generate_ics_single(appointment) -> str:
        """Generate ICS for a single appointment.

        Convenience wrapper used for email attachments and single-event
        downloads.
        """
        return CalendarExportService.generate_ics(
            [appointment],
            calendar_name=appointment.title or "Perennia Appointment",
        )

    @staticmethod
    def generate_pdf_schedule(
        appointments: list,
        user_name: str,
        date_range: Tuple[date, date],
        org_name: str = "",
    ) -> bytes:
        """Generate a printable schedule document.

        Attempts to produce a PDF via ``weasyprint``.  If weasyprint is not
        installed, falls back to returning the styled HTML as UTF-8 bytes
        (the browser can print it natively).

        Args:
            appointments: List of Appointment model instances.
            user_name: Display name of the schedule owner.
            date_range: Tuple of (start_date, end_date) inclusive.
            org_name: Organization name for the header.

        Returns:
            PDF bytes (``application/pdf``) or HTML bytes (``text/html``)
            depending on weasyprint availability.
        """
        schedule_html = _build_schedule_html(appointments, user_name, date_range, org_name)
        try:
            from weasyprint import HTML  # type: ignore[import-untyped]
            return HTML(string=schedule_html).write_pdf()
        except ImportError:
            logger.debug("weasyprint not available; returning HTML fallback for PDF export")
            return schedule_html.encode("utf-8")

    @staticmethod
    def pdf_content_type() -> str:
        """Return the appropriate Content-Type for PDF output.

        Returns ``application/pdf`` if weasyprint is installed, otherwise
        ``text/html`` for the HTML fallback.
        """
        try:
            import weasyprint  # noqa: F401
            return "application/pdf"
        except ImportError:
            return "text/html"

    @staticmethod
    def pdf_file_extension() -> str:
        """Return file extension matching the output format."""
        try:
            import weasyprint  # noqa: F401
            return "pdf"
        except ImportError:
            return "html"


# =============================================================================
# HTML schedule builder
# =============================================================================

def _build_schedule_html(
    appointments: list,
    user_name: str,
    date_range: Tuple[date, date],
    org_name: str,
) -> str:
    """Build a printable HTML schedule with professional styling."""
    start_date, end_date = date_range
    start_str = start_date.strftime("%B %d, %Y")
    end_str = end_date.strftime("%B %d, %Y")

    org_header = f"<div class='org-name'>{html_mod.escape(org_name)}</div>" if org_name else ""

    # Group appointments by date
    by_date: Dict[date, list] = {}
    for appt in appointments:
        appt_date = appt.scheduled_start.date() if isinstance(appt.scheduled_start, datetime) else appt.scheduled_start
        by_date.setdefault(appt_date, []).append(appt)

    # Sort dates
    sorted_dates = sorted(by_date.keys())

    # Build appointment rows
    rows_html = ""
    for appt_date in sorted_dates:
        day_appts = sorted(by_date[appt_date], key=lambda a: a.scheduled_start)
        date_label = appt_date.strftime("%A, %B %d, %Y")
        rows_html += f"<tr class='date-header'><td colspan='5'>{html_mod.escape(date_label)}</td></tr>\n"

        for appt in day_appts:
            start_time = appt.scheduled_start.strftime("%I:%M %p") if isinstance(appt.scheduled_start, datetime) else ""
            end_time = appt.scheduled_end.strftime("%I:%M %p") if isinstance(appt.scheduled_end, datetime) else ""
            title = html_mod.escape(appt.title or "Appointment")
            attendee = html_mod.escape(appt.attendee_name or "")
            status_str = appt.status.value if hasattr(appt.status, "value") else str(appt.status)
            status_class = status_str.lower()
            location = html_mod.escape(appt.location or appt.video_link or "")

            rows_html += (
                f"<tr>"
                f"<td class='time'>{start_time} - {end_time}</td>"
                f"<td class='title'>{title}</td>"
                f"<td class='attendee'>{attendee}</td>"
                f"<td class='location'>{location}</td>"
                f"<td class='status'><span class='badge {status_class}'>{html_mod.escape(status_str)}</span></td>"
                f"</tr>\n"
            )

    if not rows_html:
        rows_html = "<tr><td colspan='5' class='empty'>No appointments scheduled for this period.</td></tr>"

    generated_at = datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Schedule - {html_mod.escape(user_name)}</title>
<style>
  @page {{
    size: letter landscape;
    margin: 0.75in;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    color: #1a1a2e;
    font-size: 11pt;
    line-height: 1.4;
  }}
  .header {{
    text-align: center;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 2px solid #3b82f6;
  }}
  .org-name {{
    font-size: 10pt;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 4px;
  }}
  .header h1 {{
    font-size: 18pt;
    font-weight: 600;
    color: #1e3a5f;
    margin-bottom: 4px;
  }}
  .header .date-range {{
    font-size: 11pt;
    color: #4b5563;
  }}
  .summary {{
    display: flex;
    gap: 24px;
    margin-bottom: 20px;
    font-size: 10pt;
    color: #4b5563;
  }}
  .summary .stat {{
    background: #f0f4ff;
    padding: 8px 16px;
    border-radius: 6px;
  }}
  .summary .stat strong {{
    color: #1e3a5f;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 10pt;
  }}
  thead th {{
    background: #1e3a5f;
    color: white;
    padding: 8px 12px;
    text-align: left;
    font-weight: 500;
  }}
  thead th:first-child {{ border-radius: 6px 0 0 0; }}
  thead th:last-child {{ border-radius: 0 6px 0 0; }}
  tbody td {{
    padding: 6px 12px;
    border-bottom: 1px solid #e5e7eb;
    vertical-align: top;
  }}
  tr.date-header td {{
    background: #f8fafc;
    font-weight: 600;
    color: #1e3a5f;
    padding: 10px 12px 6px;
    font-size: 10.5pt;
    border-bottom: 2px solid #3b82f6;
  }}
  .time {{ white-space: nowrap; width: 150px; color: #374151; }}
  .title {{ font-weight: 500; }}
  .attendee {{ color: #4b5563; }}
  .location {{ color: #6b7280; font-size: 9pt; max-width: 200px; overflow: hidden; text-overflow: ellipsis; }}
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 8.5pt;
    font-weight: 500;
    text-transform: capitalize;
  }}
  .badge.booked, .badge.confirmed {{ background: #dcfce7; color: #166534; }}
  .badge.tentative {{ background: #fef9c3; color: #854d0e; }}
  .badge.cancelled {{ background: #fee2e2; color: #991b1b; }}
  .badge.completed {{ background: #e0e7ff; color: #3730a3; }}
  .badge.no_show {{ background: #fce7f3; color: #9d174d; }}
  .badge.rescheduled {{ background: #fff7ed; color: #9a3412; }}
  .empty {{ text-align: center; padding: 40px; color: #9ca3af; font-style: italic; }}
  .footer {{
    margin-top: 24px;
    padding-top: 12px;
    border-top: 1px solid #e5e7eb;
    font-size: 8.5pt;
    color: #9ca3af;
    text-align: center;
  }}
  @media print {{
    body {{ font-size: 10pt; }}
    .header {{ page-break-after: avoid; }}
    tr.date-header {{ page-break-after: avoid; }}
    tr {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>
<div class="header">
  {org_header}
  <h1>Schedule for {html_mod.escape(user_name)}</h1>
  <div class="date-range">{html_mod.escape(start_str)} &mdash; {html_mod.escape(end_str)}</div>
</div>

<div class="summary">
  <div class="stat"><strong>{len(appointments)}</strong> appointment{'s' if len(appointments) != 1 else ''}</div>
  <div class="stat"><strong>{len(sorted_dates)}</strong> day{'s' if len(sorted_dates) != 1 else ''} with meetings</div>
</div>

<table>
<thead>
  <tr>
    <th>Time</th>
    <th>Appointment</th>
    <th>Attendee</th>
    <th>Location</th>
    <th>Status</th>
  </tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>

<div class="footer">
  Generated by Perennia AI on {html_mod.escape(generated_at)}
</div>
</body>
</html>"""
