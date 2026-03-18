"""
No-Show Recovery Service

Manages the automated no-show recovery sequence with:
- Empathetic, graduated messaging across SMS and email channels
- Opt-out support at every step (link in emails, STOP in SMS)
- Chronic no-show detection (3+ in 90 days stops auto-recovery)
- Re-check of opt-out status and appointment state before each step

Recovery sequence:
    Step 1 (15 min after no-show):  Gentle SMS
    Step 2 (1 hour after):          Understanding email
    Step 3 (24 hours after):        Reschedule offer SMS
    Step 4 (72 hours after):        Final outreach email

Every message includes an opt-out mechanism:
    - SMS: "Reply STOP to opt out."
    - Email: Unsubscribe link with signed JWT token
"""

import html
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import jwt
from sqlalchemy import and_, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHRONIC_NO_SHOW_THRESHOLD = 3
CHRONIC_NO_SHOW_WINDOW_DAYS = 90

# Grace period after scheduled_end before marking as no-show (minutes)
NO_SHOW_GRACE_MINUTES = 15

# Stop processing recovery for appointments older than this (hours)
# Step 4 fires at 72h, so 96h gives a comfortable buffer
MAX_RECOVERY_WINDOW_HOURS = 96

# Batch size for queries to avoid excessive memory usage
RECOVERY_BATCH_SIZE = 200

_SECRET_KEY: Optional[str] = None


def _get_secret_key() -> str:
    """Lazily load SECRET_KEY from environment."""
    global _SECRET_KEY
    if _SECRET_KEY is None:
        _SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-not-for-production")
    return _SECRET_KEY


# ---------------------------------------------------------------------------
# Recovery step definitions
# ---------------------------------------------------------------------------

RECOVERY_STEPS: List[Dict] = [
    {
        "step": 1,
        "channel": "sms",
        "delay_minutes": 15,
        "template": "gentle_sms",
    },
    {
        "step": 2,
        "channel": "email",
        "delay_minutes": 60,
        "template": "understanding_email",
    },
    {
        "step": 3,
        "channel": "sms",
        "delay_minutes": 1440,  # 24 hours
        "template": "reschedule_offer",
    },
    {
        "step": 4,
        "channel": "email",
        "delay_minutes": 4320,  # 72 hours
        "template": "final_outreach",
    },
]


# ---------------------------------------------------------------------------
# Empathetic message templates
# ---------------------------------------------------------------------------

SMS_TEMPLATES = {
    "gentle_sms": (
        "Hi {name}, we noticed you weren't able to make your appointment today. "
        "No worries at all! Would you like to reschedule? {reschedule_link}\n"
        "Reply STOP to opt out of these messages."
    ),
    "reschedule_offer": (
        "Hi {name}, just a gentle reminder that we'd love to help whenever "
        "you're ready. Book at your convenience: {reschedule_link}\n"
        "Reply STOP to opt out."
    ),
}

EMAIL_TEMPLATES = {
    "understanding_email": {
        "subject": "We missed you today - would you like to reschedule?",
        "body": (
            "Hi {name},\n\n"
            "We understand things come up! We just wanted to reach out "
            "and let you know we're here whenever you're ready.\n\n"
            "If you'd like to reschedule at a time that works better: "
            "{reschedule_link}\n\n"
            "If now isn't the right time, no pressure at all. "
            "You can opt out of these messages: {opt_out_link}\n\n"
            "Wishing you well,\n{lo_name}"
        ),
    },
    "final_outreach": {
        "subject": "Your consultation is still available",
        "body": (
            "Hi {name},\n\n"
            "This is our last follow-up. We completely understand if the "
            "timing isn't right. Your consultation spot is always available "
            "if you'd like to connect in the future.\n\n"
            "Reschedule anytime: {reschedule_link}\n\n"
            "Best regards,\n{lo_name}\n\n"
            "Unsubscribe: {opt_out_link}"
        ),
    },
}


# ---------------------------------------------------------------------------
# Opt-out token helpers
# ---------------------------------------------------------------------------

def generate_opt_out_token(
    email: str,
    organization_id: int,
    appointment_id: Optional[int] = None,
) -> str:
    """Generate a signed JWT token for the opt-out link.

    Token is valid for 30 days (longer than the recovery sequence).
    """
    payload = {
        "email": email,
        "org_id": organization_id,
        "appt_id": appointment_id,
        "purpose": "recovery_opt_out",
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
    }
    return jwt.encode(payload, _get_secret_key(), algorithm="HS256")


def verify_opt_out_token(token: str) -> Optional[Dict]:
    """Verify and decode an opt-out JWT token.

    Returns the decoded payload dict or None if invalid/expired.
    """
    try:
        payload = jwt.decode(
            token,
            _get_secret_key(),
            algorithms=["HS256"],
        )
        if payload.get("purpose") != "recovery_opt_out":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Opt-out token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid opt-out token: {e}")
        return None


def build_opt_out_url(
    email: str,
    organization_id: int,
    appointment_id: Optional[int] = None,
    base_url: Optional[str] = None,
) -> str:
    """Build the full opt-out URL with a signed token."""
    if base_url is None:
        base_url = os.getenv(
            "API_BASE_URL", "https://api.perenniaai.com"
        )
    token = generate_opt_out_token(email, organization_id, appointment_id)
    return f"{base_url}/api/v1/scheduler/recovery/opt-out/{token}"


# ---------------------------------------------------------------------------
# NoShowRecoveryService
# ---------------------------------------------------------------------------

class NoShowRecoveryService:
    """Manages no-show detection and recovery with opt-out support."""

    def __init__(self):
        self._notification_service = None

    @property
    def notification_service(self):
        """Lazy import to avoid circular dependency."""
        if self._notification_service is None:
            from services.notification_service import notification_service
            self._notification_service = notification_service
        return self._notification_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_recovery(
        self,
        db: Session,
        appointment,
        reschedule_url: Optional[str] = None,
    ) -> Dict:
        """Start recovery sequence for a no-show appointment.

        Checks opt-out and chronic no-show status before scheduling
        the first step.

        Returns a dict describing what action was taken.
        """
        email = appointment.attendee_email
        org_id = appointment.organization_id

        if not email:
            logger.warning(
                f"No attendee email for appointment {appointment.id} -- "
                "skipping recovery"
            )
            return {"action": "skipped", "reason": "no_email"}

        # Check opt-out
        if self.is_opted_out(db, email, org_id):
            logger.info(
                f"Skipping recovery for opted-out attendee {email}"
            )
            return {"action": "skipped", "reason": "opted_out"}

        # Check chronic no-show
        if self.is_chronic_no_show(db, email, org_id):
            logger.info(
                f"Chronic no-show detected for {email} -- notifying LO instead"
            )
            await self._notify_lo_of_chronic_no_show(db, appointment)
            # Auto-opt-out chronic no-shows
            self.record_opt_out(
                db,
                email=email,
                organization_id=org_id,
                reason="Automatic opt-out: chronic no-show",
                source="chronic_no_show",
                appointment_id=appointment.id,
            )
            return {"action": "chronic_no_show", "reason": "flagged_and_lo_notified"}

        # Execute step 1 immediately (15 min delay is for the *messaging*
        # perspective, but start_recovery is typically called when the
        # no-show is detected which already provides a natural delay)
        result = await self.execute_step(
            db,
            appointment_id=appointment.id,
            step=1,
            reschedule_url=reschedule_url,
        )
        return {"action": "started", "first_step_result": result}

    async def execute_step(
        self,
        db: Session,
        appointment_id: int,
        step: int,
        reschedule_url: Optional[str] = None,
    ) -> Dict:
        """Execute a single recovery step.

        Re-checks opt-out status and appointment state to avoid
        sending messages to someone who has already rescheduled or
        opted out.

        Returns a dict describing the outcome.
        """
        from smart_scheduler_models import AppointmentStatus

        _models = self._get_models()
        Appointment = _models["Appointment"]

        appointment = db.query(Appointment).filter(
            Appointment.id == appointment_id
        ).first()

        if not appointment:
            return {"sent": False, "reason": "appointment_not_found"}

        # Re-check: has the appointment been rescheduled or completed?
        active_statuses = {
            AppointmentStatus.BOOKED,
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.COMPLETED,
            AppointmentStatus.RESCHEDULED,
        }
        if appointment.status in active_statuses:
            logger.info(
                f"Appointment {appointment_id} is now {appointment.status.value} "
                "-- stopping recovery sequence"
            )
            return {"sent": False, "reason": "already_resolved"}

        # Re-check opt-out
        email = appointment.attendee_email
        org_id = appointment.organization_id
        if self.is_opted_out(db, email, org_id):
            return {"sent": False, "reason": "opted_out"}

        if step < 1 or step > len(RECOVERY_STEPS):
            return {"sent": False, "reason": "invalid_step"}

        step_config = RECOVERY_STEPS[step - 1]

        # Build template context
        lo_name = self._get_lo_name(db, appointment)
        opt_out_link = build_opt_out_url(email, org_id, appointment_id)
        if not reschedule_url:
            reschedule_url = self._build_reschedule_url(appointment)

        context = {
            "name": appointment.attendee_name or "there",
            "reschedule_link": reschedule_url or "",
            "opt_out_link": opt_out_link,
            "lo_name": lo_name or "Your Loan Officer",
        }

        # Send via the appropriate channel
        if step_config["channel"] == "sms":
            result = await self._send_recovery_sms(
                appointment, step_config["template"], context
            )
        else:
            result = await self._send_recovery_email(
                appointment, step_config["template"], context
            )

        # Log the recovery step
        self._log_recovery_step(db, appointment, step, step_config, result)

        # Return info including next step details
        next_step = step + 1 if step < len(RECOVERY_STEPS) else None
        next_delay = (
            RECOVERY_STEPS[next_step - 1]["delay_minutes"]
            if next_step
            else None
        )

        return {
            "sent": result.get("success", False),
            "channel": step_config["channel"],
            "template": step_config["template"],
            "step": step,
            "next_step": next_step,
            "next_delay_minutes": next_delay,
            "error": result.get("error"),
        }

    # ------------------------------------------------------------------
    # Execution engine
    # ------------------------------------------------------------------

    async def check_and_mark_no_shows(
        self,
        db: Session,
        organization_id: Optional[int] = None,
    ) -> Dict:
        """Mark BOOKED appointments as NO_SHOW if past their end time + grace period.

        Queries appointments where:
        - status is BOOKED (or CONFIRMED/REMINDED -- the attendee was expected)
        - scheduled_end + grace period has passed
        - not already marked as no-show

        Starts recovery sequence for each newly-detected no-show.

        Returns:
            Dict with count of detected no-shows and their IDs.
        """
        from database.models.scheduler import (
            Appointment,
            AppointmentStatus,
            AppointmentStatusHistory,
        )

        now = datetime.now(timezone.utc)
        grace_cutoff = now - timedelta(minutes=NO_SHOW_GRACE_MINUTES)
        # Don't look back more than 24 hours to avoid processing very old appointments
        lookback = now - timedelta(hours=24)

        filters = [
            Appointment.status.in_([
                AppointmentStatus.BOOKED,
                AppointmentStatus.CONFIRMED,
                AppointmentStatus.REMINDED,
            ]),
            Appointment.scheduled_end < grace_cutoff,
            Appointment.scheduled_end > lookback,
        ]
        if organization_id is not None:
            filters.append(Appointment.organization_id == organization_id)

        appointments = (
            db.query(Appointment)
            .filter(and_(*filters))
            .limit(RECOVERY_BATCH_SIZE)
            .all()
        )

        if not appointments:
            return {"detected": 0, "appointment_ids": []}

        detected_ids = []
        recovery_results = []

        for appt in appointments:
            previous_status = appt.status.value if appt.status else None

            # Mark as NO_SHOW
            appt.status = AppointmentStatus.NO_SHOW
            appt.no_show_at = now
            appt.status_changed_at = now
            appt.updated_at = now

            # Record status history for audit trail
            try:
                history = AppointmentStatusHistory(
                    organization_id=appt.organization_id,
                    appointment_id=appt.id,
                    previous_status=previous_status,
                    new_status=AppointmentStatus.NO_SHOW.value,
                    change_source="system",
                    notes="Auto-detected: appointment end time + grace period elapsed with no check-in",
                    changed_at=now,
                )
                db.add(history)
            except Exception as e:
                logger.warning(f"Failed to record status history for appointment {appt.id}: {e}")

            detected_ids.append(appt.id)

            # Start recovery sequence for this appointment
            try:
                result = await self.start_recovery(db, appt)
                recovery_results.append({
                    "appointment_id": appt.id,
                    "recovery": result,
                })
            except Exception as e:
                logger.error(
                    f"Failed to start recovery for appointment {appt.id}: {e}",
                    exc_info=True,
                )
                recovery_results.append({
                    "appointment_id": appt.id,
                    "recovery": {"action": "error", "error": str(e)},
                })

        try:
            db.flush()
        except Exception as e:
            logger.error(f"Failed to flush no-show updates: {e}", exc_info=True)
            db.rollback()
            return {"detected": 0, "appointment_ids": [], "error": str(e)}

        logger.info(f"Detected and marked {len(detected_ids)} no-show appointments")
        return {
            "detected": len(detected_ids),
            "appointment_ids": detected_ids,
            "recovery_results": recovery_results,
        }

    async def execute_no_show_recovery(
        self,
        db: Session,
        organization_id: Optional[int] = None,
    ) -> Dict:
        """Find no-show appointments and execute the next due recovery step.

        For each NO_SHOW appointment within the recovery window:
        1. Determine which steps have already been completed (from internal_notes)
        2. Check if enough time has elapsed for the next step
        3. Execute the step if due

        This is designed to be called periodically (e.g., every 5-10 minutes)
        so that each step fires close to its configured delay time.

        Returns:
            Dict with counts of steps executed, skipped, and errors.
        """
        from database.models.scheduler import Appointment, AppointmentStatus

        now = datetime.now(timezone.utc)
        # Only process appointments within the recovery window
        window_start = now - timedelta(hours=MAX_RECOVERY_WINDOW_HOURS)

        filters = [
            Appointment.status == AppointmentStatus.NO_SHOW,
            Appointment.no_show_at.isnot(None),
            Appointment.no_show_at >= window_start,
        ]
        if organization_id is not None:
            filters.append(Appointment.organization_id == organization_id)

        appointments = (
            db.query(Appointment)
            .filter(and_(*filters))
            .limit(RECOVERY_BATCH_SIZE)
            .all()
        )

        if not appointments:
            return {"processed": 0, "steps_executed": 0, "skipped": 0, "errors": 0}

        stats = {
            "processed": 0,
            "steps_executed": 0,
            "skipped": 0,
            "errors": 0,
            "completed_sequences": 0,
            "details": [],
        }

        for appt in appointments:
            stats["processed"] += 1
            try:
                result = await self._process_appointment_recovery(db, appt, now)
                if result["action"] == "executed":
                    stats["steps_executed"] += 1
                elif result["action"] == "skipped":
                    stats["skipped"] += 1
                elif result["action"] == "sequence_complete":
                    stats["completed_sequences"] += 1
                    stats["skipped"] += 1
                elif result["action"] == "error":
                    stats["errors"] += 1
                stats["details"].append(result)
            except Exception as e:
                stats["errors"] += 1
                logger.error(
                    f"Recovery processing failed for appointment {appt.id}: {e}",
                    exc_info=True,
                )
                stats["details"].append({
                    "appointment_id": appt.id,
                    "action": "error",
                    "error": str(e),
                })

        try:
            db.flush()
        except Exception as e:
            logger.error(f"Failed to flush recovery updates: {e}", exc_info=True)

        logger.info(
            f"Recovery cycle: {stats['processed']} processed, "
            f"{stats['steps_executed']} steps executed, "
            f"{stats['skipped']} skipped, {stats['errors']} errors"
        )
        return stats

    async def _process_appointment_recovery(
        self,
        db: Session,
        appointment,
        now: datetime,
    ) -> Dict:
        """Process recovery for a single no-show appointment.

        Determines the next step to execute based on:
        - Which steps have already been completed (parsed from internal_notes)
        - How much time has elapsed since the appointment was marked no-show

        Returns a dict describing what action was taken.
        """
        appt_id = appointment.id
        no_show_at = appointment.no_show_at

        if no_show_at is None:
            return {
                "appointment_id": appt_id,
                "action": "skipped",
                "reason": "no_show_at_not_set",
            }

        # Make no_show_at timezone-aware if needed
        if no_show_at.tzinfo is None:
            no_show_at = no_show_at.replace(tzinfo=timezone.utc)

        # Determine which steps have already been completed
        last_completed = self._get_last_completed_step(appointment)

        if last_completed >= len(RECOVERY_STEPS):
            return {
                "appointment_id": appt_id,
                "action": "sequence_complete",
                "reason": "all_steps_executed",
            }

        # Determine the next step
        next_step_num = last_completed + 1
        next_step_config = RECOVERY_STEPS[next_step_num - 1]
        delay_minutes = next_step_config["delay_minutes"]

        # Check if enough time has elapsed for the next step
        elapsed_minutes = (now - no_show_at).total_seconds() / 60
        if elapsed_minutes < delay_minutes:
            return {
                "appointment_id": appt_id,
                "action": "skipped",
                "reason": "not_yet_due",
                "next_step": next_step_num,
                "minutes_remaining": round(delay_minutes - elapsed_minutes, 1),
            }

        # Pre-check opt-out before executing (avoid unnecessary work)
        email = appointment.attendee_email
        org_id = appointment.organization_id
        if not email:
            return {
                "appointment_id": appt_id,
                "action": "skipped",
                "reason": "no_email",
            }

        if self.is_opted_out(db, email, org_id):
            return {
                "appointment_id": appt_id,
                "action": "skipped",
                "reason": "opted_out",
            }

        # Execute the step (execute_step does its own re-checks)
        result = await self.execute_step(
            db,
            appointment_id=appt_id,
            step=next_step_num,
        )

        return {
            "appointment_id": appt_id,
            "action": "executed" if result.get("sent") else "error",
            "step": next_step_num,
            "channel": next_step_config["channel"],
            "result": result,
        }

    def _get_last_completed_step(self, appointment) -> int:
        """Parse internal_notes to determine the last completed recovery step.

        The _log_recovery_step method writes notes in the format:
            [Recovery Step N/4] SMS template=gentle_sms sent=YES at 2026-03-18 14:30 UTC

        We look for the highest step number with sent=YES.

        Returns:
            The highest completed step number (0 if none completed).
        """
        notes = appointment.internal_notes or ""
        if not notes:
            return 0

        # Pattern matches "[Recovery Step N/M] ... sent=YES ..."
        pattern = r"\[Recovery Step (\d+)/\d+\].*?sent=YES"
        matches = re.findall(pattern, notes)

        if not matches:
            return 0

        return max(int(m) for m in matches)

    # ------------------------------------------------------------------
    # Opt-out management
    # ------------------------------------------------------------------

    def is_opted_out(self, db: Session, email: str, organization_id: int) -> bool:
        """Check if an attendee has opted out of recovery messages."""
        from database.models.recovery_opt_out import RecoveryOptOut

        opt_out = db.query(RecoveryOptOut).filter(
            RecoveryOptOut.email == email,
            RecoveryOptOut.organization_id == organization_id,
        ).first()
        return opt_out is not None

    def record_opt_out(
        self,
        db: Session,
        email: str,
        organization_id: int,
        reason: Optional[str] = None,
        source: str = "link",
        phone: Optional[str] = None,
        appointment_id: Optional[int] = None,
    ) -> Dict:
        """Record an opt-out. Idempotent -- returns existing record if present."""
        from database.models.recovery_opt_out import RecoveryOptOut

        existing = db.query(RecoveryOptOut).filter(
            RecoveryOptOut.email == email,
            RecoveryOptOut.organization_id == organization_id,
        ).first()

        if existing:
            logger.info(f"Opt-out already recorded for {email} in org {organization_id}")
            return {"status": "already_opted_out", "id": existing.id}

        opt_out = RecoveryOptOut(
            email=email,
            phone=phone,
            organization_id=organization_id,
            reason=reason,
            opt_out_source=source,
            triggered_by_appointment_id=appointment_id,
        )
        db.add(opt_out)
        db.flush()

        logger.info(
            f"Recorded opt-out for {email} in org {organization_id} "
            f"(source={source})"
        )
        return {"status": "opted_out", "id": opt_out.id}

    def remove_opt_out(
        self,
        db: Session,
        email: str,
        organization_id: int,
    ) -> bool:
        """Remove an opt-out record (re-subscribe). Returns True if found."""
        from database.models.recovery_opt_out import RecoveryOptOut

        deleted = db.query(RecoveryOptOut).filter(
            RecoveryOptOut.email == email,
            RecoveryOptOut.organization_id == organization_id,
        ).delete()
        return deleted > 0

    # ------------------------------------------------------------------
    # Chronic no-show detection
    # ------------------------------------------------------------------

    def is_chronic_no_show(
        self,
        db: Session,
        email: str,
        organization_id: int,
    ) -> bool:
        """Check if an attendee has >= CHRONIC_NO_SHOW_THRESHOLD
        no-shows in the last CHRONIC_NO_SHOW_WINDOW_DAYS days.
        """
        from smart_scheduler_models import AppointmentStatus

        _models = self._get_models()
        Appointment = _models["Appointment"]

        cutoff = datetime.now(timezone.utc) - timedelta(
            days=CHRONIC_NO_SHOW_WINDOW_DAYS
        )

        no_show_count = db.query(Appointment).filter(
            Appointment.attendee_email == email,
            Appointment.organization_id == organization_id,
            Appointment.status == AppointmentStatus.NO_SHOW,
            Appointment.no_show_at >= cutoff,
        ).count()

        return no_show_count >= CHRONIC_NO_SHOW_THRESHOLD

    def get_no_show_count(
        self,
        db: Session,
        email: str,
        organization_id: int,
        days: int = 90,
    ) -> int:
        """Get the number of no-shows for an attendee within a time window."""
        from smart_scheduler_models import AppointmentStatus

        _models = self._get_models()
        Appointment = _models["Appointment"]

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        return db.query(Appointment).filter(
            Appointment.attendee_email == email,
            Appointment.organization_id == organization_id,
            Appointment.status == AppointmentStatus.NO_SHOW,
            Appointment.no_show_at >= cutoff,
        ).count()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_models(self) -> Dict:
        """Lazily load scheduler models."""
        from smart_scheduler_models import create_smart_scheduler_models
        from db import Base
        return create_smart_scheduler_models(Base)

    def _get_lo_name(self, db: Session, appointment) -> Optional[str]:
        """Get the assigned LO's display name."""
        if not appointment.assigned_user_id:
            return None
        try:
            from database.models.core import User
            user = db.query(User).filter(
                User.id == appointment.assigned_user_id
            ).first()
            if user:
                return f"{user.first_name or ''} {user.last_name or ''}".strip()
        except Exception as e:
            logger.warning(f"Could not load LO name: {e}")
        return None

    def _build_reschedule_url(self, appointment) -> str:
        """Build a reschedule URL from appointment context."""
        base_url = os.getenv("APP_BASE_URL", "https://app.perenniaai.com")
        return f"{base_url}/schedule?reschedule_from={appointment.id}"

    async def _send_recovery_sms(
        self,
        appointment,
        template_key: str,
        context: Dict,
    ) -> Dict:
        """Send a recovery SMS using the notification service."""
        phone = appointment.attendee_phone
        if not phone:
            return {"success": False, "error": "no_phone_number"}

        template = SMS_TEMPLATES.get(template_key)
        if not template:
            return {"success": False, "error": f"unknown_template: {template_key}"}

        message = template.format(**context)

        try:
            result = self.notification_service.send_sms(
                to_phone=phone,
                message=message,
            )
            return {
                "success": result.get("success", False),
                "error": result.get("error"),
            }
        except Exception as e:
            logger.error(f"Failed to send recovery SMS: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _send_recovery_email(
        self,
        appointment,
        template_key: str,
        context: Dict,
    ) -> Dict:
        """Send a recovery email using the notification service."""
        email = appointment.attendee_email
        if not email:
            return {"success": False, "error": "no_email"}

        template = EMAIL_TEMPLATES.get(template_key)
        if not template:
            return {"success": False, "error": f"unknown_template: {template_key}"}

        subject = template["subject"]
        body_text = template["body"].format(**context)

        # Build HTML version
        safe_name = html.escape(context.get("name", ""))
        safe_lo_name = html.escape(context.get("lo_name", ""))
        safe_reschedule = html.escape(context.get("reschedule_link", ""))
        safe_opt_out = html.escape(context.get("opt_out_link", ""))

        reschedule_button = ""
        if safe_reschedule:
            reschedule_button = f"""
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{safe_reschedule}"
                       style="display: inline-block;
                              background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
                              color: white; padding: 16px 36px;
                              text-decoration: none; border-radius: 8px;
                              font-weight: bold; font-size: 16px;">
                        Reschedule Now
                    </a>
                </div>
            """

        opt_out_footer = ""
        if safe_opt_out:
            opt_out_footer = f"""
                <p style="text-align: center; font-size: 12px; color: #9ca3af; margin-top: 30px;">
                    Don't want to receive these messages?
                    <a href="{safe_opt_out}" style="color: #6b7280; text-decoration: underline;">
                        Unsubscribe
                    </a>
                </p>
            """

        if template_key == "understanding_email":
            body_html = f"""
                <p style="font-size: 16px; color: #374151;">Hi {safe_name},</p>
                <p style="font-size: 16px; color: #374151;">
                    We understand things come up! We just wanted to reach out
                    and let you know we're here whenever you're ready.
                </p>
                <p style="font-size: 16px; color: #374151;">
                    If you'd like to reschedule at a time that works better,
                    it only takes a moment:
                </p>
                {reschedule_button}
                <p style="font-size: 14px; color: #6b7280; margin-top: 20px;">
                    If now isn't the right time, no pressure at all.
                    Just reply to this email if you have any questions.
                </p>
                <p style="font-size: 16px; color: #374151;">
                    Wishing you well,<br>{safe_lo_name}
                </p>
                {opt_out_footer}
            """
            heading = "We Missed You Today"
            header_color = "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)"
        else:
            # final_outreach
            body_html = f"""
                <p style="font-size: 16px; color: #374151;">Hi {safe_name},</p>
                <p style="font-size: 16px; color: #374151;">
                    This is our last follow-up. We completely understand if
                    the timing isn't right. Your consultation spot is always
                    available if you'd like to connect in the future.
                </p>
                {reschedule_button}
                <p style="font-size: 14px; color: #6b7280; margin-top: 20px;">
                    We're here whenever you need us. No rush at all.
                </p>
                <p style="font-size: 16px; color: #374151;">
                    Best regards,<br>{safe_lo_name}
                </p>
                {opt_out_footer}
            """
            heading = "Your Consultation Is Still Available"
            header_color = "linear-gradient(135deg, #6b7280 0%, #4b5563 100%)"

        try:
            from scheduler_email_service import _build_scheduler_email_html

            full_html = _build_scheduler_email_html(
                header_color=header_color,
                heading=heading,
                body_content=body_html,
                footer_text="Sent from Perennia AI",
            )
        except ImportError:
            # Fallback: wrap in basic HTML
            full_html = f"<html><body>{body_html}</body></html>"

        try:
            result = self.notification_service.send_email(
                to_email=email,
                subject=subject,
                html_content=full_html,
                plain_content=body_text,
            )
            return {
                "success": result.get("success", False),
                "error": result.get("error"),
            }
        except Exception as e:
            logger.error(f"Failed to send recovery email: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _notify_lo_of_chronic_no_show(
        self,
        db: Session,
        appointment,
    ) -> None:
        """Send a notification to the LO about a chronic no-show attendee."""
        lo_name = self._get_lo_name(db, appointment)
        attendee = appointment.attendee_name or appointment.attendee_email

        count = self.get_no_show_count(
            db, appointment.attendee_email, appointment.organization_id
        )

        if appointment.assigned_user_id:
            try:
                from database.models.core import User
                user = db.query(User).filter(
                    User.id == appointment.assigned_user_id
                ).first()
                if user and user.email:
                    subject = (
                        f"Chronic No-Show Alert: {attendee} "
                        f"({count} no-shows in {CHRONIC_NO_SHOW_WINDOW_DAYS} days)"
                    )
                    body = (
                        f"Hi {lo_name or 'there'},\n\n"
                        f"{attendee} has had {count} no-shows in the last "
                        f"{CHRONIC_NO_SHOW_WINDOW_DAYS} days.\n\n"
                        f"Automated recovery messages have been paused for "
                        f"this contact. You may want to reach out personally "
                        f"to understand their situation.\n\n"
                        f"Appointment: {appointment.title}\n"
                        f"Scheduled: {appointment.scheduled_start}\n\n"
                        f"-- Perennia AI"
                    )
                    self.notification_service.send_email(
                        to_email=user.email,
                        subject=subject,
                        html_content=f"<pre>{html.escape(body)}</pre>",
                        plain_content=body,
                    )
            except Exception as e:
                logger.error(
                    f"Failed to notify LO about chronic no-show: {e}",
                    exc_info=True,
                )

    def _log_recovery_step(
        self,
        db: Session,
        appointment,
        step: int,
        step_config: Dict,
        result: Dict,
    ) -> None:
        """Log a recovery step in the appointment's internal notes."""
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            note = (
                f"[Recovery Step {step}/{len(RECOVERY_STEPS)}] "
                f"{step_config['channel'].upper()} "
                f"template={step_config['template']} "
                f"sent={'YES' if result.get('success') else 'NO'} "
                f"at {timestamp}"
            )
            if result.get("error"):
                note += f" error={result['error']}"

            existing_notes = appointment.internal_notes or ""
            appointment.internal_notes = (
                f"{existing_notes}\n{note}" if existing_notes else note
            )
            db.flush()
        except Exception as e:
            logger.warning(f"Failed to log recovery step: {e}")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

no_show_recovery_service = NoShowRecoveryService()


# ---------------------------------------------------------------------------
# Module-level convenience functions for periodic task integration
# ---------------------------------------------------------------------------

async def check_and_mark_no_shows(
    db: Session,
    organization_id: Optional[int] = None,
) -> Dict:
    """Mark past-due BOOKED appointments as NO_SHOW and start recovery.

    Convenience wrapper around the service singleton. Suitable for calling
    from a background task scheduler.

    Args:
        db: Active database session.
        organization_id: Optional filter to process a single org.

    Returns:
        Dict with detection results (count, IDs, recovery outcomes).
    """
    return await no_show_recovery_service.check_and_mark_no_shows(db, organization_id)


async def execute_no_show_recovery(
    db: Session,
    organization_id: Optional[int] = None,
) -> Dict:
    """Execute pending recovery steps for existing no-show appointments.

    Convenience wrapper around the service singleton. Suitable for calling
    from a background task scheduler.

    Args:
        db: Active database session.
        organization_id: Optional filter to process a single org.

    Returns:
        Dict with execution stats (processed, steps executed, skipped, errors).
    """
    return await no_show_recovery_service.execute_no_show_recovery(db, organization_id)


async def run_no_show_recovery_cycle(
    db: Session,
    organization_id: Optional[int] = None,
) -> Dict:
    """Main entry point for periodic execution.

    Performs two phases:
    1. Detect new no-shows (BOOKED appointments past their end time) and
       mark them as NO_SHOW, triggering step 1 of the recovery sequence.
    2. Advance the recovery sequence for all existing no-show appointments,
       executing the next due step based on elapsed time.

    Designed to be called every 5-10 minutes by a periodic task. Each call
    is idempotent -- steps that have already been executed will not repeat,
    and steps that are not yet due will be skipped.

    Args:
        db: Active database session.
        organization_id: Optional filter to process a single org.

    Returns:
        Dict with combined results from both phases.
    """
    detection_result = {"detected": 0, "appointment_ids": []}
    recovery_result = {
        "processed": 0,
        "steps_executed": 0,
        "skipped": 0,
        "errors": 0,
    }

    # Phase 1: detect and mark new no-shows
    try:
        detection_result = await check_and_mark_no_shows(db, organization_id)
    except Exception as e:
        logger.error(f"No-show detection phase failed: {e}", exc_info=True)
        detection_result["error"] = str(e)

    # Phase 2: advance recovery for existing no-shows
    try:
        recovery_result = await execute_no_show_recovery(db, organization_id)
    except Exception as e:
        logger.error(f"Recovery execution phase failed: {e}", exc_info=True)
        recovery_result["error"] = str(e)

    return {
        "detection": detection_result,
        "recovery": recovery_result,
    }
