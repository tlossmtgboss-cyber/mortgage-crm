"""
Calendar Invite Utility

Generates ICS calendar files for appointment invitations.
"""

from datetime import datetime, timedelta
from typing import Optional
import uuid


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
    """
    Generate an ICS calendar file content for an appointment.

    Args:
        title: Event title
        start_time: Event start datetime
        end_time: Event end datetime
        description: Event description
        location: Event location (or video call link)
        organizer_email: Organizer's email
        organizer_name: Organizer's name
        attendee_email: Attendee's email
        attendee_name: Attendee's name
        meeting_link: Video meeting link (Teams, Zoom, etc.)

    Returns:
        ICS file content as string
    """
    # Generate unique ID for the event
    event_uid = f"{uuid.uuid4()}@perenniaai.com"

    # Format dates in ICS format (YYYYMMDDTHHMMSSZ for UTC)
    def format_datetime(dt: datetime) -> str:
        # Convert to UTC if timezone aware, otherwise assume local
        return dt.strftime("%Y%m%dT%H%M%S")

    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dtstart = format_datetime(start_time)
    dtend = format_datetime(end_time)

    # Build description with meeting link if provided
    full_description = description
    if meeting_link:
        full_description += f"\\n\\nJoin the meeting: {meeting_link}"
        if not location:
            location = meeting_link

    # Escape special characters for ICS
    def escape_ics(text: str) -> str:
        return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    # Build ICS content
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Perennia AI//Mortgage CRM//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{event_uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{escape_ics(title)}",
    ]

    if full_description:
        ics_lines.append(f"DESCRIPTION:{escape_ics(full_description)}")

    if location:
        ics_lines.append(f"LOCATION:{escape_ics(location)}")

    # Add organizer
    ics_lines.append(f"ORGANIZER;CN={escape_ics(organizer_name)}:mailto:{organizer_email}")

    # Add attendee if provided
    if attendee_email:
        attendee_cn = attendee_name or attendee_email.split("@")[0]
        ics_lines.append(f"ATTENDEE;CN={escape_ics(attendee_cn)};RSVP=TRUE;PARTSTAT=NEEDS-ACTION:mailto:{attendee_email}")

    # Add reminder (15 minutes before)
    ics_lines.extend([
        "BEGIN:VALARM",
        "TRIGGER:-PT15M",
        "ACTION:DISPLAY",
        "DESCRIPTION:Reminder: Your mortgage consultation starts in 15 minutes",
        "END:VALARM",
    ])

    ics_lines.extend([
        "END:VEVENT",
        "END:VCALENDAR",
    ])

    return "\r\n".join(ics_lines)


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
    """
    Generate ICS content for a mortgage appointment.

    Args:
        appointment_id: Unique appointment ID
        contact_name: Client's name
        contact_email: Client's email
        start_time: Appointment start time
        duration_minutes: Appointment duration
        appointment_type: Type of appointment
        meeting_link: Optional video meeting link
        loan_officer_name: Assigned loan officer's name
        loan_officer_email: Assigned loan officer's email

    Returns:
        ICS file content as string
    """
    end_time = start_time + timedelta(minutes=duration_minutes)

    # Build title based on appointment type
    type_titles = {
        "consultation": "Mortgage Consultation",
        "discovery": "Discovery Call",
        "pre_approval": "Pre-Approval Review",
        "document_review": "Document Review",
        "rate_lock": "Rate Lock Discussion",
        "closing_prep": "Closing Preparation",
    }
    title = type_titles.get(appointment_type, "Mortgage Consultation")

    # Include loan officer name in title if available
    if loan_officer_name:
        title = f"{title} with {loan_officer_name}"
    else:
        title = f"{title} with {contact_name}"

    # Build description
    lo_info = f"\nYour Loan Officer: {loan_officer_name}" if loan_officer_name else ""
    description = f"""Thank you for scheduling your mortgage consultation with Perennia AI!
{lo_info}
Appointment Details:
- Date: {start_time.strftime('%A, %B %d, %Y')}
- Time: {start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}
- Duration: {duration_minutes} minutes

What to Prepare:
- Recent pay stubs (last 30 days)
- Bank statements (last 2 months)
- Any questions you have about the mortgage process

If you need to reschedule, please reply to this email.

Reference: {appointment_id}"""

    return generate_ics_content(
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=description,
        organizer_email=loan_officer_email or "sarah@reply.perenniaai.com",
        organizer_name=loan_officer_name or "Sarah - Perennia AI",
        attendee_email=contact_email,
        attendee_name=contact_name,
        meeting_link=meeting_link,
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
    """
    Generate ICS content for a loan officer's calendar.

    Args:
        appointment_id: Unique appointment ID
        contact_name: Client's name
        contact_email: Client's email
        contact_phone: Client's phone number
        start_time: Appointment start time
        duration_minutes: Appointment duration
        appointment_type: Type of appointment
        meeting_link: Optional video meeting link
        loan_officer_name: Loan officer's name
        loan_officer_email: Loan officer's email
        notes: Additional notes about the appointment

    Returns:
        ICS file content as string
    """
    end_time = start_time + timedelta(minutes=duration_minutes)

    # Build title
    type_titles = {
        "consultation": "Mortgage Consultation",
        "discovery": "Discovery Call",
        "pre_approval": "Pre-Approval Review",
        "document_review": "Document Review",
        "rate_lock": "Rate Lock Discussion",
        "closing_prep": "Closing Preparation",
    }
    title = type_titles.get(appointment_type, "Mortgage Consultation")
    title = f"{title} - {contact_name}"

    # Build description for loan officer (includes contact details)
    phone_info = f"\n- Phone: {contact_phone}" if contact_phone else ""
    notes_info = f"\n\nNotes:\n{notes}" if notes else ""

    description = f"""New appointment scheduled via AI Assistant

Client Information:
- Name: {contact_name}
- Email: {contact_email}{phone_info}

Appointment Details:
- Date: {start_time.strftime('%A, %B %d, %Y')}
- Time: {start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}
- Duration: {duration_minutes} minutes
- Type: {appointment_type.replace('_', ' ').title()}
{notes_info}
Reference: {appointment_id}"""

    return generate_ics_content(
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=description,
        organizer_email="sarah@reply.perenniaai.com",
        organizer_name="Sarah - Perennia AI",
        attendee_email=loan_officer_email,
        attendee_name=loan_officer_name,
        meeting_link=meeting_link,
    )
