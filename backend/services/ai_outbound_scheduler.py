"""
AI Outbound Call Scheduler

Proactively contacts leads, active clients, and MUM (past clients) via Vapi AI
to schedule appointments on the loan officer's calendar.

Caller Categories:
1. NEW LEADS -- Call within 5 minutes of lead creation ("speed to lead")
   - Goal: Schedule initial consultation
   - Script: Introduce LO, discuss loan needs, book appointment

2. ACTIVE CLIENTS -- Call for milestone check-ins
   - Goal: Schedule progress review appointments
   - Script: Update on loan status, discuss next steps, book if needed

3. MUM (MORTGAGE UNDER MANAGEMENT) -- Call for retention/referral
   - Goal: Schedule annual review, rate check, or referral discussion
   - Script: Check in on home, discuss refinance opportunity, ask for referrals

Features:
- Smart call timing (respect contact hours, timezone, DNC)
- Call priority queue (hot leads first)
- Retry logic (if no answer: try again in 2 hours, then next day, then 3 days)
- Outcome tracking (connected, voicemail, no answer, scheduled, declined)
- Learning loop: track which call times/scripts have best conversion rates
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time, timezone, date
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_, func, text, desc
from sqlalchemy.orm import Session

from services.workflow_constants import TERMINAL_LOAN_STAGES_SET as _TERMINAL_LOAN_STAGES

logger = logging.getLogger(__name__)

# TCPA safe-harbor calling window
CALLING_HOURS_START = time(8, 0)  # 8 AM local
CALLING_HOURS_END = time(20, 0)   # 8 PM local (conservative: TCPA allows up to 9 PM)

# Retry intervals (in hours)
RETRY_INTERVALS = [2, 24, 72]  # 2 hours, next day, 3 days

# Maximum calls per LO per day via outbound scheduler
MAX_AI_CALLS_PER_LO_PER_DAY = 50


# =============================================================================
# ENUMS
# =============================================================================

class CallerType(str, Enum):
    """Classification of the contact being called."""
    NEW_LEAD = "new_lead"
    ACTIVE_CLIENT = "active_client"
    MUM = "mum"


class CallOutcome(str, Enum):
    """Outcome of an outbound call attempt."""
    CONNECTED = "connected"
    VOICEMAIL = "voicemail"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    DNC_BLOCKED = "dnc_blocked"
    OUTSIDE_HOURS = "outside_hours"
    APPOINTMENT_SCHEDULED = "appointment_scheduled"
    APPOINTMENT_DECLINED = "appointment_declined"
    CALLBACK_REQUESTED = "callback_requested"
    NOT_INTERESTED = "not_interested"


class CallQueueStatus(str, Enum):
    """Status of a call in the queue."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    RETRY_SCHEDULED = "retry_scheduled"
    MAX_RETRIES = "max_retries_reached"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class CallPriority(int, Enum):
    """Call priority levels (lower number = higher priority)."""
    URGENT = 1       # Speed-to-lead, hot leads
    HIGH = 2         # High-score leads, lock expirations
    NORMAL = 3       # Standard follow-ups
    LOW = 4          # Nurture, MUM check-ins
    BACKGROUND = 5   # Bulk campaigns


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ContactInfo:
    """Normalized contact information for outbound calling."""
    id: int
    entity_type: str              # "lead", "loan", "mum_client"
    name: str
    phone: str
    email: Optional[str] = None
    timezone: str = "America/Chicago"
    caller_type: CallerType = CallerType.NEW_LEAD
    lo_id: Optional[int] = None
    lo_name: Optional[str] = None
    organization_id: Optional[int] = None

    # Context for personalization
    loan_stage: Optional[str] = None
    loan_amount: Optional[float] = None
    loan_type: Optional[str] = None
    loan_number: Optional[str] = None
    lead_source: Optional[str] = None
    ai_score: Optional[int] = None
    days_since_last_contact: Optional[int] = None
    property_address: Optional[str] = None
    rate: Optional[float] = None
    refinance_opportunity: bool = False


@dataclass
class QueuedCall:
    """A call waiting in the queue."""
    id: str
    contact: ContactInfo
    caller_type: CallerType
    priority: CallPriority
    script_variant: str = "default"
    purpose: str = ""
    scheduled_for: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    status: CallQueueStatus = CallQueueStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_attempt_at: Optional[datetime] = None
    outcome: Optional[CallOutcome] = None
    appointment_id: Optional[int] = None
    vapi_call_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversionStats:
    """Call-to-appointment conversion statistics."""
    total_calls: int = 0
    connected: int = 0
    voicemails: int = 0
    no_answers: int = 0
    appointments_scheduled: int = 0
    callbacks_requested: int = 0
    not_interested: int = 0
    connection_rate: float = 0.0
    conversion_rate: float = 0.0
    by_caller_type: Dict[str, Dict[str, int]] = field(default_factory=dict)
    by_time_of_day: Dict[str, Dict[str, int]] = field(default_factory=dict)
    avg_calls_to_appointment: float = 0.0


# =============================================================================
# CALLER CLASSIFIER
# =============================================================================

class CallerClassifier:
    """
    Classifies a contact as new_lead, active_client, or mum based on their
    presence in leads, loans, and mum_clients tables.
    """

    # Active loan stages (not terminal)
    ACTIVE_LOAN_STAGES = frozenset({
        "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
        "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
        "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE",
        "CLOSING", "DOCS", "DOCS_OUT", "NURTURE",
    })

    TERMINAL_STAGES = _TERMINAL_LOAN_STAGES

    # Lead stages that indicate active pipeline engagement
    ACTIVE_LEAD_STAGES = frozenset({
        "Application", "APPLICATION_STARTED", "Document Fulfillment",
        "Pre-Qualified", "Pre-Approved", "Under Contract", "Disclosed",
    })

    def __init__(self, db: Session):
        self.db = db

    def classify(self, contact_id: int, entity_type: str) -> Tuple[CallerType, ContactInfo]:
        """
        Classify a contact and build ContactInfo.

        Args:
            contact_id: Primary key of the entity
            entity_type: One of "lead", "loan", "mum_client"

        Returns:
            Tuple of (CallerType, ContactInfo)
        """
        if entity_type == "lead":
            return self._classify_lead(contact_id)
        elif entity_type == "loan":
            return self._classify_loan(contact_id)
        elif entity_type == "mum_client":
            return self._classify_mum(contact_id)
        else:
            raise ValueError(f"Unknown entity_type: {entity_type}")

    def _classify_lead(self, lead_id: int) -> Tuple[CallerType, ContactInfo]:
        """Classify a lead and determine caller type."""
        from database.models import Lead, Loan, User

        lead = self.db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Check if lead has an active loan (via loan_number match)
        active_loan = None
        if lead.loan_number:
            active_loan = self.db.query(Loan).filter(
                Loan.loan_number == lead.loan_number,
                ~Loan.stage.in_(list(self.TERMINAL_STAGES)),
            ).first()

        # Check if lead has a funded loan (MUM candidate)
        funded_loan = None
        if lead.loan_number:
            funded_loan = self.db.query(Loan).filter(
                Loan.loan_number == lead.loan_number,
                Loan.stage == "FUNDED",
            ).first()

        # Determine caller type
        if active_loan:
            caller_type = CallerType.ACTIVE_CLIENT
        elif funded_loan or lead.stage in ("Funded", "Closed", "AMR"):
            caller_type = CallerType.MUM
        elif lead.stage in self.ACTIVE_LEAD_STAGES:
            caller_type = CallerType.ACTIVE_CLIENT
        else:
            caller_type = CallerType.NEW_LEAD

        # Get LO info
        lo_name = None
        if lead.owner_id:
            lo = self.db.query(User).filter(User.id == lead.owner_id).first()
            if lo:
                lo_name = f"{lo.first_name or ''} {lo.last_name or ''}".strip() or None

        days_since = None
        if lead.last_contact:
            days_since = (datetime.now(timezone.utc) - lead.last_contact.replace(tzinfo=timezone.utc)).days

        contact = ContactInfo(
            id=lead.id,
            entity_type="lead",
            name=lead.name or f"{lead.first_name or ''} {lead.last_name or ''}".strip() or "Unknown",
            phone=lead.phone or "",
            email=lead.email,
            timezone=_infer_timezone(lead.state),
            caller_type=caller_type,
            lo_id=lead.owner_id,
            lo_name=lo_name,
            organization_id=lead.organization_id,
            loan_stage=lead.stage,
            loan_amount=float(lead.loan_amount) if lead.loan_amount else None,
            loan_type=lead.loan_type,
            loan_number=lead.loan_number,
            lead_source=lead.source,
            ai_score=lead.ai_score,
            days_since_last_contact=days_since,
            property_address=lead.property_address or lead.address,
            rate=float(lead.interest_rate) if lead.interest_rate else None,
        )

        return caller_type, contact

    def _classify_loan(self, loan_id: int) -> Tuple[CallerType, ContactInfo]:
        """Classify a loan borrower."""
        from database.models import Loan, User

        loan = self.db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise ValueError(f"Loan {loan_id} not found")

        if loan.stage == "FUNDED":
            caller_type = CallerType.MUM
        elif loan.stage in self.TERMINAL_STAGES:
            raise ValueError(f"Loan {loan_id} is in terminal stage {loan.stage}")
        else:
            caller_type = CallerType.ACTIVE_CLIENT

        lo_name = None
        if loan.loan_officer_id:
            lo = self.db.query(User).filter(User.id == loan.loan_officer_id).first()
            if lo:
                lo_name = f"{lo.first_name or ''} {lo.last_name or ''}".strip() or None

        contact = ContactInfo(
            id=loan.id,
            entity_type="loan",
            name=loan.borrower_name or "Unknown",
            phone=loan.borrower_phone or "",
            email=loan.borrower_email,
            timezone=_infer_timezone(loan.property_state),
            caller_type=caller_type,
            lo_id=loan.loan_officer_id,
            lo_name=lo_name or loan.loan_officer_name,
            organization_id=loan.organization_id,
            loan_stage=loan.stage,
            loan_amount=float(loan.amount) if loan.amount else None,
            loan_type=loan.loan_type,
            loan_number=loan.loan_number,
            property_address=loan.property_address,
            rate=float(loan.rate) if loan.rate else None,
        )

        return caller_type, contact

    def _classify_mum(self, mum_id: int) -> Tuple[CallerType, ContactInfo]:
        """Classify a MUM client (always MUM type)."""
        from database.models import MUMClient

        mum = self.db.query(MUMClient).filter(MUMClient.id == mum_id).first()
        if not mum:
            raise ValueError(f"MUM client {mum_id} not found")

        days_since = None
        if mum.last_contact:
            days_since = (datetime.now(timezone.utc) - mum.last_contact.replace(tzinfo=timezone.utc)).days

        contact = ContactInfo(
            id=mum.id,
            entity_type="mum_client",
            name=mum.name or "Unknown",
            phone=mum.phone or "",
            email=mum.email,
            timezone=_infer_timezone(mum.property_state),
            caller_type=CallerType.MUM,
            lo_name=mum.loan_officer,
            organization_id=mum.organization_id,
            loan_number=mum.loan_number,
            loan_amount=float(mum.original_loan_amount) if mum.original_loan_amount else None,
            rate=float(mum.original_rate) if mum.original_rate else None,
            days_since_last_contact=days_since,
            refinance_opportunity=bool(mum.refinance_opportunity),
        )

        return CallerType.MUM, contact


# =============================================================================
# CALL PRIORITY QUEUE
# =============================================================================

class CallPriorityQueue:
    """
    Prioritizes outbound calls based on lead score, time sensitivity,
    opportunity value, and contact recency.
    """

    def __init__(self, db: Session):
        self.db = db
        self._queue: List[QueuedCall] = []

    def calculate_priority(self, contact: ContactInfo, caller_type: CallerType) -> CallPriority:
        """
        Calculate call priority based on multiple factors.

        Speed-to-lead (new leads created < 5 min ago) always get URGENT.
        """
        # Speed-to-lead: new leads get highest priority
        if caller_type == CallerType.NEW_LEAD:
            score = contact.ai_score or 50
            if score >= 70:
                return CallPriority.URGENT
            return CallPriority.HIGH

        # Active clients with expiring locks or approaching milestones
        if caller_type == CallerType.ACTIVE_CLIENT:
            if contact.loan_stage in ("CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT"):
                return CallPriority.HIGH
            if contact.loan_stage in ("APPROVED", "CONDITIONAL_APPROVAL"):
                return CallPriority.HIGH
            return CallPriority.NORMAL

        # MUM clients: refinance opportunity or long time since contact
        if caller_type == CallerType.MUM:
            if contact.refinance_opportunity:
                return CallPriority.NORMAL
            return CallPriority.LOW

        return CallPriority.NORMAL

    def add_to_queue(
        self,
        contact: ContactInfo,
        caller_type: CallerType,
        purpose: str = "",
        script_variant: str = "default",
        scheduled_for: Optional[datetime] = None,
        priority_override: Optional[CallPriority] = None,
    ) -> QueuedCall:
        """Add a contact to the call queue."""
        priority = priority_override or self.calculate_priority(contact, caller_type)

        call = QueuedCall(
            id=str(uuid.uuid4()),
            contact=contact,
            caller_type=caller_type,
            priority=priority,
            script_variant=script_variant,
            purpose=purpose,
            scheduled_for=scheduled_for or datetime.now(timezone.utc),
        )

        self._queue.append(call)
        self._queue.sort(key=lambda c: (c.priority.value, c.scheduled_for or datetime.min.replace(tzinfo=timezone.utc)))

        return call

    def get_next(self) -> Optional[QueuedCall]:
        """Get the next call to process (highest priority, ready to execute)."""
        now = datetime.now(timezone.utc)
        for call in self._queue:
            if call.status != CallQueueStatus.PENDING:
                continue
            if call.scheduled_for and call.scheduled_for > now:
                continue
            return call
        return None

    def get_pending_count(self) -> int:
        """Get count of pending calls."""
        return sum(1 for c in self._queue if c.status == CallQueueStatus.PENDING)

    def get_queue_snapshot(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get a snapshot of the current queue for display."""
        results = []
        for call in self._queue[:limit]:
            results.append({
                "id": call.id,
                "contact_name": call.contact.name,
                "phone": _mask_phone(call.contact.phone),
                "caller_type": call.caller_type.value,
                "priority": call.priority.name,
                "priority_value": call.priority.value,
                "purpose": call.purpose,
                "status": call.status.value,
                "retry_count": call.retry_count,
                "scheduled_for": call.scheduled_for.isoformat() if call.scheduled_for else None,
                "created_at": call.created_at.isoformat(),
            })
        return results


# =============================================================================
# OUTBOUND SCHEDULER SERVICE
# =============================================================================

class AIOutboundScheduler:
    """
    Main service for AI-driven outbound calling to schedule appointments.

    Coordinates classification, prioritization, compliance checks,
    Vapi call initiation, and outcome tracking.
    """

    def __init__(self, db: Session):
        self.db = db
        self.classifier = CallerClassifier(db)
        self.queue = CallPriorityQueue(db)

    # -------------------------------------------------------------------------
    # Queue a single call
    # -------------------------------------------------------------------------

    async def schedule_outbound_call(
        self,
        contact_id: int,
        entity_type: str,
        lo_id: Optional[int] = None,
        purpose: str = "",
        script_variant: str = "default",
        priority_override: Optional[CallPriority] = None,
    ) -> Dict[str, Any]:
        """
        Queue an outbound call for a contact.

        Args:
            contact_id: ID of the lead, loan, or mum_client
            entity_type: "lead", "loan", or "mum_client"
            lo_id: Loan officer ID (optional override)
            purpose: Reason for the call
            script_variant: Which script template to use
            priority_override: Force a specific priority

        Returns:
            Dict with call queue info
        """
        try:
            caller_type, contact = self.classifier.classify(contact_id, entity_type)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        if not contact.phone:
            return {"success": False, "error": "Contact has no phone number"}

        if lo_id:
            contact.lo_id = lo_id

        # Pre-flight compliance check
        compliance_result = await self._check_compliance(contact)
        if not compliance_result["can_call"]:
            return {
                "success": False,
                "error": compliance_result["reason"],
                "blocked_by": compliance_result.get("check"),
            }

        # Auto-generate purpose if not provided
        if not purpose:
            purpose = _default_purpose(caller_type, contact)

        queued = self.queue.add_to_queue(
            contact=contact,
            caller_type=caller_type,
            purpose=purpose,
            script_variant=script_variant,
            priority_override=priority_override,
        )

        # Persist to database
        await self._persist_queued_call(queued)

        return {
            "success": True,
            "call_id": queued.id,
            "priority": queued.priority.name,
            "caller_type": caller_type.value,
            "contact_name": contact.name,
            "scheduled_for": queued.scheduled_for.isoformat() if queued.scheduled_for else None,
        }

    # -------------------------------------------------------------------------
    # Process the call queue
    # -------------------------------------------------------------------------

    async def process_call_queue(self, max_calls: int = 10) -> Dict[str, Any]:
        """
        Process pending calls from the queue, respecting rate limits
        and business hours.

        Args:
            max_calls: Maximum calls to process in this batch

        Returns:
            Summary of processed calls
        """
        # Load pending calls from database
        await self._load_pending_calls()

        processed = 0
        results = []

        while processed < max_calls:
            call = self.queue.get_next()
            if not call:
                break

            call.status = CallQueueStatus.IN_PROGRESS
            call.last_attempt_at = datetime.now(timezone.utc)

            # Verify calling hours for contact's timezone
            if not _is_within_calling_hours(call.contact.timezone):
                call.status = CallQueueStatus.PENDING
                # Reschedule for next available window
                next_window = _next_calling_window(call.contact.timezone)
                call.scheduled_for = next_window
                await self._update_queued_call(call)
                continue

            # Rate limit check
            if not await self._check_rate_limit(call.contact.lo_id):
                logger.warning(f"Rate limit reached for LO {call.contact.lo_id}")
                break

            # Re-check DNC (may have changed since queued)
            compliance = await self._check_compliance(call.contact)
            if not compliance["can_call"]:
                call.status = CallQueueStatus.BLOCKED
                call.outcome = CallOutcome.DNC_BLOCKED
                await self._update_queued_call(call)
                results.append({
                    "call_id": call.id,
                    "outcome": "blocked",
                    "reason": compliance["reason"],
                })
                processed += 1
                continue

            # Initiate the Vapi call
            try:
                vapi_result = await self.initiate_vapi_call(
                    contact=call.contact,
                    caller_type=call.caller_type,
                    lo_id=call.contact.lo_id,
                    script_context={
                        "purpose": call.purpose,
                        "script_variant": call.script_variant,
                    },
                )

                if vapi_result.get("success"):
                    call.vapi_call_id = vapi_result.get("vapi_call_id")
                    call.status = CallQueueStatus.IN_PROGRESS
                    results.append({
                        "call_id": call.id,
                        "outcome": "initiated",
                        "vapi_call_id": call.vapi_call_id,
                    })
                else:
                    call.outcome = CallOutcome.FAILED
                    await self._schedule_retry(call)
                    results.append({
                        "call_id": call.id,
                        "outcome": "failed",
                        "error": vapi_result.get("error"),
                    })
            except Exception as e:
                logger.error(f"Error initiating call {call.id}: {e}")
                call.outcome = CallOutcome.FAILED
                await self._schedule_retry(call)
                results.append({
                    "call_id": call.id,
                    "outcome": "error",
                    "error": str(e),
                })

            await self._update_queued_call(call)
            processed += 1

        return {
            "processed": processed,
            "pending_remaining": self.queue.get_pending_count(),
            "results": results,
        }

    # -------------------------------------------------------------------------
    # Initiate a Vapi call
    # -------------------------------------------------------------------------

    async def initiate_vapi_call(
        self,
        contact: ContactInfo,
        caller_type: CallerType,
        lo_id: Optional[int],
        script_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Trigger an outbound call via the Vapi AI platform.

        Args:
            contact: Contact information
            caller_type: Classification of the contact
            lo_id: Loan officer ID
            script_context: Script template context

        Returns:
            Dict with call initiation result
        """
        from services.ai_call_scripts import CallScriptEngine

        # Build the script for this call
        script_engine = CallScriptEngine()
        script = script_engine.build_script(
            caller_type=caller_type,
            contact=contact,
            variant=script_context.get("script_variant", "default"),
        )

        # Get Vapi assistant config
        vapi_api_key = os.getenv("VAPI_API_KEY")
        if not vapi_api_key:
            return {"success": False, "error": "VAPI_API_KEY not configured"}

        vapi_phone_number_id = os.getenv("VAPI_PHONE_NUMBER_ID")
        if not vapi_phone_number_id:
            return {"success": False, "error": "VAPI_PHONE_NUMBER_ID not configured"}

        # Format phone to E.164
        phone = _format_e164(contact.phone)
        if not phone:
            return {"success": False, "error": "Invalid phone number"}

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "phoneNumberId": vapi_phone_number_id,
                    "customer": {
                        "number": phone,
                        "name": contact.name,
                    },
                    "assistant": {
                        "firstMessage": script.first_message,
                        "model": {
                            "provider": "openai",
                            "model": "gpt-4",
                            "messages": [
                                {
                                    "role": "system",
                                    "content": script.system_prompt,
                                }
                            ],
                        },
                        "voice": {
                            "provider": "deepgram",
                            "voiceId": "asteria",
                        },
                        "endCallMessage": script.end_call_message,
                        "endCallPhrases": ["goodbye", "have a great day", "talk to you later"],
                        "metadata": {
                            "contact_id": contact.id,
                            "entity_type": contact.entity_type,
                            "caller_type": caller_type.value,
                            "lo_id": lo_id,
                            "purpose": script_context.get("purpose", ""),
                            "organization_id": contact.organization_id,
                        },
                    },
                }

                response = await client.post(
                    "https://api.vapi.ai/call/phone",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {vapi_api_key}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code in (200, 201):
                    data = response.json()
                    vapi_call_id = data.get("id")

                    # Log the outbound call
                    await self._log_call_initiation(
                        contact=contact,
                        caller_type=caller_type,
                        vapi_call_id=vapi_call_id,
                        lo_id=lo_id,
                    )

                    return {
                        "success": True,
                        "vapi_call_id": vapi_call_id,
                        "status": data.get("status", "queued"),
                    }
                else:
                    error_text = response.text[:500]
                    logger.error(f"Vapi call creation failed ({response.status_code}): {error_text}")
                    return {
                        "success": False,
                        "error": f"Vapi API error: {response.status_code}",
                    }

        except Exception as e:
            logger.error(f"Error calling Vapi API: {e}")
            return {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Handle call outcomes
    # -------------------------------------------------------------------------

    async def handle_call_outcome(
        self,
        call_id: str,
        outcome: CallOutcome,
        appointment_id: Optional[int] = None,
        notes: Optional[str] = None,
        call_duration_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Record the result of a completed call.

        Args:
            call_id: The queued call ID
            outcome: Call outcome
            appointment_id: If an appointment was booked
            notes: Call notes or transcript summary
            call_duration_seconds: Duration of the call

        Returns:
            Dict with updated status
        """
        try:
            # Update in-memory queue
            call = next((c for c in self.queue._queue if c.id == call_id), None)

            if call:
                call.outcome = outcome
                call.appointment_id = appointment_id

                if outcome == CallOutcome.APPOINTMENT_SCHEDULED:
                    call.status = CallQueueStatus.COMPLETED
                elif outcome in (CallOutcome.CONNECTED, CallOutcome.CALLBACK_REQUESTED):
                    call.status = CallQueueStatus.COMPLETED
                elif outcome == CallOutcome.NOT_INTERESTED:
                    call.status = CallQueueStatus.COMPLETED
                elif outcome in (CallOutcome.NO_ANSWER, CallOutcome.VOICEMAIL, CallOutcome.BUSY):
                    await self._schedule_retry(call)
                else:
                    call.status = CallQueueStatus.COMPLETED

            # Persist outcome to database
            self.db.execute(text("""
                UPDATE ai_outbound_calls
                SET outcome = :outcome,
                    status = :status,
                    appointment_id = :appointment_id,
                    notes = :notes,
                    call_duration_seconds = :duration,
                    completed_at = :now
                WHERE call_id = :call_id
            """), {
                "outcome": outcome.value,
                "status": call.status.value if call else CallQueueStatus.COMPLETED.value,
                "appointment_id": appointment_id,
                "notes": notes,
                "duration": call_duration_seconds,
                "now": datetime.now(timezone.utc),
                "call_id": call_id,
            })
            self.db.commit()

            # Update last_contact on the entity
            if call and outcome in (
                CallOutcome.CONNECTED,
                CallOutcome.APPOINTMENT_SCHEDULED,
                CallOutcome.CALLBACK_REQUESTED,
                CallOutcome.NOT_INTERESTED,
            ):
                await self._update_last_contact(call.contact)

            return {
                "success": True,
                "call_id": call_id,
                "outcome": outcome.value,
                "status": call.status.value if call else "completed",
                "retry_scheduled": call.status == CallQueueStatus.RETRY_SCHEDULED if call else False,
            }

        except Exception as e:
            logger.error(f"Error handling call outcome for {call_id}: {e}")
            self.db.rollback()
            return {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Conversion statistics
    # -------------------------------------------------------------------------

    async def get_conversion_stats(
        self,
        lo_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        days: int = 30,
    ) -> ConversionStats:
        """
        Get call-to-appointment conversion rate statistics.

        Args:
            lo_id: Filter by loan officer
            organization_id: Filter by organization
            days: Lookback period in days

        Returns:
            ConversionStats with aggregated metrics
        """
        params: Dict[str, Any] = {"days": days}
        filters = ["created_at >= CURRENT_TIMESTAMP - make_interval(days => :days)"]

        if lo_id:
            filters.append("lo_id = :lo_id")
            params["lo_id"] = lo_id
        if organization_id:
            filters.append("organization_id = :organization_id")
            params["organization_id"] = organization_id

        where_sql = " AND ".join(filters)

        try:
            # Overall stats
            row = self.db.execute(text(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN outcome = 'connected' THEN 1 END) as connected,
                    COUNT(CASE WHEN outcome = 'voicemail' THEN 1 END) as voicemails,
                    COUNT(CASE WHEN outcome = 'no_answer' THEN 1 END) as no_answers,
                    COUNT(CASE WHEN outcome = 'appointment_scheduled' THEN 1 END) as appointments,
                    COUNT(CASE WHEN outcome = 'callback_requested' THEN 1 END) as callbacks,
                    COUNT(CASE WHEN outcome = 'not_interested' THEN 1 END) as not_interested
                FROM ai_outbound_calls
                WHERE {where_sql}
            """), params).fetchone()

            if not row:
                return ConversionStats()

            total = row[0] or 0
            connected = row[1] or 0
            appointments = row[4] or 0

            stats = ConversionStats(
                total_calls=total,
                connected=connected,
                voicemails=row[2] or 0,
                no_answers=row[3] or 0,
                appointments_scheduled=appointments,
                callbacks_requested=row[5] or 0,
                not_interested=row[6] or 0,
                connection_rate=round(connected / total * 100, 1) if total > 0 else 0.0,
                conversion_rate=round(appointments / total * 100, 1) if total > 0 else 0.0,
            )

            # By caller type
            type_rows = self.db.execute(text(f"""
                SELECT
                    caller_type,
                    COUNT(*) as total,
                    COUNT(CASE WHEN outcome = 'appointment_scheduled' THEN 1 END) as appointments
                FROM ai_outbound_calls
                WHERE {where_sql}
                GROUP BY caller_type
            """), params).fetchall()

            for tr in type_rows:
                t_total = tr[1] or 0
                t_appts = tr[2] or 0
                stats.by_caller_type[tr[0]] = {
                    "total": t_total,
                    "appointments": t_appts,
                    "conversion_rate": round(t_appts / t_total * 100, 1) if t_total > 0 else 0.0,
                }

            # By time of day (hour buckets)
            hour_rows = self.db.execute(text(f"""
                SELECT
                    EXTRACT(HOUR FROM created_at) as hour,
                    COUNT(*) as total,
                    COUNT(CASE WHEN outcome = 'connected' THEN 1 END) as connected,
                    COUNT(CASE WHEN outcome = 'appointment_scheduled' THEN 1 END) as appointments
                FROM ai_outbound_calls
                WHERE {where_sql}
                GROUP BY EXTRACT(HOUR FROM created_at)
                ORDER BY hour
            """), params).fetchall()

            for hr in hour_rows:
                hour_label = f"{int(hr[0]):02d}:00"
                h_total = hr[1] or 0
                stats.by_time_of_day[hour_label] = {
                    "total": h_total,
                    "connected": hr[2] or 0,
                    "appointments": hr[3] or 0,
                    "connection_rate": round((hr[2] or 0) / h_total * 100, 1) if h_total > 0 else 0.0,
                }

            # Average calls to appointment
            if stats.appointments_scheduled > 0 and stats.total_calls > 0:
                stats.avg_calls_to_appointment = round(
                    stats.total_calls / stats.appointments_scheduled, 1
                )

            return stats

        except Exception as e:
            logger.error(f"Error fetching conversion stats: {e}")
            return ConversionStats()

    # -------------------------------------------------------------------------
    # Bulk queue operations
    # -------------------------------------------------------------------------

    async def bulk_queue_segment(
        self,
        segment: str,
        lo_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        limit: int = 100,
        purpose: str = "",
        script_variant: str = "default",
    ) -> Dict[str, Any]:
        """
        Queue calls for an entire segment of contacts.

        Segments:
            - "new_leads": Leads created in last 24 hours with no contact
            - "stale_leads": Leads with no contact in 7+ days
            - "active_pipeline": Loans in active stages needing check-in
            - "mum_due": MUM clients due for annual review
            - "refi_opportunity": MUM clients with refinance opportunities

        Args:
            segment: Segment identifier
            lo_id: Filter by LO
            organization_id: Filter by org
            limit: Max contacts to queue
            purpose: Purpose override
            script_variant: Script variant override

        Returns:
            Summary of queued calls
        """
        contacts = await self._get_segment_contacts(
            segment, lo_id, organization_id, limit
        )

        queued_count = 0
        errors = []

        for entity_type, contact_id in contacts:
            result = await self.schedule_outbound_call(
                contact_id=contact_id,
                entity_type=entity_type,
                lo_id=lo_id,
                purpose=purpose or f"Bulk outreach: {segment}",
                script_variant=script_variant,
            )
            if result.get("success"):
                queued_count += 1
            else:
                errors.append({
                    "contact_id": contact_id,
                    "entity_type": entity_type,
                    "error": result.get("error"),
                })

        return {
            "success": True,
            "segment": segment,
            "total_contacts": len(contacts),
            "queued": queued_count,
            "errors": len(errors),
            "error_details": errors[:10],  # Cap error detail output
        }

    # -------------------------------------------------------------------------
    # Settings management
    # -------------------------------------------------------------------------

    async def get_settings(self, organization_id: int) -> Dict[str, Any]:
        """Get outbound scheduler settings for an organization."""
        try:
            row = self.db.execute(text("""
                SELECT settings FROM ai_outbound_settings
                WHERE organization_id = :org_id
            """), {"org_id": organization_id}).fetchone()

            if row and row[0]:
                return row[0]
        except Exception as e:
            logger.debug(f"No outbound settings found: {e}")
            self.db.rollback()

        # Return defaults
        return {
            "enabled": True,
            "max_calls_per_lo_per_day": MAX_AI_CALLS_PER_LO_PER_DAY,
            "calling_hours_start": CALLING_HOURS_START.strftime("%H:%M"),
            "calling_hours_end": CALLING_HOURS_END.strftime("%H:%M"),
            "retry_intervals_hours": RETRY_INTERVALS,
            "max_retries": 3,
            "speed_to_lead_enabled": True,
            "speed_to_lead_sla_minutes": 5,
            "auto_queue_new_leads": False,
            "auto_queue_mum_reviews": False,
            "preferred_script_variants": {
                "new_lead": "default",
                "active_client": "default",
                "mum": "default",
            },
        }

    async def update_settings(
        self,
        organization_id: int,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update outbound scheduler settings."""
        try:
            # Validate settings
            valid_keys = {
                "enabled", "max_calls_per_lo_per_day", "calling_hours_start",
                "calling_hours_end", "retry_intervals_hours", "max_retries",
                "speed_to_lead_enabled", "speed_to_lead_sla_minutes",
                "auto_queue_new_leads", "auto_queue_mum_reviews",
                "preferred_script_variants",
            }
            filtered = {k: v for k, v in settings.items() if k in valid_keys}

            # Merge with existing settings
            current = await self.get_settings(organization_id)
            current.update(filtered)

            # Upsert
            self.db.execute(text("""
                INSERT INTO ai_outbound_settings (organization_id, settings, updated_at)
                VALUES (:org_id, :settings, :now)
                ON CONFLICT (organization_id)
                DO UPDATE SET settings = :settings, updated_at = :now
            """), {
                "org_id": organization_id,
                "settings": current,
                "now": datetime.now(timezone.utc),
            })
            self.db.commit()

            return {"success": True, "settings": current}

        except Exception as e:
            logger.error(f"Error updating outbound settings: {e}")
            self.db.rollback()
            return {"success": False, "error": str(e)}

    # =========================================================================
    # Private helpers
    # =========================================================================

    async def _check_compliance(self, contact: ContactInfo) -> Dict[str, Any]:
        """Run compliance checks before calling."""
        if not contact.phone:
            return {"can_call": False, "reason": "No phone number", "check": "phone"}

        # DNC check
        try:
            from telephony.compliance import ComplianceChecker
            compliance = ComplianceChecker(self.db)
            is_dnc, reason = compliance.check_dnc(contact.phone)
            if is_dnc:
                return {"can_call": False, "reason": f"DNC: {reason}", "check": "dnc"}
        except ImportError:
            logger.debug("ComplianceChecker not available, skipping DNC check")
        except Exception as e:
            logger.warning(f"DNC check error: {e}")

        # TCPA consent check: verify contact has given consent for calls
        try:
            from database.models import Lead, Loan
            if contact.entity_type == "lead":
                lead = self.db.query(Lead).filter(Lead.id == contact.id).first()
                if lead and lead.preferred_communication == "Do Not Call":
                    return {
                        "can_call": False,
                        "reason": "Contact preference is Do Not Call",
                        "check": "consent",
                    }
                if lead and lead.stage == "Do Not Call":
                    return {
                        "can_call": False,
                        "reason": "Lead is in Do Not Call stage",
                        "check": "consent",
                    }
        except Exception as e:
            logger.debug(f"Consent check error: {e}")

        # Calling hours check
        if not _is_within_calling_hours(contact.timezone):
            return {"can_call": False, "reason": "Outside calling hours", "check": "hours"}

        return {"can_call": True}

    async def _check_rate_limit(self, lo_id: Optional[int]) -> bool:
        """Check if we've exceeded the daily call limit for this LO."""
        if not lo_id:
            return True

        try:
            result = self.db.execute(text("""
                SELECT COUNT(*) FROM ai_outbound_calls
                WHERE lo_id = :lo_id
                    AND created_at >= CURRENT_DATE
                    AND status != 'cancelled'
            """), {"lo_id": lo_id}).fetchone()

            count = result[0] if result else 0
            return count < MAX_AI_CALLS_PER_LO_PER_DAY
        except Exception as e:
            logger.warning(f"Rate limit check error: {e}")
            return True

    async def _schedule_retry(self, call: QueuedCall) -> None:
        """Schedule a retry for a failed/unanswered call."""
        if call.retry_count >= call.max_retries:
            call.status = CallQueueStatus.MAX_RETRIES
            return

        retry_index = min(call.retry_count, len(RETRY_INTERVALS) - 1)
        retry_hours = RETRY_INTERVALS[retry_index]

        call.retry_count += 1
        call.status = CallQueueStatus.RETRY_SCHEDULED
        call.scheduled_for = datetime.now(timezone.utc) + timedelta(hours=retry_hours)

        logger.info(
            f"Retry {call.retry_count}/{call.max_retries} for call {call.id} "
            f"scheduled at {call.scheduled_for}"
        )

    async def _persist_queued_call(self, call: QueuedCall) -> None:
        """Persist a queued call to the database."""
        try:
            self.db.execute(text("""
                INSERT INTO ai_outbound_calls (
                    call_id, contact_id, entity_type, contact_name, contact_phone,
                    caller_type, priority, purpose, script_variant,
                    status, retry_count, max_retries, scheduled_for,
                    lo_id, organization_id, created_at
                ) VALUES (
                    :call_id, :contact_id, :entity_type, :contact_name, :contact_phone,
                    :caller_type, :priority, :purpose, :script_variant,
                    :status, :retry_count, :max_retries, :scheduled_for,
                    :lo_id, :organization_id, :created_at
                )
            """), {
                "call_id": call.id,
                "contact_id": call.contact.id,
                "entity_type": call.contact.entity_type,
                "contact_name": call.contact.name,
                "contact_phone": call.contact.phone,
                "caller_type": call.caller_type.value,
                "priority": call.priority.value,
                "purpose": call.purpose,
                "script_variant": call.script_variant,
                "status": call.status.value,
                "retry_count": call.retry_count,
                "max_retries": call.max_retries,
                "scheduled_for": call.scheduled_for,
                "lo_id": call.contact.lo_id,
                "organization_id": call.contact.organization_id,
                "created_at": call.created_at,
            })
            self.db.commit()
        except Exception as e:
            logger.error(f"Error persisting queued call: {e}")
            self.db.rollback()

    async def _update_queued_call(self, call: QueuedCall) -> None:
        """Update a queued call in the database."""
        try:
            self.db.execute(text("""
                UPDATE ai_outbound_calls
                SET status = :status,
                    outcome = :outcome,
                    retry_count = :retry_count,
                    scheduled_for = :scheduled_for,
                    last_attempt_at = :last_attempt_at,
                    vapi_call_id = :vapi_call_id,
                    appointment_id = :appointment_id
                WHERE call_id = :call_id
            """), {
                "status": call.status.value,
                "outcome": call.outcome.value if call.outcome else None,
                "retry_count": call.retry_count,
                "scheduled_for": call.scheduled_for,
                "last_attempt_at": call.last_attempt_at,
                "vapi_call_id": call.vapi_call_id,
                "appointment_id": call.appointment_id,
                "call_id": call.id,
            })
            self.db.commit()
        except Exception as e:
            logger.error(f"Error updating queued call: {e}")
            self.db.rollback()

    async def _load_pending_calls(self) -> None:
        """Load pending calls from the database into the in-memory queue."""
        try:
            rows = self.db.execute(text("""
                SELECT call_id, contact_id, entity_type, contact_name, contact_phone,
                       caller_type, priority, purpose, script_variant,
                       status, retry_count, max_retries, scheduled_for,
                       lo_id, organization_id, created_at
                FROM ai_outbound_calls
                WHERE status IN ('pending', 'retry_scheduled')
                    AND (scheduled_for IS NULL OR scheduled_for <= CURRENT_TIMESTAMP)
                ORDER BY priority ASC, scheduled_for ASC NULLS FIRST
                LIMIT 100
            """)).fetchall()

            # Merge with in-memory queue (avoid duplicates)
            existing_ids = {c.id for c in self.queue._queue}
            for row in rows:
                if row[0] not in existing_ids:
                    contact = ContactInfo(
                        id=row[1],
                        entity_type=row[2],
                        name=row[3],
                        phone=row[4],
                        caller_type=CallerType(row[5]),
                        lo_id=row[13],
                        organization_id=row[14],
                    )
                    call = QueuedCall(
                        id=row[0],
                        contact=contact,
                        caller_type=CallerType(row[5]),
                        priority=CallPriority(row[6]),
                        purpose=row[7] or "",
                        script_variant=row[8] or "default",
                        status=CallQueueStatus(row[9]),
                        retry_count=row[10] or 0,
                        max_retries=row[11] or 3,
                        scheduled_for=row[12],
                        created_at=row[15],
                    )
                    self.queue._queue.append(call)

            # Re-sort
            self.queue._queue.sort(
                key=lambda c: (c.priority.value, c.scheduled_for or datetime.min.replace(tzinfo=timezone.utc))
            )

        except Exception as e:
            logger.warning(f"Error loading pending calls: {e}")

    async def _log_call_initiation(
        self,
        contact: ContactInfo,
        caller_type: CallerType,
        vapi_call_id: Optional[str],
        lo_id: Optional[int],
    ) -> None:
        """Log the call initiation to call_logs table."""
        try:
            self.db.execute(text("""
                INSERT INTO call_logs (
                    agent_id, contact_phone, contact_name, lead_id, loan_id,
                    mum_client_id, call_sid, outcome, created_at, start_time
                ) VALUES (
                    :agent_id, :phone, :name, :lead_id, :loan_id,
                    :mum_id, :call_sid, 'initiated', :now, :now
                )
            """), {
                "agent_id": lo_id,
                "phone": contact.phone,
                "name": contact.name,
                "lead_id": contact.id if contact.entity_type == "lead" else None,
                "loan_id": contact.id if contact.entity_type == "loan" else None,
                "mum_id": contact.id if contact.entity_type == "mum_client" else None,
                "call_sid": vapi_call_id,
                "now": datetime.now(timezone.utc),
            })
            self.db.commit()
        except Exception as e:
            logger.warning(f"Error logging call initiation: {e}")
            self.db.rollback()

    async def _update_last_contact(self, contact: ContactInfo) -> None:
        """Update the last_contact timestamp on the entity."""
        now = datetime.now(timezone.utc)
        try:
            if contact.entity_type == "lead":
                self.db.execute(text(
                    "UPDATE leads SET last_contact = :now WHERE id = :id"
                ), {"now": now, "id": contact.id})
            elif contact.entity_type == "loan":
                # Loans don't have a last_contact column, skip
                pass
            elif contact.entity_type == "mum_client":
                self.db.execute(text(
                    "UPDATE mum_clients SET last_contact = :now WHERE id = :id"
                ), {"now": now, "id": contact.id})
            self.db.commit()
        except Exception as e:
            logger.warning(f"Error updating last_contact: {e}")
            self.db.rollback()

    async def _get_segment_contacts(
        self,
        segment: str,
        lo_id: Optional[int],
        organization_id: Optional[int],
        limit: int,
    ) -> List[Tuple[str, int]]:
        """
        Get contacts for a segment. Returns list of (entity_type, contact_id).
        """
        params: Dict[str, Any] = {"limit": limit}
        lo_filter = ""
        org_filter = ""

        if lo_id:
            params["lo_id"] = lo_id
        if organization_id:
            params["org_id"] = organization_id

        try:
            if segment == "new_leads":
                lo_filter = "AND l.owner_id = :lo_id" if lo_id else ""
                org_filter = "AND l.organization_id = :org_id" if organization_id else ""
                rows = self.db.execute(text(f"""
                    SELECT 'lead', l.id
                    FROM leads l
                    WHERE l.phone IS NOT NULL AND l.phone != ''
                        AND l.stage IN ('New', 'Attempted Contact', 'Prospect')
                        AND l.created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                        AND l.last_contact IS NULL
                        {lo_filter} {org_filter}
                    ORDER BY l.ai_score DESC NULLS LAST, l.created_at DESC
                    LIMIT :limit
                """), params).fetchall()

            elif segment == "stale_leads":
                lo_filter = "AND l.owner_id = :lo_id" if lo_id else ""
                org_filter = "AND l.organization_id = :org_id" if organization_id else ""
                rows = self.db.execute(text(f"""
                    SELECT 'lead', l.id
                    FROM leads l
                    WHERE l.phone IS NOT NULL AND l.phone != ''
                        AND l.stage NOT IN (
                            'Closed', 'Funded', 'Withdrawn', 'Does Not Qualify',
                            'Do Not Call', 'Credit Repair'
                        )
                        AND (l.last_contact IS NULL OR l.last_contact < CURRENT_TIMESTAMP - INTERVAL '7 days')
                        {lo_filter} {org_filter}
                    ORDER BY l.ai_score DESC NULLS LAST
                    LIMIT :limit
                """), params).fetchall()

            elif segment == "active_pipeline":
                lo_loan_filter = "AND lo.loan_officer_id = :lo_id" if lo_id else ""
                org_loan_filter = "AND lo.organization_id = :org_id" if organization_id else ""
                rows = self.db.execute(text(f"""
                    SELECT 'loan', lo.id
                    FROM loans lo
                    WHERE lo.borrower_phone IS NOT NULL AND lo.borrower_phone != ''
                        AND lo.stage NOT IN (
                            'FUNDED', 'CANCELLED', 'DENIED', 'DEAD',
                            'WITHDRAWN', 'DOES_NOT_QUALIFY'
                        )
                        AND lo.stage_changed_at < CURRENT_TIMESTAMP - INTERVAL '5 days'
                        {lo_loan_filter} {org_loan_filter}
                    ORDER BY lo.stage_changed_at ASC
                    LIMIT :limit
                """), params).fetchall()

            elif segment == "mum_due":
                mum_user_filter = "AND m.user_id = :lo_id" if lo_id else ""
                mum_org_filter = "AND m.organization_id = :org_id" if organization_id else ""
                rows = self.db.execute(text(f"""
                    SELECT 'mum_client', m.id
                    FROM mum_clients m
                    WHERE m.phone IS NOT NULL AND m.phone != ''
                        AND (m.last_contact IS NULL OR m.last_contact < CURRENT_TIMESTAMP - INTERVAL '90 days')
                        AND (m.status IS NULL OR m.status != 'inactive')
                        {mum_user_filter} {mum_org_filter}
                    ORDER BY m.last_contact ASC NULLS FIRST
                    LIMIT :limit
                """), params).fetchall()

            elif segment == "refi_opportunity":
                mum_user_filter = "AND m.user_id = :lo_id" if lo_id else ""
                mum_org_filter = "AND m.organization_id = :org_id" if organization_id else ""
                rows = self.db.execute(text(f"""
                    SELECT 'mum_client', m.id
                    FROM mum_clients m
                    WHERE m.phone IS NOT NULL AND m.phone != ''
                        AND m.refinance_opportunity = true
                        AND (m.status IS NULL OR m.status != 'inactive')
                        {mum_user_filter} {mum_org_filter}
                    ORDER BY m.refi_score DESC NULLS LAST
                    LIMIT :limit
                """), params).fetchall()

            else:
                logger.warning(f"Unknown segment: {segment}")
                return []

            return [(row[0], row[1]) for row in rows]

        except Exception as e:
            logger.error(f"Error getting segment contacts for '{segment}': {e}")
            return []


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _infer_timezone(state_code: Optional[str]) -> str:
    """Infer timezone from US state code. Falls back to America/Chicago."""
    if not state_code:
        return "America/Chicago"

    state_tz_map = {
        "CT": "America/New_York", "DE": "America/New_York", "FL": "America/New_York",
        "GA": "America/New_York", "IN": "America/Indiana/Indianapolis",
        "KY": "America/New_York", "MA": "America/New_York", "MD": "America/New_York",
        "ME": "America/New_York", "MI": "America/Detroit", "NC": "America/New_York",
        "NH": "America/New_York", "NJ": "America/New_York", "NY": "America/New_York",
        "OH": "America/New_York", "PA": "America/New_York", "RI": "America/New_York",
        "SC": "America/New_York", "TN": "America/New_York", "VA": "America/New_York",
        "VT": "America/New_York", "WV": "America/New_York", "DC": "America/New_York",
        "AL": "America/Chicago", "AR": "America/Chicago", "IA": "America/Chicago",
        "IL": "America/Chicago", "KS": "America/Chicago", "LA": "America/Chicago",
        "MN": "America/Chicago", "MO": "America/Chicago", "MS": "America/Chicago",
        "ND": "America/Chicago", "NE": "America/Chicago", "OK": "America/Chicago",
        "SD": "America/Chicago", "TX": "America/Chicago", "WI": "America/Chicago",
        "AZ": "America/Phoenix", "CO": "America/Denver", "ID": "America/Boise",
        "MT": "America/Denver", "NM": "America/Denver", "UT": "America/Denver",
        "WY": "America/Denver",
        "CA": "America/Los_Angeles", "NV": "America/Los_Angeles",
        "OR": "America/Los_Angeles", "WA": "America/Los_Angeles",
        "AK": "America/Anchorage", "HI": "Pacific/Honolulu",
    }

    return state_tz_map.get(state_code.upper().strip(), "America/Chicago")


def _is_within_calling_hours(tz_name: str) -> bool:
    """Check if current time is within TCPA calling hours for the given timezone."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        import pytz
        local_now = datetime.now(pytz.timezone(tz_name))
        current_time = local_now.time()
        return CALLING_HOURS_START <= current_time <= CALLING_HOURS_END

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/Chicago")

    local_now = datetime.now(tz)
    current_time = local_now.time()
    return CALLING_HOURS_START <= current_time <= CALLING_HOURS_END


def _next_calling_window(tz_name: str) -> datetime:
    """Calculate the next time we can call in the contact's timezone."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
    except Exception:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Chicago")

    local_now = datetime.now(tz)

    if local_now.time() >= CALLING_HOURS_END:
        # Next day at start time
        next_day = local_now.date() + timedelta(days=1)
        next_start = datetime.combine(next_day, CALLING_HOURS_START, tzinfo=tz)
    elif local_now.time() < CALLING_HOURS_START:
        # Today at start time
        next_start = datetime.combine(local_now.date(), CALLING_HOURS_START, tzinfo=tz)
    else:
        # We're within hours (shouldn't normally reach here)
        return datetime.now(timezone.utc)

    # Convert to UTC
    return next_start.astimezone(timezone.utc)


def _format_e164(phone: str) -> Optional[str]:
    """Format phone number to E.164 format."""
    if not phone:
        return None

    digits = "".join(c for c in phone if c.isdigit())

    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    elif len(digits) > 10 and phone.startswith("+"):
        return f"+{digits}"

    return None


def _mask_phone(phone: str) -> str:
    """Mask phone number for display."""
    if not phone or len(phone) < 7:
        return "***"
    return phone[:3] + "***" + phone[-4:]


def _default_purpose(caller_type: CallerType, contact: ContactInfo) -> str:
    """Generate a default purpose string for the call."""
    if caller_type == CallerType.NEW_LEAD:
        return "Initial consultation - discuss loan needs and schedule appointment"
    elif caller_type == CallerType.ACTIVE_CLIENT:
        stage = contact.loan_stage or "active"
        return f"Loan progress check-in ({stage}) - discuss next steps"
    elif caller_type == CallerType.MUM:
        if contact.refinance_opportunity:
            return "Refinance opportunity discussion - rate savings review"
        return "Annual mortgage review - check in and discuss home equity"
    return "Follow-up call"


# =============================================================================
# TABLE CREATION
# =============================================================================

def ensure_outbound_tables(db: Session) -> None:
    """Create the ai_outbound_calls and ai_outbound_settings tables if needed."""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_outbound_calls (
                id SERIAL PRIMARY KEY,
                call_id VARCHAR(100) UNIQUE NOT NULL,
                contact_id INTEGER NOT NULL,
                entity_type VARCHAR(20) NOT NULL,
                contact_name VARCHAR(255),
                contact_phone VARCHAR(20),
                caller_type VARCHAR(30) NOT NULL,
                priority INTEGER DEFAULT 3,
                purpose TEXT,
                script_variant VARCHAR(50) DEFAULT 'default',
                status VARCHAR(30) DEFAULT 'pending',
                outcome VARCHAR(40),
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                scheduled_for TIMESTAMP WITH TIME ZONE,
                last_attempt_at TIMESTAMP WITH TIME ZONE,
                completed_at TIMESTAMP WITH TIME ZONE,
                vapi_call_id VARCHAR(100),
                appointment_id INTEGER,
                lo_id INTEGER,
                organization_id INTEGER,
                notes TEXT,
                call_duration_seconds INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS ix_outbound_calls_status
                ON ai_outbound_calls (status, scheduled_for);
            CREATE INDEX IF NOT EXISTS ix_outbound_calls_lo
                ON ai_outbound_calls (lo_id, created_at);
            CREATE INDEX IF NOT EXISTS ix_outbound_calls_org
                ON ai_outbound_calls (organization_id, created_at);
            CREATE INDEX IF NOT EXISTS ix_outbound_calls_contact
                ON ai_outbound_calls (entity_type, contact_id);

            CREATE TABLE IF NOT EXISTS ai_outbound_settings (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER UNIQUE NOT NULL,
                settings JSONB DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """))
        db.commit()
        logger.info("AI outbound tables ensured")
    except Exception as e:
        logger.warning(f"Outbound table creation note: {e}")
        try:
            db.rollback()
        except Exception:
            pass
