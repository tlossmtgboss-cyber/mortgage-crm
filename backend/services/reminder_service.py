"""
Appointment Reminder Service

Manages the full lifecycle of appointment reminders:
  - Scheduling reminders when appointments are created
  - Querying for pending (due) reminders
  - Sending reminders via email / SMS with template rendering
  - Cancelling reminders when appointments are cancelled
  - Rescheduling reminders when appointments move
  - TCPA compliance: SMS consent check before sending
  - Rate limiting: max 3 reminders per appointment

Usage:
    from services.reminder_service import ReminderService

    service = ReminderService(db_session)
    service.schedule_reminders(appointment_id)
    pending = service.get_pending_reminders(batch_size=50)
    service.send_reminder(appointment_id, template_id)
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from routes.scheduler.constants import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)

# Maximum reminders that may be sent per appointment (across all templates)
MAX_REMINDERS_PER_APPOINTMENT = 3

# Frontend base URL for building cancel / reschedule links
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


class ReminderService:
    """
    Stateless service that operates on a caller-provided DB session.

    The caller is responsible for committing / rolling back the session.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Lazy model accessors (avoids import-time circular deps)
    # ------------------------------------------------------------------

    def _get_models(self):
        """Return dict of scheduler models created via factory."""
        from smart_scheduler_models import create_smart_scheduler_models
        from db import Base
        return create_smart_scheduler_models(Base)

    def _get_reminder_models(self):
        from database.models.reminder_config import ReminderTemplate, ReminderLog
        return ReminderTemplate, ReminderLog

    # ------------------------------------------------------------------
    # Template variable rendering
    # ------------------------------------------------------------------

    @staticmethod
    def render_template(template_text: str, variables: Dict[str, str]) -> str:
        """
        Replace ``{variable_name}`` placeholders in *template_text* with
        values from *variables*.  Unknown placeholders are left as-is so
        the output is safe even if a variable is missing.
        """
        if not template_text:
            return ""

        def _replacer(match):
            key = match.group(1)
            return variables.get(key, match.group(0))

        return re.sub(r"\{(\w+)\}", _replacer, template_text)

    def _build_variables(self, appointment, assigned_user=None) -> Dict[str, str]:
        """Build the standard variable dict for an appointment."""
        from smart_scheduler_models import MeetingType

        models = self._get_models()

        # Resolve appointment type name
        appt_type_name = "Appointment"
        if appointment.appointment_type_id:
            AppointmentType = models["AppointmentType"]
            appt_type = (
                self.db.query(AppointmentType)
                .filter(AppointmentType.id == appointment.appointment_type_id)
                .first()
            )
            if appt_type:
                appt_type_name = appt_type.type_name
        elif appointment.meeting_type:
            appt_type_name = appointment.meeting_type.value.replace("_", " ").title()

        # Resolve LO name
        lo_name = ""
        if assigned_user:
            lo_name = f"{getattr(assigned_user, 'first_name', '')} {getattr(assigned_user, 'last_name', '')}".strip()
        elif appointment.assigned_user_id:
            from database.models.core import User
            user = self.db.query(User).filter(User.id == appointment.assigned_user_id).first()
            if user:
                lo_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

        # Format date and time
        start = appointment.scheduled_start
        tz_name = appointment.timezone or DEFAULT_TIMEZONE
        try:
            import pytz
            tz = pytz.timezone(tz_name)
            local_start = start.astimezone(tz) if start.tzinfo else pytz.utc.localize(start).astimezone(tz)
        except Exception:
            local_start = start

        date_str = local_start.strftime("%B %d, %Y")  # e.g. "March 12, 2026"
        time_str = local_start.strftime("%I:%M %p").lstrip("0")  # e.g. "2:00 PM"

        # Location
        location = appointment.location or "Video Call"

        # URLs
        join_url = appointment.video_link or ""
        cancel_url = f"{FRONTEND_URL}/appointments/{appointment.id}/cancel"
        reschedule_url = f"{FRONTEND_URL}/appointments/{appointment.id}/reschedule"

        return {
            "client_name": appointment.attendee_name or "there",
            "appointment_type": appt_type_name,
            "date": date_str,
            "time": time_str,
            "lo_name": lo_name or "your loan officer",
            "location": location,
            "join_url": join_url,
            "cancel_url": cancel_url,
            "reschedule_url": reschedule_url,
        }

    # ------------------------------------------------------------------
    # Schedule / cancel / reschedule
    # ------------------------------------------------------------------

    def schedule_reminders(self, appointment_id: int) -> List[Dict[str, Any]]:
        """
        Create pending AppointmentReminder rows for all active templates
        that match this appointment's organization (and optionally type).

        Returns list of dicts describing created reminders.
        """
        models = self._get_models()
        Appointment = models["Appointment"]
        AppointmentReminder = models["AppointmentReminder"]
        ReminderTemplate, _ = self._get_reminder_models()

        appointment = (
            self.db.query(Appointment)
            .filter(Appointment.id == appointment_id)
            .first()
        )
        if not appointment:
            logger.warning(f"schedule_reminders: appointment {appointment_id} not found")
            return []

        # Fetch active templates for this org
        query = self.db.query(ReminderTemplate).filter(
            ReminderTemplate.organization_id == appointment.organization_id,
            ReminderTemplate.is_active == True,
        )

        # Filter by appointment type if template is type-specific
        templates = query.all()
        applicable = [
            t for t in templates
            if t.appointment_type_id is None
            or t.appointment_type_id == appointment.appointment_type_id
        ]

        created = []
        for tmpl in applicable:
            scheduled_for = appointment.scheduled_start - timedelta(minutes=tmpl.timing_minutes)

            # Don't create reminders in the past
            if scheduled_for <= datetime.now(timezone.utc):
                continue

            # Map channel string -> ReminderChannel enum(s)
            from smart_scheduler_models import ReminderChannel, ReminderStatus
            channels_to_create = []
            if tmpl.channel in ("email", "both"):
                channels_to_create.append(ReminderChannel.EMAIL)
            if tmpl.channel in ("sms", "both"):
                channels_to_create.append(ReminderChannel.SMS)

            for channel in channels_to_create:
                reminder = AppointmentReminder(
                    organization_id=appointment.organization_id,
                    appointment_id=appointment.id,
                    channel=channel,
                    scheduled_for=scheduled_for,
                    hours_before=tmpl.timing_minutes // 60,
                    message_template=str(tmpl.id),
                    status=ReminderStatus.PENDING,
                )
                self.db.add(reminder)
                created.append({
                    "template_id": tmpl.id,
                    "template_name": tmpl.name,
                    "channel": channel.value,
                    "scheduled_for": scheduled_for.isoformat(),
                })

        self.db.flush()
        return created

    def cancel_reminders(self, appointment_id: int) -> int:
        """
        Cancel all pending reminders for an appointment.

        Returns number of reminders cancelled.
        """
        models = self._get_models()
        AppointmentReminder = models["AppointmentReminder"]
        from smart_scheduler_models import ReminderStatus

        count = (
            self.db.query(AppointmentReminder)
            .filter(
                AppointmentReminder.appointment_id == appointment_id,
                AppointmentReminder.status == ReminderStatus.PENDING,
            )
            .update(
                {
                    AppointmentReminder.status: ReminderStatus.FAILED,
                    AppointmentReminder.failure_reason: "Appointment cancelled",
                    AppointmentReminder.failed_at: datetime.now(timezone.utc),
                },
                synchronize_session="fetch",
            )
        )
        self.db.flush()
        logger.info(f"Cancelled {count} pending reminders for appointment {appointment_id}")
        return count

    def reschedule_reminders(self, appointment_id: int) -> List[Dict[str, Any]]:
        """
        Cancel existing pending reminders and create new ones based on
        the updated appointment time.

        Returns list of newly created reminders.
        """
        self.cancel_reminders(appointment_id)
        return self.schedule_reminders(appointment_id)

    # ------------------------------------------------------------------
    # Query pending
    # ------------------------------------------------------------------

    def get_pending_reminders(self, batch_size: int = 50) -> list:
        """
        Find reminders whose ``scheduled_for`` is now or in the past and
        whose status is still PENDING.

        Limits to *batch_size* rows (oldest first) to keep each processing
        cycle bounded.

        Returns list of AppointmentReminder ORM instances.
        """
        models = self._get_models()
        AppointmentReminder = models["AppointmentReminder"]
        from smart_scheduler_models import ReminderStatus

        now = datetime.now(timezone.utc)

        return (
            self.db.query(AppointmentReminder)
            .filter(
                AppointmentReminder.status == ReminderStatus.PENDING,
                AppointmentReminder.scheduled_for <= now,
            )
            .order_by(AppointmentReminder.scheduled_for.asc())
            .limit(batch_size)
            .all()
        )

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def _check_rate_limit(self, appointment_id: int) -> bool:
        """Return True if appointment has NOT exceeded max reminders."""
        _, ReminderLog = self._get_reminder_models()
        sent_count = (
            self.db.query(func.count(ReminderLog.id))
            .filter(
                ReminderLog.appointment_id == appointment_id,
                ReminderLog.status == "sent",
            )
            .scalar()
        ) or 0
        return sent_count < MAX_REMINDERS_PER_APPOINTMENT

    def _check_sms_consent(self, phone: str, organization_id: int) -> bool:
        """
        TCPA compliance: verify the recipient has active SMS consent.

        Returns True if consent is found or if the TCPAConsent table is
        not available (graceful degradation for orgs that haven't set up
        TCPA tracking yet).
        """
        if not phone:
            return False

        try:
            from database.models.tcpa_consent import TCPAConsent

            consent = (
                self.db.query(TCPAConsent)
                .filter(
                    TCPAConsent.phone_number == phone,
                    TCPAConsent.organization_id == organization_id,
                    TCPAConsent.is_active == True,
                    TCPAConsent.consent_channel.in_(["sms", "both"]),
                )
                .first()
            )
            return consent is not None
        except Exception as e:
            # COMP-001: Fail-closed — block SMS when consent check fails
            logger.error("TCPA_CONSENT_CHECK_FAILURE: blocking SMS as fail-safe: %s", e, exc_info=True)
            return False

    def send_reminder(
        self,
        appointment_id: int,
        template_id: int,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Send a reminder for *appointment_id* using *template_id*.

        Steps:
            1. Load appointment and template
            2. Check rate limit (max 3 per appointment)
            3. For SMS: check TCPA consent
            4. Render template with appointment variables
            5. Dispatch via notification service
            6. Write ReminderLog row

        Args:
            appointment_id: Target appointment
            template_id: ReminderTemplate to use
            force: Skip rate-limit check (for test sends)

        Returns:
            Dict with ``success``, ``channel``, ``log_id`` keys.
        """
        models = self._get_models()
        Appointment = models["Appointment"]
        ReminderTemplate, ReminderLog = self._get_reminder_models()

        appointment = self.db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not appointment:
            return {"success": False, "error": "Appointment not found"}

        template = self.db.query(ReminderTemplate).filter(ReminderTemplate.id == template_id).first()
        if not template:
            return {"success": False, "error": "Template not found"}

        # Rate limit
        if not force and not self._check_rate_limit(appointment_id):
            log = ReminderLog(
                appointment_id=appointment_id,
                template_id=template_id,
                channel=template.channel if template.channel != "both" else "email",
                status="skipped",
                error_message=f"Rate limit exceeded (max {MAX_REMINDERS_PER_APPOINTMENT})",
            )
            self.db.add(log)
            self.db.flush()
            return {"success": False, "error": "Rate limit exceeded", "log_id": log.id}

        # Build variables
        variables = self._build_variables(appointment)

        results = []

        channels = []
        if template.channel in ("email", "both"):
            channels.append("email")
        if template.channel in ("sms", "both"):
            channels.append("sms")

        for channel in channels:
            result = self._send_single_channel(
                appointment=appointment,
                template=template,
                channel=channel,
                variables=variables,
            )
            results.append(result)

        # Return aggregate result
        any_success = any(r["success"] for r in results)
        return {
            "success": any_success,
            "channels": results,
        }

    def _send_single_channel(
        self,
        appointment,
        template,
        channel: str,
        variables: Dict[str, str],
    ) -> Dict[str, Any]:
        """Send via a single channel and log the result."""
        _, ReminderLog = self._get_reminder_models()

        rendered_body = self.render_template(template.body_template, variables)
        rendered_subject = self.render_template(template.subject_template or "", variables)

        recipient_email = appointment.attendee_email
        recipient_phone = appointment.attendee_phone

        log = ReminderLog(
            appointment_id=appointment.id,
            template_id=template.id,
            channel=channel,
            recipient_email=recipient_email if channel == "email" else None,
            recipient_phone=recipient_phone if channel == "sms" else None,
        )

        try:
            if channel == "email":
                result = self._send_email(recipient_email, rendered_subject, rendered_body)
            elif channel == "sms":
                # TCPA check
                if not self._check_sms_consent(recipient_phone, appointment.organization_id):
                    log.status = "skipped"
                    log.error_message = "No TCPA SMS consent on file"
                    self.db.add(log)
                    self.db.flush()
                    return {"success": False, "channel": channel, "error": "No SMS consent", "log_id": log.id}

                result = self._send_sms(recipient_phone, rendered_body)
            else:
                result = {"success": False, "error": f"Unknown channel: {channel}"}

            if result.get("success"):
                log.status = "sent"
                log.external_id = result.get("message_id") or result.get("message_sid")
            else:
                log.status = "failed"
                log.error_message = result.get("error", "Unknown send failure")

        except Exception as e:
            logger.exception(f"Reminder send failed for appointment {appointment.id}")
            log.status = "failed"
            log.error_message = str(e)[:500]
            result = {"success": False, "error": str(e)}

        self.db.add(log)
        self.db.flush()

        return {
            "success": log.status == "sent",
            "channel": channel,
            "log_id": log.id,
            "external_id": log.external_id,
        }

    # ------------------------------------------------------------------
    # Transport helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _send_email(to_email: str, subject: str, body: str) -> Dict[str, Any]:
        """Send email via the shared notification service."""
        if not to_email:
            return {"success": False, "error": "No recipient email"}

        from services.notification_service import notification_service

        # Convert plain text body to simple HTML
        html_body = body.replace("\n", "<br>")
        html_content = (
            f'<!DOCTYPE html><html><body style="font-family: -apple-system, '
            f"BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; "
            f'color: #333;">{html_body}</body></html>'
        )

        result = notification_service.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            plain_content=body,
        )
        return result

    @staticmethod
    def _send_sms(to_phone: str, body: str) -> Dict[str, Any]:
        """Send SMS via the shared notification service."""
        if not to_phone:
            return {"success": False, "error": "No recipient phone"}

        from services.notification_service import notification_service

        result = notification_service.send_sms(
            to_phone=to_phone,
            message=body,
        )
        return result

    # ------------------------------------------------------------------
    # Batch processing (called by background task)
    # ------------------------------------------------------------------

    def process_pending_batch(self, batch_size: int = 50) -> Dict[str, Any]:
        """
        Process a batch of due reminders.

        For each pending reminder:
            1. Look up the template via message_template field
            2. Call send_reminder
            3. Update the AppointmentReminder status

        Returns summary dict.
        """
        models = self._get_models()
        AppointmentReminder = models["AppointmentReminder"]
        from smart_scheduler_models import ReminderStatus

        pending = self.get_pending_reminders(batch_size=batch_size)

        sent = 0
        failed = 0
        skipped = 0

        for reminder in pending:
            try:
                template_id = None
                if reminder.message_template:
                    try:
                        template_id = int(reminder.message_template)
                    except (ValueError, TypeError):
                        pass

                if template_id is None:
                    # No linked template -- mark as failed
                    reminder.status = ReminderStatus.FAILED
                    reminder.failure_reason = "No template linked"
                    reminder.failed_at = datetime.now(timezone.utc)
                    failed += 1
                    continue

                result = self.send_reminder(
                    appointment_id=reminder.appointment_id,
                    template_id=template_id,
                )

                if result.get("success"):
                    reminder.status = ReminderStatus.SENT
                    reminder.sent_at = datetime.now(timezone.utc)
                    sent += 1
                else:
                    error = result.get("error", "Unknown")
                    if "Rate limit" in str(error):
                        reminder.status = ReminderStatus.FAILED
                        reminder.failure_reason = "Rate limit exceeded"
                        reminder.failed_at = datetime.now(timezone.utc)
                        skipped += 1
                    elif "consent" in str(error).lower():
                        reminder.status = ReminderStatus.FAILED
                        reminder.failure_reason = error
                        reminder.failed_at = datetime.now(timezone.utc)
                        skipped += 1
                    else:
                        reminder.status = ReminderStatus.FAILED
                        reminder.failure_reason = error
                        reminder.failed_at = datetime.now(timezone.utc)
                        failed += 1

            except Exception as e:
                logger.exception(f"Error processing reminder {reminder.id}")
                reminder.status = ReminderStatus.FAILED
                reminder.failure_reason = str(e)[:500]
                reminder.failed_at = datetime.now(timezone.utc)
                failed += 1

        self.db.flush()

        summary = {
            "processed": len(pending),
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
        }
        logger.info(f"Reminder batch complete: {summary}")
        return summary
