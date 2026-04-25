"""
Smart Follow-Up Cadence Engine for Smart Docs V2

Orchestrates intelligent, multi-channel follow-up sequences for outstanding
document requests. Combines configurable cadence definitions with AI-optimized
send timing, TCPA-compliant outreach, and real-time response tracking.

Key capabilities:
    1. Multi-channel cadence sequences (email -> SMS -> call -> escalate)
    2. AI-optimized send timing based on borrower engagement history
    3. Auto-pause when borrower responds or uploads document
    4. Escalation to loan officer after N failed attempts
    5. TCPA-compliant quiet hours enforcement
    6. Weekend/holiday awareness
    7. Cadence templates for common scenarios
    8. A/B testing support for message templates
    9. Response tracking (email opens, link clicks, document uploads)
   10. Cadence analytics (response rates by channel, optimal timing)
   11. Bulk cadence management (start/stop for all docs on a loan)
   12. Default system cadences + org-customizable cadences

Architecture:
    - Async service with org_id isolation on every query
    - Integrates with TCPAComplianceService for consent/quiet-hours gating
    - Uses FollowupAutomationService for actual message dispatch
    - All mutations go through atomic_operation for consistency
    - Background scheduler calls process_due_executions() on a cron

Usage:
    from services.smart_docs.smart_cadence_service import SmartCadenceService

    service = SmartCadenceService(db, org_id=42)

    # Start a cadence for a borrower
    result = await service.start_cadence(
        cadence_id=1,
        loan_id=100,
        borrower_email="borrower@example.com",
        borrower_phone="+15551234567",
        borrower_name="Jane Doe",
        document_request_id=55,
    )

    # Process all due executions (cron)
    summary = await service.process_due_executions()

    # Borrower uploaded a document - auto-pause relevant cadences
    await service.handle_response(loan_id=100, response_type="doc_uploaded")
"""

import hashlib
import logging
import os
import random
from datetime import datetime, date, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, func, text
from sqlalchemy.orm import Session

from database.models.followup_cadence import FollowupCadence, FollowupExecution

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Dynamic US Federal Holiday Calculator
# ---------------------------------------------------------------------------

def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence of a weekday in a given month.

    Args:
        year: Calendar year.
        month: Month (1-12).
        weekday: Day of week (0=Monday, 6=Sunday).
        n: Which occurrence (1-based). Use -1 for last.

    Returns:
        The matching date.
    """
    import calendar
    if n == -1:
        last_day = calendar.monthrange(year, month)[1]
        d = date(year, month, last_day)
        while d.weekday() != weekday:
            d -= timedelta(days=1)
        return d
    first_day = date(year, month, 1)
    days_ahead = (weekday - first_day.weekday()) % 7
    first_occurrence = first_day + timedelta(days=days_ahead)
    return first_occurrence + timedelta(weeks=n - 1)


def _get_federal_holidays(year: int) -> set[date]:
    """Compute US federal holidays for a given year.

    Covers the 10 standard federal holidays:
      - New Year's Day (Jan 1)
      - MLK Day (3rd Monday of January)
      - Presidents' Day (3rd Monday of February)
      - Memorial Day (last Monday of May)
      - Independence Day (Jul 4)
      - Labor Day (1st Monday of September)
      - Columbus Day (2nd Monday of October)
      - Veterans Day (Nov 11)
      - Thanksgiving (4th Thursday of November)
      - Christmas Day (Dec 25)

    Returns:
        Set of date objects for all federal holidays in the given year.
    """
    holidays: set[date] = set()

    # Fixed-date holidays
    holidays.add(date(year, 1, 1))    # New Year's Day
    holidays.add(date(year, 7, 4))    # Independence Day
    holidays.add(date(year, 11, 11))  # Veterans Day
    holidays.add(date(year, 12, 25))  # Christmas Day

    # Floating holidays (weekday 0=Monday, 3=Thursday)
    holidays.add(_nth_weekday_of_month(year, 1, 0, 3))    # MLK Day: 3rd Monday of Jan
    holidays.add(_nth_weekday_of_month(year, 2, 0, 3))    # Presidents' Day: 3rd Monday of Feb
    holidays.add(_nth_weekday_of_month(year, 5, 0, -1))   # Memorial Day: last Monday of May
    holidays.add(_nth_weekday_of_month(year, 9, 0, 1))    # Labor Day: 1st Monday of Sep
    holidays.add(_nth_weekday_of_month(year, 10, 0, 2))   # Columbus Day: 2nd Monday of Oct
    holidays.add(_nth_weekday_of_month(year, 11, 3, 4))   # Thanksgiving: 4th Thursday of Nov

    return holidays

# Status constants (match FollowupExecution.status values)
_STATUS_ACTIVE = "ACTIVE"
_STATUS_COMPLETED = "COMPLETED"
_STATUS_CANCELLED = "CANCELLED"
_STATUS_ESCALATED = "ESCALATED"
_STATUS_PAUSED = "PAUSED"

_TERMINAL_STATUSES = {_STATUS_COMPLETED, _STATUS_CANCELLED, _STATUS_ESCALATED}

# Maximum number of executions to process in a single cron tick to prevent
# one org from monopolizing the worker.
_MAX_EXECUTIONS_PER_TICK = 200

# Default cadence definitions seeded for new orgs
_SYSTEM_CADENCE_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "cadence_name": "Missing Document - Standard",
        "description": "5-step cadence for initially requested documents. "
                       "Progresses from email to SMS to call, then escalates to LO.",
        "trigger_type": "DOC_REQUESTED",
        "channel_sequence": [
            {"day": 0, "channel": "email", "template": "initial_request", "ab_variant": None},
            {"day": 2, "channel": "sms", "template": "gentle_reminder_sms", "ab_variant": None},
            {"day": 5, "channel": "email", "template": "gentle_reminder", "ab_variant": None},
            {"day": 7, "channel": "call", "template": "appointment_offer", "ab_variant": None},
            {"day": 10, "channel": "escalate", "template": "escalation", "ab_variant": None},
        ],
        "max_attempts": 5,
        "escalation_after": 3,
    },
    {
        "cadence_name": "Overdue Document - Urgent",
        "description": "Aggressive 3-step cadence for overdue documents. "
                       "Same-day email + next-day SMS, then LO escalation.",
        "trigger_type": "DOC_OVERDUE",
        "channel_sequence": [
            {"day": 0, "channel": "email", "template": "urgent_reminder", "ab_variant": None},
            {"day": 1, "channel": "sms", "template": "urgent_reminder_sms", "ab_variant": None},
            {"day": 3, "channel": "escalate", "template": "escalation", "ab_variant": None},
        ],
        "max_attempts": 3,
        "escalation_after": 2,
    },
    {
        "cadence_name": "Expiring Document - Renewal",
        "description": "2-step cadence for documents about to expire. "
                       "Email notification followed by SMS reminder.",
        "trigger_type": "DOC_EXPIRING",
        "channel_sequence": [
            {"day": 0, "channel": "email", "template": "document_expired", "ab_variant": None},
            {"day": 3, "channel": "sms", "template": "document_expired_sms", "ab_variant": None},
        ],
        "max_attempts": 2,
        "escalation_after": 2,
    },
    {
        "cadence_name": "Condition Added",
        "description": "3-step cadence for new underwriting conditions. "
                       "Email with condition details, SMS nudge, then LO escalation.",
        "trigger_type": "CONDITION_ADDED",
        "channel_sequence": [
            {"day": 0, "channel": "email", "template": "initial_request", "ab_variant": None},
            {"day": 2, "channel": "sms", "template": "gentle_reminder_sms", "ab_variant": None},
            {"day": 5, "channel": "escalate", "template": "escalation", "ab_variant": None},
        ],
        "max_attempts": 3,
        "escalation_after": 2,
    },
    {
        "cadence_name": "Document Rejected - Resubmit",
        "description": "3-step cadence for rejected documents. "
                       "Email with rejection reason, SMS reminder, then appointment offer.",
        "trigger_type": "DOC_REJECTED",
        "channel_sequence": [
            {"day": 0, "channel": "email", "template": "document_rejected", "ab_variant": None},
            {"day": 3, "channel": "sms", "template": "document_rejected_sms", "ab_variant": None},
            {"day": 5, "channel": "call", "template": "appointment_offer", "ab_variant": None},
        ],
        "max_attempts": 3,
        "escalation_after": 3,
    },
]


# ===========================================================================
# Service
# ===========================================================================

class SmartCadenceService:
    """
    Async cadence engine with org-scoped tenant isolation.

    Every query filters on organization_id. All mutations use
    atomic_operation for transactional consistency.

    Args:
        db: SQLAlchemy Session.
        org_id: Organization ID for tenant isolation.
    """

    def __init__(self, db: Session, org_id: int):
        self.db = db
        self.org_id = org_id
        self._portal_base_url = os.getenv(
            "PORTAL_BASE_URL", "https://app.perenniaai.com/portal"
        )

    # ======================================================================
    # 1. CADENCE DEFINITION CRUD
    # ======================================================================

    async def list_cadences(
        self,
        trigger_type: Optional[str] = None,
        include_system: bool = True,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """List cadences available to this org (org-specific + system defaults).

        Args:
            trigger_type: Filter by trigger type (e.g. DOC_REQUESTED).
            include_system: Include system-default cadences.
            active_only: Only return active cadences.

        Returns:
            List of cadence definition dicts.
        """
        filters = []

        # Org-specific OR system defaults
        org_filter = FollowupCadence.organization_id == self.org_id
        if include_system:
            org_filter = (
                (FollowupCadence.organization_id == self.org_id)
                | (FollowupCadence.is_system == True)
            )
        filters.append(org_filter)

        if trigger_type:
            filters.append(FollowupCadence.trigger_type == trigger_type)
        if active_only:
            filters.append(FollowupCadence.is_active == True)

        cadences = (
            self.db.query(FollowupCadence)
            .filter(and_(*filters))
            .order_by(FollowupCadence.is_system.desc(), FollowupCadence.cadence_name.asc())
            .all()
        )

        return [self._serialize_cadence(c) for c in cadences]

    async def get_cadence(self, cadence_id: int) -> Optional[Dict[str, Any]]:
        """Get a single cadence by ID (must belong to this org or be system).

        Args:
            cadence_id: Cadence primary key.

        Returns:
            Cadence dict or None.
        """
        cadence = (
            self.db.query(FollowupCadence)
            .filter(
                FollowupCadence.id == cadence_id,
                (FollowupCadence.organization_id == self.org_id)
                | (FollowupCadence.is_system == True),
            )
            .first()
        )
        if not cadence:
            return None
        return self._serialize_cadence(cadence)

    async def create_cadence(
        self,
        cadence_name: str,
        trigger_type: str,
        channel_sequence: List[Dict[str, Any]],
        max_attempts: int = 5,
        escalation_after: int = 3,
        quiet_hours_start: int = 20,
        quiet_hours_end: int = 8,
        weekend_enabled: bool = False,
        holiday_aware: bool = True,
        description: Optional[str] = None,
        created_by_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a new org-specific cadence.

        Args:
            cadence_name: Human-readable name.
            trigger_type: When to trigger (DOC_REQUESTED, DOC_OVERDUE, etc.).
            channel_sequence: Ordered list of step definitions.
            max_attempts: Max outreach attempts.
            escalation_after: Escalate after N unanswered attempts.
            quiet_hours_start: Hour (0-23) to stop sending.
            quiet_hours_end: Hour (0-23) to resume sending.
            weekend_enabled: Allow weekend sends.
            holiday_aware: Skip federal holidays.
            description: Optional description.
            created_by_user_id: User who created this cadence.

        Returns:
            Created cadence dict.
        """
        from services.smart_docs.db_transaction import atomic_operation

        # Validate channel_sequence structure
        self._validate_channel_sequence(channel_sequence)

        cadence = FollowupCadence(
            organization_id=self.org_id,
            cadence_name=cadence_name,
            description=description,
            trigger_type=trigger_type,
            channel_sequence=channel_sequence,
            max_attempts=max_attempts,
            escalation_after=escalation_after,
            quiet_hours_start=quiet_hours_start,
            quiet_hours_end=quiet_hours_end,
            weekend_enabled=weekend_enabled,
            holiday_aware=holiday_aware,
            is_active=True,
            is_system=False,
            created_by_user_id=created_by_user_id,
        )

        with atomic_operation(self.db):
            self.db.add(cadence)
            self.db.flush()

        logger.info(
            "Created cadence %d '%s' (trigger=%s, steps=%d) for org %d",
            cadence.id, cadence_name, trigger_type, len(channel_sequence), self.org_id,
        )
        return self._serialize_cadence(cadence)

    async def update_cadence(
        self,
        cadence_id: int,
        **updates: Any,
    ) -> Optional[Dict[str, Any]]:
        """Update an org-owned cadence (system cadences cannot be edited).

        Args:
            cadence_id: Cadence primary key.
            **updates: Fields to update.

        Returns:
            Updated cadence dict or None if not found.

        Raises:
            ValueError: If attempting to edit a system cadence.
        """
        from services.smart_docs.db_transaction import atomic_operation

        cadence = (
            self.db.query(FollowupCadence)
            .filter(
                FollowupCadence.id == cadence_id,
                FollowupCadence.organization_id == self.org_id,
            )
            .first()
        )
        if not cadence:
            return None

        if cadence.is_system:
            raise ValueError("Cannot edit system cadences. Clone it to create an org-specific version.")

        allowed_fields = {
            "cadence_name", "description", "trigger_type", "channel_sequence",
            "max_attempts", "escalation_after", "quiet_hours_start",
            "quiet_hours_end", "weekend_enabled", "holiday_aware",
            "is_active", "ab_test_enabled", "ab_test_name", "ab_test_split_pct",
        }

        with atomic_operation(self.db):
            for field_name, value in updates.items():
                if field_name in allowed_fields:
                    if field_name == "channel_sequence":
                        self._validate_channel_sequence(value)
                    setattr(cadence, field_name, value)
            cadence.updated_at = datetime.now(timezone.utc)
            self.db.flush()

        logger.info("Updated cadence %d for org %d", cadence_id, self.org_id)
        return self._serialize_cadence(cadence)

    async def clone_system_cadence(
        self,
        system_cadence_id: int,
        new_name: Optional[str] = None,
        created_by_user_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Clone a system cadence into an org-specific version for customization.

        Args:
            system_cadence_id: ID of the system cadence to clone.
            new_name: Optional custom name (defaults to original + " (Custom)").
            created_by_user_id: User performing the clone.

        Returns:
            New cadence dict or None if source not found.
        """
        source = (
            self.db.query(FollowupCadence)
            .filter(
                FollowupCadence.id == system_cadence_id,
                FollowupCadence.is_system == True,
            )
            .first()
        )
        if not source:
            return None

        return await self.create_cadence(
            cadence_name=new_name or f"{source.cadence_name} (Custom)",
            trigger_type=source.trigger_type,
            channel_sequence=source.channel_sequence or [],
            max_attempts=source.max_attempts or 5,
            escalation_after=source.escalation_after or 3,
            quiet_hours_start=source.quiet_hours_start or 20,
            quiet_hours_end=source.quiet_hours_end or 8,
            weekend_enabled=source.weekend_enabled or False,
            holiday_aware=source.holiday_aware if source.holiday_aware is not None else True,
            description=source.description,
            created_by_user_id=created_by_user_id,
        )

    async def deactivate_cadence(self, cadence_id: int) -> bool:
        """Deactivate a cadence (soft delete). Active executions are not affected.

        Args:
            cadence_id: Cadence primary key.

        Returns:
            True if deactivated, False if not found.
        """
        from services.smart_docs.db_transaction import atomic_operation

        cadence = (
            self.db.query(FollowupCadence)
            .filter(
                FollowupCadence.id == cadence_id,
                FollowupCadence.organization_id == self.org_id,
            )
            .first()
        )
        if not cadence:
            return False

        with atomic_operation(self.db):
            cadence.is_active = False
            cadence.updated_at = datetime.now(timezone.utc)

        logger.info("Deactivated cadence %d for org %d", cadence_id, self.org_id)
        return True

    # ======================================================================
    # 2. CADENCE EXECUTION LIFECYCLE
    # ======================================================================

    async def start_cadence(
        self,
        cadence_id: int,
        loan_id: int,
        borrower_email: Optional[str] = None,
        borrower_phone: Optional[str] = None,
        borrower_name: Optional[str] = None,
        document_request_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Start a cadence execution for a specific borrower + loan.

        Checks for duplicate active executions on the same cadence + loan
        to prevent double-sending.

        Args:
            cadence_id: Which cadence to execute.
            loan_id: Loan this cadence relates to.
            borrower_email: Borrower email for email steps.
            borrower_phone: Borrower phone for SMS/call steps.
            borrower_name: Borrower display name.
            document_request_id: Specific doc request triggering this.

        Returns:
            Execution dict with ID and schedule.

        Raises:
            ValueError: If cadence not found or not accessible.
        """
        from services.smart_docs.db_transaction import atomic_operation

        # Load cadence definition
        cadence = (
            self.db.query(FollowupCadence)
            .filter(
                FollowupCadence.id == cadence_id,
                FollowupCadence.is_active == True,
                (FollowupCadence.organization_id == self.org_id)
                | (FollowupCadence.is_system == True),
            )
            .first()
        )
        if not cadence:
            raise ValueError(f"Cadence {cadence_id} not found or not active for org {self.org_id}")

        # Check for duplicate: active execution on same cadence + loan + doc request
        existing = (
            self.db.query(FollowupExecution)
            .filter(
                FollowupExecution.organization_id == self.org_id,
                FollowupExecution.cadence_id == cadence_id,
                FollowupExecution.loan_id == loan_id,
                FollowupExecution.status == _STATUS_ACTIVE,
            )
        )
        if document_request_id is not None:
            existing = existing.filter(
                FollowupExecution.document_request_id == document_request_id,
            )
        if existing.first():
            logger.info(
                "Duplicate cadence execution blocked: cadence=%d loan=%d doc_req=%s org=%d",
                cadence_id, loan_id, document_request_id, self.org_id,
            )
            return {
                "status": "duplicate",
                "message": "An active execution already exists for this cadence and loan",
            }

        # Determine A/B variant
        ab_variant = self._assign_ab_variant(cadence, borrower_email)

        # Calculate first send time using AI-optimized timing
        first_step = (cadence.channel_sequence or [{}])[0]
        first_day_offset = first_step.get("day", 0)
        optimal_send_time = await self._calculate_optimal_send_time(
            cadence=cadence,
            borrower_email=borrower_email,
            borrower_phone=borrower_phone,
            day_offset=first_day_offset,
        )

        execution = FollowupExecution(
            organization_id=self.org_id,
            cadence_id=cadence_id,
            loan_id=loan_id,
            document_request_id=document_request_id,
            borrower_email=borrower_email,
            borrower_phone=borrower_phone,
            borrower_name=borrower_name,
            current_step=0,
            status=_STATUS_ACTIVE,
            next_send_at=optimal_send_time,
            attempts_made=0,
            consecutive_failures=0,
            response_received=False,
            ab_variant=ab_variant,
            execution_log=[],
        )

        with atomic_operation(self.db):
            self.db.add(execution)
            self.db.flush()

            # Update cadence analytics
            cadence.total_executions = (cadence.total_executions or 0) + 1

        logger.info(
            "Started cadence execution %d (cadence=%d, loan=%d, org=%d, variant=%s, next=%s)",
            execution.id, cadence_id, loan_id, self.org_id, ab_variant,
            optimal_send_time.isoformat() if optimal_send_time else "immediate",
        )

        return self._serialize_execution(execution)

    async def start_cadence_by_trigger(
        self,
        trigger_type: str,
        loan_id: int,
        borrower_email: Optional[str] = None,
        borrower_phone: Optional[str] = None,
        borrower_name: Optional[str] = None,
        document_request_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Start all matching cadences for a given trigger event.

        Looks up active cadences for this trigger_type (org-specific first,
        then system defaults) and starts executions for each.

        Args:
            trigger_type: DOC_REQUESTED, DOC_OVERDUE, DOC_EXPIRING, etc.
            loan_id: Loan ID.
            borrower_email: Borrower email.
            borrower_phone: Borrower phone.
            borrower_name: Borrower name.
            document_request_id: Specific doc request ID.

        Returns:
            List of started execution dicts.
        """
        # Prefer org-specific cadence; fall back to system default
        cadences = (
            self.db.query(FollowupCadence)
            .filter(
                FollowupCadence.trigger_type == trigger_type,
                FollowupCadence.is_active == True,
                (FollowupCadence.organization_id == self.org_id)
                | (FollowupCadence.is_system == True),
            )
            .order_by(
                # Org-specific cadences take priority
                case(
                    (FollowupCadence.organization_id == self.org_id, 0),
                    else_=1,
                ).asc(),
            )
            .all()
        )

        if not cadences:
            logger.warning(
                "No cadences found for trigger=%s org=%d", trigger_type, self.org_id,
            )
            return []

        # If org has its own cadence for this trigger, skip system defaults
        org_cadences = [c for c in cadences if c.organization_id == self.org_id]
        selected = org_cadences if org_cadences else cadences

        results = []
        for cadence in selected:
            try:
                result = await self.start_cadence(
                    cadence_id=cadence.id,
                    loan_id=loan_id,
                    borrower_email=borrower_email,
                    borrower_phone=borrower_phone,
                    borrower_name=borrower_name,
                    document_request_id=document_request_id,
                )
                results.append(result)
            except Exception as e:
                logger.exception(
                    "Failed to start cadence %d for trigger %s: %s",
                    cadence.id, trigger_type, e,
                )

        return results

    # ======================================================================
    # 3. EXECUTION PROCESSING (scheduler/cron entry point)
    # ======================================================================

    async def process_due_executions(self) -> Dict[str, Any]:
        """Main scheduler entry point. Process all due executions for this org.

        Called periodically by a background task (e.g., every 5 minutes).
        Finds executions where status=ACTIVE and next_send_at <= now(),
        then executes the next step for each.

        Returns:
            Summary dict with counts of processed, succeeded, failed, etc.
        """
        now = datetime.now(timezone.utc)

        due_executions = (
            self.db.query(FollowupExecution)
            .filter(
                FollowupExecution.organization_id == self.org_id,
                FollowupExecution.status == _STATUS_ACTIVE,
                FollowupExecution.next_send_at <= now,
            )
            .order_by(FollowupExecution.next_send_at.asc())
            .limit(_MAX_EXECUTIONS_PER_TICK)
            .all()
        )

        summary = {
            "org_id": self.org_id,
            "processed": 0,
            "sent": 0,
            "skipped_quiet_hours": 0,
            "skipped_weekend": 0,
            "skipped_holiday": 0,
            "skipped_tcpa": 0,
            "failed": 0,
            "completed": 0,
            "escalated": 0,
        }

        for execution in due_executions:
            try:
                step_result = await self._execute_next_step(execution)
                summary["processed"] += 1

                outcome = step_result.get("outcome", "unknown")
                if outcome == "sent":
                    summary["sent"] += 1
                elif outcome == "skipped_quiet_hours":
                    summary["skipped_quiet_hours"] += 1
                elif outcome == "skipped_weekend":
                    summary["skipped_weekend"] += 1
                elif outcome == "skipped_holiday":
                    summary["skipped_holiday"] += 1
                elif outcome == "skipped_tcpa":
                    summary["skipped_tcpa"] += 1
                elif outcome == "completed":
                    summary["completed"] += 1
                elif outcome == "escalated":
                    summary["escalated"] += 1
                elif outcome == "failed":
                    summary["failed"] += 1

            except Exception as e:
                logger.exception(
                    "Error processing execution %d: %s", execution.id, e,
                )
                summary["processed"] += 1
                summary["failed"] += 1

        if summary["processed"] > 0:
            logger.info(
                "Cadence engine processed %d executions for org %d: "
                "sent=%d, skipped=%d, failed=%d, completed=%d, escalated=%d",
                summary["processed"], self.org_id,
                summary["sent"],
                summary["skipped_quiet_hours"] + summary["skipped_weekend"] + summary["skipped_holiday"] + summary["skipped_tcpa"],
                summary["failed"],
                summary["completed"],
                summary["escalated"],
            )

        return summary

    async def _execute_next_step(
        self, execution: FollowupExecution,
    ) -> Dict[str, Any]:
        """Execute the next step in a cadence for a given execution.

        Handles quiet hours, weekends, holidays, TCPA checks, message dispatch,
        and step advancement atomically.

        Args:
            execution: The FollowupExecution row to advance.

        Returns:
            Dict with outcome and details.
        """
        from services.smart_docs.db_transaction import atomic_operation

        now = datetime.now(timezone.utc)

        # Load cadence definition
        cadence = (
            self.db.query(FollowupCadence)
            .filter(FollowupCadence.id == execution.cadence_id)
            .first()
        )
        if not cadence:
            logger.error(
                "Cadence %d not found for execution %d, cancelling",
                execution.cadence_id, execution.id,
            )
            with atomic_operation(self.db):
                execution.status = _STATUS_CANCELLED
                execution.cancel_reason = "Cadence definition deleted"
                execution.cancelled_at = now
            return {"outcome": "failed", "reason": "cadence_not_found"}

        sequence = cadence.channel_sequence or []
        step_index = execution.current_step or 0

        # Check if all steps exhausted
        if step_index >= len(sequence):
            with atomic_operation(self.db):
                self._complete_execution(execution, "all_steps_exhausted")
            return {"outcome": "completed", "reason": "all_steps_exhausted"}

        step = sequence[step_index]
        channel = step.get("channel", "email")
        template_slug = step.get("template", "gentle_reminder")

        # ----- Pre-send checks -----

        # 1. Quiet hours check (cadence-level + TCPA)
        if self._is_quiet_hours(cadence, execution.borrower_phone):
            # Reschedule to next available window
            next_available = self._next_available_send_time(cadence, execution.borrower_phone)
            with atomic_operation(self.db):
                execution.next_send_at = next_available
            return {
                "outcome": "skipped_quiet_hours",
                "rescheduled_to": next_available.isoformat(),
            }

        # 2. Weekend check
        if not cadence.weekend_enabled and self._is_weekend(now):
            next_monday = self._next_weekday(now)
            rescheduled = next_monday.replace(
                hour=cadence.quiet_hours_end or 8, minute=0, second=0, microsecond=0,
            )
            with atomic_operation(self.db):
                execution.next_send_at = rescheduled
            return {
                "outcome": "skipped_weekend",
                "rescheduled_to": rescheduled.isoformat(),
            }

        # 3. Holiday check
        if cadence.holiday_aware and self._is_holiday(now):
            next_day = (now + timedelta(days=1)).replace(
                hour=cadence.quiet_hours_end or 8, minute=0, second=0, microsecond=0,
            )
            with atomic_operation(self.db):
                execution.next_send_at = next_day
            return {
                "outcome": "skipped_holiday",
                "rescheduled_to": next_day.isoformat(),
            }

        # 4. TCPA compliance check for SMS/call channels
        if channel in ("sms", "call") and execution.borrower_phone:
            tcpa_result = self._check_tcpa_compliance(
                phone=execution.borrower_phone,
                channel=channel,
            )
            if not tcpa_result["allowed"]:
                # Log but don't count as attempt -- reschedule
                next_window = self._next_available_send_time(cadence, execution.borrower_phone)
                with atomic_operation(self.db):
                    execution.next_send_at = next_window
                    log_entry = {
                        "step": step_index,
                        "channel": channel,
                        "attempted_at": now.isoformat(),
                        "status": "blocked_tcpa",
                        "blockers": tcpa_result.get("blockers", []),
                    }
                    execution.execution_log = (execution.execution_log or []) + [log_entry]
                return {
                    "outcome": "skipped_tcpa",
                    "blockers": tcpa_result.get("blockers", []),
                    "rescheduled_to": next_window.isoformat(),
                }

        # 5. Check if max attempts reached
        if (execution.attempts_made or 0) >= (cadence.max_attempts or 5):
            with atomic_operation(self.db):
                self._complete_execution(execution, "max_attempts_reached")
            return {"outcome": "completed", "reason": "max_attempts_reached"}

        # ----- Execute the step -----

        # Resolve A/B template variant
        effective_template = template_slug
        step_ab = step.get("ab_variant")
        if step_ab and execution.ab_variant == "B" and step_ab == "B":
            effective_template = f"{template_slug}_b"

        dispatch_result = await self._dispatch_step(
            execution=execution,
            cadence=cadence,
            channel=channel,
            template_slug=effective_template,
            step_index=step_index,
        )

        send_success = dispatch_result.get("status") in ("sent", "delivered", "queued")

        # ----- Post-send: advance execution -----

        with atomic_operation(self.db):
            log_entry = {
                "step": step_index,
                "channel": channel,
                "template": effective_template,
                "sent_at": now.isoformat(),
                "status": dispatch_result.get("status", "unknown"),
                "ab_variant": execution.ab_variant,
            }
            execution.execution_log = (execution.execution_log or []) + [log_entry]

            execution.last_sent_at = now
            execution.attempts_made = (execution.attempts_made or 0) + 1

            if send_success:
                execution.consecutive_failures = 0
            else:
                execution.consecutive_failures = (execution.consecutive_failures or 0) + 1

            # Check if we should escalate
            if (
                (execution.attempts_made or 0) >= (cadence.escalation_after or 3)
                and not execution.response_received
                and channel != "escalate"
            ):
                await self._escalate_execution(execution, cadence)
                return {"outcome": "escalated", "step": step_index}

            # Advance to next step
            next_step_index = step_index + 1
            execution.current_step = next_step_index

            if next_step_index >= len(sequence):
                self._complete_execution(execution, "all_steps_completed")
                return {"outcome": "completed", "reason": "all_steps_completed"}

            # Calculate next send time
            next_step = sequence[next_step_index]
            next_day_offset = next_step.get("day", 0)
            current_day_offset = step.get("day", 0)
            days_delta = max(next_day_offset - current_day_offset, 1)

            next_send = await self._calculate_optimal_send_time(
                cadence=cadence,
                borrower_email=execution.borrower_email,
                borrower_phone=execution.borrower_phone,
                day_offset=days_delta,
                base_time=now,
            )
            execution.next_send_at = next_send

        return {
            "outcome": "sent",
            "step": step_index,
            "channel": channel,
            "template": effective_template,
            "next_send_at": execution.next_send_at.isoformat() if execution.next_send_at else None,
            "dispatch_result": dispatch_result,
        }

    # ======================================================================
    # 4. RESPONSE HANDLING (auto-pause / complete)
    # ======================================================================

    async def handle_response(
        self,
        loan_id: int,
        response_type: str,
        document_request_id: Optional[int] = None,
        borrower_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle a borrower response event. Auto-pauses or completes cadences.

        Called when:
        - Borrower uploads a document (response_type="doc_uploaded")
        - Borrower clicks a link in a follow-up email ("link_clicked")
        - Borrower replies to an email ("email_reply")
        - Borrower calls back ("call_back")
        - Borrower books an appointment ("appointment_booked")

        Args:
            loan_id: Loan the response relates to.
            response_type: Type of response.
            document_request_id: Specific doc request, if applicable.
            borrower_email: Email that responded, for matching.

        Returns:
            Summary of affected executions.
        """
        from services.smart_docs.db_transaction import atomic_operation

        now = datetime.now(timezone.utc)

        # Find active executions for this loan
        query = self.db.query(FollowupExecution).filter(
            FollowupExecution.organization_id == self.org_id,
            FollowupExecution.loan_id == loan_id,
            FollowupExecution.status.in_([_STATUS_ACTIVE, _STATUS_PAUSED]),
        )

        if document_request_id is not None:
            query = query.filter(
                FollowupExecution.document_request_id == document_request_id,
            )

        executions = query.all()
        affected = []

        with atomic_operation(self.db):
            for execution in executions:
                execution.response_received = True
                execution.response_type = response_type
                execution.response_at = now

                # Track engagement metrics
                if response_type == "doc_uploaded":
                    execution.docs_uploaded = (execution.docs_uploaded or 0) + 1
                    # Complete the cadence -- the document was received
                    self._complete_execution(execution, f"borrower_{response_type}")
                elif response_type == "link_clicked":
                    execution.links_clicked = (execution.links_clicked or 0) + 1
                    # Pause -- borrower is engaging but hasn't submitted yet
                    execution.status = _STATUS_PAUSED
                    execution.paused_at = now
                    execution.pause_reason = "Borrower clicked link"
                    execution.next_send_at = None
                elif response_type == "email_reply":
                    # Pause -- LO should handle the reply
                    execution.status = _STATUS_PAUSED
                    execution.paused_at = now
                    execution.pause_reason = "Borrower replied to email"
                    execution.next_send_at = None
                elif response_type == "appointment_booked":
                    execution.status = _STATUS_PAUSED
                    execution.paused_at = now
                    execution.pause_reason = "Borrower booked appointment"
                    execution.next_send_at = None
                else:
                    # Generic response -- pause for review
                    execution.status = _STATUS_PAUSED
                    execution.paused_at = now
                    execution.pause_reason = f"Borrower response: {response_type}"
                    execution.next_send_at = None

                # Update cadence-level analytics
                cadence = (
                    self.db.query(FollowupCadence)
                    .filter(FollowupCadence.id == execution.cadence_id)
                    .first()
                )
                if cadence:
                    cadence.total_responses = (cadence.total_responses or 0) + 1
                    # Update average response time
                    if execution.created_at:
                        response_hours = (now - execution.created_at).total_seconds() / 3600.0
                        if cadence.avg_response_time_hours:
                            # Running average
                            total_responses = cadence.total_responses or 1
                            cadence.avg_response_time_hours = (
                                (cadence.avg_response_time_hours * (total_responses - 1) + response_hours)
                                / total_responses
                            )
                        else:
                            cadence.avg_response_time_hours = response_hours

                affected.append({
                    "execution_id": execution.id,
                    "cadence_id": execution.cadence_id,
                    "new_status": execution.status,
                    "response_type": response_type,
                })

        logger.info(
            "Handled borrower response '%s' for loan %d org %d: %d executions affected",
            response_type, loan_id, self.org_id, len(affected),
        )

        return {
            "loan_id": loan_id,
            "response_type": response_type,
            "affected_count": len(affected),
            "affected": affected,
        }

    async def track_email_open(
        self, execution_id: int,
    ) -> bool:
        """Track an email open event for response analytics.

        Args:
            execution_id: Execution that had an email opened.

        Returns:
            True if tracked successfully.
        """
        from services.smart_docs.db_transaction import atomic_operation

        execution = (
            self.db.query(FollowupExecution)
            .filter(
                FollowupExecution.id == execution_id,
                FollowupExecution.organization_id == self.org_id,
            )
            .first()
        )
        if not execution:
            return False

        with atomic_operation(self.db):
            execution.emails_opened = (execution.emails_opened or 0) + 1

        return True

    async def track_link_click(
        self, execution_id: int,
    ) -> bool:
        """Track a link click event. Auto-pauses the cadence.

        Args:
            execution_id: Execution that had a link clicked.

        Returns:
            True if tracked successfully.
        """
        execution = (
            self.db.query(FollowupExecution)
            .filter(
                FollowupExecution.id == execution_id,
                FollowupExecution.organization_id == self.org_id,
            )
            .first()
        )
        if not execution:
            return False

        await self.handle_response(
            loan_id=execution.loan_id,
            response_type="link_clicked",
            document_request_id=execution.document_request_id,
        )
        return True

    # ======================================================================
    # 5. BULK CADENCE MANAGEMENT
    # ======================================================================

    async def pause_all_for_loan(
        self, loan_id: int, reason: str = "Manual pause",
    ) -> int:
        """Pause all active cadence executions for a loan.

        Args:
            loan_id: Loan to pause cadences for.
            reason: Reason for the pause.

        Returns:
            Number of executions paused.
        """
        from services.smart_docs.db_transaction import atomic_operation

        now = datetime.now(timezone.utc)
        executions = (
            self.db.query(FollowupExecution)
            .filter(
                FollowupExecution.organization_id == self.org_id,
                FollowupExecution.loan_id == loan_id,
                FollowupExecution.status == _STATUS_ACTIVE,
            )
            .all()
        )

        with atomic_operation(self.db):
            for ex in executions:
                ex.status = _STATUS_PAUSED
                ex.paused_at = now
                ex.pause_reason = reason
                ex.next_send_at = None

        logger.info(
            "Paused %d cadence executions for loan %d org %d: %s",
            len(executions), loan_id, self.org_id, reason,
        )
        return len(executions)

    async def resume_all_for_loan(self, loan_id: int) -> int:
        """Resume all paused cadence executions for a loan.

        Recalculates next_send_at for each resumed execution.

        Args:
            loan_id: Loan to resume cadences for.

        Returns:
            Number of executions resumed.
        """
        from services.smart_docs.db_transaction import atomic_operation

        now = datetime.now(timezone.utc)
        executions = (
            self.db.query(FollowupExecution)
            .filter(
                FollowupExecution.organization_id == self.org_id,
                FollowupExecution.loan_id == loan_id,
                FollowupExecution.status == _STATUS_PAUSED,
            )
            .all()
        )

        with atomic_operation(self.db):
            for ex in executions:
                cadence = (
                    self.db.query(FollowupCadence)
                    .filter(FollowupCadence.id == ex.cadence_id)
                    .first()
                )
                ex.status = _STATUS_ACTIVE
                ex.paused_at = None
                ex.pause_reason = None
                # Schedule next send immediately (within compliance windows)
                if cadence:
                    next_send = self._next_available_send_time(cadence, ex.borrower_phone)
                else:
                    next_send = now
                ex.next_send_at = next_send

        logger.info(
            "Resumed %d cadence executions for loan %d org %d",
            len(executions), loan_id, self.org_id,
        )
        return len(executions)

    async def cancel_all_for_loan(
        self, loan_id: int, reason: str = "Manual cancellation",
    ) -> int:
        """Cancel all active/paused cadence executions for a loan.

        Args:
            loan_id: Loan to cancel cadences for.
            reason: Cancellation reason.

        Returns:
            Number of executions cancelled.
        """
        from services.smart_docs.db_transaction import atomic_operation

        now = datetime.now(timezone.utc)
        executions = (
            self.db.query(FollowupExecution)
            .filter(
                FollowupExecution.organization_id == self.org_id,
                FollowupExecution.loan_id == loan_id,
                FollowupExecution.status.in_([_STATUS_ACTIVE, _STATUS_PAUSED]),
            )
            .all()
        )

        with atomic_operation(self.db):
            for ex in executions:
                ex.status = _STATUS_CANCELLED
                ex.cancelled_at = now
                ex.cancel_reason = reason
                ex.next_send_at = None

        logger.info(
            "Cancelled %d cadence executions for loan %d org %d: %s",
            len(executions), loan_id, self.org_id, reason,
        )
        return len(executions)

    async def cancel_execution(
        self, execution_id: int, reason: str = "Manual cancellation",
    ) -> bool:
        """Cancel a single execution.

        Args:
            execution_id: Execution to cancel.
            reason: Cancellation reason.

        Returns:
            True if cancelled, False if not found.
        """
        from services.smart_docs.db_transaction import atomic_operation

        execution = (
            self.db.query(FollowupExecution)
            .filter(
                FollowupExecution.id == execution_id,
                FollowupExecution.organization_id == self.org_id,
                FollowupExecution.status.in_([_STATUS_ACTIVE, _STATUS_PAUSED]),
            )
            .first()
        )
        if not execution:
            return False

        now = datetime.now(timezone.utc)
        with atomic_operation(self.db):
            execution.status = _STATUS_CANCELLED
            execution.cancelled_at = now
            execution.cancel_reason = reason
            execution.next_send_at = None

        logger.info("Cancelled execution %d for org %d: %s", execution_id, self.org_id, reason)
        return True

    # ======================================================================
    # 6. ANALYTICS
    # ======================================================================

    async def get_cadence_analytics(
        self, cadence_id: Optional[int] = None, days: int = 30,
    ) -> Dict[str, Any]:
        """Get analytics for cadence performance.

        Args:
            cadence_id: Specific cadence to analyze (None for all).
            days: Lookback window.

        Returns:
            Analytics dict with response rates, channel effectiveness,
            timing patterns, and A/B test results.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        filters = [
            FollowupExecution.organization_id == self.org_id,
            FollowupExecution.created_at >= cutoff,
        ]
        if cadence_id:
            filters.append(FollowupExecution.cadence_id == cadence_id)

        executions = (
            self.db.query(FollowupExecution)
            .filter(and_(*filters))
            .all()
        )

        if not executions:
            return {
                "period_days": days,
                "total_executions": 0,
                "message": "No executions found in the specified period",
            }

        total = len(executions)
        completed = sum(1 for e in executions if e.status == _STATUS_COMPLETED)
        active = sum(1 for e in executions if e.status == _STATUS_ACTIVE)
        cancelled = sum(1 for e in executions if e.status == _STATUS_CANCELLED)
        escalated = sum(1 for e in executions if e.status == _STATUS_ESCALATED)
        responded = sum(1 for e in executions if e.response_received)

        # Response rate by channel (from execution_log)
        channel_stats: Dict[str, Dict[str, int]] = {}
        for ex in executions:
            for entry in (ex.execution_log or []):
                ch = entry.get("channel", "unknown")
                if ch not in channel_stats:
                    channel_stats[ch] = {
                        "sent": 0, "delivered": 0, "failed": 0, "blocked": 0,
                    }
                status = entry.get("status", "unknown")
                if status in ("sent", "delivered", "queued"):
                    channel_stats[ch]["sent"] += 1
                elif status == "failed":
                    channel_stats[ch]["failed"] += 1
                elif status.startswith("blocked"):
                    channel_stats[ch]["blocked"] += 1

        # Average response time
        response_times = []
        for ex in executions:
            if ex.response_received and ex.response_at and ex.created_at:
                hours = (ex.response_at - ex.created_at).total_seconds() / 3600.0
                response_times.append(hours)

        avg_response_time = (
            round(sum(response_times) / len(response_times), 1)
            if response_times else None
        )

        # A/B test results
        ab_results = {}
        variant_a = [e for e in executions if e.ab_variant == "A"]
        variant_b = [e for e in executions if e.ab_variant == "B"]
        if variant_a or variant_b:
            ab_results = {
                "variant_a": {
                    "count": len(variant_a),
                    "response_rate": round(
                        sum(1 for e in variant_a if e.response_received) / max(len(variant_a), 1) * 100, 1
                    ),
                    "avg_opens": round(
                        sum(e.emails_opened or 0 for e in variant_a) / max(len(variant_a), 1), 1
                    ),
                },
                "variant_b": {
                    "count": len(variant_b),
                    "response_rate": round(
                        sum(1 for e in variant_b if e.response_received) / max(len(variant_b), 1) * 100, 1
                    ),
                    "avg_opens": round(
                        sum(e.emails_opened or 0 for e in variant_b) / max(len(variant_b), 1), 1
                    ),
                },
            }

        # Engagement metrics aggregate
        total_opens = sum(e.emails_opened or 0 for e in executions)
        total_clicks = sum(e.links_clicked or 0 for e in executions)
        total_docs = sum(e.docs_uploaded or 0 for e in executions)

        # Most effective channel
        best_channel = None
        best_rate = 0
        for ch, stats in channel_stats.items():
            sent = stats.get("sent", 0)
            if sent > 0 and ch != "escalate":
                # Proxy for effectiveness: sent count relative to failures
                effective_rate = sent / max(sent + stats.get("failed", 0), 1)
                if effective_rate > best_rate:
                    best_rate = effective_rate
                    best_channel = ch

        return {
            "period_days": days,
            "total_executions": total,
            "active": active,
            "completed": completed,
            "cancelled": cancelled,
            "escalated": escalated,
            "response_rate": round(responded / max(total, 1) * 100, 1),
            "avg_response_time_hours": avg_response_time,
            "collection_rate": round(completed / max(total, 1) * 100, 1),
            "engagement": {
                "total_opens": total_opens,
                "total_clicks": total_clicks,
                "total_docs_uploaded": total_docs,
                "open_rate": round(total_opens / max(total, 1) * 100, 1),
                "click_rate": round(total_clicks / max(total, 1) * 100, 1),
            },
            "channel_stats": channel_stats,
            "most_effective_channel": best_channel,
            "ab_test_results": ab_results,
        }

    async def get_execution_timeline(
        self, execution_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Get detailed timeline for a single execution.

        Args:
            execution_id: Execution to inspect.

        Returns:
            Execution details with full step-by-step log, or None.
        """
        execution = (
            self.db.query(FollowupExecution)
            .filter(
                FollowupExecution.id == execution_id,
                FollowupExecution.organization_id == self.org_id,
            )
            .first()
        )
        if not execution:
            return None

        cadence = (
            self.db.query(FollowupCadence)
            .filter(FollowupCadence.id == execution.cadence_id)
            .first()
        )

        return {
            "execution_id": execution.id,
            "cadence_id": execution.cadence_id,
            "cadence_name": cadence.cadence_name if cadence else None,
            "loan_id": execution.loan_id,
            "borrower_name": execution.borrower_name,
            "borrower_email": execution.borrower_email,
            "status": execution.status,
            "current_step": execution.current_step,
            "total_steps": len(cadence.channel_sequence or []) if cadence else 0,
            "attempts_made": execution.attempts_made,
            "response_received": execution.response_received,
            "response_type": execution.response_type,
            "response_at": execution.response_at.isoformat() if execution.response_at else None,
            "ab_variant": execution.ab_variant,
            "engagement": {
                "emails_opened": execution.emails_opened,
                "links_clicked": execution.links_clicked,
                "docs_uploaded": execution.docs_uploaded,
            },
            "escalated_at": execution.escalated_at.isoformat() if execution.escalated_at else None,
            "escalation_note": execution.escalation_note,
            "execution_log": execution.execution_log or [],
            "created_at": execution.created_at.isoformat() if execution.created_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "next_send_at": execution.next_send_at.isoformat() if execution.next_send_at else None,
        }

    async def get_active_executions(
        self,
        loan_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List active cadence executions for the org.

        Args:
            loan_id: Optionally filter by loan.
            limit: Max results.

        Returns:
            List of execution summary dicts.
        """
        query = self.db.query(FollowupExecution).filter(
            FollowupExecution.organization_id == self.org_id,
            FollowupExecution.status.in_([_STATUS_ACTIVE, _STATUS_PAUSED]),
        )

        if loan_id is not None:
            query = query.filter(FollowupExecution.loan_id == loan_id)

        executions = (
            query.order_by(FollowupExecution.next_send_at.asc().nullslast())
            .limit(limit)
            .all()
        )

        return [self._serialize_execution(e) for e in executions]

    # ======================================================================
    # 7. SYSTEM CADENCE SEEDING
    # ======================================================================

    async def seed_system_cadences(self) -> int:
        """Seed system-default cadences if they don't already exist.

        Called during application startup or migration.

        Returns:
            Number of cadences seeded.
        """
        from services.smart_docs.db_transaction import atomic_operation

        existing = (
            self.db.query(FollowupCadence)
            .filter(FollowupCadence.is_system == True)
            .count()
        )

        if existing >= len(_SYSTEM_CADENCE_DEFINITIONS):
            logger.debug("System cadences already seeded (%d exist)", existing)
            return 0

        seeded = 0
        with atomic_operation(self.db):
            for defn in _SYSTEM_CADENCE_DEFINITIONS:
                # Check if this trigger_type + name already exists as system
                exists = (
                    self.db.query(FollowupCadence)
                    .filter(
                        FollowupCadence.is_system == True,
                        FollowupCadence.trigger_type == defn["trigger_type"],
                        FollowupCadence.cadence_name == defn["cadence_name"],
                    )
                    .first()
                )
                if exists:
                    continue

                cadence = FollowupCadence(
                    organization_id=None,
                    cadence_name=defn["cadence_name"],
                    description=defn.get("description"),
                    trigger_type=defn["trigger_type"],
                    channel_sequence=defn["channel_sequence"],
                    max_attempts=defn.get("max_attempts", 5),
                    escalation_after=defn.get("escalation_after", 3),
                    quiet_hours_start=20,
                    quiet_hours_end=8,
                    weekend_enabled=False,
                    holiday_aware=True,
                    is_active=True,
                    is_system=True,
                )
                self.db.add(cadence)
                seeded += 1

        if seeded > 0:
            logger.info("Seeded %d system cadences", seeded)

        return seeded

    # ======================================================================
    # INTERNAL HELPERS
    # ======================================================================

    def _serialize_cadence(self, cadence: FollowupCadence) -> Dict[str, Any]:
        """Serialize a FollowupCadence to a dict."""
        return {
            "id": cadence.id,
            "organization_id": cadence.organization_id,
            "cadence_name": cadence.cadence_name,
            "description": cadence.description,
            "trigger_type": cadence.trigger_type,
            "channel_sequence": cadence.channel_sequence,
            "max_attempts": cadence.max_attempts,
            "escalation_after": cadence.escalation_after,
            "quiet_hours_start": cadence.quiet_hours_start,
            "quiet_hours_end": cadence.quiet_hours_end,
            "weekend_enabled": cadence.weekend_enabled,
            "holiday_aware": cadence.holiday_aware,
            "is_active": cadence.is_active,
            "is_system": cadence.is_system,
            "ab_test_enabled": cadence.ab_test_enabled,
            "ab_test_name": cadence.ab_test_name,
            "ab_test_split_pct": cadence.ab_test_split_pct,
            "total_executions": cadence.total_executions,
            "total_responses": cadence.total_responses,
            "avg_response_time_hours": cadence.avg_response_time_hours,
            "created_at": cadence.created_at.isoformat() if cadence.created_at else None,
            "updated_at": cadence.updated_at.isoformat() if cadence.updated_at else None,
        }

    def _serialize_execution(self, execution: FollowupExecution) -> Dict[str, Any]:
        """Serialize a FollowupExecution to a dict."""
        return {
            "id": execution.id,
            "cadence_id": execution.cadence_id,
            "loan_id": execution.loan_id,
            "document_request_id": execution.document_request_id,
            "borrower_email": execution.borrower_email,
            "borrower_phone": execution.borrower_phone,
            "borrower_name": execution.borrower_name,
            "current_step": execution.current_step,
            "status": execution.status,
            "last_sent_at": execution.last_sent_at.isoformat() if execution.last_sent_at else None,
            "next_send_at": execution.next_send_at.isoformat() if execution.next_send_at else None,
            "attempts_made": execution.attempts_made,
            "response_received": execution.response_received,
            "response_type": execution.response_type,
            "ab_variant": execution.ab_variant,
            "engagement": {
                "emails_opened": execution.emails_opened or 0,
                "links_clicked": execution.links_clicked or 0,
                "docs_uploaded": execution.docs_uploaded or 0,
            },
            "escalated_to_user_id": execution.escalated_to_user_id,
            "created_at": execution.created_at.isoformat() if execution.created_at else None,
        }

    def _validate_channel_sequence(self, sequence: List[Dict[str, Any]]) -> None:
        """Validate channel_sequence structure.

        Raises:
            ValueError: If the sequence is malformed.
        """
        if not isinstance(sequence, list) or len(sequence) == 0:
            raise ValueError("channel_sequence must be a non-empty list")

        valid_channels = {"email", "sms", "call", "escalate", "portal", "in_app"}
        prev_day = -1

        for i, step in enumerate(sequence):
            if not isinstance(step, dict):
                raise ValueError(f"Step {i} must be a dict")

            day = step.get("day")
            if day is None or not isinstance(day, (int, float)):
                raise ValueError(f"Step {i} missing 'day' (integer)")

            if day < prev_day:
                raise ValueError(
                    f"Step {i} day={day} is before previous step day={prev_day}. "
                    "Days must be non-decreasing."
                )
            prev_day = day

            channel = step.get("channel")
            if channel not in valid_channels:
                raise ValueError(
                    f"Step {i} channel='{channel}' invalid. "
                    f"Must be one of: {', '.join(sorted(valid_channels))}"
                )

            if not step.get("template"):
                raise ValueError(f"Step {i} missing 'template'")

    def _assign_ab_variant(
        self, cadence: FollowupCadence, borrower_email: Optional[str],
    ) -> Optional[str]:
        """Assign an A/B test variant deterministically based on borrower identity.

        Uses a hash of the borrower email + cadence ID for stable assignment
        (same borrower always gets the same variant for the same cadence).

        Args:
            cadence: The cadence definition.
            borrower_email: Borrower email for hashing.

        Returns:
            "A", "B", or None if A/B testing is disabled.
        """
        if not cadence.ab_test_enabled:
            return None

        # Deterministic hash-based assignment for consistency
        seed = f"{cadence.id}:{borrower_email or 'unknown'}"
        hash_val = int(hashlib.md5(seed.encode()).hexdigest(), 16) % 100
        split_pct = cadence.ab_test_split_pct or 50.0

        return "B" if hash_val < split_pct else "A"

    async def _calculate_optimal_send_time(
        self,
        cadence: FollowupCadence,
        borrower_email: Optional[str],
        borrower_phone: Optional[str],
        day_offset: int,
        base_time: Optional[datetime] = None,
    ) -> datetime:
        """Calculate optimal send time using engagement history analysis.

        Strategy:
        1. Check borrower's past engagement for best hour-of-day
        2. Fall back to org-level aggregate best send time
        3. Default to 10 AM in borrower's timezone (if detectable)
        4. Apply quiet hours and weekend constraints

        Args:
            cadence: Cadence definition (for quiet hours config).
            borrower_email: Borrower email for history lookup.
            borrower_phone: Borrower phone for timezone inference.
            day_offset: Days from base_time for this step.
            base_time: Starting point (defaults to now).

        Returns:
            Optimal send datetime (UTC).
        """
        base = base_time or datetime.now(timezone.utc)
        target_date = base + timedelta(days=day_offset)

        # Try to determine optimal hour from borrower engagement history
        optimal_hour = await self._get_borrower_optimal_hour(borrower_email)

        if optimal_hour is None:
            # Fall back to org-level aggregate
            optimal_hour = await self._get_org_optimal_hour()

        if optimal_hour is None:
            # Default: 10 AM (safe business hours for all US timezones)
            optimal_hour = 10

        # Build the candidate send time
        candidate = target_date.replace(
            hour=optimal_hour, minute=0, second=0, microsecond=0,
        )

        # If candidate is in the past, push to the next day
        if candidate <= base:
            candidate += timedelta(days=1)

        # Apply compliance constraints
        candidate = self._apply_send_constraints(cadence, candidate, borrower_phone)

        return candidate

    async def _get_borrower_optimal_hour(
        self, borrower_email: Optional[str],
    ) -> Optional[int]:
        """Analyze past engagement to find borrower's best response hour.

        Queries FollowupExecution logs for this borrower's email opens and
        link clicks, then returns the most common hour.

        Args:
            borrower_email: Borrower email to look up.

        Returns:
            Optimal hour (0-23 UTC) or None if insufficient data.
        """
        if not borrower_email:
            return None

        try:
            # Find past executions with engagement for this borrower
            past_executions = (
                self.db.query(FollowupExecution)
                .filter(
                    FollowupExecution.organization_id == self.org_id,
                    FollowupExecution.borrower_email == borrower_email,
                    FollowupExecution.response_received == True,
                )
                .limit(20)
                .all()
            )

            if len(past_executions) < 3:
                return None  # Not enough data

            # Extract response hours from execution logs
            response_hours = []
            for ex in past_executions:
                if ex.response_at:
                    response_hours.append(ex.response_at.hour)
                for entry in (ex.execution_log or []):
                    if entry.get("status") in ("delivered", "sent"):
                        sent_str = entry.get("sent_at", "")
                        if sent_str:
                            try:
                                sent_dt = datetime.fromisoformat(sent_str.replace("Z", "+00:00"))
                                response_hours.append(sent_dt.hour)
                            except (ValueError, TypeError):
                                pass

            if not response_hours:
                return None

            # Most common hour
            from collections import Counter
            hour_counts = Counter(response_hours)
            best_hour = hour_counts.most_common(1)[0][0]
            return best_hour

        except Exception as e:
            logger.debug("Failed to get borrower optimal hour: %s", e)
            return None

    async def _get_org_optimal_hour(self) -> Optional[int]:
        """Get the org-level optimal send hour from aggregate response data.

        Returns:
            Optimal hour (0-23 UTC) or None if insufficient data.
        """
        try:
            recent_responses = (
                self.db.query(FollowupExecution.response_at)
                .filter(
                    FollowupExecution.organization_id == self.org_id,
                    FollowupExecution.response_received == True,
                    FollowupExecution.response_at.isnot(None),
                    FollowupExecution.created_at >= datetime.now(timezone.utc) - timedelta(days=90),
                )
                .limit(100)
                .all()
            )

            if len(recent_responses) < 10:
                return None

            hours = [r.response_at.hour for r in recent_responses if r.response_at]
            if not hours:
                return None

            from collections import Counter
            return Counter(hours).most_common(1)[0][0]

        except Exception as e:
            logger.debug("Failed to get org optimal hour: %s", e)
            return None

    def _apply_send_constraints(
        self,
        cadence: FollowupCadence,
        candidate: datetime,
        borrower_phone: Optional[str],
    ) -> datetime:
        """Apply quiet hours, weekend, and holiday constraints to a candidate time.

        Pushes the candidate forward until it lands in an acceptable window.

        Args:
            cadence: Cadence definition with constraint config.
            candidate: Proposed send time (UTC).
            borrower_phone: For timezone-aware quiet hours.

        Returns:
            Adjusted send time (UTC).
        """
        max_iterations = 14  # Safety: don't loop more than 2 weeks

        for _ in range(max_iterations):
            # Weekend check
            if not cadence.weekend_enabled and candidate.weekday() >= 5:
                # Push to Monday
                days_ahead = 7 - candidate.weekday()
                candidate = candidate.replace(
                    hour=cadence.quiet_hours_end or 8, minute=0, second=0,
                ) + timedelta(days=days_ahead)
                continue

            # Holiday check
            if cadence.holiday_aware and self._is_holiday(candidate):
                candidate = (candidate + timedelta(days=1)).replace(
                    hour=cadence.quiet_hours_end or 8, minute=0, second=0,
                )
                continue

            # Quiet hours check
            quiet_start = cadence.quiet_hours_start or 20
            quiet_end = cadence.quiet_hours_end or 8
            hour = candidate.hour

            if quiet_start > quiet_end:
                # Quiet period wraps midnight (e.g. 20:00 - 08:00)
                in_quiet = hour >= quiet_start or hour < quiet_end
            else:
                # Quiet period within same day (e.g. 22:00 - 06:00 doesn't happen normally)
                in_quiet = quiet_start <= hour < quiet_end

            if in_quiet:
                if hour >= quiet_start:
                    # Push to next day's quiet_end
                    candidate = (candidate + timedelta(days=1)).replace(
                        hour=quiet_end, minute=0, second=0,
                    )
                else:
                    # Currently before quiet_end, push to quiet_end same day
                    candidate = candidate.replace(
                        hour=quiet_end, minute=0, second=0,
                    )
                continue

            # All checks passed
            break

        return candidate

    def _is_quiet_hours(
        self, cadence: FollowupCadence, borrower_phone: Optional[str],
    ) -> bool:
        """Check if current time is within quiet hours.

        Uses both cadence-level config and TCPA service for phone-based checks.

        Args:
            cadence: Cadence with quiet hours config.
            borrower_phone: Borrower phone for TCPA timezone lookup.

        Returns:
            True if currently in quiet hours.
        """
        now = datetime.now(timezone.utc)
        quiet_start = cadence.quiet_hours_start or 20
        quiet_end = cadence.quiet_hours_end or 8
        hour = now.hour

        if quiet_start > quiet_end:
            in_cadence_quiet = hour >= quiet_start or hour < quiet_end
        else:
            in_cadence_quiet = quiet_start <= hour < quiet_end

        if in_cadence_quiet:
            return True

        # Also check TCPA quiet hours (recipient timezone)
        if borrower_phone:
            try:
                from services.smart_docs.tcpa_compliance_service import TCPAComplianceService
                tcpa = TCPAComplianceService(self.db)
                return tcpa.check_quiet_hours(borrower_phone)
            except Exception as e:
                logger.debug("TCPA quiet hours check failed: %s", e)

        return False

    def _next_available_send_time(
        self,
        cadence: FollowupCadence,
        borrower_phone: Optional[str],
    ) -> datetime:
        """Calculate the next time a message can be sent (respecting all constraints).

        Args:
            cadence: Cadence with scheduling config.
            borrower_phone: For timezone inference.

        Returns:
            Next available send time (UTC).
        """
        now = datetime.now(timezone.utc)
        # Start from the next quiet_end hour
        quiet_end = cadence.quiet_hours_end or 8

        candidate = now.replace(hour=quiet_end, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)

        return self._apply_send_constraints(cadence, candidate, borrower_phone)

    def _is_weekend(self, dt: datetime) -> bool:
        """Check if a datetime falls on a weekend."""
        return dt.weekday() >= 5  # Saturday=5, Sunday=6

    def _next_weekday(self, dt: datetime) -> datetime:
        """Get the next Monday (or same day if already weekday)."""
        days_ahead = 7 - dt.weekday()  # Monday is 0
        if dt.weekday() < 5:
            return dt
        return dt + timedelta(days=days_ahead)

    def _is_holiday(self, dt: datetime) -> bool:
        """Check if a date is a US federal holiday.

        Dynamically computes all 10 standard US federal holidays for the
        year of the given datetime, including floating holidays (MLK Day,
        Presidents Day, Memorial Day, Labor Day, Columbus Day, Thanksgiving).

        Args:
            dt: DateTime to check.

        Returns:
            True if the date is a recognized holiday.
        """
        return dt.date() in _get_federal_holidays(dt.year)

    def _check_tcpa_compliance(
        self, phone: str, channel: str,
    ) -> Dict[str, Any]:
        """Run TCPA compliance checks via the TCPAComplianceService.

        Args:
            phone: Recipient phone number.
            channel: "sms" or "call".

        Returns:
            Dict with "allowed" bool and optional "blockers" list.
        """
        try:
            from services.smart_docs.tcpa_compliance_service import TCPAComplianceService
            tcpa = TCPAComplianceService(self.db)
            result = tcpa.validate_outreach(
                phone=phone,
                org_id=self.org_id,
                channel=channel,
            )
            return {
                "allowed": result.allowed,
                "blockers": result.blockers,
                "warnings": result.warnings,
            }
        except Exception as e:
            logger.exception("TCPA compliance check failed: %s", e)
            # Fail-safe: block if TCPA check fails
            return {
                "allowed": False,
                "blockers": [f"TCPA check error: {str(e)}"],
            }

    async def _dispatch_step(
        self,
        execution: FollowupExecution,
        cadence: FollowupCadence,
        channel: str,
        template_slug: str,
        step_index: int,
    ) -> Dict[str, Any]:
        """Dispatch a single cadence step via the appropriate channel.

        Delegates to the existing FollowupAutomationService for actual
        message composition and delivery.

        Args:
            execution: The execution being advanced.
            cadence: Cadence definition.
            channel: Channel for this step (email, sms, call, escalate).
            template_slug: Template identifier.
            step_index: Current step index.

        Returns:
            Dict with delivery status.
        """
        try:
            if channel == "email":
                return await self._dispatch_email(execution, template_slug)
            elif channel == "sms":
                return await self._dispatch_sms(execution, template_slug)
            elif channel == "call":
                return await self._dispatch_call(execution, template_slug)
            elif channel == "escalate":
                return await self._dispatch_escalation(execution, cadence)
            elif channel == "portal":
                return await self._dispatch_portal_notification(execution, template_slug)
            elif channel == "in_app":
                return await self._dispatch_in_app_notification(execution, template_slug)
            else:
                logger.warning("Unknown channel '%s' for execution %d", channel, execution.id)
                return {"status": "failed", "error": f"Unknown channel: {channel}"}
        except Exception as e:
            logger.exception(
                "Failed to dispatch %s step for execution %d: %s", channel, execution.id, e,
            )
            return {"status": "failed", "error": str(e)}

    async def _dispatch_email(
        self, execution: FollowupExecution, template_slug: str,
    ) -> Dict[str, Any]:
        """Send an email follow-up using the existing followup automation service.

        Args:
            execution: Current execution.
            template_slug: Email template to use.

        Returns:
            Delivery result dict.
        """
        if not execution.borrower_email:
            return {"status": "failed", "error": "No borrower email"}

        try:
            from services.smart_docs.followup_automation_service import FollowupAutomationService
            followup_svc = FollowupAutomationService(self.db)

            # Build portal link
            portal_link = f"{self._portal_base_url}/loans/{execution.loan_id}/documents"

            result = followup_svc._send_email_reminder(
                campaign_id=0,  # No legacy campaign; tracked by cadence execution
                template_slug=template_slug,
                borrower_email=execution.borrower_email,
                borrower_name=execution.borrower_name or "Borrower",
                documents=[],  # Document list populated by template
                lo_name="Your Loan Officer",
                portal_link=portal_link,
            )
            return result
        except Exception as e:
            logger.exception("Email dispatch failed for execution %d: %s", execution.id, e)
            return {"status": "failed", "error": str(e)}

    async def _dispatch_sms(
        self, execution: FollowupExecution, template_slug: str,
    ) -> Dict[str, Any]:
        """Send an SMS follow-up.

        Args:
            execution: Current execution.
            template_slug: SMS template to use.

        Returns:
            Delivery result dict.
        """
        if not execution.borrower_phone:
            return {"status": "failed", "error": "No borrower phone"}

        try:
            from services.smart_docs.followup_automation_service import FollowupAutomationService
            followup_svc = FollowupAutomationService(self.db)

            result = followup_svc._send_sms_reminder(
                campaign_id=0,
                template_slug=template_slug,
                borrower_phone=execution.borrower_phone,
                borrower_name=execution.borrower_name or "Borrower",
                document_count=1,
            )

            # Log outreach for TCPA frequency tracking
            if result.get("status") == "sent":
                try:
                    from services.smart_docs.tcpa_compliance_service import TCPAComplianceService
                    tcpa = TCPAComplianceService(self.db)
                    tcpa.log_outreach(
                        phone=execution.borrower_phone,
                        org_id=self.org_id,
                        channel="sms",
                    )
                except Exception as e:
                    logger.warning("Failed to log TCPA outreach: %s", e)

            return result
        except Exception as e:
            logger.exception("SMS dispatch failed for execution %d: %s", execution.id, e)
            return {"status": "failed", "error": str(e)}

    async def _dispatch_call(
        self, execution: FollowupExecution, template_slug: str,
    ) -> Dict[str, Any]:
        """Schedule a call follow-up.

        Args:
            execution: Current execution.
            template_slug: Call script template.

        Returns:
            Delivery result dict.
        """
        if not execution.borrower_phone:
            return {"status": "failed", "error": "No borrower phone"}

        try:
            from services.smart_docs.followup_automation_service import FollowupAutomationService
            followup_svc = FollowupAutomationService(self.db)

            # Get LO user ID from the loan
            lo_user_id = None
            try:
                from database.models.lead_loan import Loan
                loan = self.db.query(Loan).filter(Loan.id == execution.loan_id).first()
                if loan:
                    lo_user_id = loan.loan_officer_id
            except Exception as e:
                logger.debug("Could not get LO for loan %d: %s", execution.loan_id, e)

            result = followup_svc._schedule_call(
                campaign_id=0,
                loan_id=execution.loan_id,
                borrower_phone=execution.borrower_phone,
                lo_user_id=lo_user_id,
            )

            # Log TCPA outreach
            if result.get("status") == "sent":
                try:
                    from services.smart_docs.tcpa_compliance_service import TCPAComplianceService
                    tcpa = TCPAComplianceService(self.db)
                    tcpa.log_outreach(
                        phone=execution.borrower_phone,
                        org_id=self.org_id,
                        channel="call",
                    )
                except Exception as e:
                    logger.warning("Failed to log TCPA call outreach: %s", e)

            return result
        except Exception as e:
            logger.exception("Call dispatch failed for execution %d: %s", execution.id, e)
            return {"status": "failed", "error": str(e)}

    async def _dispatch_escalation(
        self, execution: FollowupExecution, cadence: FollowupCadence,
    ) -> Dict[str, Any]:
        """Escalate to the loan officer.

        Args:
            execution: Current execution.
            cadence: Cadence definition.

        Returns:
            Escalation result dict.
        """
        try:
            # Find the LO for this loan
            lo_user_id = None
            lo_email = None
            try:
                from database.models.lead_loan import Loan
                from database.models.core import User
                loan = self.db.query(Loan).filter(Loan.id == execution.loan_id).first()
                if loan and loan.loan_officer_id:
                    lo_user_id = loan.loan_officer_id
                    lo = self.db.query(User).filter(User.id == lo_user_id).first()
                    if lo:
                        lo_email = lo.email
            except Exception as e:
                logger.debug("Could not find LO for escalation: %s", e)

            if not lo_email:
                return {"status": "failed", "error": "Could not determine LO for escalation"}

            # Send escalation email to LO
            from services.smart_docs.followup_automation_service import FollowupAutomationService
            followup_svc = FollowupAutomationService(self.db)
            result = followup_svc._send_email_reminder(
                campaign_id=0,
                template_slug="escalation",
                borrower_email=lo_email,
                borrower_name=execution.borrower_name or "Borrower",
                documents=[],
                lo_name="Team",
                portal_link=f"{self._portal_base_url}/loans/{execution.loan_id}/documents",
            )

            # Update execution with escalation info
            execution.escalated_to_user_id = lo_user_id
            execution.escalated_at = datetime.now(timezone.utc)
            execution.escalation_note = (
                f"Escalated after {execution.attempts_made} attempts. "
                f"Cadence: {cadence.cadence_name}"
            )

            return {"status": "sent", "escalated_to": lo_email, "lo_user_id": lo_user_id}

        except Exception as e:
            logger.exception("Escalation failed for execution %d: %s", execution.id, e)
            return {"status": "failed", "error": str(e)}

    async def _dispatch_portal_notification(
        self, execution: FollowupExecution, template_slug: str,
    ) -> Dict[str, Any]:
        """Send an in-portal notification (push to borrower portal).

        Args:
            execution: Current execution.
            template_slug: Notification template.

        Returns:
            Delivery result dict.
        """
        # Portal notifications are created as Notification records
        try:
            from database.models.security import Notification
            notification = Notification(
                organization_id=self.org_id,
                user_id=None,  # Borrower-facing; not a user notification
                title="Document Reminder",
                message=f"You have outstanding documents for your loan application.",
                notification_type="document_followup",
                metadata={
                    "loan_id": execution.loan_id,
                    "execution_id": execution.id,
                    "template": template_slug,
                },
            )
            self.db.add(notification)
            self.db.flush()
            return {"status": "sent", "notification_id": notification.id}
        except Exception as e:
            logger.exception("Portal notification failed: %s", e)
            return {"status": "failed", "error": str(e)}

    async def _dispatch_in_app_notification(
        self, execution: FollowupExecution, template_slug: str,
    ) -> Dict[str, Any]:
        """Send an in-app notification to the loan officer.

        Args:
            execution: Current execution.
            template_slug: Notification template.

        Returns:
            Delivery result dict.
        """
        try:
            from database.models.security import Notification
            from database.models.lead_loan import Loan

            loan = self.db.query(Loan).filter(Loan.id == execution.loan_id).first()
            lo_user_id = loan.loan_officer_id if loan else None

            if not lo_user_id:
                return {"status": "failed", "error": "No LO found for in-app notification"}

            notification = Notification(
                organization_id=self.org_id,
                user_id=lo_user_id,
                title="Document Follow-Up Update",
                message=(
                    f"Borrower {execution.borrower_name or 'Unknown'} has not responded "
                    f"to document requests after {execution.attempts_made} attempts."
                ),
                notification_type="document_followup",
                metadata={
                    "loan_id": execution.loan_id,
                    "execution_id": execution.id,
                    "template": template_slug,
                    "attempts": execution.attempts_made,
                },
            )
            self.db.add(notification)
            self.db.flush()
            return {"status": "sent", "notification_id": notification.id, "user_id": lo_user_id}
        except Exception as e:
            logger.exception("In-app notification failed: %s", e)
            return {"status": "failed", "error": str(e)}

    async def _escalate_execution(
        self, execution: FollowupExecution, cadence: FollowupCadence,
    ) -> None:
        """Mark an execution as escalated and notify the LO.

        Args:
            execution: Execution to escalate.
            cadence: Cadence definition.
        """
        now = datetime.now(timezone.utc)
        execution.status = _STATUS_ESCALATED
        execution.escalated_at = now
        execution.next_send_at = None
        execution.completed_at = now

        # Send the escalation notification
        await self._dispatch_escalation(execution, cadence)

        logger.info(
            "Escalated execution %d (cadence=%d, loan=%d) after %d attempts",
            execution.id, cadence.id, execution.loan_id, execution.attempts_made,
        )

    def _complete_execution(
        self, execution: FollowupExecution, reason: str,
    ) -> None:
        """Mark an execution as completed.

        Args:
            execution: Execution to complete.
            reason: Completion reason for audit trail.
        """
        now = datetime.now(timezone.utc)
        execution.status = _STATUS_COMPLETED
        execution.completed_at = now
        execution.next_send_at = None

        # Append completion entry to log
        log_entry = {
            "event": "completed",
            "reason": reason,
            "at": now.isoformat(),
            "attempts_made": execution.attempts_made,
            "response_received": execution.response_received,
        }
        execution.execution_log = (execution.execution_log or []) + [log_entry]

        logger.info(
            "Completed execution %d: %s (attempts=%d, responded=%s)",
            execution.id, reason, execution.attempts_made or 0, execution.response_received,
        )


# ===========================================================================
# Factory function
# ===========================================================================

def get_smart_cadence_service(db: Session, org_id: int) -> SmartCadenceService:
    """Factory function for creating a SmartCadenceService instance.

    Args:
        db: SQLAlchemy session.
        org_id: Organization ID for tenant isolation.

    Returns:
        Configured SmartCadenceService.
    """
    return SmartCadenceService(db=db, org_id=org_id)
