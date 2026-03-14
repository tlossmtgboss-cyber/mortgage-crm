"""
Cancellation Policy Service

Server-side enforcement of appointment cancellation policies.

All enforcement decisions are made here -- the frontend shows warnings
but the backend makes the final allow/deny decision.

Methods:
    get_or_create_policy(org_id)           - Fetch or create default policy
    can_cancel(appointment_id, cancelled_by_email, org_id)
                                            - Pre-flight check: {allowed, reason, is_late, ...}
    get_borrower_cancel_count(email, org_id, days)
                                            - Count recent cancellations by borrower
    enforce_policy(appointment_id, cancelled_by_email, org_id, reason, notes)
                                            - Check policy, cancel if allowed, return result
    get_cancellation_stats(org_id, period_days)
                                            - Cancellation analytics for admin dashboard

Usage:
    from services.cancellation_policy_service import CancellationPolicyService

    svc = CancellationPolicyService(db)
    check = svc.can_cancel(appointment_id, "borrower@example.com", org_id)
    if check["allowed"]:
        svc.enforce_policy(appointment_id, "borrower@example.com", org_id, reason="Schedule conflict")
"""

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CancellationPolicyService:
    """Service for cancellation policy enforcement."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # LAZY IMPORTS (avoid circular imports at module load)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_policy_model():
        from database.models.cancellation_policy import CancellationPolicy
        return CancellationPolicy

    @staticmethod
    def _get_appointment_model():
        """Get the Appointment model from the smart_scheduler_models module."""
        from smart_scheduler_models import Appointment, AppointmentStatus
        return Appointment, AppointmentStatus

    # ==================================================================
    # POLICY CRUD
    # ==================================================================

    def get_or_create_policy(self, org_id: int):
        """
        Fetch the cancellation policy for an org. If none exists, create one
        with defaults and flush (so the caller's commit includes it).

        Returns:
            CancellationPolicy instance
        """
        CancellationPolicy = self._get_policy_model()

        policy = (
            self.db.query(CancellationPolicy)
            .filter(CancellationPolicy.organization_id == org_id)
            .first()
        )

        if policy is None:
            from database.models.cancellation_policy import (
                DEFAULT_CANCELLATION_REASONS,
                DEFAULT_LATE_CANCEL_MESSAGE,
            )
            policy = CancellationPolicy(
                organization_id=org_id,
                min_notice_hours=24,
                max_cancellations_per_borrower=3,
                allow_borrower_cancel=True,
                require_reason=True,
                cancellation_reasons=list(DEFAULT_CANCELLATION_REASONS),
                late_cancel_message=DEFAULT_LATE_CANCEL_MESSAGE,
            )
            self.db.add(policy)
            self.db.flush()
            logger.info(f"Created default cancellation policy for org {org_id}")

        return policy

    def update_policy(self, org_id: int, updates: dict):
        """
        Update the cancellation policy for an org. Only provided fields are changed.

        Allowed fields: min_notice_hours, max_cancellations_per_borrower,
                        allow_borrower_cancel, require_reason,
                        cancellation_reasons, late_cancel_message

        Returns:
            Updated CancellationPolicy instance
        """
        policy = self.get_or_create_policy(org_id)

        allowed_fields = {
            "min_notice_hours",
            "max_cancellations_per_borrower",
            "allow_borrower_cancel",
            "require_reason",
            "cancellation_reasons",
            "late_cancel_message",
        }

        for field, value in updates.items():
            if field in allowed_fields:
                # Validate types
                if field == "min_notice_hours":
                    value = max(0, int(value))
                elif field == "max_cancellations_per_borrower":
                    value = max(0, int(value))
                elif field in ("allow_borrower_cancel", "require_reason"):
                    value = bool(value)
                elif field == "cancellation_reasons":
                    if not isinstance(value, list):
                        continue
                    # Sanitize: strip whitespace, remove empties, deduplicate
                    seen = set()
                    cleaned = []
                    for r in value:
                        r_stripped = str(r).strip()
                        if r_stripped and r_stripped not in seen:
                            seen.add(r_stripped)
                            cleaned.append(r_stripped)
                    value = cleaned
                elif field == "late_cancel_message":
                    value = str(value).strip() if value else ""

                setattr(policy, field, value)

        self.db.flush()
        return policy

    # ==================================================================
    # POLICY ENFORCEMENT
    # ==================================================================

    def can_cancel(
        self,
        appointment_id: int,
        cancelled_by_email: Optional[str],
        org_id: int,
        is_staff: bool = False,
    ) -> Dict:
        """
        Pre-flight check: can this appointment be cancelled?

        Args:
            appointment_id: The appointment to cancel
            cancelled_by_email: Email of the person requesting cancellation
            org_id: Organization ID (tenant isolation)
            is_staff: True if the requester is authenticated staff (bypasses
                      borrower-specific restrictions)

        Returns:
            {
                "allowed": bool,
                "reason": str,           # Human-readable explanation
                "is_late": bool,          # True if within notice period
                "late_cancel_message": str | None,
                "cancel_count": int,      # Borrower's recent cancellation count
                "max_cancellations": int,
                "require_reason": bool,
                "cancellation_reasons": list[str],
            }
        """
        Appointment, AppointmentStatus = self._get_appointment_model()
        policy = self.get_or_create_policy(org_id)

        # Fetch appointment
        appointment = (
            self.db.query(Appointment)
            .filter(
                Appointment.id == appointment_id,
                Appointment.organization_id == org_id,
            )
            .first()
        )

        if not appointment:
            return {
                "allowed": False,
                "reason": "Appointment not found",
                "is_late": False,
                "late_cancel_message": None,
                "cancel_count": 0,
                "max_cancellations": policy.max_cancellations_per_borrower,
                "require_reason": policy.require_reason,
                "cancellation_reasons": policy.cancellation_reasons or [],
            }

        # Already cancelled or completed?
        status_val = appointment.status.value if hasattr(appointment.status, 'value') else str(appointment.status)
        if status_val in ("cancelled", "completed", "no_show"):
            return {
                "allowed": False,
                "reason": f"Appointment is already {status_val}",
                "is_late": False,
                "late_cancel_message": None,
                "cancel_count": 0,
                "max_cancellations": policy.max_cancellations_per_borrower,
                "require_reason": policy.require_reason,
                "cancellation_reasons": policy.cancellation_reasons or [],
            }

        # Borrower self-cancel check (only applies to non-staff)
        if not is_staff and not policy.allow_borrower_cancel:
            return {
                "allowed": False,
                "reason": "Borrower self-cancellation is not allowed. Please contact your loan officer.",
                "is_late": False,
                "late_cancel_message": None,
                "cancel_count": 0,
                "max_cancellations": policy.max_cancellations_per_borrower,
                "require_reason": policy.require_reason,
                "cancellation_reasons": policy.cancellation_reasons or [],
            }

        # Late cancellation check
        is_late = False
        now = datetime.now(timezone.utc)
        if appointment.scheduled_start:
            # Normalize to UTC-aware for comparison
            appt_start = appointment.scheduled_start
            if appt_start.tzinfo is None:
                appt_start = appt_start.replace(tzinfo=timezone.utc)
            notice_cutoff = appt_start - timedelta(hours=policy.min_notice_hours)
            is_late = now >= notice_cutoff

        # Cancellation count check (borrower limit, based on attendee email)
        check_email = cancelled_by_email or getattr(appointment, 'attendee_email', None)
        cancel_count = 0
        if check_email:
            cancel_count = self.get_borrower_cancel_count(check_email, org_id)

        max_cancellations = policy.max_cancellations_per_borrower
        over_limit = False
        if not is_staff and max_cancellations > 0 and cancel_count >= max_cancellations:
            over_limit = True

        # Staff always allowed (they see warnings but aren't blocked)
        if is_staff:
            return {
                "allowed": True,
                "reason": "Staff cancellation" + (" (late)" if is_late else ""),
                "is_late": is_late,
                "late_cancel_message": policy.late_cancel_message if is_late else None,
                "cancel_count": cancel_count,
                "max_cancellations": max_cancellations,
                "require_reason": policy.require_reason,
                "cancellation_reasons": policy.cancellation_reasons or [],
            }

        # Borrower: blocked if over limit
        if over_limit:
            return {
                "allowed": False,
                "reason": (
                    f"You have cancelled {cancel_count} appointments in the last 30 days. "
                    f"Maximum allowed is {max_cancellations}. Please contact your loan officer."
                ),
                "is_late": is_late,
                "late_cancel_message": policy.late_cancel_message if is_late else None,
                "cancel_count": cancel_count,
                "max_cancellations": max_cancellations,
                "require_reason": policy.require_reason,
                "cancellation_reasons": policy.cancellation_reasons or [],
            }

        # Allowed (possibly late)
        return {
            "allowed": True,
            "reason": "Late cancellation" if is_late else "Cancellation allowed",
            "is_late": is_late,
            "late_cancel_message": policy.late_cancel_message if is_late else None,
            "cancel_count": cancel_count,
            "max_cancellations": max_cancellations,
            "require_reason": policy.require_reason,
            "cancellation_reasons": policy.cancellation_reasons or [],
        }

    def get_borrower_cancel_count(
        self,
        borrower_email: str,
        org_id: int,
        days: int = 30,
    ) -> int:
        """
        Count the number of cancelled appointments for a borrower email
        within the rolling window.

        Uses the scheduler_appointments table: status = 'cancelled' and
        attendee_email matches.
        """
        Appointment, AppointmentStatus = self._get_appointment_model()

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        count = (
            self.db.query(func.count(Appointment.id))
            .filter(
                Appointment.organization_id == org_id,
                Appointment.attendee_email == borrower_email,
                Appointment.status == AppointmentStatus.CANCELLED,
                Appointment.cancelled_at >= cutoff,
            )
            .scalar()
        ) or 0

        return count

    def enforce_policy(
        self,
        appointment_id: int,
        cancelled_by_email: Optional[str],
        org_id: int,
        reason: Optional[str] = None,
        notes: Optional[str] = None,
        is_staff: bool = False,
        cancelled_by_user_id: Optional[int] = None,
    ) -> Dict:
        """
        Check policy and cancel the appointment if allowed.

        This is the main entry point for policy-enforced cancellation. It:
        1. Runs can_cancel() to check policy
        2. If allowed, sets the appointment status to CANCELLED
        3. Records the reason and metadata
        4. Flushes (does NOT commit -- caller owns the transaction)

        Returns:
            {
                "cancelled": bool,
                "policy_check": dict,  # full can_cancel result
                "appointment_id": int,
                "is_late": bool,
            }
        """
        Appointment, AppointmentStatus = self._get_appointment_model()
        policy = self.get_or_create_policy(org_id)

        # Run policy check
        check = self.can_cancel(appointment_id, cancelled_by_email, org_id, is_staff=is_staff)

        if not check["allowed"]:
            return {
                "cancelled": False,
                "policy_check": check,
                "appointment_id": appointment_id,
                "is_late": check["is_late"],
            }

        # Validate reason requirement
        if policy.require_reason and not reason:
            check["allowed"] = False
            check["reason"] = "A cancellation reason is required"
            return {
                "cancelled": False,
                "policy_check": check,
                "appointment_id": appointment_id,
                "is_late": check["is_late"],
            }

        # Perform cancellation
        appointment = (
            self.db.query(Appointment)
            .filter(
                Appointment.id == appointment_id,
                Appointment.organization_id == org_id,
            )
            .first()
        )

        if not appointment:
            check["allowed"] = False
            check["reason"] = "Appointment not found"
            return {
                "cancelled": False,
                "policy_check": check,
                "appointment_id": appointment_id,
                "is_late": check["is_late"],
            }

        now = datetime.now(timezone.utc)
        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancelled_at = now
        appointment.cancellation_reason = reason
        if cancelled_by_user_id:
            appointment.status_changed_by = cancelled_by_user_id
        appointment.status_changed_at = now

        # Store late-cancel flag in notes or existing metadata if available
        if notes:
            existing_notes = getattr(appointment, 'attendee_notes', '') or ''
            if existing_notes:
                appointment.attendee_notes = f"{existing_notes}\n[Cancel notes: {notes}]"
            else:
                appointment.attendee_notes = f"[Cancel notes: {notes}]"

        self.db.flush()

        logger.info(
            f"Policy-enforced cancellation: appointment {appointment_id} "
            f"by {cancelled_by_email or 'staff'} "
            f"(late={check['is_late']}, reason={reason})"
        )

        return {
            "cancelled": True,
            "policy_check": check,
            "appointment_id": appointment_id,
            "is_late": check["is_late"],
        }

    # ==================================================================
    # ANALYTICS
    # ==================================================================

    def get_cancellation_stats(self, org_id: int, period_days: int = 30) -> Dict:
        """
        Cancellation analytics for the admin dashboard.

        Returns:
            {
                "period_days": int,
                "total_appointments": int,
                "total_cancellations": int,
                "cancellation_rate": float,         # percentage
                "late_cancellations": int,
                "top_reasons": [{"reason": str, "count": int}, ...],
                "repeat_cancellers": [{"email": str, "count": int}, ...],
                "cancellations_by_day": [{"date": str, "count": int}, ...],
            }
        """
        Appointment, AppointmentStatus = self._get_appointment_model()
        policy = self.get_or_create_policy(org_id)

        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)

        # Total appointments in period
        total_appointments = (
            self.db.query(func.count(Appointment.id))
            .filter(
                Appointment.organization_id == org_id,
                Appointment.created_at >= cutoff,
            )
            .scalar()
        ) or 0

        # Total cancellations
        cancelled_query = (
            self.db.query(Appointment)
            .filter(
                Appointment.organization_id == org_id,
                Appointment.status == AppointmentStatus.CANCELLED,
                Appointment.cancelled_at >= cutoff,
            )
        )
        cancelled_appointments = cancelled_query.all()
        total_cancellations = len(cancelled_appointments)

        cancellation_rate = 0.0
        if total_appointments > 0:
            cancellation_rate = round((total_cancellations / total_appointments) * 100, 1)

        # Late cancellations: cancelled_at is within min_notice_hours of scheduled_start
        late_cancellations = 0
        for appt in cancelled_appointments:
            if appt.cancelled_at and appt.scheduled_start:
                cancelled_at = appt.cancelled_at
                scheduled_start = appt.scheduled_start
                if cancelled_at.tzinfo is None:
                    cancelled_at = cancelled_at.replace(tzinfo=timezone.utc)
                if scheduled_start.tzinfo is None:
                    scheduled_start = scheduled_start.replace(tzinfo=timezone.utc)
                notice_given = scheduled_start - cancelled_at
                if notice_given < timedelta(hours=policy.min_notice_hours):
                    late_cancellations += 1

        # Top reasons
        reason_counter = Counter()
        for appt in cancelled_appointments:
            reason = appt.cancellation_reason or "No reason given"
            reason_counter[reason] += 1
        top_reasons = [
            {"reason": reason, "count": count}
            for reason, count in reason_counter.most_common(10)
        ]

        # Repeat cancellers (borrowers with 2+ cancellations)
        email_counter = Counter()
        for appt in cancelled_appointments:
            email = getattr(appt, 'attendee_email', None)
            if email:
                email_counter[email] += 1
        repeat_cancellers = [
            {"email": email, "count": count}
            for email, count in email_counter.most_common(20)
            if count >= 2
        ]

        # Cancellations by day
        day_counter = Counter()
        for appt in cancelled_appointments:
            if appt.cancelled_at:
                day_key = appt.cancelled_at.strftime("%Y-%m-%d")
                day_counter[day_key] += 1
        cancellations_by_day = sorted(
            [{"date": day, "count": count} for day, count in day_counter.items()],
            key=lambda x: x["date"],
        )

        return {
            "period_days": period_days,
            "total_appointments": total_appointments,
            "total_cancellations": total_cancellations,
            "cancellation_rate": cancellation_rate,
            "late_cancellations": late_cancellations,
            "top_reasons": top_reasons,
            "repeat_cancellers": repeat_cancellers,
            "cancellations_by_day": cancellations_by_day,
        }
