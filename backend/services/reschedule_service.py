"""
Reschedule Service — appointment rescheduling logic.

Provides:
- RescheduleService: stateless service class that receives a DB session
  and scheduler models dict, then performs reschedule operations.

Flow (LO-initiated):
  1. initiate_reschedule(appointment_id, requested_by) -> creates history record
  2. get_available_slots(appointment_id, target_date, ...) -> available slots
  3. confirm_reschedule(appointment_id, new_start, new_end) -> moves appointment

Flow (Borrower self-service):
  1. generate_reschedule_link(appointment_id) -> URL with JWT token
  2. Borrower hits GET /reschedule/{token}/slots -> available slots
  3. Borrower hits POST /reschedule/{token}/confirm -> moves appointment
"""

from datetime import datetime, timedelta, date, time, timezone
from typing import Optional, List, Dict, Any
import logging
import os
import secrets

logger = logging.getLogger(__name__)

MAX_RESCHEDULES_PER_APPOINTMENT = 3
RESCHEDULE_TOKEN_TTL_HOURS = 72  # borrower link valid for 3 days
SLOTS_LOOKAHEAD_DAYS = 14  # how far ahead to offer slots


class RescheduleService:
    """
    Stateless service: instantiate with a DB session and models dict per request.

    Usage:
        svc = RescheduleService(db, models)
        result = svc.initiate_reschedule(appointment_id, "lo", reason="Client request")
    """

    def __init__(self, db, models: dict):
        self.db = db
        self.models = models
        self.Appointment = models["Appointment"]
        # Lazy import to avoid circular dependency at module level
        from database.models.reschedule_history import RescheduleHistory
        self.RescheduleHistory = RescheduleHistory

    # ------------------------------------------------------------------
    # 1. Initiate
    # ------------------------------------------------------------------

    def initiate_reschedule(
        self,
        appointment_id: int,
        requested_by_type: str = "lo",
        reason: Optional[str] = None,
        org_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create a reschedule request record.

        Returns dict with reschedule_history id, current reschedule_count,
        and whether the limit has been reached.

        Raises ValueError if appointment not found or limit exceeded.
        """
        appt = self._get_appointment(appointment_id, org_id)

        # Enforce max reschedules
        count = self._reschedule_count(appointment_id)
        if count >= MAX_RESCHEDULES_PER_APPOINTMENT:
            raise ValueError(
                f"Appointment has already been rescheduled {count} times "
                f"(maximum {MAX_RESCHEDULES_PER_APPOINTMENT}). "
                "Please cancel and create a new appointment."
            )

        history = self.RescheduleHistory(
            appointment_id=appointment_id,
            organization_id=appt.organization_id,
            original_start=appt.scheduled_start,
            original_end=appt.scheduled_end,
            reason=reason,
            requested_by_type=requested_by_type,
        )
        self.db.add(history)
        self.db.flush()

        return {
            "reschedule_history_id": history.id,
            "appointment_id": appointment_id,
            "reschedule_count": count + 1,
            "max_reschedules": MAX_RESCHEDULES_PER_APPOINTMENT,
            "original_start": appt.scheduled_start.isoformat(),
            "original_end": appt.scheduled_end.isoformat(),
        }

    # ------------------------------------------------------------------
    # 2. Available slots
    # ------------------------------------------------------------------

    def get_available_slots(
        self,
        appointment_id: int,
        target_date: Optional[date] = None,
        days: int = SLOTS_LOOKAHEAD_DAYS,
        org_id: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        Return available slots for the same LO / duration as the original
        appointment, starting from target_date (default: tomorrow).
        """
        appt = self._get_appointment(appointment_id, org_id)

        start_date = target_date or (datetime.now(timezone.utc).date() + timedelta(days=1))
        end_date = start_date + timedelta(days=days)

        # Use the shared slot engine from _helpers
        from routes.scheduler._helpers import _generate_available_slots
        slots = _generate_available_slots(
            db=self.db,
            user_ids=[appt.assigned_user_id],
            start_date=start_date,
            end_date=end_date,
            duration_minutes=appt.duration_minutes,
            org_id=appt.organization_id,
            check_cross_source=True,
            include_user_id=False,
            time_key_format="start",
            exclude_appointment_id=appointment_id,
        )
        return slots

    # ------------------------------------------------------------------
    # 3. Confirm reschedule
    # ------------------------------------------------------------------

    def confirm_reschedule(
        self,
        appointment_id: int,
        new_start: datetime,
        new_end: datetime,
        org_id: Optional[int] = None,
        confirmed_by: str = "lo",
    ) -> Dict[str, Any]:
        """
        Move the appointment to the new time.

        Steps:
          1. Validate no conflicts at the new time
          2. Update the appointment record
          3. Update the latest reschedule_history with new_start/new_end
          4. Record status history
          5. Send confirmation email (best-effort)

        Returns summary dict.  Raises ValueError on validation failures.
        """
        appt = self._get_appointment(appointment_id, org_id)

        # Enforce max reschedules
        count = self._reschedule_count(appointment_id)
        if count > MAX_RESCHEDULES_PER_APPOINTMENT:
            raise ValueError("Reschedule limit exceeded")

        # Cannot reschedule cancelled / completed appointments
        from smart_scheduler_models import AppointmentStatus
        terminal_statuses = {
            AppointmentStatus.CANCELLED,
            AppointmentStatus.COMPLETED,
            AppointmentStatus.NO_SHOW,
        }
        if appt.status in terminal_statuses:
            raise ValueError(f"Cannot reschedule an appointment with status '{appt.status.value}'")

        # Conflict check (SELECT FOR UPDATE)
        from routes.scheduler._helpers import _check_appointment_conflict
        _check_appointment_conflict(
            self.db,
            appt.assigned_user_id,
            new_start,
            new_end,
            org_id=appt.organization_id,
            exclude_appointment_id=appointment_id,
        )

        old_start = appt.scheduled_start
        old_end = appt.scheduled_end

        # Move the appointment
        appt.scheduled_start = new_start
        appt.scheduled_end = new_end
        appt.status = AppointmentStatus.RESCHEDULED
        appt.status_changed_at = datetime.now(timezone.utc)
        appt.reschedule_count = (appt.reschedule_count or 0) + 1
        appt.updated_at = datetime.now(timezone.utc)

        # Update reschedule history (find the most recent pending one)
        latest_hist = (
            self.db.query(self.RescheduleHistory)
            .filter(
                self.RescheduleHistory.appointment_id == appointment_id,
                self.RescheduleHistory.new_start.is_(None),
            )
            .order_by(self.RescheduleHistory.created_at.desc())
            .first()
        )
        if latest_hist:
            latest_hist.new_start = new_start
            latest_hist.new_end = new_end
        else:
            # No pending history row — create one (e.g. borrower self-service
            # may skip initiate_reschedule and go straight to confirm)
            hist = self.RescheduleHistory(
                appointment_id=appointment_id,
                organization_id=appt.organization_id,
                original_start=old_start,
                original_end=old_end,
                new_start=new_start,
                new_end=new_end,
                requested_by_type=confirmed_by,
            )
            self.db.add(hist)

        # Record status history
        AppointmentStatusHistory = self.models.get("AppointmentStatusHistory")
        if AppointmentStatusHistory:
            sh = AppointmentStatusHistory(
                organization_id=appt.organization_id,
                appointment_id=appointment_id,
                previous_status="booked",
                new_status=AppointmentStatus.RESCHEDULED.value,
                change_source="system" if confirmed_by == "system" else (
                    "public" if confirmed_by == "borrower" else "manual"
                ),
                notes=f"Rescheduled from {old_start.isoformat()} to {new_start.isoformat()}",
                metadata={
                    "old_start": old_start.isoformat(),
                    "old_end": old_end.isoformat(),
                    "new_start": new_start.isoformat(),
                    "new_end": new_end.isoformat(),
                },
            )
            self.db.add(sh)

        self.db.flush()

        # Best-effort confirmation email
        self._send_reschedule_confirmation(appt, old_start, old_end)

        return {
            "appointment_id": appointment_id,
            "old_start": old_start.isoformat(),
            "old_end": old_end.isoformat(),
            "new_start": new_start.isoformat(),
            "new_end": new_end.isoformat(),
            "reschedule_count": appt.reschedule_count,
            "status": "rescheduled",
        }

    # ------------------------------------------------------------------
    # 4. Generate borrower reschedule link
    # ------------------------------------------------------------------

    def generate_reschedule_link(
        self,
        appointment_id: int,
        org_id: Optional[int] = None,
    ) -> Dict[str, str]:
        """
        Create a time-limited reschedule URL for the borrower.

        Returns {"url": "...", "expires_at": "...", "token": "..."}.
        """
        import jwt as pyjwt

        appt = self._get_appointment(appointment_id, org_id)

        # Enforce max reschedules
        count = self._reschedule_count(appointment_id)
        if count >= MAX_RESCHEDULES_PER_APPOINTMENT:
            raise ValueError("Reschedule limit reached for this appointment")

        secret = os.getenv("SECRET_KEY")
        if not secret:
            raise RuntimeError("SECRET_KEY environment variable is required")

        expires_at = datetime.now(timezone.utc) + timedelta(hours=RESCHEDULE_TOKEN_TTL_HOURS)

        # SEC-010: Use email_hash instead of plaintext email in JWT payload
        import hashlib
        email_hash = ""
        if appt.attendee_email:
            email_hash = hashlib.sha256(appt.attendee_email.lower().strip().encode()).hexdigest()[:16]
        payload = {
            "appt_id": appointment_id,
            "org_id": appt.organization_id,
            "email_hash": email_hash,
            "action": "reschedule",
            "exp": expires_at,
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")

        # Persist token on the latest history row or create one
        latest_hist = (
            self.db.query(self.RescheduleHistory)
            .filter(
                self.RescheduleHistory.appointment_id == appointment_id,
                self.RescheduleHistory.new_start.is_(None),
            )
            .order_by(self.RescheduleHistory.created_at.desc())
            .first()
        )
        if latest_hist:
            latest_hist.reschedule_token = token
            latest_hist.token_expires_at = expires_at
        else:
            hist = self.RescheduleHistory(
                appointment_id=appointment_id,
                organization_id=appt.organization_id,
                original_start=appt.scheduled_start,
                original_end=appt.scheduled_end,
                requested_by_type="borrower",
                reschedule_token=token,
                token_expires_at=expires_at,
            )
            self.db.add(hist)

        self.db.flush()

        frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
        url = f"{frontend_url}/reschedule/{token}"

        return {
            "url": url,
            "token": token,
            "expires_at": expires_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # 5. History
    # ------------------------------------------------------------------

    def get_reschedule_history(
        self,
        appointment_id: int,
        org_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return the reschedule history for an appointment."""
        query = self.db.query(self.RescheduleHistory).filter(
            self.RescheduleHistory.appointment_id == appointment_id,
        )
        if org_id is not None:
            query = query.filter(self.RescheduleHistory.organization_id == org_id)

        rows = query.order_by(self.RescheduleHistory.created_at.asc()).all()
        return [
            {
                "id": r.id,
                "original_start": r.original_start.isoformat() if r.original_start else None,
                "original_end": r.original_end.isoformat() if r.original_end else None,
                "new_start": r.new_start.isoformat() if r.new_start else None,
                "new_end": r.new_end.isoformat() if r.new_end else None,
                "reason": r.reason,
                "requested_by_type": r.requested_by_type,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Token verification (for public endpoints)
    # ------------------------------------------------------------------

    def verify_reschedule_token(self, token: str, consume: bool = False) -> Dict[str, Any]:
        """
        Verify a borrower reschedule JWT token.

        Returns the decoded payload dict with keys: appt_id, org_id, email.
        Raises ValueError on invalid / expired / already-used tokens.

        Args:
            token: The JWT token string.
            consume: If True, marks the token as used (single-use enforcement).
        """
        import jwt as pyjwt

        secret = os.getenv("SECRET_KEY")
        if not secret:
            raise RuntimeError("SECRET_KEY not configured")

        try:
            payload = pyjwt.decode(token, secret, algorithms=["HS256"])
        except pyjwt.ExpiredSignatureError:
            raise ValueError("Reschedule link has expired")
        except pyjwt.InvalidTokenError:
            raise ValueError("Invalid reschedule link")

        if payload.get("action") != "reschedule":
            raise ValueError("Invalid token purpose")

        # Single-use enforcement: check if this token has already been consumed
        hist = (
            self.db.query(self.RescheduleHistory)
            .filter(
                self.RescheduleHistory.reschedule_token == token,
            )
            .first()
        )
        if hist and hist.new_start is not None:
            # Token was already used to complete a reschedule
            raise ValueError("This reschedule link has already been used")

        if consume and hist:
            # Mark will happen in the confirm step (new_start gets set)
            pass

        return payload

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_appointment(self, appointment_id: int, org_id: Optional[int] = None):
        """Fetch appointment by ID, scoped by org_id when provided."""
        query = self.db.query(self.Appointment).filter(
            self.Appointment.id == appointment_id,
        )
        if org_id is not None:
            query = query.filter(self.Appointment.organization_id == org_id)

        appt = query.first()
        if not appt:
            raise ValueError(f"Appointment {appointment_id} not found")
        return appt

    def _reschedule_count(self, appointment_id: int) -> int:
        """Count completed reschedules (those with new_start populated)."""
        return (
            self.db.query(self.RescheduleHistory)
            .filter(
                self.RescheduleHistory.appointment_id == appointment_id,
                self.RescheduleHistory.new_start.isnot(None),
            )
            .count()
        )

    def _send_reschedule_confirmation(self, appt, old_start, old_end):
        """Best-effort reschedule confirmation email to the attendee."""
        if not appt.attendee_email:
            return
        try:
            from scheduler_email_service import send_appointment_update_email

            # Format dates for the email
            new_date = appt.scheduled_start.strftime("%A, %B %d, %Y")
            new_time = appt.scheduled_start.strftime("%I:%M %p")
            old_date = old_start.strftime("%A, %B %d, %Y")
            old_time = old_start.strftime("%I:%M %p")
            duration = f"{appt.duration_minutes} minutes"

            # Get LO name
            lo_name = None
            if appt.assigned_user_id:
                try:
                    from database.models.core import User
                    lo = self.db.query(User).filter(User.id == appt.assigned_user_id).first()
                    if lo:
                        lo_name = f"{getattr(lo, 'first_name', '')} {getattr(lo, 'last_name', '')}".strip()
                except Exception as _exc:  # noqa: BLE001
                    pass

            send_appointment_update_email(
                attendee_email=appt.attendee_email,
                attendee_name=appt.attendee_name or "",
                appointment_title=appt.title or "Appointment",
                appointment_date=new_date,
                appointment_time=new_time,
                duration=duration,
                meeting_mode=appt.meeting_mode.value if appt.meeting_mode else "Phone Call",
                team_member_name=lo_name,
                video_link=appt.video_link,
                scheduled_start=appt.scheduled_start,
                duration_minutes=appt.duration_minutes,
                old_date=old_date,
                old_time=old_time,
            )
            logger.info(f"Reschedule confirmation email sent for appointment {appt.id}")
        except Exception as e:
            logger.error(f"Failed to send reschedule confirmation email: {e}")
