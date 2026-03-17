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
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import jwt
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHRONIC_NO_SHOW_THRESHOLD = 3
CHRONIC_NO_SHOW_WINDOW_DAYS = 90

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
