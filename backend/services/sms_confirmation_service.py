"""
SMS Appointment Confirmation & Reminder Service

Sends appointment lifecycle SMS notifications via Telnyx:
- Booking confirmation (on APPOINTMENT_CREATED)
- Appointment reminder (24h and 1h before)
- Cancellation notification (on APPOINTMENT_CANCELLED)
- Reschedule notification (on APPOINTMENT_RESCHEDULED)

Integrates with:
- services.sms_compliance.check_sms_consent for TCPA/DNC compliance
- AppointmentReminder model for tracking sent reminders
- Telnyx SDK for message delivery

Uses the existing Telnyx credentials:
- TELNYX_API_KEY (env)
- TELNYX_PHONE_NUMBER (env, required)
- TELNYX_MESSAGING_PROFILE_ID (env, required)
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SMSConfirmationService:
    """Send appointment SMS notifications via Telnyx.

    Centralizes all scheduler-related SMS into a single service that
    handles consent checks, message formatting, delivery tracking,
    and reminder scheduling via the AppointmentReminder model.
    """

    def __init__(self):
        self.api_key = os.getenv("TELNYX_API_KEY")
        self.from_number = os.getenv("TELNYX_PHONE_NUMBER", "")
        self.messaging_profile_id = os.getenv(
            "TELNYX_MESSAGING_PROFILE_ID", ""
        )
        if not self.api_key:
            logger.warning("TELNYX_API_KEY not configured, SMS will use HTTP fallback")

    # =========================================================================
    # Public API: appointment lifecycle notifications
    # =========================================================================

    async def send_booking_confirmation(
        self,
        appointment,
        org_name: str = "",
        organization_id: int = None,
    ) -> Dict[str, Any]:
        """Send SMS confirmation when an appointment is booked.

        Args:
            appointment: Appointment model instance (needs attendee_phone,
                         attendee_name, scheduled_start, title).
            org_name: Organization display name for the message.
            organization_id: For TCPA/DNC consent scoping.

        Returns:
            dict with keys: sent (bool), message_id (str|None), error (str|None)
        """
        if not getattr(appointment, "attendee_phone", None):
            return {"sent": False, "message_id": None, "error": "No attendee phone"}

        attendee_name = getattr(appointment, "attendee_name", "") or "there"
        start = appointment.scheduled_start

        org_text = f" with {org_name}" if org_name else ""
        message = (
            f"Hi {attendee_name}! Your appointment{org_text} is confirmed.\n"
            f"Date: {start.strftime('%B %d, %Y')}\n"
            f"Time: {start.strftime('%I:%M %p')}\n"
            f"Reply CONFIRM to confirm or CANCEL to cancel."
        )

        return await self._send(
            to_number=appointment.attendee_phone,
            message=message,
            organization_id=organization_id,
        )

    async def send_reminder(
        self,
        appointment,
        hours_before: int = 24,
        org_name: str = "",
        organization_id: int = None,
    ) -> Dict[str, Any]:
        """Send SMS reminder before an appointment.

        Args:
            appointment: Appointment model instance.
            hours_before: How many hours before the appointment this is.
            org_name: Organization display name.
            organization_id: For TCPA/DNC consent scoping.

        Returns:
            dict with keys: sent (bool), message_id (str|None), error (str|None)
        """
        if not getattr(appointment, "attendee_phone", None):
            return {"sent": False, "message_id": None, "error": "No attendee phone"}

        attendee_name = getattr(appointment, "attendee_name", "") or "there"
        start = appointment.scheduled_start

        if hours_before >= 20:
            time_text = "tomorrow"
        elif hours_before >= 2:
            time_text = f"in {hours_before} hours"
        else:
            time_text = "soon"

        org_text = f" with {org_name}" if org_name else ""
        video_link_text = ""
        if getattr(appointment, "video_link", None):
            video_link_text = f"\nJoin: {appointment.video_link}"

        message = (
            f"Reminder: Your appointment{org_text} is {time_text}.\n"
            f"Date: {start.strftime('%B %d at %I:%M %p')}{video_link_text}\n"
            f"Reply CONFIRM to confirm or CANCEL to cancel."
        )

        return await self._send(
            to_number=appointment.attendee_phone,
            message=message,
            organization_id=organization_id,
        )

    async def send_cancellation(
        self,
        appointment,
        org_name: str = "",
        cancellation_reason: str = None,
        organization_id: int = None,
    ) -> Dict[str, Any]:
        """Notify attendee of appointment cancellation.

        Args:
            appointment: Appointment model instance.
            org_name: Organization display name.
            cancellation_reason: Optional reason for cancellation.
            organization_id: For TCPA/DNC consent scoping.

        Returns:
            dict with keys: sent (bool), message_id (str|None), error (str|None)
        """
        if not getattr(appointment, "attendee_phone", None):
            return {"sent": False, "message_id": None, "error": "No attendee phone"}

        attendee_name = getattr(appointment, "attendee_name", "") or "there"
        start = appointment.scheduled_start

        org_text = f" with {org_name}" if org_name else ""
        reason_text = f"\nReason: {cancellation_reason}" if cancellation_reason else ""

        message = (
            f"Hi {attendee_name}, your appointment{org_text} on "
            f"{start.strftime('%B %d at %I:%M %p')} has been cancelled.{reason_text}\n"
            f"Please contact us to reschedule."
        )

        return await self._send(
            to_number=appointment.attendee_phone,
            message=message,
            organization_id=organization_id,
        )

    async def send_reschedule(
        self,
        appointment,
        old_time: datetime,
        org_name: str = "",
        organization_id: int = None,
    ) -> Dict[str, Any]:
        """Notify attendee of appointment reschedule.

        Args:
            appointment: Appointment model instance with NEW scheduled_start.
            old_time: The previous scheduled_start time.
            org_name: Organization display name.
            organization_id: For TCPA/DNC consent scoping.

        Returns:
            dict with keys: sent (bool), message_id (str|None), error (str|None)
        """
        if not getattr(appointment, "attendee_phone", None):
            return {"sent": False, "message_id": None, "error": "No attendee phone"}

        attendee_name = getattr(appointment, "attendee_name", "") or "there"
        new_start = appointment.scheduled_start

        org_text = f" with {org_name}" if org_name else ""

        message = (
            f"Hi {attendee_name}, your appointment{org_text} has been rescheduled.\n"
            f"Old: {old_time.strftime('%B %d at %I:%M %p')}\n"
            f"New: {new_start.strftime('%B %d, %Y at %I:%M %p')}\n"
            f"Reply CONFIRM to confirm or CANCEL to cancel."
        )

        return await self._send(
            to_number=appointment.attendee_phone,
            message=message,
            organization_id=organization_id,
        )

    # =========================================================================
    # Reminder scheduling: create AppointmentReminder records
    # =========================================================================

    def schedule_reminders(
        self,
        db,
        appointment,
        reminder_hours: list = None,
        organization_id: int = None,
    ) -> list:
        """Create AppointmentReminder records for an appointment.

        Schedules SMS reminders at the specified hours before the appointment.
        Does NOT commit; caller owns the transaction.

        Args:
            db: SQLAlchemy session.
            appointment: Appointment model instance.
            reminder_hours: List of hours before appointment to send reminders.
                           Defaults to [24, 1].
            organization_id: For the reminder record.

        Returns:
            List of created AppointmentReminder records.
        """
        if reminder_hours is None:
            reminder_hours = [24, 1]

        if not getattr(appointment, "attendee_phone", None):
            logger.debug(f"No attendee phone for appointment {appointment.id}, skipping SMS reminders")
            return []

        created = []

        try:
            from smart_scheduler_models import ReminderChannel, ReminderStatus
        except ImportError:
            logger.warning("Cannot import ReminderChannel/ReminderStatus, skipping reminder scheduling")
            return []

        # Get the AppointmentReminder model from the appointment's reminders relationship
        # The model is created via factory, so we need to get it from the db metadata
        AppointmentReminder = type(appointment).reminders.property.mapper.class_

        for hours in reminder_hours:
            scheduled_for = appointment.scheduled_start - timedelta(hours=hours)

            # Skip if the reminder time is in the past
            if scheduled_for <= datetime.now(timezone.utc):
                logger.debug(
                    f"Skipping {hours}h reminder for appointment {appointment.id}: "
                    f"scheduled_for {scheduled_for} is in the past"
                )
                continue

            # Check for existing reminder at this interval
            existing = (
                db.query(AppointmentReminder)
                .filter(
                    AppointmentReminder.appointment_id == appointment.id,
                    AppointmentReminder.channel == ReminderChannel.SMS,
                    AppointmentReminder.hours_before == hours,
                )
                .first()
            )
            if existing:
                logger.debug(
                    f"SMS reminder already exists for appointment {appointment.id} "
                    f"at {hours}h before"
                )
                continue

            org_id = organization_id or getattr(appointment, "organization_id", None)

            reminder = AppointmentReminder(
                organization_id=org_id,
                appointment_id=appointment.id,
                channel=ReminderChannel.SMS,
                scheduled_for=scheduled_for,
                hours_before=hours,
                message_template=f"appointment_reminder_{hours}h",
                status=ReminderStatus.PENDING,
            )
            db.add(reminder)
            created.append(reminder)
            logger.info(
                f"Scheduled SMS reminder for appointment {appointment.id}: "
                f"{hours}h before ({scheduled_for.isoformat()})"
            )

        return created

    # =========================================================================
    # Reminder processing: send pending reminders that are due
    # =========================================================================

    async def process_pending_reminders(
        self,
        db,
        models: dict,
        org_name: str = "",
    ) -> Dict[str, int]:
        """Process all pending SMS reminders that are due.

        Should be called periodically (e.g., every 5-10 minutes) by a
        background task or cron job.

        Args:
            db: SQLAlchemy session.
            models: Dict of model classes (must include 'AppointmentReminder', 'Appointment').
            org_name: Organization display name.

        Returns:
            dict with keys: processed (int), sent (int), failed (int), skipped (int)
        """
        try:
            from smart_scheduler_models import (
                ReminderChannel,
                ReminderStatus,
                AppointmentStatus,
            )
        except ImportError:
            logger.warning("Cannot import scheduler enums for reminder processing")
            return {"processed": 0, "sent": 0, "failed": 0, "skipped": 0}

        AppointmentReminder = models.get("AppointmentReminder")
        Appointment = models.get("Appointment")

        if not AppointmentReminder or not Appointment:
            logger.warning("AppointmentReminder or Appointment model not available")
            return {"processed": 0, "sent": 0, "failed": 0, "skipped": 0}

        now = datetime.now(timezone.utc)
        stats = {"processed": 0, "sent": 0, "failed": 0, "skipped": 0}

        # Get all pending SMS reminders that are due
        pending = (
            db.query(AppointmentReminder)
            .filter(
                AppointmentReminder.channel == ReminderChannel.SMS,
                AppointmentReminder.status == ReminderStatus.PENDING,
                AppointmentReminder.scheduled_for <= now,
            )
            .all()
        )

        for reminder in pending:
            stats["processed"] += 1

            # Load the appointment
            appointment = (
                db.query(Appointment)
                .filter(Appointment.id == reminder.appointment_id)
                .first()
            )

            if not appointment:
                reminder.status = ReminderStatus.FAILED
                reminder.failed_at = now
                reminder.failure_reason = "Appointment not found"
                stats["failed"] += 1
                continue

            # Skip if appointment is cancelled or completed
            if appointment.status in (
                AppointmentStatus.CANCELLED,
                AppointmentStatus.COMPLETED,
                AppointmentStatus.NO_SHOW,
            ):
                reminder.status = ReminderStatus.FAILED
                reminder.failed_at = now
                reminder.failure_reason = f"Appointment status: {appointment.status.value}"
                stats["skipped"] += 1
                continue

            # Send the reminder
            result = await self.send_reminder(
                appointment=appointment,
                hours_before=reminder.hours_before or 24,
                org_name=org_name,
                organization_id=reminder.organization_id,
            )

            if result.get("sent"):
                reminder.status = ReminderStatus.SENT
                reminder.sent_at = now
                reminder.external_message_id = result.get("message_id")
                stats["sent"] += 1
            else:
                reminder.status = ReminderStatus.FAILED
                reminder.failed_at = now
                reminder.failure_reason = result.get("error", "Unknown error")
                stats["failed"] += 1

        try:
            db.commit()
        except Exception as e:
            logger.error(f"Failed to commit reminder updates: {e}")
            db.rollback()

        logger.info(
            f"Reminder processing complete: {stats['processed']} processed, "
            f"{stats['sent']} sent, {stats['failed']} failed, {stats['skipped']} skipped"
        )
        return stats

    # =========================================================================
    # Internal: send SMS with consent check
    # =========================================================================

    async def _send(
        self,
        to_number: str,
        message: str,
        organization_id: int = None,
    ) -> Dict[str, Any]:
        """Send an SMS message via Telnyx with TCPA/DNC consent check.

        Args:
            to_number: Recipient phone number (E.164 or 10-digit).
            message: SMS body text.
            organization_id: For consent check scoping.

        Returns:
            dict with keys: sent (bool), message_id (str|None), error (str|None)
        """
        if not self.api_key:
            logger.warning("TELNYX_API_KEY not set, skipping SMS")
            return {"sent": False, "message_id": None, "error": "SMS not configured"}

        if not to_number:
            return {"sent": False, "message_id": None, "error": "No phone number"}

        # Normalize to E.164
        clean_number = to_number.strip()
        if not clean_number.startswith("+"):
            digits = "".join(c for c in clean_number if c.isdigit())
            if len(digits) == 10:
                clean_number = f"+1{digits}"
            elif len(digits) == 11 and digits.startswith("1"):
                clean_number = f"+{digits}"
            else:
                clean_number = f"+{digits}"

        # TCPA/DNC consent check using existing scheduler_email_service infrastructure
        try:
            from services.sms_compliance import check_sms_consent

            can_send, reason = check_sms_consent(clean_number, organization_id=organization_id)
            if not can_send:
                logger.info(f"SMS blocked by consent check for {clean_number}: {reason}")
                return {"sent": False, "message_id": None, "error": f"Consent blocked: {reason}"}
        except ImportError:
            logger.debug("check_sms_consent not available, proceeding with send")
        except Exception as e:
            # Fail-closed: block if consent check errors (TCPA compliance)
            logger.error(f"SMS consent check error, blocking send: {e}")
            return {"sent": False, "message_id": None, "error": f"Consent check error: {e}"}

        # Send via Telnyx SDK
        try:
            from telephony.sms import send_sms as telnyx_send_sms

            result = telnyx_send_sms(
                to=clean_number,
                from_=self.from_number,
                text=message,
                messaging_profile_id=self.messaging_profile_id or None,
                api_key=self.api_key,
            )

            msg_id = result.get("id", "unknown")
            logger.info(f"SMS sent to {clean_number}, message_id: {msg_id}")

            try:
                from db import SessionLocal
                _panel_db = SessionLocal()
                try:
                    from integrations.sms_delivery_tracker import record_message_sent
                    record_message_sent(
                        _panel_db, str(msg_id), clean_number, self.from_number,
                        message, organization_id=organization_id,
                    )
                    _panel_db.commit()
                except Exception:
                    _panel_db.rollback()
                finally:
                    _panel_db.close()
            except Exception as _rec_err:
                logger.debug("SMS delivery/panel record skipped: %s", _rec_err)

            return {"sent": True, "message_id": str(msg_id), "error": None}

        except ImportError:
            # Fallback to HTTP API if telnyx SDK not installed
            return await self._send_via_http(clean_number, message)
        except Exception as e:
            logger.error(f"SMS send failed to {clean_number}: {e}")
            return {"sent": False, "message_id": None, "error": str(e)}

    async def _send_via_http(
        self, to_number: str, message: str
    ) -> Dict[str, Any]:
        """Fallback: send SMS via the centralized async chokepoint.

        Bypasses compliance because the caller (_send_sms_to_number)
        already ran the TCPA consent check.
        """
        try:
            from telephony.sms import send_sms_verified_async

            result = await send_sms_verified_async(
                to=to_number,
                from_=self.from_number,
                text=message,
                messaging_profile_id=self.messaging_profile_id or None,
                api_key=self.api_key,
                bypass_compliance=True,  # Already checked by caller
            )

            if result.get("status") == "sent":
                msg_id = result.get("id", "unknown")
                logger.info(f"SMS sent via chokepoint to {to_number}, message_id: {msg_id}")
                return {"sent": True, "message_id": str(msg_id), "error": None}
            else:
                reason = result.get("reason", "unknown")
                logger.error(f"SMS send failed: {reason}")
                return {"sent": False, "message_id": None, "error": reason}

        except Exception as e:
            logger.error(f"SMS send error to {to_number}: {e}")
            return {"sent": False, "message_id": None, "error": str(e)}


# ===========================================================================
# Module-level singleton
# ===========================================================================

_sms_confirmation_service: Optional[SMSConfirmationService] = None


def get_sms_confirmation_service() -> SMSConfirmationService:
    """Get or create the global SMSConfirmationService instance."""
    global _sms_confirmation_service
    if _sms_confirmation_service is None:
        _sms_confirmation_service = SMSConfirmationService()
    return _sms_confirmation_service
