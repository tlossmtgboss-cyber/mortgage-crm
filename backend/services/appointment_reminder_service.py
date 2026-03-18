"""
Appointment Reminder Service
==============================
Sends automated reminders (email + SMS) before appointments.
Designed to be called by a periodic task (e.g., every 5 minutes).

Uses the existing ``AppointmentReminder`` model (``scheduler_reminders`` table)
to track which reminders have been scheduled and sent, avoiding duplicates.

Integrates with:
- ``scheduler_email_service.send_appointment_reminder_email`` for email delivery
- ``services.scheduler_sms_sender.send_appointment_reminder_sms`` for SMS delivery
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_

import logging

logger = logging.getLogger(__name__)

# Default reminder windows (minutes before appointment)
DEFAULT_REMINDER_WINDOWS = [
    {"minutes_before": 1440, "channel": "email", "template": "24h_reminder"},  # 24 hours
    {"minutes_before": 60, "channel": "sms", "template": "1h_reminder"},       # 1 hour
]


def _get_models():
    """Lazy-import models to avoid circular imports at module load time."""
    from database.models.scheduler import (
        Appointment,
        AppointmentReminder,
        AppointmentStatus,
        ReminderChannel,
        ReminderStatus,
    )
    return Appointment, AppointmentReminder, AppointmentStatus, ReminderChannel, ReminderStatus


async def send_due_reminders(
    db: Session,
    organization_id: Optional[int] = None,
    reminder_windows: Optional[List[dict]] = None,
) -> int:
    """
    Find appointments needing reminders and send them.

    Called by a periodic task every 5 minutes. For each configured reminder
    window, finds appointments whose start time falls within the window and
    that have not already had a reminder sent for that window.

    Uses the ``scheduler_reminders`` table (``AppointmentReminder`` model) to
    track sent reminders -- no separate ``appointment_reminders_sent`` table
    is needed.

    Args:
        db: SQLAlchemy session.
        organization_id: Optional org filter (None = all orgs).
        reminder_windows: Override default windows. Each dict must have
            ``minutes_before``, ``channel``, and ``template`` keys.

    Returns:
        Number of reminders successfully sent.
    """
    Appointment, AppointmentReminder, AppointmentStatus, ReminderChannel, ReminderStatus = _get_models()

    windows = reminder_windows or DEFAULT_REMINDER_WINDOWS
    now = datetime.now(timezone.utc)
    sent_count = 0

    # Only process appointments that are still active
    active_statuses = [
        AppointmentStatus.BOOKED,
        AppointmentStatus.CONFIRMED,
    ]

    for window in windows:
        minutes_before = window["minutes_before"]
        channel_str = window["channel"]
        template = window["template"]

        try:
            channel_enum = ReminderChannel(channel_str)
        except ValueError:
            logger.warning(f"Unknown reminder channel '{channel_str}', skipping")
            continue

        hours_before = minutes_before // 60

        # The ideal send time is ``minutes_before`` minutes before the
        # appointment start.  We use a +/- 5-minute tolerance so that the
        # periodic runner (every 5 min) never misses a window.
        window_start = now + timedelta(minutes=minutes_before - 5)
        window_end = now + timedelta(minutes=minutes_before + 5)

        # Query appointments in the window that do NOT yet have a matching
        # reminder row in scheduler_reminders.
        query = (
            db.query(Appointment)
            .filter(
                Appointment.scheduled_start.between(window_start, window_end),
                Appointment.status.in_(active_statuses),
            )
        )

        if organization_id is not None:
            query = query.filter(Appointment.organization_id == organization_id)

        appointments = query.all()

        for appt in appointments:
            # Check if a reminder for this window was already created
            existing = (
                db.query(AppointmentReminder)
                .filter(
                    AppointmentReminder.appointment_id == appt.id,
                    AppointmentReminder.channel == channel_enum,
                    AppointmentReminder.hours_before == hours_before,
                )
                .first()
            )

            if existing is not None:
                # Already scheduled or sent -- skip
                continue

            try:
                success = False

                if channel_str == "email" and appt.attendee_email:
                    success = await _send_email_reminder(appt, hours_before)
                elif channel_str == "sms" and appt.attendee_phone:
                    success = await _send_sms_reminder(appt, hours_before)
                else:
                    logger.debug(
                        f"No {channel_str} contact for appointment {appt.id}, skipping"
                    )
                    continue

                # Record the reminder in scheduler_reminders
                reminder = AppointmentReminder(
                    organization_id=appt.organization_id,
                    appointment_id=appt.id,
                    channel=channel_enum,
                    scheduled_for=now,
                    hours_before=hours_before,
                    message_template=template,
                    status=ReminderStatus.SENT if success else ReminderStatus.FAILED,
                    sent_at=now if success else None,
                    failed_at=None if success else now,
                    failure_reason=None if success else "Delivery function returned failure",
                )
                db.add(reminder)
                db.commit()

                if success:
                    sent_count += 1

            except Exception as e:
                logger.exception(
                    f"Failed to send {channel_str} reminder for appointment {appt.id}: {e}"
                )
                db.rollback()

    if sent_count > 0:
        logger.info(f"Sent {sent_count} appointment reminders")

    return sent_count


async def _send_email_reminder(appt, hours_before: int) -> bool:
    """
    Send an email reminder using the existing scheduler email service.

    Returns True on success.
    """
    import asyncio

    try:
        lo_name = None
        if appt.assigned_user:
            lo_name = f"{appt.assigned_user.first_name or ''} {appt.assigned_user.last_name or ''}".strip() or None

        lo_email = None
        if appt.assigned_user and hasattr(appt.assigned_user, "email"):
            lo_email = appt.assigned_user.email

        # Format date/time for the email
        appt_date_str = appt.scheduled_start.strftime("%A, %B %d, %Y")
        appt_time_str = appt.scheduled_start.strftime("%I:%M %p")

        meeting_mode = "Phone Call"
        if appt.meeting_mode:
            mode_val = appt.meeting_mode.value if hasattr(appt.meeting_mode, "value") else str(appt.meeting_mode)
            mode_display = {
                "video": "Video Call",
                "phone": "Phone Call",
                "in_person": "In Person",
                "screen_share": "Screen Share",
            }
            meeting_mode = mode_display.get(mode_val, mode_val.replace("_", " ").title())

        from scheduler_email_service import send_appointment_reminder_email

        result = await asyncio.to_thread(
            send_appointment_reminder_email,
            attendee_email=appt.attendee_email,
            attendee_name=appt.attendee_name or "there",
            appointment_title=appt.title,
            appointment_date=appt_date_str,
            appointment_time=appt_time_str,
            duration_minutes=appt.duration_minutes or 30,
            hours_before=hours_before,
            meeting_mode=meeting_mode,
            team_member_name=lo_name,
            team_member_email=lo_email,
            video_link=appt.video_link,
            scheduled_start=appt.scheduled_start,
        )

        success = result.get("success", False) if isinstance(result, dict) else bool(result)

        if success:
            logger.info(
                f"Email reminder sent to {appt.attendee_email} for appointment {appt.id} "
                f"({hours_before}h before)"
            )
        else:
            error = result.get("error", "unknown") if isinstance(result, dict) else "unknown"
            logger.warning(
                f"Email reminder failed for appointment {appt.id}: {error}"
            )

        return success

    except Exception as e:
        logger.exception(f"Email reminder exception for appointment {appt.id}: {e}")
        return False


async def _send_sms_reminder(appt, hours_before: int) -> bool:
    """
    Send an SMS reminder using the existing scheduler SMS sender.

    Returns True on success.
    """
    try:
        lo_name = None
        if appt.assigned_user:
            lo_name = f"{appt.assigned_user.first_name or ''} {appt.assigned_user.last_name or ''}".strip() or None

        appt_date_str = appt.scheduled_start.strftime("%m/%d/%Y")
        appt_time_str = appt.scheduled_start.strftime("%I:%M %p")

        from services.scheduler_sms_sender import send_appointment_reminder_sms

        result = send_appointment_reminder_sms(
            attendee_phone=appt.attendee_phone,
            attendee_name=appt.attendee_name or "there",
            appointment_date=appt_date_str,
            appointment_time=appt_time_str,
            hours_before=hours_before,
            team_member_name=lo_name,
            video_link=appt.video_link,
            organization_id=appt.organization_id,
        )

        success = result.get("success", False) if isinstance(result, dict) else bool(result)

        if success:
            logger.info(
                f"SMS reminder sent to {appt.attendee_phone} for appointment {appt.id} "
                f"({hours_before}h before)"
            )
        else:
            error = result.get("error", "unknown") if isinstance(result, dict) else "unknown"
            logger.warning(
                f"SMS reminder failed for appointment {appt.id}: {error}"
            )

        return success

    except Exception as e:
        logger.exception(f"SMS reminder exception for appointment {appt.id}: {e}")
        return False
