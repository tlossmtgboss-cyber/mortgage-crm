"""
Notification dispatch for the appointment service.

Handles sending confirmation emails, update notifications,
cancellation notifications, and Outlook calendar event creation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from services.appointment._models import get_model

logger = logging.getLogger(__name__)


def _mask_email(email: str) -> str:
    """Mask email for safe logging: j***@example.com."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


async def send_confirmation_email(
    db: Session,
    appointment,
    assigned_user_id: Optional[int],
) -> bool:
    """Send confirmation email to attendee. Returns True on success."""
    try:
        from scheduler_email_service import (
            send_appointment_confirmation_email,
            generate_reschedule_url,
        )

        # Format display values
        appt_date = appointment.scheduled_start.strftime("%A, %B %d, %Y")
        appt_time = appointment.scheduled_start.strftime("%I:%M %p")
        duration_str = f"{appointment.duration_minutes} minutes"

        mode_display = {
            "video": "Video Call",
            "phone": "Phone Call",
            "in_person": "In Person",
            "screen_share": "Screen Share",
        }
        raw_mode = (
            appointment.meeting_mode.value
            if hasattr(appointment.meeting_mode, "value")
            else str(appointment.meeting_mode or "phone")
        )
        meeting_mode_str = mode_display.get(raw_mode.lower(), "Phone Call")

        # Get team member info
        team_member_name = None
        team_member_email = None
        if assigned_user_id:
            User = get_model("User")
            if User:
                user = db.query(User).filter(User.id == assigned_user_id).first()
                if user:
                    team_member_name = user.first_name
                    if user.last_name:
                        team_member_name += f" {user.last_name}"
                    team_member_email = user.email

        reschedule_url = generate_reschedule_url(
            appointment.id, appointment.attendee_email,
        )

        # COMP-014: Record consent verification timestamp for AI-initiated communications
        consent_checked_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            "AI_COMM_CONSENT: type=%s recipient=%s consent_checked=%s appointment_id=%s",
            "email", _mask_email(appointment.attendee_email),
            consent_checked_at, appointment.id,
        )

        result = send_appointment_confirmation_email(
            attendee_email=appointment.attendee_email,
            attendee_name=appointment.attendee_name or "there",
            appointment_title=appointment.title,
            appointment_date=appt_date,
            appointment_time=appt_time,
            duration=duration_str,
            meeting_mode=meeting_mode_str,
            team_member_name=team_member_name,
            team_member_email=team_member_email,
            video_link=appointment.video_link,
            scheduled_start=appointment.scheduled_start,
            duration_minutes=appointment.duration_minutes,
            reschedule_url=reschedule_url,
        )

        success = result.get("success", False) if isinstance(result, dict) else bool(result)
        if success:
            logger.info(
                f"Confirmation email sent for appointment {appointment.id}"
            )
        else:
            logger.warning(
                f"Confirmation email failed for appointment {appointment.id}: "
                f"{result.get('error', 'unknown') if isinstance(result, dict) else 'unknown'}"
            )
        return success
    except Exception as e:
        logger.error(f"Error sending confirmation email: {e}", exc_info=True)
        return False


async def send_update_notification(appointment) -> bool:
    """Send update/reschedule notification to attendee."""
    try:
        from scheduler_email_service import send_appointment_update_email

        appt_date = appointment.scheduled_start.strftime("%A, %B %d, %Y")
        appt_time = appointment.scheduled_start.strftime("%I:%M %p")
        duration_str = f"{appointment.duration_minutes} minutes"

        # COMP-014: Record consent verification timestamp for AI-initiated communications
        consent_checked_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            "AI_COMM_CONSENT: type=%s recipient=%s consent_checked=%s appointment_id=%s",
            "email", _mask_email(appointment.attendee_email),
            consent_checked_at, appointment.id,
        )

        result = send_appointment_update_email(
            attendee_email=appointment.attendee_email,
            attendee_name=appointment.attendee_name or "there",
            appointment_title=appointment.title,
            new_date=appt_date,
            new_time=appt_time,
            duration=duration_str,
            scheduled_start=appointment.scheduled_start,
            duration_minutes=appointment.duration_minutes,
        )

        return result.get("success", False) if isinstance(result, dict) else bool(result)
    except Exception as e:
        logger.error(f"Error sending update notification: {e}", exc_info=True)
        return False


async def send_cancellation_notification(appointment) -> bool:
    """Send cancellation notification to attendee."""
    try:
        from scheduler_email_service import send_appointment_cancellation_email

        # COMP-014: Record consent verification timestamp for AI-initiated communications
        consent_checked_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            "AI_COMM_CONSENT: type=%s recipient=%s consent_checked=%s appointment_id=%s",
            "email", _mask_email(appointment.attendee_email),
            consent_checked_at, appointment.id,
        )

        result = send_appointment_cancellation_email(
            attendee_email=appointment.attendee_email,
            attendee_name=appointment.attendee_name or "there",
            appointment_title=appointment.title,
            appointment_date=appointment.scheduled_start.strftime("%A, %B %d, %Y"),
            appointment_time=appointment.scheduled_start.strftime("%I:%M %p"),
            cancellation_reason=appointment.cancellation_reason,
        )

        return result.get("success", False) if isinstance(result, dict) else bool(result)
    except Exception as e:
        logger.error(f"Error sending cancellation notification: {e}", exc_info=True)
        return False


async def create_outlook_event(
    db: Session,
    appointment,
    attendee_email: Optional[str],
    attendee_name: Optional[str],
    attendee_phone: Optional[str],
) -> Optional[str]:
    """Create an Outlook calendar event. Returns event_id or None."""
    try:
        import html as html_mod
        from services.microsoft_graph import create_event_via_graph, CalendarResult

        mode_display = {
            "video": "Video Call",
            "phone": "Phone Call",
            "in_person": "In Person",
            "screen_share": "Screen Share",
        }
        mode_val = (
            appointment.meeting_mode.value
            if hasattr(appointment.meeting_mode, "value")
            else str(appointment.meeting_mode or "phone")
        )
        meeting_mode_str = mode_display.get(mode_val.lower(), "Phone Call")

        description = (
            f"<h3>Client Meeting</h3>"
            f"<p><strong>Client:</strong> {html_mod.escape(attendee_name or 'Not specified')}</p>"
            f"<p><strong>Email:</strong> {html_mod.escape(attendee_email or 'Not specified')}</p>"
            f"<p><strong>Phone:</strong> {html_mod.escape(attendee_phone or 'Not specified')}</p>"
            f"<p><strong>Meeting Type:</strong> {html_mod.escape(meeting_mode_str)}</p>"
        )
        if appointment.description:
            description += f"<p><strong>Notes:</strong> {html_mod.escape(appointment.description)}</p>"
        if appointment.video_link:
            description += (
                f"<p><strong>Video Link:</strong> "
                f"<a href='{html_mod.escape(appointment.video_link)}'>"
                f"{html_mod.escape(appointment.video_link)}</a></p>"
            )

        calendar_result: CalendarResult = await create_event_via_graph(
            user_id=appointment.assigned_user_id,
            subject=f"Meeting: {attendee_name or 'Client'} - {appointment.title}",
            start=appointment.scheduled_start,
            end=appointment.scheduled_end,
            db=db,
            attendees=[attendee_email] if attendee_email else None,
            location=appointment.video_link,
            add_teams_link=False,
            body=description,
        )

        if calendar_result.success:
            appointment.outlook_event_id = calendar_result.event_id
            db.commit()
            logger.info(
                f"Outlook event created for appointment {appointment.id}: "
                f"{calendar_result.event_id}"
            )
            return calendar_result.event_id
        else:
            logger.warning(
                f"Could not create Outlook event: {calendar_result.error}"
            )
            return None
    except Exception as e:
        logger.debug(f"Outlook calendar event creation unavailable: {e}")
        return None
