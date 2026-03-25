"""
Pipeline-to-Calendar Appointment Trigger Service

Automatically triggers appointment creation when loans change stages in the pipeline.
This is the core competitive differentiator — no mortgage CRM auto-schedules appointments
from loan stage changes.

Usage:
    trigger = PipelineAppointmentTrigger(db, organization_id)
    await trigger.on_stage_change(loan_id, "APPLICATION", "DISCLOSED", loan_officer_id)

Supports:
    - Default mortgage-specific rules (APPLICATION, DISCLOSED, CONDITIONAL_APPROVAL, etc.)
    - Custom per-organization rules
    - Auto-book (create appointment directly) vs. send booking link
    - Compliance-required vs. suggested appointments
    - Delay-based scheduling (hours after stage change)
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Index
from sqlalchemy.orm import Session

from db import Base

# Fallback timezone — import from canonical scheduler constants
from routes.scheduler.constants import DEFAULT_TIMEZONE as _FALLBACK_TIMEZONE

# Retry configuration for transient failures
_MAX_RETRIES = 2
_BASE_BACKOFF_SECONDS = 1
_MAX_BACKOFF_SECONDS = 8
_TRANSIENT_ERRORS = (ConnectionError, TimeoutError, OSError)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PipelineAppointmentRule:
    """Defines when and how a pipeline stage change triggers an appointment.

    Attributes:
        from_stage: Loan stage that triggers the appointment (e.g., "APPLICATION").
        appointment_type: Type of meeting to schedule (e.g., "closing_prep").
        appointment_title: Human-readable title for the appointment.
        delay_hours: Hours after stage change to schedule the appointment.
        duration_minutes: Default meeting duration in minutes.
        auto_book: If True, auto-create the appointment. If False, send a booking link.
        required: If True, this is compliance-required. If False, it is suggested.
        description: Description text included in the appointment or booking link.
        meeting_mode: Default mode (video, phone, in_person).
    """
    from_stage: str
    appointment_type: str
    appointment_title: str
    delay_hours: int = 0
    duration_minutes: int = 30
    auto_book: bool = False
    required: bool = False
    description: str = ""
    meeting_mode: str = "video"


# =============================================================================
# DEFAULT RULES — Mortgage-specific stage-to-appointment triggers
# =============================================================================

DEFAULT_RULES: List[PipelineAppointmentRule] = [
    PipelineAppointmentRule(
        from_stage="APPLICATION",
        appointment_type="initial_consultation",
        appointment_title="Initial Consultation",
        delay_hours=0,
        duration_minutes=30,
        auto_book=False,
        required=False,
        description=(
            "Welcome! Let's review your application together, discuss loan options, "
            "and outline next steps in the process."
        ),
        meeting_mode="video",
    ),
    PipelineAppointmentRule(
        from_stage="DISCLOSED",
        appointment_type="document_collection_review",
        appointment_title="Document Collection Review",
        delay_hours=24,
        duration_minutes=30,
        auto_book=False,
        required=False,
        description=(
            "Let's go over the documents needed to move your loan forward. "
            "We'll walk through the checklist together so nothing is missed."
        ),
        meeting_mode="video",
    ),
    PipelineAppointmentRule(
        from_stage="CONDITIONAL_APPROVAL",
        appointment_type="condition_clearing_session",
        appointment_title="Condition Clearing Session",
        delay_hours=4,
        duration_minutes=30,
        auto_book=True,
        required=True,
        description=(
            "Your loan has conditional approval. Let's review the outstanding conditions "
            "and create a plan to clear them quickly."
        ),
        meeting_mode="video",
    ),
    PipelineAppointmentRule(
        from_stage="APPROVED",
        appointment_type="closing_prep_meeting",
        appointment_title="Closing Prep Meeting",
        delay_hours=24,
        duration_minutes=45,
        auto_book=False,
        required=False,
        description=(
            "Congratulations on your approval! Let's prepare for closing — we'll review "
            "the final numbers, timeline, and what to expect at the signing table."
        ),
        meeting_mode="video",
    ),
    PipelineAppointmentRule(
        from_stage="CLEAR_TO_CLOSE",
        appointment_type="final_walkthrough_scheduling",
        appointment_title="Final Walkthrough Scheduling",
        delay_hours=4,
        duration_minutes=15,
        auto_book=False,
        required=False,
        description=(
            "You're clear to close! Let's coordinate the final walkthrough and "
            "confirm your signing appointment details."
        ),
        meeting_mode="phone",
    ),
    PipelineAppointmentRule(
        from_stage="CTC",
        appointment_type="signing_appointment",
        appointment_title="Signing Appointment",
        delay_hours=24,
        duration_minutes=60,
        auto_book=True,
        required=True,
        description=(
            "Time to sign! This appointment is for the loan signing with the notary. "
            "Please bring a valid photo ID and any cashier's checks as discussed."
        ),
        meeting_mode="in_person",
    ),
]


# =============================================================================
# DATABASE MODEL — Per-organization custom rules + trigger history
# =============================================================================

class PipelineAppointmentRuleModel(Base):
    """Per-organization custom pipeline appointment rules.

    Organizations can override defaults or add their own stage-to-appointment triggers.
    """
    __tablename__ = "pipeline_appointment_rules"
    __table_args__ = (
        Index("ix_pa_rules_org_id", "organization_id"),
        Index("ix_pa_rules_org_stage", "organization_id", "from_stage"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    # Rule definition
    from_stage = Column(String(50), nullable=False)
    appointment_type = Column(String(100), nullable=False)
    appointment_title = Column(String(255), nullable=False)
    delay_hours = Column(Integer, default=0, nullable=False)
    duration_minutes = Column(Integer, default=30, nullable=False)
    auto_book = Column(Boolean, default=False, nullable=False)
    required = Column(Boolean, default=False, nullable=False)
    description = Column(Text, default="")
    meeting_mode = Column(String(20), default="video")

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    def to_rule(self) -> PipelineAppointmentRule:
        """Convert ORM model to PipelineAppointmentRule dataclass."""
        return PipelineAppointmentRule(
            from_stage=self.from_stage,
            appointment_type=self.appointment_type,
            appointment_title=self.appointment_title,
            delay_hours=self.delay_hours,
            duration_minutes=self.duration_minutes,
            auto_book=self.auto_book,
            required=self.required,
            description=self.description or "",
            meeting_mode=self.meeting_mode or "video",
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for API response."""
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "from_stage": self.from_stage,
            "appointment_type": self.appointment_type,
            "appointment_title": self.appointment_title,
            "delay_hours": self.delay_hours,
            "duration_minutes": self.duration_minutes,
            "auto_book": self.auto_book,
            "required": self.required,
            "description": self.description,
            "meeting_mode": self.meeting_mode,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PipelineAppointmentTriggerLog(Base):
    """Audit log of triggered appointments from pipeline stage changes."""
    __tablename__ = "pipeline_appointment_trigger_log"
    __table_args__ = (
        Index("ix_pa_log_org_id", "organization_id"),
        Index("ix_pa_log_loan_id", "loan_id"),
        Index("ix_pa_log_lo_id", "loan_officer_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    # Context
    loan_id = Column(Integer, ForeignKey("loans.id", ondelete="CASCADE"), nullable=False)
    loan_officer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    old_stage = Column(String(50), nullable=False)
    new_stage = Column(String(50), nullable=False)

    # Trigger result
    rule_from_stage = Column(String(50), nullable=False)
    appointment_type = Column(String(100), nullable=False)
    appointment_title = Column(String(255), nullable=False)
    action_taken = Column(String(50), nullable=False)  # "auto_booked", "booking_link_sent", "suggestion_created", "skipped"
    appointment_id = Column(Integer, nullable=True)  # FK to scheduler_appointments if auto-booked
    scheduled_for = Column(DateTime, nullable=True)  # When the appointment was scheduled
    booking_link = Column(String(500), nullable=True)

    # Status
    status = Column(String(30), default="pending")  # pending, completed, failed, cancelled
    error_message = Column(Text, nullable=True)
    extra_data = Column("metadata", JSON, default=dict)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    acknowledged_at = Column(DateTime, nullable=True)  # When an LO acknowledged a failure

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for API response."""
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "loan_officer_id": self.loan_officer_id,
            "old_stage": self.old_stage,
            "new_stage": self.new_stage,
            "rule_from_stage": self.rule_from_stage,
            "appointment_type": self.appointment_type,
            "appointment_title": self.appointment_title,
            "action_taken": self.action_taken,
            "appointment_id": self.appointment_id,
            "scheduled_for": self.scheduled_for.isoformat() if self.scheduled_for else None,
            "booking_link": self.booking_link,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
        }


# =============================================================================
# TRIGGER SERVICE
# =============================================================================

class PipelineAppointmentTrigger:
    """Orchestrates automatic appointment creation from loan pipeline stage changes.

    Tenant-aware: all operations are scoped to a single organization_id.

    Usage:
        trigger = PipelineAppointmentTrigger(db_session, organization_id)
        result = await trigger.on_stage_change(loan_id, "APPLICATION", "DISCLOSED", lo_id)
    """

    def __init__(self, db_session: Session, organization_id: int):
        self.db = db_session
        self.organization_id = organization_id

    async def on_stage_change(
        self,
        loan_id: int,
        old_stage: str,
        new_stage: str,
        loan_officer_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Main entry point: process a loan stage change and trigger any matching rules.

        Args:
            loan_id: The loan that changed stages.
            old_stage: Previous loan stage (e.g., "APPLICATION").
            new_stage: New loan stage (e.g., "DISCLOSED").
            loan_officer_id: The assigned loan officer's user ID.

        Returns:
            List of action results (one per triggered rule).
        """
        results = []

        # Capture the trigger timestamp for speed-to-lead measurement
        trigger_time = datetime.now(timezone.utc)

        # Get matching rules for the new stage
        rules = await self.get_rules(self.organization_id)
        matching = [r for r in rules if r.from_stage == new_stage]

        if not matching:
            logger.debug(
                f"No pipeline appointment rules match stage '{new_stage}' "
                f"for org={self.organization_id}, loan={loan_id}"
            )
            return results

        # Load loan context for personalization
        loan = self._get_loan(loan_id)
        if not loan:
            logger.warning(f"Loan {loan_id} not found — skipping appointment triggers")
            return results

        for rule in matching:
            try:
                if rule.auto_book:
                    result = await self.create_appointment_suggestion(
                        loan_id=loan_id,
                        rule=rule,
                        loan_officer_id=loan_officer_id,
                        loan=loan,
                    )
                else:
                    result = await self.send_booking_link(
                        loan_id=loan_id,
                        rule=rule,
                        loan_officer_id=loan_officer_id,
                        loan=loan,
                    )

                # Log the trigger
                self._log_trigger(
                    loan_id=loan_id,
                    loan_officer_id=loan_officer_id,
                    old_stage=old_stage,
                    new_stage=new_stage,
                    rule=rule,
                    result=result,
                )

                # Record speed-to-lead timing (non-fatal)
                delivery_time = datetime.now(timezone.utc)
                action = result.get("action", "")
                if action in ("auto_booked", "booking_link_sent"):
                    self._record_speed_to_lead(
                        loan_id=loan_id,
                        loan_officer_id=loan_officer_id,
                        trigger_time=trigger_time,
                        delivery_time=delivery_time,
                        delivery_method=action,
                        trigger_stage=new_stage,
                    )

                results.append(result)

            except Exception as e:
                logger.exception(
                    f"Failed to process pipeline appointment rule "
                    f"'{rule.appointment_type}' for loan {loan_id}: {e}"
                )
                error_result = {
                    "action": "error",
                    "rule": rule.appointment_type,
                    "error": str(e),
                }
                self._log_trigger(
                    loan_id=loan_id,
                    loan_officer_id=loan_officer_id,
                    old_stage=old_stage,
                    new_stage=new_stage,
                    rule=rule,
                    result=error_result,
                )
                # Notify the LO so failures are not silently swallowed
                self._notify_lo_of_failure(
                    loan_officer_id=loan_officer_id,
                    loan_id=loan_id,
                    rule=rule,
                    error_message=str(e),
                )
                results.append(error_result)

        return results

    async def get_rules(self, organization_id: int) -> List[PipelineAppointmentRule]:
        """Get appointment trigger rules for an organization.

        Returns custom rules if any exist for the org; otherwise returns defaults.
        Custom rules completely override defaults for the org (not merged) so that
        organizations have full control.

        Args:
            organization_id: The organization to get rules for.

        Returns:
            List of PipelineAppointmentRule instances.
        """
        custom_rules = (
            self.db.query(PipelineAppointmentRuleModel)
            .filter(
                PipelineAppointmentRuleModel.organization_id == organization_id,
                PipelineAppointmentRuleModel.is_active == True,
            )
            .order_by(PipelineAppointmentRuleModel.from_stage)
            .all()
        )

        if custom_rules:
            return [r.to_rule() for r in custom_rules]

        return list(DEFAULT_RULES)

    async def create_appointment_suggestion(
        self,
        loan_id: int,
        rule: PipelineAppointmentRule,
        loan_officer_id: Optional[int],
        loan: Any = None,
    ) -> Dict[str, Any]:
        """Auto-book a draft appointment based on the rule.

        Delegates appointment creation to the shared appointment_creation_service,
        which handles conflict checking, lead linking, CRM activity logging,
        follow-up task creation, and audit logging.

        Pipeline-specific logic preserved here:
          - Business hours snapping for the scheduled time
          - Retry loop for transient errors (ConnectionError, TimeoutError, OSError)
          - Fallback to booking link when auto-book fails
          - LO failure notification when both paths fail

        Args:
            loan_id: Loan that triggered the rule.
            rule: The matching PipelineAppointmentRule.
            loan_officer_id: LO to assign the appointment to.
            loan: Pre-loaded Loan ORM object (optional, avoids re-query).

        Returns:
            Dict with action details and created appointment info.
        """
        if loan is None:
            loan = self._get_loan(loan_id)

        now = datetime.now(timezone.utc)
        target_start = now + timedelta(hours=rule.delay_hours)

        # Round up to next business hour (9 AM - 5 PM range)
        target_start = self._snap_to_business_hours(target_start)
        target_end = target_start + timedelta(minutes=rule.duration_minutes)

        # Build appointment title with borrower context
        borrower_name = getattr(loan, "borrower_name", "Borrower") if loan else "Borrower"
        title = f"{rule.appointment_title} — {borrower_name}"

        # Resolve the LO's timezone from their SchedulerConfig
        lo_timezone = self._get_lo_timezone(loan_officer_id)

        # Extract borrower details from loan
        borrower_email = getattr(loan, "borrower_email", None) if loan else None
        borrower_phone = getattr(loan, "borrower_phone", None) if loan else None

        ai_context = {
            "trigger": "pipeline_stage_change",
            "from_stage": rule.from_stage,
            "appointment_type": rule.appointment_type,
            "rule_required": rule.required,
        }

        # Retry transient errors (ConnectionError, TimeoutError) up to _MAX_RETRIES times
        last_error = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                from services.appointment_creation_service import create_appointment

                result = await create_appointment(
                    db=self.db,
                    organization_id=self.organization_id,
                    assigned_user_id=loan_officer_id,
                    created_by_user_id=None,  # AI-initiated, no user context
                    source="ai_pipeline",
                    title=title,
                    scheduled_start=target_start,
                    scheduled_end=target_end,
                    duration_minutes=rule.duration_minutes,
                    timezone=lo_timezone,
                    attendee_name=borrower_name,
                    attendee_email=borrower_email,
                    attendee_phone=borrower_phone,
                    loan_id=loan_id,
                    description=rule.description,
                    meeting_mode=rule.meeting_mode,
                    booked_by_ai=True,
                    ai_booking_context=ai_context,
                    internal_notes=f"Auto-scheduled by pipeline trigger on stage change to {rule.from_stage}",
                    external_source="pipeline_stage_change",
                    # Pipeline path manages its own transaction — trigger log
                    # entries and speed-to-lead metrics are written after this
                    # returns, and the caller commits.
                    auto_commit=False,
                    # Enable conflict + cross-source checks and lead linking
                    check_conflicts=True,
                    check_cross_source=True,
                    create_lead_if_missing=True,
                    generate_meeting_link=True,
                )

                if not result.success:
                    # Conflict or duplicate detected — treat as non-transient failure
                    logger.warning(
                        f"Auto-book blocked for loan {loan_id}: {result.error}"
                    )
                    last_error = Exception(result.error)
                    break

                appointment_id = result.appointment_id

                # Audit: structured log for AI pipeline booking path (non-blocking)
                try:
                    from services.scheduler_audit_logger import scheduler_audit
                    scheduler_audit.log_appointment_event(
                        db=self.db,
                        appointment_id=appointment_id,
                        event_type="created",
                        organization_id=self.organization_id,
                        booking_source="ai_pipeline",
                        details={
                            "trigger": "pipeline_stage_change",
                            "from_stage": rule.from_stage,
                            "appointment_type": rule.appointment_type,
                            "rule_required": rule.required,
                            "loan_id": loan_id,
                            "loan_officer_id": loan_officer_id,
                            "auto_booked": True,
                        },
                    )
                except Exception as audit_err:
                    logger.debug(f"Pipeline audit log failed (non-blocking): {audit_err}")

                logger.info(
                    f"Auto-booked appointment {appointment_id} ({rule.appointment_type}) "
                    f"for loan {loan_id}, LO {loan_officer_id}, org {self.organization_id}"
                )

                return {
                    "action": "auto_booked",
                    "appointment_id": appointment_id,
                    "appointment_type": rule.appointment_type,
                    "appointment_title": title,
                    "scheduled_start": target_start.isoformat(),
                    "scheduled_end": target_end.isoformat(),
                    "duration_minutes": rule.duration_minutes,
                    "required": rule.required,
                    "loan_id": loan_id,
                }

            except _TRANSIENT_ERRORS as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    backoff = min(_BASE_BACKOFF_SECONDS * (2 ** attempt), _MAX_BACKOFF_SECONDS)
                    logger.warning(
                        f"Transient error on auto-book attempt {attempt + 1}/{_MAX_RETRIES + 1} "
                        f"for loan {loan_id}: {e}. Retrying in {backoff}s..."
                    )
                    await asyncio.sleep(backoff)
                    continue
                # Exhausted retries — fall through to fallback below
                logger.exception(
                    f"Failed to auto-book appointment for loan {loan_id} after "
                    f"{_MAX_RETRIES + 1} attempts: {e}"
                )

            except Exception as e:
                # Non-transient error (validation, model loading, etc.) — do not retry
                logger.exception(f"Failed to auto-book appointment for loan {loan_id}: {e}")
                last_error = e
                break

        # Fall back to booking link if auto-book failed
        try:
            fallback_result = await self.send_booking_link(
                loan_id=loan_id,
                rule=rule,
                loan_officer_id=loan_officer_id,
                loan=loan,
            )
            return fallback_result
        except Exception as fallback_err:
            logger.exception(
                f"Fallback booking link also failed for loan {loan_id}: {fallback_err}"
            )
            # Notify LO since both auto-book AND fallback failed
            self._notify_lo_of_failure(
                loan_officer_id=loan_officer_id,
                loan_id=loan_id,
                rule=rule,
                error_message=(
                    f"Auto-book failed: {last_error}. "
                    f"Fallback booking link also failed: {fallback_err}"
                ),
            )
            raise

    async def send_booking_link(
        self,
        loan_id: int,
        rule: PipelineAppointmentRule,
        loan_officer_id: Optional[int],
        loan: Any = None,
    ) -> Dict[str, Any]:
        """Generate and queue a booking link to send to the borrower.

        Instead of auto-creating an appointment, this generates a booking URL
        that the borrower can use to pick their preferred time.

        Args:
            loan_id: Loan that triggered the rule.
            rule: The matching PipelineAppointmentRule.
            loan_officer_id: LO whose calendar to book against.
            loan: Pre-loaded Loan ORM object (optional).

        Returns:
            Dict with action details and booking link info.
        """
        if loan is None:
            loan = self._get_loan(loan_id)

        borrower_name = getattr(loan, "borrower_name", "Borrower") if loan else "Borrower"
        borrower_email = getattr(loan, "borrower_email", None) if loan else None
        loan_number = getattr(loan, "loan_number", "") if loan else ""

        # Generate a booking link with context
        # Format: /book/{lo_id}?type={appointment_type}&loan={loan_id}&ref={token}&expires={iso}
        # Default expiration: 7 days from now
        PIPELINE_BOOKING_LINK_EXPIRY_DAYS = 7
        booking_token = uuid.uuid4().hex[:12]
        link_expires_at = datetime.now(timezone.utc) + timedelta(days=PIPELINE_BOOKING_LINK_EXPIRY_DAYS)
        booking_link = (
            f"/book/{loan_officer_id}"
            f"?type={rule.appointment_type}"
            f"&loan_id={loan_id}"
            f"&ref={booking_token}"
            f"&duration={rule.duration_minutes}"
            f"&expires={link_expires_at.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )

        # Queue notification to borrower (async, non-blocking)
        notification_data = {
            "type": "pipeline_appointment_booking",
            "borrower_name": borrower_name,
            "borrower_email": borrower_email,
            "loan_number": loan_number,
            "appointment_title": rule.appointment_title,
            "appointment_description": rule.description,
            "booking_link": booking_link,
            "required": rule.required,
            "loan_officer_id": loan_officer_id,
        }

        try:
            from services.notification_service import notification_service
            if notification_service and borrower_email:
                await self._send_booking_notification(notification_data)
        except Exception as e:
            logger.warning(f"Failed to send booking notification for loan {loan_id}: {e}")

        logger.info(
            f"Booking link generated for loan {loan_id} ({rule.appointment_type}), "
            f"org {self.organization_id}"
        )

        return {
            "action": "booking_link_sent",
            "appointment_type": rule.appointment_type,
            "appointment_title": rule.appointment_title,
            "booking_link": booking_link,
            "booking_token": booking_token,
            "borrower_email": borrower_email,
            "required": rule.required,
            "loan_id": loan_id,
            "delay_hours": rule.delay_hours,
        }

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _get_loan(self, loan_id: int):
        """Load a Loan ORM object with tenant isolation."""
        try:
            from database.models.lead_loan import Loan
            return (
                self.db.query(Loan)
                .filter(
                    Loan.id == loan_id,
                    Loan.organization_id == self.organization_id,
                )
                .first()
            )
        except Exception as e:
            logger.exception(f"Failed to load loan {loan_id}: {e}")
            return None

    def _log_trigger(
        self,
        loan_id: int,
        loan_officer_id: Optional[int],
        old_stage: str,
        new_stage: str,
        rule: PipelineAppointmentRule,
        result: Dict[str, Any],
    ) -> None:
        """Write an audit record of the triggered action."""
        try:
            action = result.get("action", "unknown")
            status = "completed" if action not in ("error",) else "failed"

            log_entry = PipelineAppointmentTriggerLog(
                organization_id=self.organization_id,
                loan_id=loan_id,
                loan_officer_id=loan_officer_id,
                old_stage=old_stage,
                new_stage=new_stage,
                rule_from_stage=rule.from_stage,
                appointment_type=rule.appointment_type,
                appointment_title=rule.appointment_title,
                action_taken=action,
                appointment_id=result.get("appointment_id"),
                scheduled_for=(
                    datetime.fromisoformat(result["scheduled_start"])
                    if result.get("scheduled_start")
                    else None
                ),
                booking_link=result.get("booking_link"),
                status=status,
                error_message=result.get("error"),
                extra_data={
                    "required": rule.required,
                    "delay_hours": rule.delay_hours,
                    "auto_book": rule.auto_book,
                },
            )
            self.db.add(log_entry)
            # Don't commit here — let the caller's transaction manage the commit
        except Exception as e:
            logger.warning(f"Failed to log pipeline appointment trigger: {e}")

    @staticmethod
    def _snap_to_business_hours(dt: datetime) -> datetime:
        """Snap a datetime to the next available business hour slot.

        Business hours: Monday-Friday, 9:00 AM - 5:00 PM (in the original TZ).
        If the time falls outside business hours, advance to the next 9:00 AM weekday.
        Times are rounded up to the next 15-minute boundary.
        """
        # Round up to next 15-minute mark
        minutes = dt.minute
        remainder = minutes % 15
        if remainder > 0:
            dt = dt + timedelta(minutes=(15 - remainder))
        dt = dt.replace(second=0, microsecond=0)

        # Snap to business hours
        hour = dt.hour
        weekday = dt.weekday()  # 0=Monday, 6=Sunday

        if weekday >= 5:
            # Weekend — advance to Monday 9 AM
            days_until_monday = 7 - weekday
            dt = dt.replace(hour=9, minute=0) + timedelta(days=days_until_monday)
        elif hour < 9:
            dt = dt.replace(hour=9, minute=0)
        elif hour >= 17:
            # After 5 PM — advance to next business day 9 AM
            dt = dt + timedelta(days=1)
            dt = dt.replace(hour=9, minute=0)
            # Skip weekends
            if dt.weekday() >= 5:
                days_until_monday = 7 - dt.weekday()
                dt = dt + timedelta(days=days_until_monday)

        return dt

    async def _send_booking_notification(self, notification_data: Dict[str, Any]) -> None:
        """Send a booking link notification to the borrower via email.

        This is a best-effort operation — failures are logged but do not
        block the trigger flow.
        """
        try:
            from services.notification_service import notification_service as ns
            if ns is None:
                logger.debug("Notification service not available — skipping booking notification")
                return

            borrower_email = notification_data.get("borrower_email")
            if not borrower_email:
                logger.debug("No borrower email — skipping booking notification")
                return

            # Use the notification service's email channel
            await ns.send_notification(
                recipient_email=borrower_email,
                subject=f"Schedule Your {notification_data['appointment_title']}",
                template="pipeline_appointment_booking",
                context=notification_data,
            )
        except Exception as e:
            logger.warning(f"Booking notification send failed (non-fatal): {e}")

    def _get_lo_timezone(self, loan_officer_id: Optional[int]) -> str:
        """Get the loan officer's configured timezone from SchedulerConfig.

        Queries the scheduler_configs table for the LO's timezone setting,
        scoped by organization_id for tenant isolation. Falls back to
        _FALLBACK_TIMEZONE ("America/Chicago") if no config exists.
        """
        if not loan_officer_id:
            return _FALLBACK_TIMEZONE
        try:
            from database.models.scheduler import SchedulerConfig
            config = (
                self.db.query(SchedulerConfig)
                .filter(
                    SchedulerConfig.user_id == loan_officer_id,
                    SchedulerConfig.organization_id == self.organization_id,
                )
                .first()
            )
            if config and getattr(config, "timezone", None):
                return config.timezone
        except Exception as e:
            logger.warning(f"Failed to look up LO timezone for user {loan_officer_id}: {e}")
        return _FALLBACK_TIMEZONE

    def _record_speed_to_lead(
        self,
        loan_id: int,
        loan_officer_id: Optional[int],
        trigger_time: datetime,
        delivery_time: datetime,
        delivery_method: str,
        trigger_stage: str,
    ) -> None:
        """Record speed-to-lead timing metric (non-fatal, best-effort).

        Writes to speed_to_lead_metrics table to track how fast
        booking links / auto-booked appointments reach borrowers.
        """
        try:
            from services.speed_to_lead_tracker import record_trigger_timing
            # Fire-and-forget using asyncio — don't await in the sync caller
            import asyncio
            # DATA-015: Safely dispatch async coroutine regardless of event loop state.
            # asyncio.run() fails if called from a thread that already has a loop.
            _coro = record_trigger_timing(
                db=self.db,
                loan_id=loan_id,
                trigger_event="stage_change",
                trigger_time=trigger_time,
                delivery_time=delivery_time,
                delivery_method=delivery_method,
                organization_id=self.organization_id,
                loan_officer_id=loan_officer_id,
                trigger_stage=trigger_stage,
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_coro)
            except RuntimeError:
                # No running event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(_coro, loop=loop)
                    else:
                        loop.run_until_complete(_coro)
                except RuntimeError:
                    asyncio.run(_coro)
        except Exception as e:
            # Never let speed-to-lead tracking break the trigger flow
            logger.warning(f"Speed-to-lead recording failed (non-fatal) for loan {loan_id}: {e}")

    def _notify_lo_of_failure(
        self,
        loan_officer_id: Optional[int],
        loan_id: int,
        rule: PipelineAppointmentRule,
        error_message: str,
    ) -> None:
        """Create an in-app notification for the LO when auto-booking fails.

        Uses the Notification model (notifications table) so the failure
        surfaces in the LO's notification feed rather than being silently
        buried in server logs.
        """
        if not loan_officer_id:
            logger.warning(
                f"Cannot notify LO of appointment failure — no loan_officer_id "
                f"for loan {loan_id}, rule '{rule.appointment_type}'"
            )
            return

        try:
            from database.models.security import Notification

            notification = Notification(
                organization_id=self.organization_id,
                user_id=loan_officer_id,
                type="pipeline_appointment_failed",
                title=f"Auto-scheduling failed: {rule.appointment_title}",
                message=(
                    f"An automatic '{rule.appointment_title}' appointment could not be "
                    f"created for loan #{loan_id} after a stage change to "
                    f"{rule.from_stage}. Please schedule this appointment manually. "
                    f"Error: {error_message[:500]}"
                ),
                link=f"/pipeline/loans/{loan_id}",
                is_read=False,
            )
            self.db.add(notification)
            # Don't commit — let the caller's transaction manage the commit
            logger.info(
                f"Created failure notification for LO {loan_officer_id}, "
                f"loan {loan_id}, rule '{rule.appointment_type}'"
            )
        except Exception as e:
            logger.exception(
                f"Failed to create LO notification for appointment failure "
                f"(loan {loan_id}, rule '{rule.appointment_type}'): {e}"
            )
