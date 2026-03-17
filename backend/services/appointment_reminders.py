"""
Automated Appointment Reminder System

Sends reminders via email and SMS at configurable intervals before appointments.
Default schedule: 24 hours, 2 hours, 15 minutes before.

Features:
- Multi-channel: email + SMS
- Configurable per org (reminder intervals, channels, templates)
- Include reschedule/cancel links in reminders
- Pre-appointment prep info (documents to bring, meeting link, address)
- No-show detection and recovery (if appointment time passes with no check-in)
- Post-appointment follow-up (thank you + next steps)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from sqlalchemy import text, and_
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# =============================================================================
# REMINDER CONFIGURATION
# =============================================================================

# Default reminder intervals in minutes before appointment
DEFAULT_REMINDER_INTERVALS = [1440, 120, 15]  # 24h, 2h, 15min

# Human-readable labels for each interval
INTERVAL_LABELS = {
    1440: "24h",
    120: "2h",
    15: "15min",
    60: "1h",
    720: "12h",
    2880: "48h",
}

# No-show grace period: minutes after scheduled end before marking no-show
NO_SHOW_GRACE_MINUTES = 15

# Post-appointment follow-up delay in minutes
POST_APPOINTMENT_DELAY_MINUTES = 60


@dataclass
class ReminderConfig:
    """Configurable reminder settings per organization or appointment type."""

    # Intervals in minutes before appointment to send reminders
    intervals: List[int] = field(default_factory=lambda: list(DEFAULT_REMINDER_INTERVALS))

    # Channels to use for each interval
    # Maps interval_minutes -> list of channels
    channels: Dict[int, List[str]] = field(default_factory=lambda: {
        1440: ["email", "sms"],   # 24h: both
        120: ["email", "sms"],    # 2h: both
        15: ["sms"],              # 15min: SMS only (quick nudge)
    })

    # Whether to send no-show recovery messages
    no_show_enabled: bool = True

    # Whether to send post-appointment follow-up
    followup_enabled: bool = True

    # No-show grace period in minutes after scheduled end
    no_show_grace_minutes: int = NO_SHOW_GRACE_MINUTES

    # Post-appointment delay in minutes
    followup_delay_minutes: int = POST_APPOINTMENT_DELAY_MINUTES

    # Custom template overrides (interval -> template_key)
    custom_templates: Dict[int, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReminderConfig":
        """Create config from a dictionary (e.g., stored in DB JSON column)."""
        if not data:
            return cls()
        return cls(
            intervals=data.get("intervals", list(DEFAULT_REMINDER_INTERVALS)),
            channels=data.get("channels", cls.__dataclass_fields__["channels"].default_factory()),
            no_show_enabled=data.get("no_show_enabled", True),
            followup_enabled=data.get("followup_enabled", True),
            no_show_grace_minutes=data.get("no_show_grace_minutes", NO_SHOW_GRACE_MINUTES),
            followup_delay_minutes=data.get("followup_delay_minutes", POST_APPOINTMENT_DELAY_MINUTES),
            custom_templates=data.get("custom_templates", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "intervals": self.intervals,
            "channels": self.channels,
            "no_show_enabled": self.no_show_enabled,
            "followup_enabled": self.followup_enabled,
            "no_show_grace_minutes": self.no_show_grace_minutes,
            "followup_delay_minutes": self.followup_delay_minutes,
            "custom_templates": self.custom_templates,
        }


# =============================================================================
# HELPER: LAZY MODEL ACCESS
# =============================================================================

def _get_models():
    """Lazily import scheduler models to avoid circular imports."""
    try:
        from db import Base
        from smart_scheduler_models import (
            create_smart_scheduler_models,
            AppointmentStatus, ReminderChannel, ReminderStatus,
        )
        models = create_smart_scheduler_models(Base)
        return models, AppointmentStatus, ReminderChannel, ReminderStatus
    except Exception as e:
        logger.error(f"Failed to load scheduler models: {e}")
        return None, None, None, None


def _get_db_session():
    """Get a DB session using the shared engine."""
    from database import SessionLocal
    return SessionLocal()


# =============================================================================
# CORE REMINDER FUNCTIONS
# =============================================================================

async def schedule_reminders(appointment_id: int, db: Session) -> Dict[str, Any]:
    """
    Schedule reminders for an appointment when it is created or rescheduled.

    This creates AppointmentReminder rows in the scheduler_reminders table
    for each configured interval. The background task processor picks these up.

    Args:
        appointment_id: The appointment to schedule reminders for
        db: Active database session

    Returns:
        Dict with scheduled reminder count and details
    """
    models, AppointmentStatus, ReminderChannel, ReminderStatus = _get_models()
    if not models:
        return {"error": "Models not available", "scheduled": 0}

    Appointment = models["Appointment"]
    AppointmentReminder = models["AppointmentReminder"]

    try:
        appointment = db.query(Appointment).filter(
            Appointment.id == appointment_id
        ).first()

        if not appointment:
            return {"error": f"Appointment {appointment_id} not found", "scheduled": 0}

        if appointment.status not in (AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE):
            return {"error": f"Appointment status is {appointment.status}, not scheduling reminders", "scheduled": 0}

        # Load reminder config for the org (or use defaults)
        config = _get_org_reminder_config(db, appointment.organization_id)

        # Cancel any existing pending reminders for this appointment (in case of reschedule)
        db.query(AppointmentReminder).filter(
            AppointmentReminder.appointment_id == appointment_id,
            AppointmentReminder.status == ReminderStatus.PENDING,
        ).update({"status": ReminderStatus.FAILED, "failure_reason": "Rescheduled"})

        scheduled_count = 0
        now = datetime.now(timezone.utc)

        for interval_minutes in config.intervals:
            reminder_time = appointment.scheduled_start - timedelta(minutes=interval_minutes)

            # Skip reminders that would have already passed
            if reminder_time <= now:
                continue

            # Determine channels for this interval
            channels = config.channels.get(interval_minutes, ["email"])

            for channel_name in channels:
                try:
                    channel = ReminderChannel(channel_name.upper()) if channel_name.upper() in [c.value for c in ReminderChannel] else ReminderChannel.EMAIL
                except (ValueError, KeyError):
                    channel = ReminderChannel.EMAIL

                # Determine template key
                template_key = config.custom_templates.get(interval_minutes)
                if not template_key:
                    label = INTERVAL_LABELS.get(interval_minutes, f"{interval_minutes}min")
                    template_key = f"reminder_{label}"

                reminder = AppointmentReminder(
                    organization_id=appointment.organization_id,
                    appointment_id=appointment_id,
                    channel=channel,
                    scheduled_for=reminder_time,
                    hours_before=interval_minutes // 60 if interval_minutes >= 60 else 0,
                    message_template=template_key,
                    status=ReminderStatus.PENDING,
                )
                db.add(reminder)
                scheduled_count += 1

        db.commit()

        logger.info(
            f"Scheduled {scheduled_count} reminders for appointment {appointment_id} "
            f"(intervals: {config.intervals})"
        )

        return {
            "appointment_id": appointment_id,
            "scheduled": scheduled_count,
            "intervals": config.intervals,
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to schedule reminders for appointment {appointment_id}: {e}")
        return {"error": str(e), "scheduled": 0}


async def cancel_reminders(appointment_id: int, db: Session) -> Dict[str, Any]:
    """
    Cancel all pending reminders for an appointment.

    Called when an appointment is cancelled.

    Args:
        appointment_id: The appointment to cancel reminders for
        db: Active database session

    Returns:
        Dict with cancelled count
    """
    models, _, _, ReminderStatus = _get_models()
    if not models:
        return {"error": "Models not available", "cancelled": 0}

    AppointmentReminder = models["AppointmentReminder"]

    try:
        cancelled = db.query(AppointmentReminder).filter(
            AppointmentReminder.appointment_id == appointment_id,
            AppointmentReminder.status == ReminderStatus.PENDING,
        ).update({
            "status": ReminderStatus.FAILED,
            "failure_reason": "Appointment cancelled",
        })

        db.commit()

        logger.info(f"Cancelled {cancelled} pending reminders for appointment {appointment_id}")
        return {"appointment_id": appointment_id, "cancelled": cancelled}

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to cancel reminders for appointment {appointment_id}: {e}")
        return {"error": str(e), "cancelled": 0}


async def send_reminder(
    appointment_id: int,
    reminder_type: str,
    channel: str,
    db: Session,
) -> Dict[str, Any]:
    """
    Send an individual reminder for an appointment.

    Args:
        appointment_id: The appointment
        reminder_type: Type key (e.g., "reminder_24h", "reminder_2h", "reminder_15min")
        channel: "email" or "sms"
        db: Active database session

    Returns:
        Dict with send status
    """
    models, AppointmentStatus, _, _ = _get_models()
    if not models:
        return {"success": False, "error": "Models not available"}

    Appointment = models["Appointment"]

    try:
        # Fetch appointment with assigned user info
        result = db.execute(text("""
            SELECT
                sa.id, sa.title, sa.scheduled_start, sa.scheduled_end,
                sa.duration_minutes, sa.video_link, sa.location, sa.phone_number,
                sa.meeting_mode, sa.attendee_name, sa.attendee_email,
                sa.attendee_phone, sa.organization_id, sa.status,
                u.full_name as lo_name, u.email as lo_email
            FROM scheduler_appointments sa
            LEFT JOIN users u ON u.id = sa.assigned_user_id
            WHERE sa.id = :appt_id
        """), {"appt_id": appointment_id})

        appt = result.fetchone()
        if not appt:
            return {"success": False, "error": f"Appointment {appointment_id} not found"}

        appt_dict = dict(appt._mapping)

        # Skip if appointment is not active
        status_str = str(appt_dict.get("status", "")).upper()
        if status_str not in ("BOOKED", "TENTATIVE"):
            return {"success": False, "error": f"Appointment status is {status_str}"}

        scheduled_start = appt_dict["scheduled_start"]
        if not scheduled_start:
            return {"success": False, "error": "No scheduled_start on appointment"}

        # Format date/time
        appointment_date = scheduled_start.strftime("%B %d, %Y")
        appointment_time = scheduled_start.strftime("%I:%M %p")

        lo_name = appt_dict.get("lo_name") or "Your Loan Officer"
        attendee_name = appt_dict.get("attendee_name") or "there"
        meeting_mode = appt_dict.get("meeting_mode") or "Phone Call"

        # Generate reschedule URL
        reschedule_url = None
        if appt_dict.get("attendee_email"):
            try:
                from scheduler_email_service import generate_reschedule_url
                reschedule_url = generate_reschedule_url(
                    appointment_id=appointment_id,
                    attendee_email=appt_dict["attendee_email"],
                )
            except Exception as e:
                logger.warning(f"Failed to generate reschedule URL: {e}")

        # Determine prep info based on reminder type
        prep_info = _get_prep_info(reminder_type, appt_dict)

        if channel == "email" and appt_dict.get("attendee_email"):
            return _send_email_reminder(
                reminder_type=reminder_type,
                attendee_email=appt_dict["attendee_email"],
                attendee_name=attendee_name,
                appointment_title=appt_dict.get("title", "Appointment"),
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                duration_minutes=appt_dict.get("duration_minutes", 30),
                lo_name=lo_name,
                video_link=appt_dict.get("video_link"),
                location=appt_dict.get("location"),
                meeting_mode=meeting_mode,
                reschedule_url=reschedule_url,
                prep_info=prep_info,
                scheduled_start=scheduled_start,
                lo_email=appt_dict.get("lo_email"),
            )

        elif channel == "sms" and appt_dict.get("attendee_phone"):
            return _send_sms_reminder(
                reminder_type=reminder_type,
                attendee_phone=appt_dict["attendee_phone"],
                attendee_name=attendee_name,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                lo_name=lo_name,
                video_link=appt_dict.get("video_link"),
                reschedule_url=reschedule_url,
                organization_id=appt_dict.get("organization_id"),
            )

        return {"success": False, "error": f"No {channel} contact info for attendee"}

    except Exception as e:
        logger.error(f"Failed to send {channel} reminder for appointment {appointment_id}: {e}")
        return {"success": False, "error": str(e)}


async def check_no_shows(db: Session) -> Dict[str, Any]:
    """
    Detect appointments past their end time with no completion check-in.

    Queries appointments that:
    - Have status 'booked'
    - scheduled_end has passed (plus grace period)
    - Not already marked as no_show
    - no_show_detected is False or NULL

    Args:
        db: Active database session

    Returns:
        Dict with detected no-show count and appointment IDs
    """
    try:
        now = datetime.now(timezone.utc)
        grace_cutoff = now - timedelta(minutes=NO_SHOW_GRACE_MINUTES)

        # Find appointments past end time that are still "booked"
        result = db.execute(text("""
            SELECT sa.id, sa.attendee_name, sa.attendee_email, sa.attendee_phone,
                   sa.organization_id, sa.scheduled_start, sa.scheduled_end, sa.title,
                   u.full_name as lo_name
            FROM scheduler_appointments sa
            LEFT JOIN users u ON u.id = sa.assigned_user_id
            WHERE UPPER(sa.status::text) = 'BOOKED'
              AND sa.scheduled_end < :grace_cutoff
              AND sa.scheduled_end > :lookback
              AND (sa.no_show_detected IS NULL OR sa.no_show_detected = false)
            LIMIT 200
        """), {
            "grace_cutoff": grace_cutoff.replace(tzinfo=None),
            "lookback": (now - timedelta(hours=24)).replace(tzinfo=None),
        })

        no_show_appts = result.fetchall()

        if not no_show_appts:
            return {"detected": 0, "appointment_ids": []}

        detected_ids = []
        for appt in no_show_appts:
            appt_dict = dict(appt._mapping)
            appt_id = appt_dict["id"]

            # Update appointment status to NO_SHOW
            db.execute(text("""
                UPDATE scheduler_appointments
                SET status = 'no_show',
                    no_show_at = :now,
                    no_show_detected = true,
                    status_changed_at = :now,
                    updated_at = :now
                WHERE id = :appt_id
                  AND UPPER(status::text) = 'BOOKED'
            """), {"appt_id": appt_id, "now": now.replace(tzinfo=None)})

            detected_ids.append(appt_id)

            # Send no-show recovery message
            try:
                await send_no_show_recovery(appt_id, db, appt_data=appt_dict)
            except Exception as e:
                logger.error(f"Failed to send no-show recovery for appointment {appt_id}: {e}")

        db.commit()

        logger.info(f"Detected {len(detected_ids)} no-show appointments")
        return {"detected": len(detected_ids), "appointment_ids": detected_ids}

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"No-show detection failed: {e}")
        return {"error": str(e), "detected": 0}


async def send_no_show_recovery(
    appointment_id: int,
    db: Session,
    appt_data: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Send a "We missed you" recovery message with a reschedule link.

    Args:
        appointment_id: The no-show appointment
        db: Active database session
        appt_data: Optional pre-fetched appointment data to avoid extra query

    Returns:
        Dict with send status
    """
    try:
        if not appt_data:
            result = db.execute(text("""
                SELECT sa.id, sa.title, sa.attendee_name, sa.attendee_email,
                       sa.attendee_phone, sa.organization_id, sa.scheduled_start,
                       u.full_name as lo_name
                FROM scheduler_appointments sa
                LEFT JOIN users u ON u.id = sa.assigned_user_id
                WHERE sa.id = :appt_id
            """), {"appt_id": appointment_id})
            row = result.fetchone()
            if not row:
                return {"success": False, "error": f"Appointment {appointment_id} not found"}
            appt_data = dict(row._mapping)

        attendee_email = appt_data.get("attendee_email")
        attendee_phone = appt_data.get("attendee_phone")
        attendee_name = appt_data.get("attendee_name") or "there"
        lo_name = appt_data.get("lo_name") or "Your Loan Officer"
        org_id = appt_data.get("organization_id")

        # Generate reschedule link
        reschedule_url = None
        if attendee_email:
            try:
                from scheduler_email_service import generate_reschedule_url
                reschedule_url = generate_reschedule_url(
                    appointment_id=appointment_id,
                    attendee_email=attendee_email,
                )
            except Exception as e:
                logger.warning(f"Failed to generate reschedule URL for no-show recovery: {e}")

        results = {"email": None, "sms": None}

        # Send no-show recovery email
        if attendee_email:
            try:
                from scheduler_email_service import send_no_show_recovery_email
                email_result = send_no_show_recovery_email(
                    attendee_email=attendee_email,
                    attendee_name=attendee_name,
                    appointment_title=appt_data.get("title", "Your Appointment"),
                    lo_name=lo_name,
                    reschedule_url=reschedule_url,
                )
                results["email"] = email_result
            except Exception as e:
                logger.error(f"No-show recovery email failed for {appointment_id}: {e}")
                results["email"] = {"success": False, "error": str(e)}

        # Send no-show recovery SMS
        if attendee_phone:
            try:
                from scheduler_email_service import send_no_show_recovery_sms
                sms_result = send_no_show_recovery_sms(
                    attendee_phone=attendee_phone,
                    attendee_name=attendee_name,
                    lo_name=lo_name,
                    reschedule_url=reschedule_url,
                    organization_id=org_id,
                )
                results["sms"] = sms_result
            except Exception as e:
                logger.error(f"No-show recovery SMS failed for {appointment_id}: {e}")
                results["sms"] = {"success": False, "error": str(e)}

        # Mark no_show_detected on the appointment
        db.execute(text("""
            UPDATE scheduler_appointments
            SET no_show_detected = true, updated_at = :now
            WHERE id = :appt_id
        """), {"appt_id": appointment_id, "now": datetime.now(timezone.utc).replace(tzinfo=None)})

        return {
            "success": True,
            "appointment_id": appointment_id,
            "results": results,
        }

    except Exception as e:
        logger.error(f"No-show recovery failed for appointment {appointment_id}: {e}")
        return {"success": False, "error": str(e)}


async def send_post_appointment_followup(
    appointment_id: int,
    db: Session,
) -> Dict[str, Any]:
    """
    Send a post-appointment thank-you with next steps.

    Called after an appointment is marked as completed and the follow-up
    delay has elapsed.

    Args:
        appointment_id: The completed appointment
        db: Active database session

    Returns:
        Dict with send status
    """
    try:
        result = db.execute(text("""
            SELECT sa.id, sa.title, sa.attendee_name, sa.attendee_email,
                   sa.attendee_phone, sa.organization_id, sa.scheduled_start,
                   sa.meeting_type, sa.loan_id, sa.lead_id,
                   u.full_name as lo_name, u.email as lo_email
            FROM scheduler_appointments sa
            LEFT JOIN users u ON u.id = sa.assigned_user_id
            WHERE sa.id = :appt_id
        """), {"appt_id": appointment_id})

        row = result.fetchone()
        if not row:
            return {"success": False, "error": f"Appointment {appointment_id} not found"}

        appt_data = dict(row._mapping)

        attendee_email = appt_data.get("attendee_email")
        attendee_name = appt_data.get("attendee_name") or "there"
        lo_name = appt_data.get("lo_name") or "Your Loan Officer"
        lo_email = appt_data.get("lo_email")

        # Determine next steps based on meeting type
        next_steps = _get_next_steps(appt_data.get("meeting_type"))

        results = {"email": None, "sms": None}

        # Send follow-up email
        if attendee_email:
            try:
                from scheduler_email_service import send_post_appointment_email
                email_result = send_post_appointment_email(
                    attendee_email=attendee_email,
                    attendee_name=attendee_name,
                    appointment_title=appt_data.get("title", "Your Meeting"),
                    lo_name=lo_name,
                    lo_email=lo_email,
                    next_steps=next_steps,
                )
                results["email"] = email_result
            except Exception as e:
                logger.error(f"Post-appointment email failed for {appointment_id}: {e}")
                results["email"] = {"success": False, "error": str(e)}

        # Send follow-up SMS
        if appt_data.get("attendee_phone"):
            try:
                from scheduler_email_service import send_post_appointment_sms
                sms_result = send_post_appointment_sms(
                    attendee_phone=appt_data["attendee_phone"],
                    attendee_name=attendee_name,
                    lo_name=lo_name,
                    organization_id=appt_data.get("organization_id"),
                )
                results["sms"] = sms_result
            except Exception as e:
                logger.error(f"Post-appointment SMS failed for {appointment_id}: {e}")
                results["sms"] = {"success": False, "error": str(e)}

        # Mark followup_sent on the appointment
        db.execute(text("""
            UPDATE scheduler_appointments
            SET followup_sent = true, updated_at = :now
            WHERE id = :appt_id
        """), {"appt_id": appointment_id, "now": datetime.now(timezone.utc).replace(tzinfo=None)})

        db.commit()

        return {
            "success": True,
            "appointment_id": appointment_id,
            "results": results,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Post-appointment followup failed for {appointment_id}: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# BATCH PROCESSING (called by background tasks)
# =============================================================================

async def process_upcoming_reminders(db: Session) -> Dict[str, Any]:
    """
    Process all pending reminders whose scheduled_for time has arrived.

    This is the main entry point called by the background task every 5 minutes.
    It queries the scheduler_reminders table for PENDING reminders whose
    scheduled_for <= now, then sends each one.

    Args:
        db: Active database session

    Returns:
        Dict with sent/failed counts
    """
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Find pending reminders that are due
        result = db.execute(text("""
            SELECT sr.id as reminder_id, sr.appointment_id, sr.channel,
                   sr.hours_before, sr.message_template
            FROM scheduler_reminders sr
            WHERE UPPER(sr.status::text) = 'PENDING'
              AND sr.scheduled_for <= :now
              AND sr.scheduled_for > :lookback
            ORDER BY sr.scheduled_for ASC
            LIMIT 500
        """), {
            "now": now,
            "lookback": now - timedelta(hours=2),
        })

        pending_reminders = result.fetchall()

        sent_count = 0
        failed_count = 0

        for reminder_row in pending_reminders:
            reminder = dict(reminder_row._mapping)
            reminder_id = reminder["reminder_id"]
            appointment_id = reminder["appointment_id"]
            channel_str = str(reminder.get("channel", "EMAIL")).lower()
            reminder_type = reminder.get("message_template", "reminder_24h")

            try:
                send_result = await send_reminder(
                    appointment_id=appointment_id,
                    reminder_type=reminder_type,
                    channel=channel_str,
                    db=db,
                )

                if send_result.get("success"):
                    db.execute(text("""
                        UPDATE scheduler_reminders
                        SET status = 'SENT', sent_at = :now, updated_at = :now
                        WHERE id = :rid
                    """), {"rid": reminder_id, "now": now})
                    sent_count += 1
                else:
                    db.execute(text("""
                        UPDATE scheduler_reminders
                        SET status = 'FAILED', failed_at = :now,
                            failure_reason = :reason, updated_at = :now
                        WHERE id = :rid
                    """), {
                        "rid": reminder_id,
                        "now": now,
                        "reason": send_result.get("error", "Unknown error")[:500],
                    })
                    failed_count += 1

            except Exception as e:
                logger.error(f"Error processing reminder {reminder_id}: {e}")
                db.execute(text("""
                    UPDATE scheduler_reminders
                    SET status = 'FAILED', failed_at = :now,
                        failure_reason = :reason, updated_at = :now
                    WHERE id = :rid
                """), {
                    "rid": reminder_id,
                    "now": now,
                    "reason": str(e)[:500],
                })
                failed_count += 1

        db.commit()

        if sent_count > 0 or failed_count > 0:
            logger.info(f"Processed reminders: {sent_count} sent, {failed_count} failed")

        return {"sent": sent_count, "failed": failed_count}

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Reminder processing failed: {e}")
        return {"error": str(e), "sent": 0, "failed": 0}


async def detect_no_shows(db: Session) -> Dict[str, Any]:
    """
    Detect and handle no-show appointments.

    Called periodically by the background task. Delegates to check_no_shows.

    Args:
        db: Active database session

    Returns:
        Dict with detection results
    """
    return await check_no_shows(db)


async def process_post_appointment_followups(db: Session) -> Dict[str, Any]:
    """
    Find completed appointments that need follow-up emails.

    Queries for appointments where:
    - Status is 'completed'
    - completed_at is at least POST_APPOINTMENT_DELAY_MINUTES ago
    - followup_sent is False or NULL

    Args:
        db: Active database session

    Returns:
        Dict with sent count
    """
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=POST_APPOINTMENT_DELAY_MINUTES)

        result = db.execute(text("""
            SELECT id
            FROM scheduler_appointments
            WHERE UPPER(status::text) = 'COMPLETED'
              AND completed_at IS NOT NULL
              AND completed_at < :cutoff
              AND completed_at > :lookback
              AND (followup_sent IS NULL OR followup_sent = false)
            LIMIT 100
        """), {
            "cutoff": cutoff.replace(tzinfo=None),
            "lookback": (now - timedelta(hours=48)).replace(tzinfo=None),
        })

        appointments = result.fetchall()
        sent_count = 0

        for row in appointments:
            appt_id = row[0]
            try:
                followup_result = await send_post_appointment_followup(appt_id, db)
                if followup_result.get("success"):
                    sent_count += 1
            except Exception as e:
                logger.error(f"Post-appointment followup failed for {appt_id}: {e}")

        if sent_count > 0:
            logger.info(f"Sent {sent_count} post-appointment follow-ups")

        return {"sent": sent_count, "total_eligible": len(appointments)}

    except SQLAlchemyError as e:
        logger.error(f"Post-appointment followup processing failed: {e}")
        return {"error": str(e), "sent": 0}


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _get_org_reminder_config(db: Session, organization_id: int) -> ReminderConfig:
    """
    Load reminder configuration for an organization.

    Falls back to defaults if no custom config exists.
    """
    try:
        result = db.execute(text("""
            SELECT landing_page_settings
            FROM scheduler_configs
            WHERE organization_id = :org_id AND is_active = true
            ORDER BY user_id NULLS FIRST
            LIMIT 1
        """), {"org_id": organization_id})

        row = result.fetchone()
        if row and row[0]:
            settings = row[0] if isinstance(row[0], dict) else {}
            reminder_settings = settings.get("reminder_config")
            if reminder_settings:
                return ReminderConfig.from_dict(reminder_settings)
    except Exception as e:
        logger.debug(f"Could not load org reminder config: {e}")

    return ReminderConfig()


def _get_prep_info(reminder_type: str, appt_data: Dict) -> Optional[str]:
    """
    Generate preparation info based on reminder timing and meeting details.

    For 24h reminders: general preparation list
    For 2h reminders: specific documents/prep
    For 15min reminders: just the connection info
    """
    meeting_mode = str(appt_data.get("meeting_mode", "")).lower()

    if "24h" in reminder_type:
        items = ["Valid photo ID"]
        if meeting_mode in ("video", "screen_share"):
            items.append("Test your camera and microphone")
            items.append("Find a quiet, well-lit space")
        elif meeting_mode == "in_person":
            items.append("Arrive 5-10 minutes early")
        items.append("Recent pay stubs (if applicable)")
        items.append("Any questions you want to discuss")
        return " | ".join(items)

    elif "2h" in reminder_type:
        items = []
        if meeting_mode in ("video", "screen_share"):
            items.append("Make sure your device is charged")
            if appt_data.get("video_link"):
                items.append("Test the meeting link now to avoid issues")
        elif meeting_mode == "in_person" and appt_data.get("location"):
            items.append(f"Address: {appt_data['location']}")
        items.append("Have your questions ready")
        return " | ".join(items) if items else None

    elif "15min" in reminder_type:
        if appt_data.get("video_link"):
            return f"Join now: {appt_data['video_link']}"
        elif appt_data.get("location"):
            return f"Location: {appt_data['location']}"
        elif appt_data.get("phone_number"):
            return f"Call: {appt_data['phone_number']}"
        return None

    return None


def _get_next_steps(meeting_type: Optional[str]) -> List[str]:
    """Get next steps based on the meeting type."""
    meeting_type_str = str(meeting_type or "").lower()

    if "discovery" in meeting_type_str:
        return [
            "Review the loan options we discussed",
            "Gather your financial documents (pay stubs, W-2s, bank statements)",
            "Schedule a pre-approval review when ready",
        ]
    elif "pre_approval" in meeting_type_str:
        return [
            "Complete and submit your mortgage application",
            "Upload required documents to your secure portal",
            "Start shopping with confidence using your pre-approval letter",
        ]
    elif "application" in meeting_type_str:
        return [
            "Upload any remaining documents to your portal",
            "Watch for your initial loan estimate disclosure",
            "We will begin processing your application right away",
        ]
    elif "document" in meeting_type_str:
        return [
            "Upload any outstanding documents we discussed",
            "Review your loan estimate for accuracy",
            "Contact us if you have any questions",
        ]
    elif "rate_lock" in meeting_type_str:
        return [
            "Your rate lock confirmation will be sent shortly",
            "Review the lock terms and expiration date",
            "Keep us posted on any changes to your closing timeline",
        ]
    elif "closing" in meeting_type_str:
        return [
            "Review your Closing Disclosure carefully",
            "Arrange certified funds for closing costs",
            "Bring valid photo ID to closing",
        ]
    else:
        return [
            "Review any materials discussed during our meeting",
            "Reach out if you have any additional questions",
            "We look forward to helping you with your next steps",
        ]


def _send_email_reminder(
    reminder_type: str,
    attendee_email: str,
    attendee_name: str,
    appointment_title: str,
    appointment_date: str,
    appointment_time: str,
    duration_minutes: int,
    lo_name: str,
    video_link: Optional[str],
    location: Optional[str],
    meeting_mode: str,
    reschedule_url: Optional[str],
    prep_info: Optional[str],
    scheduled_start: Optional[datetime],
    lo_email: Optional[str],
) -> Dict[str, Any]:
    """Dispatch to the appropriate email template function."""
    try:
        if "no_show" in reminder_type:
            from scheduler_email_service import send_no_show_recovery_email
            return send_no_show_recovery_email(
                attendee_email=attendee_email,
                attendee_name=attendee_name,
                appointment_title=appointment_title,
                lo_name=lo_name,
                reschedule_url=reschedule_url,
            )
        elif "post_appointment" in reminder_type or "followup" in reminder_type:
            from scheduler_email_service import send_post_appointment_email
            return send_post_appointment_email(
                attendee_email=attendee_email,
                attendee_name=attendee_name,
                appointment_title=appointment_title,
                lo_name=lo_name,
                lo_email=lo_email,
                next_steps=_get_next_steps(None),
            )
        else:
            # Standard reminder (24h, 2h, 15min)
            from scheduler_email_service import send_appointment_reminder_email
            return send_appointment_reminder_email(
                attendee_email=attendee_email,
                attendee_name=attendee_name,
                appointment_title=appointment_title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                duration_minutes=duration_minutes,
                hours_before=_type_to_hours(reminder_type),
                meeting_mode=meeting_mode,
                team_member_name=lo_name,
                team_member_email=lo_email,
                video_link=video_link,
                scheduled_start=scheduled_start,
            )
    except Exception as e:
        logger.error(f"Email reminder dispatch failed: {e}")
        return {"success": False, "error": str(e)}


def _send_sms_reminder(
    reminder_type: str,
    attendee_phone: str,
    attendee_name: str,
    appointment_date: str,
    appointment_time: str,
    lo_name: str,
    video_link: Optional[str],
    reschedule_url: Optional[str],
    organization_id: Optional[int],
) -> Dict[str, Any]:
    """Dispatch to the appropriate SMS function."""
    try:
        if "no_show" in reminder_type:
            from scheduler_email_service import send_no_show_recovery_sms
            return send_no_show_recovery_sms(
                attendee_phone=attendee_phone,
                attendee_name=attendee_name,
                lo_name=lo_name,
                reschedule_url=reschedule_url,
                organization_id=organization_id,
            )
        elif "post_appointment" in reminder_type or "followup" in reminder_type:
            from scheduler_email_service import send_post_appointment_sms
            return send_post_appointment_sms(
                attendee_phone=attendee_phone,
                attendee_name=attendee_name,
                lo_name=lo_name,
                organization_id=organization_id,
            )
        else:
            from scheduler_email_service import send_appointment_reminder_sms
            return send_appointment_reminder_sms(
                attendee_phone=attendee_phone,
                attendee_name=attendee_name,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                hours_before=_type_to_hours(reminder_type),
                team_member_name=lo_name,
                video_link=video_link,
                organization_id=organization_id,
            )
    except Exception as e:
        logger.error(f"SMS reminder dispatch failed: {e}")
        return {"success": False, "error": str(e)}


def _type_to_hours(reminder_type: str) -> int:
    """Convert reminder type string to hours_before integer."""
    if "24h" in reminder_type or "1440" in reminder_type:
        return 24
    elif "2h" in reminder_type or "120" in reminder_type:
        return 2
    elif "15min" in reminder_type or "15" in reminder_type:
        return 0  # Less than 1 hour
    elif "1h" in reminder_type or "60" in reminder_type:
        return 1
    elif "12h" in reminder_type:
        return 12
    return 24  # Default
