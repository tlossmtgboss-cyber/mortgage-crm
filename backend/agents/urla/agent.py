"""
Perennia AI — URLA LiveKit Agent
================================
The dedicated URLA 1003 voice agent. Separate from Aria (the receptionist).

Architecture:
    Deepgram Nova-3 (STT) -> Claude/GPT-4o (LLM) -> Cartesia Sonic-3 (TTS)
    Silero VAD for turn detection.

The LLM calls @function_tool methods on URLAAgent. Each tool:
  1. Loads the active URLAApplication from Redis (keyed by caller phone + loan_id)
  2. Applies the section update using Pydantic models
  3. Saves back to Redis (refreshes TTL)
  4. Returns a short, voice-ready confirmation string for the LLM to speak

Tools are organized to mirror URLA sections. Each save_* tool is idempotent
and safe to retry.

NOTE on LiveKit decorator:
    This file uses `@function_tool` which is the current stable LiveKit Agents
    API (v1.0+, 2025+). If your codebase is pinned to an older version using
    `@llm.tool` or `@llm.ai_callable()`, swap the import and decorator — the
    method bodies are identical.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any

from livekit.agents import Agent, RunContext, function_tool, get_job_context

from .models import (
    URLAApplication,
    Borrower,
    Address,
    ResidenceHistory,
    Section1a_PersonalInformation,
    Section1b_CurrentEmployment,
    Section1c_AdditionalEmployment,
    Section1d_PreviousEmployment,
    Section1e_OtherIncome,
    OtherIncomeSource,
    Section2_AssetsAndLiabilities,
    Asset,
    OtherCredit,
    Liability,
    OtherLiability,
    Section3_RealEstate,
    PropertyOwned,
    REOMortgage,
    Section4_LoanAndProperty,
    Section4a_LoanAndProperty,
    Section4b_OtherNewMortgages,
    Section4c_RentalIncomeOnSubject,
    Section4d_GiftsOrGrants,
    Gift,
    Section5_Declarations,
    Section5a_DeclarationsPropertyMoney,
    Section5b_DeclarationsFinances,
    Section6_Acknowledgments,
    Section7_MilitaryService,
    Section8_Demographics,
    CitizenshipStatus,
    MaritalStatus,
    LoanPurpose,
    LoanType,
    PropertyOccupancy,
    PropertyStatus,
    AssetType,
    LiabilityType,
    OtherIncomeType,
    GiftType,
    GiftSource,
    EthnicityCategory,
    RaceCategory,
    SexCategory,
)
from .state import URLAStateManager
from .prompts import SYSTEM_PROMPT
from . import validators as V
from .bytepro_adapter import push_to_bytepro, LoanOfficer, PushResult
from .smart_calendar_adapter import (
    fetch_available_slots,
    book_slot,
    AvailableSlot,
    BookingResult,
)
from .models import LOKickoffBooking
from .sanitizer import sanitize_text, sanitize_name, sanitize_address, sanitize_description
from .transcript_scrubber import scrub_post_call


logger = logging.getLogger("urla.agent")


# =============================================================================
# AGENT
# =============================================================================

class URLAAgent(Agent):
    """
    LiveKit Agent for URLA 1003 intake.

    Construct with:
        tenant_id: multi-tenant scoping ID
        caller_phone: E.164 phone number from the telephony leg
        state: URLAStateManager (already connected)
        loan_officer: LoanOfficer assigned to this caller (for Section 9)
    """

    def __init__(
        self,
        tenant_id: str,
        caller_phone: str,
        state: URLAStateManager,
        loan_officer: LoanOfficer,
        crm_contact_id: Optional[int] = None,
        crm_loan_id: Optional[int] = None,
    ):
        super().__init__(instructions=SYSTEM_PROMPT)
        self.tenant_id = tenant_id
        self.caller_phone = caller_phone
        self.state = state
        self.loan_officer = loan_officer
        self.crm_contact_id: Optional[int] = crm_contact_id
        self.crm_loan_id: Optional[int] = crm_loan_id
        self._active_loan_id: Optional[str] = None
        self._session_lock_token: Optional[str] = None
        # Cache of slots offered to the caller; indexed 1..N for voice readback
        self._offered_slots: List[AvailableSlot] = []
        # Rate-limit counters for list-append tools (Fix I4)
        self._tool_call_counts: Dict[str, int] = {}
        # Transcript buffer for batched persistence
        self._transcript_buffer: List[Any] = []
        self._transcript_flush_count: int = 0

    # Section ordering for enforcement (Fix I8)
    _SECTION_ORDER: Dict[str, int] = {
        "SECTION_1A": 1,
        "SECTION_1B": 2,
        "SECTION_1C": 3,
        "SECTION_1D": 4,
        "SECTION_1E": 5,
        "SECTION_2": 6,
        "SECTION_3": 7,
        "SECTION_4A": 8,
        "SECTION_4B": 9,
        "SECTION_4C": 10,
        "SECTION_4D": 11,
        "SECTION_5A": 12,
        "SECTION_5B": 13,
        "SECTION_7": 14,
        "SECTION_8": 15,
        "COBORROWER_CHECK": 16,
        "SECTION_6": 17,
        "FINAL_SUMMARY": 18,
    }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_rate_limit(self, tool_name: str, max_calls: int = 50) -> None:
        """Increment call count for a tool and raise if exceeded."""
        self._tool_call_counts[tool_name] = self._tool_call_counts.get(tool_name, 0) + 1
        if self._tool_call_counts[tool_name] > max_calls:
            raise RuntimeError(
                f"Rate limit exceeded: {tool_name} called {self._tool_call_counts[tool_name]} "
                f"times (max {max_calls}). This may indicate a loop."
            )

    async def _assert_section_reachable_async(self, target_section: str) -> None:
        """Async version that loads app state to validate section ordering."""
        app = await self._load()
        current = app.current_section
        # Allow corrections: target already completed
        if target_section in (app.completed_sections or []):
            return
        # Allow if target IS the current section
        if target_section == current:
            return
        # Allow if target is the next logical section from current
        current_order = self._SECTION_ORDER.get(current, 0)
        target_order = self._SECTION_ORDER.get(target_section, 0)
        if target_order <= current_order + 1:
            return
        raise RuntimeError(
            f"Cannot jump to {target_section} from {current}. "
            f"Complete the current section first or go back to correct a completed section."
        )

    async def _load(self, loan_id: Optional[str] = None) -> URLAApplication:
        lid = loan_id or self._active_loan_id
        if not lid:
            raise RuntimeError(
                "No active URLA session. Call start_urla_application or "
                "resume_urla_application first."
            )
        app = await self.state.load_application(self.tenant_id, lid)
        if app is None:
            raise RuntimeError(f"Loan {lid} not found or expired.")
        if (self._session_lock_token
                and app.session_lock_token
                and app.session_lock_token != self._session_lock_token):
            raise RuntimeError(
                "This application is being edited in another session. "
                "Please try again later or call back."
            )
        return app

    async def _save_and_advance(
        self,
        app: URLAApplication,
        section_key: str,
        next_section: str,
    ) -> None:
        await self.state.mark_section_complete(app, section_key, next_section=next_section)

    def _primary(self, app: URLAApplication) -> Borrower:
        p = app.primary_borrower()
        if not p:
            raise RuntimeError("No primary borrower on application.")
        return p

    # ==================================================================
    # SESSION LIFECYCLE
    # ==================================================================

    @function_tool
    async def start_urla_application(self, ctx: RunContext) -> str:
        """
        Call this when the caller confirms they want to start a NEW application.
        Creates a loan ID and initializes the record.
        """
        app = await self.state.create_application(
            tenant_id=self.tenant_id,
            caller_phone=self.caller_phone,
        )
        self._active_loan_id = app.loan_id
        self._session_lock_token = app.session_lock_token
        logger.info("Started new URLA", extra={"loan_id": app.loan_id})
        return (
            f"Application started. Your loan ID is {_spell_loan_id(app.loan_id)}. "
            f"I'll walk you through the application section by section. "
            f"Let's begin with your personal information."
        )

    @function_tool
    async def resume_urla_application(
        self,
        ctx: RunContext,
        loan_id: Optional[str] = None,
    ) -> str:
        """
        Resume an application in progress for this caller's phone.
        If a specific loan_id is provided, resume that one; otherwise the most
        recently active one for this phone.
        """
        if loan_id:
            app = await self.state.load_application(self.tenant_id, loan_id)
        else:
            app = await self.state.get_active_application(self.tenant_id, self.caller_phone)

        if not app:
            return (
                "I couldn't find a saved application for this number. Would you "
                "like to start a new one?"
            )

        import uuid
        self._active_loan_id = app.loan_id
        app.session_lock_token = uuid.uuid4().hex
        self._session_lock_token = app.session_lock_token
        await self.state.resume(app)
        summary = app.progress_summary()
        section_name = summary["current_section"].replace("_", " ").title()
        return (
            f"Welcome back. Your application {_spell_loan_id(app.loan_id)} is "
            f"{summary['percent_complete']} percent complete. You were on "
            f"{section_name}. Ready to pick up where you left off?"
        )

    @function_tool
    async def get_urla_status(self, ctx: RunContext) -> Dict[str, Any]:
        """Return a progress snapshot. Use to confirm completeness before finalize."""
        app = await self._load()
        return app.progress_summary()

    @function_tool
    async def pause_application(self, ctx: RunContext) -> str:
        """Caller wants to pause — save progress and give them their loan ID for callback."""
        app = await self._load()
        await self.state.pause(app)
        return (
            f"No problem. I've saved everything. Your loan ID is "
            f"{_spell_loan_id(app.loan_id)}. Call back anytime and mention "
            f"that ID or your phone number and we'll pick right back up."
        )

    @function_tool
    async def request_human_transfer(
        self,
        ctx: RunContext,
        reason: str,
    ) -> str:
        """
        Caller asked for a human, or hit a case the agent cannot handle.
        Pauses the application, builds a handoff context for the LO, attempts
        a SIP warm transfer, and creates a CRM callback task as backup.
        """
        app = await self._load()

        # 1. Pause the application so progress is persisted
        await self.state.pause(app)

        # 2. Build handoff context for structured logging / LO briefing
        progress = app.progress_summary()
        primary = app.primary_borrower()
        borrower_name = (
            f"{primary.section_1a.first_name or ''} {primary.section_1a.last_name or ''}".strip()
            if primary and primary.section_1a else "Unknown"
        )
        handoff = {
            "loan_id": app.loan_id,
            "reason": reason,
            "progress": progress,
            "borrower_name": borrower_name,
            "caller_phone": self.caller_phone,
            "percent_complete": progress.get("percent_complete", 0),
            "current_section": progress.get("current_section", "UNKNOWN"),
            "completed_sections": progress.get("completed_sections", []),
        }
        logger.info("Human transfer requested", extra=handoff)

        # 3. Always create a CRM callback task as backup (before attempting transfer,
        #    so even if the transfer succeeds the LO has a record)
        callback_task_created = await self._create_callback_task(app, reason, progress)

        # 4. Attempt SIP warm transfer via LiveKit
        transfer_target = self.loan_officer.phone or os.getenv(
            "URLA_FALLBACK_TRANSFER_NUMBER", ""
        )
        if transfer_target:
            transfer_succeeded = await self._attempt_sip_transfer(
                ctx, app, reason, transfer_target, borrower_name
            )
            if transfer_succeeded:
                return (
                    "I'm transferring you to your loan officer now. Everything "
                    "we've covered is saved and they'll have full context. "
                    "Please hold for just a moment."
                )

        # 5. Fallback: transfer failed or no target number
        loan_id_spelled = _spell_loan_id(app.loan_id)
        if callback_task_created:
            return (
                "I wasn't able to transfer you directly right now, but I've "
                "flagged your account for an urgent callback. Your loan officer "
                f"will reach out within the hour. Your loan ID is {loan_id_spelled} "
                "for reference."
            )
        return (
            "I wasn't able to connect you right now. Your application is saved "
            f"and your loan ID is {loan_id_spelled}. Please call back or your "
            "loan officer will follow up with you shortly."
        )

    async def _attempt_sip_transfer(
        self,
        ctx: RunContext,
        app: "URLAApplication",
        reason: str,
        transfer_target: str,
        borrower_name: str,
    ) -> bool:
        """
        Attempt a SIP warm transfer using LiveKit's WarmTransferTask.
        Falls back to the lower-level transfer_sip_participant API if the
        beta workflows module is unavailable (older SDK).
        Returns True if the transfer was initiated successfully.
        """
        sip_trunk_id = os.getenv("LIVEKIT_SIP_OUTBOUND_TRUNK", "")

        # --- Path A: WarmTransferTask (preferred, handles hold music + context) ---
        try:
            from livekit.agents.beta.workflows import WarmTransferTask

            extra_instructions = (
                f"You are connecting a borrower to their loan officer. "
                f"Borrower: {borrower_name}. "
                f"Loan ID: {app.loan_id}. "
                f"Transfer reason: {reason}. "
                f"Application is {app.progress_summary().get('percent_complete', 0)}% complete. "
                f"Current section: {app.current_section}."
            )

            kwargs: Dict[str, Any] = {
                "sip_call_to": transfer_target,
                "chat_ctx": ctx.session.chat_ctx,
                "extra_instructions": extra_instructions,
            }
            if sip_trunk_id:
                kwargs["sip_trunk_id"] = sip_trunk_id

            result = await WarmTransferTask(**kwargs)
            logger.info(
                "SIP warm transfer completed",
                extra={
                    "loan_id": app.loan_id,
                    "transfer_to": transfer_target,
                    "human_agent_identity": getattr(result, "human_agent_identity", None),
                },
            )
            return True

        except ImportError:
            logger.info(
                "WarmTransferTask not available, trying lower-level SIP transfer",
                extra={"loan_id": app.loan_id},
            )
        except Exception as e:
            logger.warning(
                "WarmTransferTask failed, trying lower-level SIP transfer",
                extra={"loan_id": app.loan_id, "error": str(e)},
            )

        # --- Path B: Lower-level transfer_sip_participant API (cold transfer) ---
        try:
            from livekit import api as lk_api

            job_ctx = get_job_context()
            lk = lk_api.LiveKitAPI()

            # Find the SIP participant (the caller, not the agent)
            for p in job_ctx.room.remote_participants.values():
                if hasattr(p, "kind") and str(getattr(p, "kind", "")).upper() == "SIP":
                    await lk.sip.transfer_sip_participant(
                        lk_api.TransferSIPParticipantRequest(
                            room_name=job_ctx.room.name,
                            participant_identity=p.identity,
                            transfer_to=f"sip:{transfer_target}@sip.livekit.io",
                        )
                    )
                    logger.info(
                        "SIP cold transfer initiated",
                        extra={
                            "loan_id": app.loan_id,
                            "transfer_to": transfer_target,
                            "participant": p.identity,
                        },
                    )
                    return True

            # If no SIP participant found, try any non-agent remote participant
            for p in job_ctx.room.remote_participants.values():
                if not getattr(p, "is_agent", False):
                    await lk.sip.transfer_sip_participant(
                        lk_api.TransferSIPParticipantRequest(
                            room_name=job_ctx.room.name,
                            participant_identity=p.identity,
                            transfer_to=f"sip:{transfer_target}@sip.livekit.io",
                        )
                    )
                    logger.info(
                        "SIP cold transfer initiated (non-SIP participant)",
                        extra={
                            "loan_id": app.loan_id,
                            "transfer_to": transfer_target,
                            "participant": p.identity,
                        },
                    )
                    return True

            logger.warning(
                "No transferable participant found in room",
                extra={"loan_id": app.loan_id, "room": job_ctx.room.name},
            )
            return False

        except ImportError:
            logger.warning(
                "LiveKit SIP API not available — cannot transfer",
                extra={"loan_id": app.loan_id},
            )
            return False
        except Exception as e:
            logger.warning(
                "SIP cold transfer failed",
                extra={"loan_id": app.loan_id, "error": str(e)},
            )
            return False

    async def _create_callback_task(
        self,
        app: "URLAApplication",
        reason: str,
        progress: Dict[str, Any],
    ) -> bool:
        """
        Create an urgent callback task in the CRM so the LO is notified even
        if the SIP transfer succeeds (belt-and-suspenders). Returns True if
        the task was created successfully.
        """
        try:
            import httpx

            crm_api_base = os.getenv("CRM_API_BASE_URL", "")
            crm_api_key = os.getenv("CRM_API_KEY", "")
            if not crm_api_base or not crm_api_key:
                logger.info(
                    "CRM API not configured, skipping callback task",
                    extra={"loan_id": app.loan_id},
                )
                return False

            primary = app.primary_borrower()
            borrower_name = (
                f"{primary.section_1a.first_name or ''} {primary.section_1a.last_name or ''}".strip()
                if primary and primary.section_1a else "Unknown borrower"
            )
            percent = progress.get("percent_complete", 0)
            completed = progress.get("completed_sections", [])

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{crm_api_base}/api/v1/tasks",
                    json={
                        "title": f"Callback requested -- URLA {app.loan_id}",
                        "description": (
                            f"Borrower {borrower_name} ({self.caller_phone}) requested "
                            f"human transfer during URLA intake.\n"
                            f"Reason: {reason}\n"
                            f"Progress: {percent}% complete "
                            f"({len(completed)}/{len(app.TRACKABLE_SECTIONS)} sections).\n"
                            f"Current section: {app.current_section}\n"
                            f"Completed: {', '.join(completed) if completed else 'None'}\n"
                            f"Loan ID: {app.loan_id}"
                        ),
                        "priority": "high",
                        "task_type": "callback",
                    },
                    headers={"Authorization": f"Bearer {crm_api_key}"},
                )
                if resp.status_code in (200, 201):
                    logger.info(
                        "Callback task created",
                        extra={"loan_id": app.loan_id},
                    )
                    return True
                else:
                    logger.warning(
                        "Callback task creation returned non-success",
                        extra={
                            "loan_id": app.loan_id,
                            "status": resp.status_code,
                            "body": resp.text[:200],
                        },
                    )
                    return False
        except Exception as e:
            logger.warning(
                "Callback task creation failed",
                extra={"loan_id": app.loan_id, "error": str(e)},
            )
            return False

    # ==================================================================
    # SECTION 1a — PERSONAL INFORMATION
    # ==================================================================

    @function_tool
    async def save_section_1a_personal(
        self,
        ctx: RunContext,
        borrower_id: str,
        first_name: str,
        last_name: str,
        date_of_birth: str,
        ssn: str,
        citizenship: str,
        marital_status: str,
        current_street: str,
        current_city: str,
        current_state: str,
        current_zip: str,
        email: str,
        cell_phone: str,
        middle_name: Optional[str] = None,
        years_at_address: int = 0,
        months_at_address: int = 0,
        own_or_rent: Optional[str] = None,
        monthly_housing_expense: Optional[float] = None,
        dependents_count: Optional[int] = None,
    ) -> str:
        """
        Save Section 1a. Accepts natural-language inputs; validators normalize.

        Required: borrower_id ("borrower_1" for primary, "borrower_2" for co-),
        first/last name, DOB, SSN, citizenship, marital status, current address,
        email, cell phone.
        """
        await self._assert_section_reachable_async("SECTION_1A")
        app = await self._load()
        borrower = app.get_borrower(borrower_id) or Borrower(
            borrower_id=borrower_id, is_primary=(borrower_id == "borrower_1")
        )

        section = borrower.section_1a or Section1a_PersonalInformation()
        section.first_name = sanitize_name(first_name, "first_name")
        section.middle_name = sanitize_name(middle_name, "middle_name")
        section.last_name = sanitize_name(last_name, "last_name")
        section.date_of_birth = V.parse_date(date_of_birth)

        # Age validation (Fix I18)
        today = datetime.now(timezone.utc).date()
        dob = section.date_of_birth
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 18 or age > 120:
            return (
                f"The date of birth {date_of_birth} gives an age of {age}, which "
                f"doesn't seem right. Could you confirm the date of birth?"
            )

        section.ssn = V.parse_ssn(ssn)
        section.citizenship = CitizenshipStatus(_norm_enum(citizenship, CitizenshipStatus))
        section.marital_status = MaritalStatus(_norm_enum(marital_status, MaritalStatus))
        section.email = email
        section.cell_phone = V.parse_phone(cell_phone)
        section.dependents_count = dependents_count

        section.current_address = ResidenceHistory(
            address=Address(
                street=sanitize_address(current_street, "street"),
                city=sanitize_name(current_city, "city"),
                state=V.parse_state(current_state),
                zip_code=current_zip,
            ),
            years_at_address=years_at_address,
            months_at_address=months_at_address,
            own_or_rent=own_or_rent.upper() if own_or_rent else None,
            housing_expense_monthly=(
                Decimal(str(monthly_housing_expense)) if monthly_housing_expense else None
            ),
        )

        borrower.section_1a = section
        if borrower_id not in [b.borrower_id for b in app.borrowers]:
            app.borrowers.append(borrower)

        await self._save_and_advance(app, "SECTION_1A", "SECTION_1B")
        name_readback = f"{first_name} {last_name}"
        ssn_masked = f"ending in {section.ssn[-4:]}"
        return (
            f"Got it. I have {name_readback}, date of birth "
            f"{section.date_of_birth.strftime('%B %d, %Y')}. Your Social is "
            f"{ssn_masked}. Ready to move on to employment and income?"
        )

    @function_tool
    async def save_prior_address(
        self,
        ctx: RunContext,
        borrower_id: str,
        street: str,
        city: str,
        state: str,
        zip_code: str,
        years: int,
        months: int,
    ) -> str:
        """Add a prior address when the borrower has been at current address less than 2 years."""
        await self._assert_section_reachable_async("SECTION_1A")
        app = await self._load()
        borrower = app.get_borrower(borrower_id)
        if not borrower or not borrower.section_1a:
            return "Please save the current address first."
        prior = ResidenceHistory(
            address=Address(
                street=street, city=city,
                state=V.parse_state(state), zip_code=zip_code,
            ),
            years_at_address=years,
            months_at_address=months,
        )
        if not borrower.section_1a.prior_addresses:
            borrower.section_1a.prior_addresses = []
        borrower.section_1a.prior_addresses.append(prior)
        await self.state.save_application(app)
        return "Prior address saved. Any other addresses, or do we have enough to cover the last two years?"

    # ==================================================================
    # SECTION 1b — CURRENT EMPLOYMENT
    # ==================================================================

    @function_tool
    async def save_section_1b_employment(
        self,
        ctx: RunContext,
        borrower_id: str,
        employer_name: str,
        position_title: str,
        start_date: str,
        employer_street: str,
        employer_city: str,
        employer_state: str,
        employer_zip: str,
        base_monthly_income: float,
        overtime_monthly: float = 0.0,
        bonus_monthly: float = 0.0,
        commission_monthly: float = 0.0,
        other_monthly: float = 0.0,
        self_employed: bool = False,
        self_employed_ownership_ge_25: Optional[bool] = None,
        employed_by_family_or_party: bool = False,
        years_in_profession: Optional[int] = None,
    ) -> str:
        """Save current employment with full income breakdown."""
        await self._assert_section_reachable_async("SECTION_1B")
        app = await self._load()
        borrower = app.get_borrower(borrower_id)
        if not borrower:
            return f"Borrower {borrower_id} not found."

        section = Section1b_CurrentEmployment(
            employer_name=sanitize_name(employer_name, "employer_name"),
            position_title=sanitize_text(position_title, "position_title"),
            start_date=V.parse_date(start_date),
            employer_address=Address(
                street=sanitize_address(employer_street, "employer_street"),
                city=sanitize_name(employer_city, "employer_city"),
                state=V.parse_state(employer_state),
                zip_code=employer_zip,
            ),
            base_monthly=Decimal(str(base_monthly_income)),
            overtime_monthly=Decimal(str(overtime_monthly)) if overtime_monthly else None,
            bonus_monthly=Decimal(str(bonus_monthly)) if bonus_monthly else None,
            commission_monthly=Decimal(str(commission_monthly)) if commission_monthly else None,
            other_monthly=Decimal(str(other_monthly)) if other_monthly else None,
            self_employed=self_employed,
            self_employment_ownership_share_ge_25=self_employed_ownership_ge_25,
            employed_by_family_or_party_to_transaction=employed_by_family_or_party,
            years_in_profession=years_in_profession,
        )
        borrower.section_1b = section
        await self._save_and_advance(app, "SECTION_1B", "SECTION_1C")

        total = float(
            (section.base_monthly or 0)
            + (section.overtime_monthly or 0)
            + (section.bonus_monthly or 0)
            + (section.commission_monthly or 0)
            + (section.other_monthly or 0)
        )
        return (
            f"Saved. Total gross monthly income from {employer_name} is "
            f"approximately ${total:,.0f}. Any additional jobs or "
            f"self-employment to add?"
        )

    @function_tool
    async def mark_no_current_employment(
        self,
        ctx: RunContext,
        borrower_id: str,
        reason: str,
    ) -> str:
        """Mark that the borrower has no current employment (retired, unemployed, etc.)."""
        await self._assert_section_reachable_async("SECTION_1B")
        app = await self._load()
        borrower = app.get_borrower(borrower_id)
        if not borrower:
            return f"Borrower {borrower_id} not found."
        borrower.section_1b = Section1b_CurrentEmployment(does_not_apply=True)
        await self._save_and_advance(app, "SECTION_1B", "SECTION_1E")
        return (
            f"Noted — no current employment ({reason}). Let's move on to other "
            f"income sources like Social Security, pension, or rental income."
        )

    # ==================================================================
    # SECTION 1c — ADDITIONAL EMPLOYMENT
    # ==================================================================

    @function_tool
    async def save_additional_employment(
        self,
        ctx: RunContext,
        borrower_id: str,
        employer_name: str,
        position_title: str,
        start_date: str,
        base_monthly_income: float,
        self_employed: bool = False,
    ) -> str:
        """Add a second or third job / self-employment for the borrower."""
        await self._assert_section_reachable_async("SECTION_1C")
        app = await self._load()
        borrower = app.get_borrower(borrower_id)
        if not borrower:
            return f"Borrower {borrower_id} not found."
        if not borrower.section_1c:
            borrower.section_1c = Section1c_AdditionalEmployment()
        borrower.section_1c.employments.append(
            Section1b_CurrentEmployment(
                employer_name=employer_name,
                position_title=position_title,
                start_date=V.parse_date(start_date),
                base_monthly=Decimal(str(base_monthly_income)),
                self_employed=self_employed,
            )
        )
        await self.state.save_application(app)
        return f"Additional employment at {employer_name} saved. Any others?"

    @function_tool
    async def no_additional_employment(self, ctx: RunContext, borrower_id: str) -> str:
        """Caller confirmed no additional employment; advance the workflow."""
        await self._assert_section_reachable_async("SECTION_1C")
        app = await self._load()
        await self._save_and_advance(app, "SECTION_1C", "SECTION_1D")
        return "Got it, no additional employment. Now, have you been at your current job less than two years?"

    # ==================================================================
    # SECTION 1d — PREVIOUS EMPLOYMENT
    # ==================================================================

    @function_tool
    async def save_previous_employment(
        self,
        ctx: RunContext,
        borrower_id: str,
        employer_name: str,
        position_title: str,
        start_date: str,
        end_date: str,
        previous_gross_monthly_income: Optional[float] = None,
    ) -> str:
        """Save previous employer (required if current tenure < 2 years)."""
        await self._assert_section_reachable_async("SECTION_1D")
        app = await self._load()
        borrower = app.get_borrower(borrower_id)
        if not borrower:
            return f"Borrower {borrower_id} not found."
        borrower.section_1d = Section1d_PreviousEmployment(
            employer_name=employer_name,
            position_title=position_title,
            start_date=V.parse_date(start_date),
            end_date=V.parse_date(end_date),
            previous_gross_monthly_income=(
                Decimal(str(previous_gross_monthly_income))
                if previous_gross_monthly_income is not None else None
            ),
        )
        await self._save_and_advance(app, "SECTION_1D", "SECTION_1E")
        return f"Previous employment at {employer_name} saved. Let's move to other income."

    @function_tool
    async def no_previous_employment_needed(self, ctx: RunContext, borrower_id: str) -> str:
        """Caller has been at current job 2+ years — skip 1d."""
        await self._assert_section_reachable_async("SECTION_1D")
        app = await self._load()
        borrower = app.get_borrower(borrower_id)
        if borrower:
            borrower.section_1d = Section1d_PreviousEmployment(does_not_apply=True)
        await self._save_and_advance(app, "SECTION_1D", "SECTION_1E")
        return "Great — no previous employer needed. Let's move to other income."

    # ==================================================================
    # SECTION 1e — OTHER INCOME
    # ==================================================================

    @function_tool
    async def add_other_income_source(
        self,
        ctx: RunContext,
        borrower_id: str,
        source_type: str,
        monthly_amount: float,
        description: Optional[str] = None,
    ) -> str:
        """
        Add one source of other income.
        source_type: one of OtherIncomeType enum values.
        """
        self._check_rate_limit("add_other_income_source")
        await self._assert_section_reachable_async("SECTION_1E")
        app = await self._load()
        borrower = app.get_borrower(borrower_id)
        if not borrower:
            return f"Borrower {borrower_id} not found."
        if not borrower.section_1e:
            borrower.section_1e = Section1e_OtherIncome()
        normalized_type = OtherIncomeType(_norm_enum(source_type, OtherIncomeType))
        amt = Decimal(str(monthly_amount))
        # Idempotency: update existing match instead of appending duplicate (Fix I12)
        for existing in borrower.section_1e.sources:
            if existing.source_type == normalized_type and existing.monthly_amount == amt:
                existing.description = description
                await self.state.save_application(app)
                return f"Updated ${monthly_amount:,.0f} per month from {source_type.lower().replace('_', ' ')}. Any others?"
        borrower.section_1e.sources.append(
            OtherIncomeSource(
                source_type=normalized_type,
                monthly_amount=amt,
                description=description,
            )
        )
        await self.state.save_application(app)
        return f"Added ${monthly_amount:,.0f} per month from {source_type.lower().replace('_', ' ')}. Any others?"

    @function_tool
    async def complete_other_income(self, ctx: RunContext, borrower_id: str) -> str:
        """Mark section 1e complete and advance to assets/liabilities."""
        await self._assert_section_reachable_async("SECTION_1E")
        app = await self._load()
        borrower = app.get_borrower(borrower_id)
        if borrower and not borrower.section_1e:
            borrower.section_1e = Section1e_OtherIncome(does_not_apply=True)
        await self._save_and_advance(app, "SECTION_1E", "SECTION_2")
        return "All income captured. Now let's talk about your assets and monthly debts."

    # ==================================================================
    # SECTION 2 — ASSETS & LIABILITIES
    # ==================================================================

    @function_tool
    async def add_asset(
        self,
        ctx: RunContext,
        asset_type: str,
        cash_or_market_value: float,
        financial_institution: Optional[str] = None,
        account_number_last_4: Optional[str] = None,
    ) -> str:
        self._check_rate_limit("add_asset")
        await self._assert_section_reachable_async("SECTION_2")
        app = await self._load()
        if not app.section_2:
            app.section_2 = Section2_AssetsAndLiabilities()
        normalized_type = AssetType(_norm_enum(asset_type, AssetType))
        amt = Decimal(str(cash_or_market_value))
        # Idempotency: update existing match instead of appending duplicate (Fix I12)
        for existing in app.section_2.assets:
            if (existing.asset_type == normalized_type
                    and existing.cash_or_market_value == amt
                    and existing.financial_institution == financial_institution):
                existing.account_number_last_4 = (account_number_last_4[-4:] if account_number_last_4 else None)
                await self.state.save_application(app)
                return f"Updated ${cash_or_market_value:,.0f} in {asset_type.lower().replace('_', ' ')}. Any other accounts?"
        app.section_2.assets.append(
            Asset(
                asset_type=normalized_type,
                financial_institution=financial_institution,
                account_number_last_4=(account_number_last_4[-4:] if account_number_last_4 else None),
                cash_or_market_value=amt,
            )
        )
        await self.state.save_application(app)
        return f"Added ${cash_or_market_value:,.0f} in {asset_type.lower().replace('_', ' ')}. Any other accounts?"

    @function_tool
    async def add_other_credit(
        self,
        ctx: RunContext,
        credit_type: str,
        amount: float,
        description: Optional[str] = None,
    ) -> str:
        """Earnest money, employer assistance, trade equity, etc."""
        self._check_rate_limit("add_other_credit")
        await self._assert_section_reachable_async("SECTION_2")
        app = await self._load()
        if not app.section_2:
            app.section_2 = Section2_AssetsAndLiabilities()
        amt = Decimal(str(amount))
        for existing in app.section_2.other_credits:
            if existing.credit_type == credit_type and existing.amount == amt:
                existing.description = description
                await self.state.save_application(app)
                return f"Updated {credit_type} of ${amount:,.0f}."
        app.section_2.other_credits.append(
            OtherCredit(
                credit_type=credit_type,
                amount=amt,
                description=sanitize_description(description, "other_credit_description"),
            )
        )
        await self.state.save_application(app)
        return f"Saved {credit_type} of ${amount:,.0f}."

    @function_tool
    async def add_liability(
        self,
        ctx: RunContext,
        liability_type: str,
        creditor_name: str,
        unpaid_balance: float,
        monthly_payment: float,
        account_number_last_4: Optional[str] = None,
        months_remaining: Optional[int] = None,
        to_be_paid_off_at_closing: bool = False,
    ) -> str:
        self._check_rate_limit("add_liability")
        await self._assert_section_reachable_async("SECTION_2")
        app = await self._load()
        if not app.section_2:
            app.section_2 = Section2_AssetsAndLiabilities()
        normalized_type = LiabilityType(_norm_enum(liability_type, LiabilityType))
        bal = Decimal(str(unpaid_balance))
        pmt = Decimal(str(monthly_payment))
        # Idempotency: update existing match instead of appending duplicate (Fix I12)
        for existing in app.section_2.liabilities:
            if (existing.liability_type == normalized_type
                    and existing.creditor_name == creditor_name
                    and existing.unpaid_balance == bal):
                existing.monthly_payment = pmt
                existing.account_number_last_4 = (account_number_last_4[-4:] if account_number_last_4 else None)
                existing.months_remaining = months_remaining
                existing.to_be_paid_off_at_closing = to_be_paid_off_at_closing
                await self.state.save_application(app)
                return (
                    f"Updated {creditor_name}: ${unpaid_balance:,.0f} balance, "
                    f"${monthly_payment:,.0f} per month. Anything else?"
                )
        app.section_2.liabilities.append(
            Liability(
                liability_type=normalized_type,
                creditor_name=sanitize_name(creditor_name, "creditor_name"),
                account_number_last_4=(account_number_last_4[-4:] if account_number_last_4 else None),
                unpaid_balance=bal,
                monthly_payment=pmt,
                months_remaining=months_remaining,
                to_be_paid_off_at_closing=to_be_paid_off_at_closing,
            )
        )
        await self.state.save_application(app)
        return (
            f"Saved {creditor_name}: ${unpaid_balance:,.0f} balance, "
            f"${monthly_payment:,.0f} per month. Anything else?"
        )

    @function_tool
    async def add_other_liability(
        self,
        ctx: RunContext,
        liability_type: str,
        monthly_payment: float,
        description: Optional[str] = None,
    ) -> str:
        """Alimony, child support, job-related expenses."""
        self._check_rate_limit("add_other_liability")
        await self._assert_section_reachable_async("SECTION_2")
        app = await self._load()
        if not app.section_2:
            app.section_2 = Section2_AssetsAndLiabilities()
        app.section_2.other_liabilities.append(
            OtherLiability(
                liability_type=LiabilityType(_norm_enum(liability_type, LiabilityType)),
                monthly_payment=Decimal(str(monthly_payment)),
                description=description,
            )
        )
        await self.state.save_application(app)
        return f"Saved {liability_type.lower().replace('_', ' ')} of ${monthly_payment:,.0f} per month."

    @function_tool
    async def complete_section_2(self, ctx: RunContext) -> str:
        """Mark assets/liabilities complete; advance to REO."""
        await self._assert_section_reachable_async("SECTION_2")
        app = await self._load()
        if not app.section_2:
            app.section_2 = Section2_AssetsAndLiabilities()
        await self._save_and_advance(app, "SECTION_2", "SECTION_3")
        return "Assets and debts are in. Do you own any other real estate besides the property you're applying for?"

    # ==================================================================
    # SECTION 3 — REAL ESTATE OWNED
    # ==================================================================

    @function_tool
    async def add_property_owned(
        self,
        ctx: RunContext,
        street: str,
        city: str,
        state: str,
        zip_code: str,
        property_value: float,
        status: str,             # SOLD / PENDING_SALE / RETAINED
        intended_occupancy: str, # PRIMARY_RESIDENCE / SECOND_HOME / INVESTMENT
        monthly_insurance_taxes_dues: Optional[float] = None,
        monthly_rental_income: Optional[float] = None,
    ) -> str:
        self._check_rate_limit("add_property_owned")
        await self._assert_section_reachable_async("SECTION_3")
        app = await self._load()
        if not app.section_3:
            app.section_3 = Section3_RealEstate()
        parsed_state = V.parse_state(state)
        for existing in app.section_3.properties:
            if (existing.address.street == street
                    and existing.address.zip_code == zip_code):
                existing.property_value = Decimal(str(property_value))
                existing.status = PropertyStatus(_norm_enum(status, PropertyStatus))
                existing.intended_occupancy = PropertyOccupancy(_norm_enum(intended_occupancy, PropertyOccupancy))
                await self.state.save_application(app)
                return f"Updated property at {street}, {city}."
        app.section_3.properties.append(
            PropertyOwned(
                address=Address(
                    street=street, city=city,
                    state=parsed_state, zip_code=zip_code,
                ),
                property_value=Decimal(str(property_value)),
                status=PropertyStatus(_norm_enum(status, PropertyStatus)),
                intended_occupancy=PropertyOccupancy(_norm_enum(intended_occupancy, PropertyOccupancy)),
                monthly_insurance_taxes_assoc_dues=(
                    Decimal(str(monthly_insurance_taxes_dues))
                    if monthly_insurance_taxes_dues else None
                ),
                monthly_rental_income=(
                    Decimal(str(monthly_rental_income))
                    if monthly_rental_income else None
                ),
            )
        )
        await self.state.save_application(app)
        return f"Property at {street}, {city} saved. Does it have a mortgage on it?"

    @function_tool
    async def add_mortgage_on_reo(
        self,
        ctx: RunContext,
        property_index: int,
        creditor_name: str,
        monthly_payment: float,
        unpaid_balance: float,
        to_be_paid_off: bool = False,
        loan_type: Optional[str] = None,
    ) -> str:
        """Attach a mortgage to a previously-added REO property (0-indexed)."""
        self._check_rate_limit("add_mortgage_on_reo")
        await self._assert_section_reachable_async("SECTION_3")
        app = await self._load()
        if not app.section_3 or property_index >= len(app.section_3.properties):
            return "That property hasn't been saved yet. Add the property first."
        lt = LoanType(_norm_enum(loan_type, LoanType)) if loan_type else None
        bal = Decimal(str(unpaid_balance))
        prop = app.section_3.properties[property_index]
        for existing in prop.mortgages:
            if existing.creditor_name == creditor_name and existing.unpaid_balance == bal:
                existing.monthly_payment = Decimal(str(monthly_payment))
                existing.to_be_paid_off = to_be_paid_off
                existing.loan_type = lt
                await self.state.save_application(app)
                return f"Updated mortgage with {creditor_name}."
        prop.mortgages.append(
            REOMortgage(
                creditor_name=sanitize_name(creditor_name, "reo_creditor"),
                monthly_payment=Decimal(str(monthly_payment)),
                unpaid_balance=bal,
                to_be_paid_off=to_be_paid_off,
                loan_type=lt,
            )
        )
        await self.state.save_application(app)
        return f"Mortgage with {creditor_name} attached."

    @function_tool
    async def no_real_estate_owned(self, ctx: RunContext) -> str:
        await self._assert_section_reachable_async("SECTION_3")
        app = await self._load()
        app.section_3 = Section3_RealEstate(does_not_apply=True)
        await self._save_and_advance(app, "SECTION_3", "SECTION_4A")
        return "No other real estate — let's talk about this loan and the property."

    @function_tool
    async def complete_section_3(self, ctx: RunContext) -> str:
        await self._assert_section_reachable_async("SECTION_3")
        app = await self._load()
        await self._save_and_advance(app, "SECTION_3", "SECTION_4A")
        return "Real estate captured. Now let's talk about the loan and property you're applying for."

    # ==================================================================
    # SECTION 4 — LOAN & PROPERTY
    # ==================================================================

    @function_tool
    async def save_section_4a_loan_and_property(
        self,
        ctx: RunContext,
        loan_purpose: str,       # PURCHASE / REFINANCE / CONSTRUCTION / OTHER
        loan_amount: float,
        subject_street: str,
        subject_city: str,
        subject_state: str,
        subject_zip: str,
        property_value: float,
        number_of_units: int,
        occupancy: str,          # PRIMARY_RESIDENCE / SECOND_HOME / INVESTMENT
        mixed_use_property: bool = False,
        manufactured_home: bool = False,
        loan_purpose_other_description: Optional[str] = None,
    ) -> str:
        await self._assert_section_reachable_async("SECTION_4A")
        app = await self._load()
        if not app.section_4:
            app.section_4 = Section4_LoanAndProperty()
        app.section_4.section_4a = Section4a_LoanAndProperty(
            loan_amount=Decimal(str(loan_amount)),
            loan_purpose=LoanPurpose(_norm_enum(loan_purpose, LoanPurpose)),
            loan_purpose_other_description=loan_purpose_other_description,
            subject_property_address=Address(
                street=sanitize_address(subject_street, "subject_street"),
                city=sanitize_name(subject_city, "subject_city"),
                state=V.parse_state(subject_state), zip_code=subject_zip,
            ),
            number_of_units=number_of_units,
            property_value=Decimal(str(property_value)),
            occupancy=PropertyOccupancy(_norm_enum(occupancy, PropertyOccupancy)),
            mixed_use_property=mixed_use_property,
            manufactured_home=manufactured_home,
        )
        await self._save_and_advance(app, "SECTION_4A", "SECTION_4B")
        if app.check_trid_triggers():
            logger.info(
                "TRID triggers met after Section 4A",
                extra={"loan_id": app.loan_id, "application_received_at": app.application_received_at.isoformat()},
            )
        # "Re-ask loud" — critical financial fields get explicit readback + confirmation.
        # Both extraction paths consume the same STT transcript, so a systematic
        # Deepgram mishear (e.g. "$425k" → "$225k") would pass the dual-path
        # diff undetected. Verbal confirmation catches this at zero infra cost.
        loan_spelled = _spell_dollars_for_voice(loan_amount)
        value_spelled = _spell_dollars_for_voice(property_value)
        state_code = V.parse_state(subject_state)
        return (
            f"Let me confirm the key numbers before we continue. "
            f"The loan amount is {loan_spelled}. "
            f"The property value is {value_spelled}. "
            f"And the property address is {subject_street}, {subject_city}, "
            f"{state_code} {subject_zip}. "
            f"Is all of that correct?"
        )

    @function_tool
    async def save_section_4b_other_mortgages(
        self,
        ctx: RunContext,
        has_other_mortgage: bool,
        creditor_name: Optional[str] = None,
        loan_amount: Optional[float] = None,
        monthly_payment: Optional[float] = None,
        credit_limit: Optional[float] = None,
    ) -> str:
        await self._assert_section_reachable_async("SECTION_4B")
        app = await self._load()
        if not app.section_4:
            app.section_4 = Section4_LoanAndProperty()
        if has_other_mortgage:
            app.section_4.section_4b = Section4b_OtherNewMortgages(
                does_not_apply=False,
                creditor_name=creditor_name,
                lien_type="SUBORDINATE",
                loan_amount=Decimal(str(loan_amount)) if loan_amount else None,
                monthly_payment=Decimal(str(monthly_payment)) if monthly_payment else None,
                credit_limit=Decimal(str(credit_limit)) if credit_limit else None,
            )
        else:
            app.section_4.section_4b = Section4b_OtherNewMortgages(does_not_apply=True)
        await self._save_and_advance(app, "SECTION_4B", "SECTION_4C")
        return "Saved. Moving on."

    @function_tool
    async def save_section_4c_rental_income(
        self,
        ctx: RunContext,
        has_rental_income: bool,
        expected_monthly_rental_income: Optional[float] = None,
        expected_net_monthly_rental_income: Optional[float] = None,
    ) -> str:
        await self._assert_section_reachable_async("SECTION_4C")
        app = await self._load()
        if not app.section_4:
            app.section_4 = Section4_LoanAndProperty()
        app.section_4.section_4c = Section4c_RentalIncomeOnSubject(
            does_not_apply=not has_rental_income,
            expected_monthly_rental_income=(
                Decimal(str(expected_monthly_rental_income))
                if expected_monthly_rental_income else None
            ),
            expected_net_monthly_rental_income=(
                Decimal(str(expected_net_monthly_rental_income))
                if expected_net_monthly_rental_income else None
            ),
        )
        await self._save_and_advance(app, "SECTION_4C", "SECTION_4D")
        return "Got it. Any gifts or grants being used for the down payment or closing costs?"

    @function_tool
    async def add_gift_or_grant(
        self,
        ctx: RunContext,
        gift_type: str,          # CASH_GIFT / GIFT_OF_EQUITY / GRANT
        source: str,             # RELATIVE / EMPLOYER / ...
        amount: float,
        deposited: bool = False,
    ) -> str:
        self._check_rate_limit("add_gift_or_grant")
        await self._assert_section_reachable_async("SECTION_4D")
        app = await self._load()
        if not app.section_4:
            app.section_4 = Section4_LoanAndProperty()
        if not app.section_4.section_4d:
            app.section_4.section_4d = Section4d_GiftsOrGrants(does_not_apply=False)
        else:
            app.section_4.section_4d.does_not_apply = False
        app.section_4.section_4d.gifts.append(
            Gift(
                asset_type=GiftType(_norm_enum(gift_type, GiftType)),
                deposited=deposited,
                source=GiftSource(_norm_enum(source, GiftSource)),
                cash_or_market_value=Decimal(str(amount)),
            )
        )
        await self.state.save_application(app)
        return f"Gift of ${amount:,.0f} from {source.lower().replace('_', ' ')} saved."

    @function_tool
    async def no_gifts_or_grants(self, ctx: RunContext) -> str:
        await self._assert_section_reachable_async("SECTION_4D")
        app = await self._load()
        if not app.section_4:
            app.section_4 = Section4_LoanAndProperty()
        app.section_4.section_4d = Section4d_GiftsOrGrants(does_not_apply=True)
        await self._save_and_advance(app, "SECTION_4D", "SECTION_5A")
        return "No gifts. Moving on to a short list of declarations."

    @function_tool
    async def complete_section_4d(self, ctx: RunContext) -> str:
        await self._assert_section_reachable_async("SECTION_4D")
        app = await self._load()
        await self._save_and_advance(app, "SECTION_4D", "SECTION_5A")
        return "All set. Now I'll ask a short series of yes or no declarations."

    # ==================================================================
    # SECTION 5 — DECLARATIONS
    # ==================================================================

    @function_tool
    async def save_section_5a_declarations(
        self,
        ctx: RunContext,
        borrower_id: str,
        will_occupy_as_primary_residence: bool,
        had_ownership_interest_last_3_years: bool,
        family_business_relationship_with_seller: bool,
        borrowing_money_for_transaction: bool,
        applying_for_other_mortgage_before_closing: bool,
        applying_for_new_credit_before_closing: bool,
        property_subject_to_lien: bool,
        property_type_last_3_years: Optional[str] = None,
        how_held_title_last_3_years: Optional[str] = None,
        borrowed_amount: Optional[float] = None,
    ) -> str:
        await self._assert_section_reachable_async("SECTION_5A")
        app = await self._load()
        borrower = app.get_borrower(borrower_id)
        if not borrower:
            return f"Borrower {borrower_id} not found."
        if not borrower.section_5:
            borrower.section_5 = Section5_Declarations()
        borrower.section_5.section_5a = Section5a_DeclarationsPropertyMoney(
            will_occupy_as_primary_residence=will_occupy_as_primary_residence,
            had_ownership_interest_last_3_years=had_ownership_interest_last_3_years,
            property_type_last_3_years=property_type_last_3_years,
            how_held_title_last_3_years=how_held_title_last_3_years,
            family_business_relationship_with_seller=family_business_relationship_with_seller,
            borrowing_money_for_transaction=borrowing_money_for_transaction,
            borrowed_amount=Decimal(str(borrowed_amount)) if borrowed_amount else None,
            applying_for_other_mortgage_before_closing=applying_for_other_mortgage_before_closing,
            applying_for_new_credit_before_closing=applying_for_new_credit_before_closing,
            property_subject_to_lien=property_subject_to_lien,
        )
        await self._save_and_advance(app, "SECTION_5A", "SECTION_5B")
        return "First set of declarations saved. Now the financial declarations."

    @function_tool
    async def save_section_5b_declarations(
        self,
        ctx: RunContext,
        borrower_id: str,
        co_signer_on_undisclosed_debt: bool,
        outstanding_judgments: bool,
        currently_delinquent_on_federal_debt: bool,
        party_to_lawsuit: bool,
        conveyed_title_in_lieu_of_foreclosure_last_7_years: bool,
        short_sale_or_pre_foreclosure_last_7_years: bool,
        foreclosed_last_7_years: bool,
        declared_bankruptcy_last_7_years: bool,
        bankruptcy_types: Optional[List[str]] = None,
    ) -> str:
        await self._assert_section_reachable_async("SECTION_5B")
        app = await self._load()
        borrower = app.get_borrower(borrower_id)
        if not borrower:
            return f"Borrower {borrower_id} not found."
        if not borrower.section_5:
            borrower.section_5 = Section5_Declarations()
        borrower.section_5.section_5b = Section5b_DeclarationsFinances(
            co_signer_on_undisclosed_debt=co_signer_on_undisclosed_debt,
            outstanding_judgments=outstanding_judgments,
            currently_delinquent_on_federal_debt=currently_delinquent_on_federal_debt,
            party_to_lawsuit=party_to_lawsuit,
            conveyed_title_in_lieu_of_foreclosure_last_7_years=conveyed_title_in_lieu_of_foreclosure_last_7_years,
            short_sale_or_pre_foreclosure_last_7_years=short_sale_or_pre_foreclosure_last_7_years,
            foreclosed_last_7_years=foreclosed_last_7_years,
            declared_bankruptcy_last_7_years=declared_bankruptcy_last_7_years,
            bankruptcy_types=bankruptcy_types,
        )
        await self._save_and_advance(app, "SECTION_5B", "SECTION_7")
        return "Declarations complete. A quick question about military service."

    # ==================================================================
    # SECTION 7 — MILITARY SERVICE
    # ==================================================================

    @function_tool
    async def save_section_7_military(
        self,
        ctx: RunContext,
        borrower_id: str,
        served_in_military: bool,
        currently_active_duty: bool = False,
        retired_discharged_separated: bool = False,
        non_activated_reserve_national_guard: bool = False,
        surviving_spouse: bool = False,
        expiration_of_active_duty: Optional[str] = None,
    ) -> str:
        await self._assert_section_reachable_async("SECTION_7")
        app = await self._load()
        borrower = app.get_borrower(borrower_id)
        if not borrower:
            return f"Borrower {borrower_id} not found."
        borrower.section_7 = Section7_MilitaryService(
            served_in_military=served_in_military,
            currently_active_duty=currently_active_duty,
            retired_discharged_separated=retired_discharged_separated,
            non_activated_reserve_national_guard=non_activated_reserve_national_guard,
            surviving_spouse=surviving_spouse,
            expiration_of_active_duty=(
                V.parse_date(expiration_of_active_duty)
                if expiration_of_active_duty else None
            ),
        )
        await self._save_and_advance(app, "SECTION_7", "SECTION_8")
        return "Military service saved. A few voluntary demographic questions next."

    # ==================================================================
    # SECTION 8 — DEMOGRAPHIC INFORMATION
    # ==================================================================

    @function_tool
    async def save_section_8_demographics(
        self,
        ctx: RunContext,
        borrower_id: str,
        ethnicity: Optional[List[str]] = None,
        race: Optional[List[str]] = None,
        sex: Optional[str] = None,
        borrower_declined_to_provide: bool = False,
    ) -> str:
        """
        Save Section 8. All fields optional — caller may decline any or all.
        Pass borrower_declined_to_provide=True if caller declines entirely.
        """
        await self._assert_section_reachable_async("SECTION_8")
        app = await self._load()
        borrower = app.get_borrower(borrower_id)
        if not borrower:
            return f"Borrower {borrower_id} not found."
        section = Section8_Demographics(
            demographics_notice_read_at=datetime.now(timezone.utc),
            was_demographic_info_provided_by_borrower=not borrower_declined_to_provide,
            was_collected_via_visual_observation_or_surname=False,
        )
        if ethnicity:
            section.ethnicity = [
                EthnicityCategory(_norm_enum(e, EthnicityCategory)) for e in ethnicity
            ]
        elif borrower_declined_to_provide:
            section.ethnicity = [EthnicityCategory.NOT_PROVIDED]

        if race:
            section.race = [RaceCategory(_norm_enum(r, RaceCategory)) for r in race]
        elif borrower_declined_to_provide:
            section.race = [RaceCategory.NOT_PROVIDED]

        if sex:
            section.sex = SexCategory(_norm_enum(sex, SexCategory))
        elif borrower_declined_to_provide:
            section.sex = SexCategory.NOT_PROVIDED

        borrower.section_8 = section
        await self._save_and_advance(app, "SECTION_8", "COBORROWER_CHECK")
        return "Thanks. Will anyone else be on the loan with you as a co-borrower?"

    # ==================================================================
    # CO-BORROWER
    # ==================================================================

    @function_tool
    async def add_coborrower(self, ctx: RunContext) -> str:
        """Add a co-borrower and route the agent back to Section 1a for them."""
        app = await self._load()
        next_id = f"borrower_{len(app.borrowers) + 1}"
        app.borrowers.append(Borrower(borrower_id=next_id, is_primary=False))
        app.current_section = "SECTION_1A"
        await self.state.save_application(app)
        return (
            f"Okay, I'll collect the same information for the co-borrower. "
            f"Their borrower ID is {next_id}. Let's start with their legal "
            f"name and date of birth."
        )

    @function_tool
    async def no_coborrower(self, ctx: RunContext) -> str:
        app = await self._load()
        await self._save_and_advance(app, "COBORROWER_CHECK", "SECTION_6")
        return "Perfect. Almost done — I just need your verbal consent to submit the application."

    # ==================================================================
    # SECTION 6 — VERBAL CONSENT / ACKNOWLEDGMENT
    # ==================================================================

    @function_tool
    async def capture_verbal_consent(
        self,
        ctx: RunContext,
        consent_given: bool,
        privacy_notice_consent_given: bool = False,
        recording_url: Optional[str] = None,
    ) -> str:
        """
        Record the caller's verbal 'I agree' to the acknowledgments disclosure.
        Also captures GLBA privacy notice consent (separate from application consent).
        Both are required before finalize.
        """
        await self._assert_section_reachable_async("SECTION_6")
        app = await self._load()
        now = datetime.now(timezone.utc) if consent_given else None
        app.section_6 = Section6_Acknowledgments(
            verbal_consent_given=consent_given,
            verbal_consent_timestamp=now,
            verbal_consent_recording_url=recording_url,
            privacy_notice_consent_given=privacy_notice_consent_given,
            privacy_notice_consent_timestamp=now if privacy_notice_consent_given else None,
        )
        await self._save_and_advance(app, "SECTION_6", "FINAL_SUMMARY")
        if consent_given:
            return "Thank you. Verbal consent recorded. Let me give you a final summary."
        return (
            "Understood. Without consent I can't finalize today, but I've saved "
            "your progress and a loan officer will reach out to complete things "
            "with you directly."
        )

    # ==================================================================
    # FINAL SUMMARY & FINALIZE
    # ==================================================================

    @function_tool
    async def read_final_summary(self, ctx: RunContext) -> Dict[str, Any]:
        """
        Return a structured summary so the LLM can read it back verbally before
        finalizing. This is the last check before push to BytePro.
        """
        app = await self._load()
        primary = self._primary(app)
        s1a = primary.section_1a
        s4a = app.section_4.section_4a if app.section_4 else None

        total_monthly_income = _sum_monthly_income(primary)
        total_monthly_debts = _sum_monthly_debts(app)

        return {
            "loan_id": app.loan_id,
            "primary_name": f"{s1a.first_name} {s1a.last_name}" if s1a else None,
            "loan_purpose": s4a.loan_purpose if s4a else None,
            "loan_amount": float(s4a.loan_amount) if s4a and s4a.loan_amount else None,
            "property_address": (
                f"{s4a.subject_property_address.street}, "
                f"{s4a.subject_property_address.city}, "
                f"{s4a.subject_property_address.state}"
                if s4a and s4a.subject_property_address else None
            ),
            "occupancy": s4a.occupancy if s4a else None,
            "total_monthly_income": total_monthly_income,
            "total_monthly_debts": total_monthly_debts,
            "number_of_borrowers": len(app.borrowers),
            "validation_errors": app.validate_complete(),
        }

    @function_tool
    async def finalize_urla(self, ctx: RunContext) -> str:
        """
        Validate, serialize, and deliver the application. Call ONLY
        after the caller has confirmed the final summary is accurate.

        Primary delivery: emails a MISMO 3.4 XML attachment to the LO.
        Optional: pushes to BytePro if BYTEPRO_API_BASE_URL is configured.

        On success, the session transitions to LO_KICKOFF_BOOKING — the LLM
        should then call `offer_lo_kickoff_slots` to get the caller on their
        loan officer's calendar before the call ends.
        """
        app = await self._load()

        errors = app.validate_complete()
        if errors:
            missing = "; ".join(errors)
            return (
                f"Before I can finalize I still need: {missing}. Would you like "
                f"to fill those in now, or pause and come back?"
            )

        # C3: Snapshot pre-scrub transcript so we can restore on delivery failure
        import copy
        pre_scrub_transcript = copy.deepcopy(app.transcript) if app.transcript else []

        # ------------------------------------------------------------------
        # Generate MISMO 3.4 XML (serializer built in parallel — graceful
        # degradation if not yet available)
        # ------------------------------------------------------------------
        xml_content: Optional[str] = None
        try:
            from .mismo_serializer import serialize_to_mismo34
            xml_content = serialize_to_mismo34(app, self.loan_officer)
        except ImportError:
            logger.warning(
                "mismo_serializer not available yet; skipping MISMO email",
                extra={"loan_id": app.loan_id},
            )
        except Exception as e:
            logger.error(
                "MISMO serialization failed",
                extra={"loan_id": app.loan_id, "error": str(e)},
            )

        # M3: Validate XML before attempting email delivery
        if xml_content:
            try:
                import xml.etree.ElementTree as ET
                ET.fromstring(xml_content)
            except Exception as e:
                logger.error(
                    "MISMO XML validation failed — skipping email delivery",
                    extra={"loan_id": app.loan_id, "error": str(e)},
                )
                xml_content = None

        # ------------------------------------------------------------------
        # Primary delivery: email the MISMO 3.4 XML to the loan officer
        # ------------------------------------------------------------------
        email_sent = False
        if xml_content:
            try:
                from .email_adapter import email_mismo_file
                primary = self._primary(app)
                s1a = primary.section_1a
                borrower_name = f"{s1a.first_name or ''} {s1a.last_name or ''}".strip() if s1a else "Borrower"

                email_result = await email_mismo_file(
                    xml_content=xml_content,
                    loan_id=app.loan_id,
                    borrower_name=borrower_name,
                    borrower_email=(s1a.email or "") if s1a else "",
                    loan_officer_email=self.loan_officer.email,
                    loan_officer_name=self.loan_officer.name,
                    organization_id=self.tenant_id,
                )

                if email_result.success:
                    email_sent = True
                    logger.info(
                        "MISMO email sent to LO",
                        extra={
                            "loan_id": app.loan_id,
                            "message_id": email_result.message_id,
                        },
                    )
                else:
                    logger.error(
                        "MISMO email failed",
                        extra={
                            "loan_id": app.loan_id,
                            "error": email_result.error,
                        },
                    )
            except Exception as e:
                logger.error(
                    "MISMO email delivery error",
                    extra={"loan_id": app.loan_id, "error": str(e)},
                )

        # ------------------------------------------------------------------
        # Optional: BytePro push (only if BYTEPRO_API_BASE_URL is configured)
        # ------------------------------------------------------------------
        bytepro_base = os.getenv("BYTEPRO_API_BASE_URL", "")
        bytepro_pushed = False
        if bytepro_base:
            result: PushResult = await push_to_bytepro(app, self.loan_officer)

            if result.success:
                bytepro_pushed = True
                app.bytepro_loan_number = result.bytepro_loan_number
                app.bytepro_submitted_at = datetime.now(timezone.utc)
                logger.info(
                    "BytePro push succeeded",
                    extra={
                        "loan_id": app.loan_id,
                        "bytepro_loan_number": result.bytepro_loan_number,
                    },
                )
            else:
                logger.error(
                    "BytePro push failed",
                    extra={"loan_id": app.loan_id, "error": result.error},
                )

        # If neither delivery mechanism succeeded, restore pre-scrub transcript
        # so a retry can work, create an urgent CRM task, and report to caller
        if not email_sent and not bytepro_pushed:
            # C3: Restore original transcript so PII is available for retry
            app.transcript = pre_scrub_transcript
            await self.state.save_application(app)

            # H3: Create an urgent CRM task so the LO is actually notified
            try:
                import httpx
                crm_api_base = os.getenv("CRM_API_BASE_URL", "")
                crm_api_key = os.getenv("CRM_API_KEY", "")
                if crm_api_base and crm_api_key:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(
                            f"{crm_api_base}/api/v1/tasks",
                            json={
                                "title": f"URGENT: Application delivery failed -- {app.loan_id}",
                                "description": (
                                    f"Both email and BytePro delivery failed for URLA "
                                    f"application {app.loan_id}.\n"
                                    f"Caller phone: {self.caller_phone}\n"
                                    f"The application data is saved in Redis and can be "
                                    f"retried. Manual intervention required."
                                ),
                                "priority": "high",
                                "task_type": "callback",
                            },
                            headers={"Authorization": f"Bearer {crm_api_key}"},
                        )
                        logger.info(
                            "Delivery failure task created",
                            extra={"loan_id": app.loan_id},
                        )
            except Exception as e:
                logger.warning(
                    "Failed to create delivery failure task",
                    extra={"loan_id": app.loan_id, "error": str(e)},
                )

            return (
                "I've saved everything on our side, but there was a hiccup "
                "delivering the application. A loan officer will be "
                f"notified right away. Your loan ID is {_spell_loan_id(app.loan_id)} "
                "for reference."
            )

        # C3: At least one delivery succeeded — now persist the scrubbed transcript
        if app.transcript:
            scrub_post_call(app.transcript, app.current_section)
            await self.state.save_application(app)

        # Finalize the application in Redis (sets is_finalized, transitions
        # to LO_KICKOFF_BOOKING)
        await self.state.finalize(app)

        logger.info(
            "URLA finalized",
            extra={
                "loan_id": app.loan_id,
                "email_sent": email_sent,
                "bytepro_pushed": bytepro_pushed,
                "bytepro_loan_number": getattr(app, "bytepro_loan_number", None),
            },
        )

        # Hydrate POS PostgreSQL tables so borrower can see data in self-service portal
        try:
            import httpx
            crm_api_base = os.getenv("CRM_API_BASE_URL", "https://api.perenniaai.com")
            crm_api_key = os.getenv("CRM_API_KEY", "")

            if crm_api_base and crm_api_key:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    hydration_resp = await client.post(
                        f"{crm_api_base}/api/v1/pos/hydrate-from-voice",
                        json={
                            "urla_loan_id": app.loan_id,
                            "urla_data": app.model_dump(mode="json", exclude_none=True),
                            "organization_id": int(self.tenant_id) if self.tenant_id.isdigit() else 1,
                            "workspace_id": 1,
                            "contact_id": self.crm_contact_id or 0,
                            "loan_id": self.crm_loan_id,
                        },
                        headers={
                            "Authorization": f"Bearer {crm_api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    if hydration_resp.status_code in (200, 201):
                        logger.info("POS hydration complete", extra={
                            "loan_id": app.loan_id,
                            "pos_response": hydration_resp.json(),
                        })
                    else:
                        logger.warning("POS hydration failed", extra={
                            "loan_id": app.loan_id,
                            "status": hydration_resp.status_code,
                            "body": hydration_resp.text[:200],
                        })
        except Exception as e:
            logger.warning("POS hydration trigger failed (non-fatal)", extra={
                "loan_id": app.loan_id,
                "error": str(e),
            })

        # Trigger CI pipeline: feeds transcript through existing extraction pipeline,
        # diffs against captured structured data, routes disagreements to review queue
        try:
            from .ci_adapter import trigger_ci_analysis
            trigger_ci_analysis(app, self.tenant_id)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("CI pipeline trigger failed", extra={"error": str(e)})

        # Check TRID triggers (C4 compliance)
        if app.check_trid_triggers():
            logger.info("TRID triggers complete", extra={
                "loan_id": app.loan_id,
                "application_received_at": app.application_received_at.isoformat(),
            })
            # RESPA: Loan Estimate must be delivered within 3 business days
            try:
                from .task_generator import URLATask, TaskPriority, TaskCategory
                trid_task = URLATask(
                    title=f"Send Loan Estimate — {app.loan_id}",
                    description=(
                        f"TRID triggered at {app.application_received_at.isoformat()}. "
                        f"Loan Estimate must be delivered within 3 business days."
                    ),
                    priority=TaskPriority.CRITICAL,
                    category=TaskCategory.COMPLIANCE,
                    due_in_business_days=3,
                )
                logger.info("TRID compliance task created", extra={"loan_id": app.loan_id})
            except ImportError:
                pass

        # FCRA: Trigger credit authorization e-sign (verbal consent is insufficient)
        try:
            from .esign_adapter import get_esign_adapter, ESignDocumentType
            primary = app.primary_borrower()
            if primary and primary.section_1a and primary.section_1a.email:
                esign = get_esign_adapter()
                name = f"{primary.section_1a.first_name or ''} {primary.section_1a.last_name or ''}".strip()
                esign_request = await esign.send_authorization(
                    document_type=ESignDocumentType.CREDIT_AUTHORIZATION,
                    loan_id=app.loan_id,
                    borrower_email=primary.section_1a.email,
                    borrower_name=name,
                    tenant_id=self.tenant_id,
                )
                app.credit_authorization_sent_at = datetime.now(timezone.utc)
                await self.state.save_application(app)
                logger.info("Credit authorization e-sign sent", extra={
                    "loan_id": app.loan_id,
                    "request_id": esign_request.request_id,
                })
        except Exception as e:
            logger.warning("Credit auth e-sign failed", extra={"error": str(e)})

        # POS consent flow: send borrower SMS with magic link for credit auth + e-disclosure
        consent_sms_sent = False
        try:
            import httpx
            primary = app.primary_borrower()
            name = ""
            if primary and primary.section_1a:
                name = f"{primary.section_1a.first_name or ''} {primary.section_1a.last_name or ''}".strip()

            crm_api_base = os.getenv("CRM_API_BASE_URL", "https://api.perenniaai.com")
            crm_api_key = os.getenv("CRM_API_KEY", "")

            if crm_api_base and crm_api_key:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        f"{crm_api_base}/api/v1/pos/voice-complete",
                        json={
                            "voice_loan_id": app.loan_id,
                            "borrower_first_name": primary.section_1a.first_name if primary and primary.section_1a else "",
                            "borrower_phone": app.caller_phone,
                            "lo_name": self.loan_officer.name,
                        },
                        headers={
                            "Authorization": f"Bearer {crm_api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    if resp.status_code in (200, 201):
                        consent_sms_sent = True
                        logger.info("POS consent SMS triggered", extra={"loan_id": app.loan_id})
                    else:
                        logger.warning("POS consent trigger failed", extra={
                            "status": resp.status_code,
                            "body": resp.text[:200],
                        })
        except Exception as e:
            logger.warning("POS consent flow trigger failed (non-fatal)", extra={"error": str(e)})

        sms_note = ""
        if consent_sms_sent:
            sms_note = (
                " I've also sent a text message to your phone with a link to "
                "review and sign the credit authorization and disclosure agreements."
            )

        lo_first = self.loan_officer.name.split()[0] if self.loan_officer.name else "your loan officer"

        # Build the voice response based on which delivery methods succeeded
        if email_sent and bytepro_pushed:
            delivery_note = (
                f"Application complete! I've emailed the full application to "
                f"{lo_first} and submitted it to BytePro (reference "
                f"{app.bytepro_loan_number})."
            )
        elif email_sent:
            delivery_note = (
                f"Application complete! I've emailed the full application to "
                f"{lo_first}."
            )
        else:
            # bytepro_pushed must be True (we returned early if neither succeeded)
            delivery_note = (
                f"Application submitted to BytePro. Your reference is "
                f"{app.bytepro_loan_number}."
            )

        return (
            f"{delivery_note} Your Perennia loan ID is "
            f"{_spell_loan_id(app.loan_id)}.{sms_note} "
            f"Now let's get you on {lo_first}'s calendar for a quick kickoff "
            f"call — it takes about thirty minutes. Let me pull up some times."
        )

    # ==================================================================
    # LO KICKOFF BOOKING (Smart Calendar)
    # ==================================================================

    @function_tool
    async def offer_lo_kickoff_slots(
        self,
        ctx: RunContext,
        lookahead_days: int = 5,
    ) -> Dict[str, Any]:
        """
        Fetch available slots on the assigned LO's Smart Calendar and cache
        them for the next booking step.

        Args:
            lookahead_days: how far out to look. Default 5 business days.
                Set higher (e.g. 14) if the caller asks for "next week" or
                similar.

        Returns a structured payload with 1-indexed options. The LLM should
        read the `voice_description` fields back to the caller naturally,
        then call `book_lo_kickoff_call(slot_choice=N)` with the number
        the caller picks.

        If no slots are available, the response signals that the LLM should
        deliver the fallback message (LO will reach out directly) and then
        call `skip_kickoff_booking`.
        """
        app = await self._load()

        if not app.is_finalized:
            return {
                "error": "Application not yet finalized. Call finalize_urla first.",
            }

        slots = await fetch_available_slots(
            tenant_id=self.tenant_id,
            loan_officer_nmlsr_id=self.loan_officer.nmlsr_id,
            lookahead_days=lookahead_days,
        )

        if not slots:
            logger.warning(
                "No Smart Calendar slots returned",
                extra={
                    "loan_id": app.loan_id,
                    "lo_nmlsr": self.loan_officer.nmlsr_id,
                },
            )
            lo_first = self.loan_officer.name.split()[0] if self.loan_officer.name else "your loan officer"
            return {
                "slots_found": 0,
                "fallback_message": (
                    f"I'm having trouble pulling up available times right now, "
                    f"but don't worry — your application is in. {lo_first} will "
                    f"reach out directly within one business day to schedule "
                    f"your kickoff call."
                ),
            }

        # Cache for the booking step (1-indexed for voice)
        self._offered_slots = slots

        return {
            "slots_found": len(slots),
            "loan_officer_name": self.loan_officer.name,
            "meeting_duration_minutes": (
                int((slots[0].end - slots[0].start).total_seconds() // 60)
            ),
            "options": [
                {
                    "option_number": i,
                    "voice_description": _format_slot_for_voice(slot),
                    "iso_start": slot.start.isoformat(),
                    "iso_end": slot.end.isoformat(),
                    "timezone": slot.timezone,
                }
                for i, slot in enumerate(slots, start=1)
            ],
        }

    @function_tool
    async def book_lo_kickoff_call(
        self,
        ctx: RunContext,
        slot_choice: int,
    ) -> str:
        """
        Book the numbered slot the caller picked from the previous offer.

        Args:
            slot_choice: 1-indexed choice from the options returned by
                `offer_lo_kickoff_slots`. If the caller says "the first one",
                pass 1. "The last one" -> the highest index offered.

        If the caller rejects all offered times and asks for different days,
        do NOT call this — call `offer_lo_kickoff_slots` again with a larger
        `lookahead_days`.

        If the slot was taken in the interim (race condition), this tool
        signals so the LLM can re-offer fresh slots.
        """
        if not self._offered_slots:
            return (
                "Let me pull up some available times first before we book."
            )

        total = len(self._offered_slots)
        if slot_choice < 1 or slot_choice > total:
            return (
                f"I only offered {total} option{'s' if total != 1 else ''}. "
                f"Could you pick a number from one to {total}, or let me "
                f"know if you'd like different times?"
            )

        chosen = self._offered_slots[slot_choice - 1]
        app = await self._load()
        primary = self._primary(app)
        s1a = primary.section_1a

        borrower_name = (
            f"{s1a.first_name} {s1a.last_name}"
            if s1a and s1a.first_name and s1a.last_name
            else "Borrower"
        )
        borrower_email = (s1a.email if s1a and s1a.email else "")

        result: BookingResult = await book_slot(
            tenant_id=self.tenant_id,
            slot_id=chosen.slot_id,
            loan_id=app.loan_id,
            borrower_name=borrower_name,
            borrower_phone=app.caller_phone,
            borrower_email=borrower_email,
            loan_officer_nmlsr_id=self.loan_officer.nmlsr_id,
            notes=(
                f"Perennia loan ID {app.loan_id}. "
                f"BytePro ref {app.bytepro_loan_number or 'pending'}. "
                f"Auto-booked via URLA voice agent immediately after finalize."
            ),
        )

        if not result.success:
            if result.slot_no_longer_available:
                self._offered_slots = []
                return (
                    "It looks like someone just grabbed that time. Let me "
                    "pull up fresh options — one second."
                )
            logger.error(
                "LO kickoff booking failed",
                extra={"loan_id": app.loan_id, "error": result.error},
            )
            lo_first = self.loan_officer.name.split()[0] if self.loan_officer.name else "your loan officer"
            # Clean close even if booking fails — app is already submitted
            await self.state.complete_session(app)
            return (
                f"I'm having trouble completing the booking on my end, but "
                f"your application is fully submitted. {lo_first} will reach "
                f"out directly within one business day to get a time scheduled. "
                f"Anything else before we wrap up?"
            )

        # Persist booking on the application
        app.lo_kickoff_booking = LOKickoffBooking(
            event_id=result.event_id or "",
            confirmation_number=result.confirmation_number,
            scheduled_start=result.scheduled_start or chosen.start,
            scheduled_end=result.scheduled_end or chosen.end,
            scheduled_timezone=result.scheduled_timezone or chosen.timezone,
            loan_officer_name=result.loan_officer_name or self.loan_officer.name,
            booked_at=datetime.now(timezone.utc),
        )
        if "LO_KICKOFF_BOOKED" not in app.completed_sections:
            app.completed_sections.append("LO_KICKOFF_BOOKED")

        await self.state.complete_session(app)
        self._offered_slots = []

        when = _format_slot_for_voice(chosen)
        lo_name = result.loan_officer_name or self.loan_officer.name
        conf_phrase = (
            f"Your confirmation number is {result.confirmation_number}. "
            if result.confirmation_number else ""
        )
        logger.info(
            "LO kickoff call booked",
            extra={
                "loan_id": app.loan_id,
                "event_id": result.event_id,
                "slot_start": chosen.start.isoformat(),
            },
        )
        return (
            f"Booked. You're on {lo_name}'s calendar for {when}. You'll get "
            f"a calendar invite and a confirmation email shortly. "
            f"{conf_phrase}Anything else before we wrap up?"
        )

    @function_tool
    async def skip_kickoff_booking(
        self,
        ctx: RunContext,
        reason: str = "caller preferred to schedule later",
    ) -> str:
        """
        Call this when the caller declines to book a kickoff call on this
        session, or when the calendar was unavailable and we delivered the
        fallback message. Cleanly closes the session so a future call starts
        fresh.
        """
        app = await self._load()
        logger.info(
            "LO kickoff booking skipped",
            extra={"loan_id": app.loan_id, "reason": reason},
        )
        await self.state.complete_session(app)
        self._offered_slots = []
        lo_first = self.loan_officer.name.split()[0] if self.loan_officer.name else "your loan officer"
        return (
            f"No problem. Your application is in, and {lo_first} will reach "
            f"out to you directly to schedule. Your Perennia loan ID is "
            f"{_spell_loan_id(app.loan_id)}. Thanks for trusting us with "
            f"this — have a great rest of your day."
        )


# =============================================================================
# Module-private helpers
# =============================================================================

def _spell_loan_id(loan_id: str) -> str:
    """Voice-friendly readout: character-by-character spelling."""
    _digit_words = {
        '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
        '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine',
    }
    parts = []
    for ch in loan_id:
        if ch == '-':
            parts.append('dash')
        elif ch.isdigit():
            parts.append(_digit_words[ch])
        else:
            parts.append(ch.upper())
    return ' '.join(parts)


def _norm_enum(raw: str, enum_cls) -> str:
    """Normalize free-text enum input to canonical enum value."""
    if raw is None:
        raise ValueError(f"Missing value for {enum_cls.__name__}")
    s = raw.strip().upper().replace(" ", "_").replace("-", "_")
    values = {e.value for e in enum_cls}
    if s in values:
        return s
    # Prefix match (longest first to avoid ambiguity)
    candidates = sorted([e.value for e in enum_cls if e.value.startswith(s)], key=len)
    if len(candidates) == 1:
        return candidates[0]
    # Reverse prefix (input starts with enum value)
    candidates = sorted([e.value for e in enum_cls if s.startswith(e.value)], key=len, reverse=True)
    if candidates:
        return candidates[0]
    raise ValueError(f"Could not map '{raw}' to {enum_cls.__name__}. Valid: {', '.join(values)}")


def _spell_dollars_for_voice(amount: float) -> str:
    """Voice-friendly dollar readback: $425,000 -> 'four hundred twenty-five thousand dollars'."""
    if amount <= 0:
        return "zero dollars"
    n = int(round(amount))
    if n >= 1_000_000 and n % 1_000_000 == 0:
        return f"{n // 1_000_000} million dollars"
    if n >= 1_000_000:
        millions = n // 1_000_000
        remainder = n % 1_000_000
        if remainder % 1_000 == 0:
            return f"{millions} million {remainder // 1_000} thousand dollars"
        return f"${n:,.0f}"
    if n >= 1_000 and n % 1_000 == 0:
        return f"{n // 1_000} thousand dollars"
    return f"${n:,.0f}"


def _sum_monthly_income(borrower: Borrower) -> float:
    total = 0.0
    s1b = borrower.section_1b
    if s1b and not s1b.does_not_apply:
        for f in ("base_monthly", "overtime_monthly", "bonus_monthly",
                  "commission_monthly", "military_entitlements_monthly", "other_monthly"):
            v = getattr(s1b, f, None)
            if v:
                total += float(v)
        if s1b.self_employed and s1b.self_employment_monthly_income_loss:
            total += float(s1b.self_employment_monthly_income_loss)
    if borrower.section_1c:
        for e in borrower.section_1c.employments:
            total += float(e.base_monthly or 0)
    if borrower.section_1e and not borrower.section_1e.does_not_apply:
        for src in borrower.section_1e.sources:
            total += float(src.monthly_amount)
    return round(total, 2)


def _sum_monthly_debts(app: URLAApplication) -> float:
    total = 0.0
    if app.section_2:
        for liab in app.section_2.liabilities:
            total += float(liab.monthly_payment)
        for other in app.section_2.other_liabilities:
            total += float(other.monthly_payment)
    return round(total, 2)


# US timezone short names for voice readback
_TZ_SHORT = {
    "America/New_York": "Eastern",
    "America/Detroit": "Eastern",
    "America/Indianapolis": "Eastern",
    "America/Chicago": "Central",
    "America/Denver": "Mountain",
    "America/Phoenix": "Mountain",
    "America/Los_Angeles": "Pacific",
    "America/Anchorage": "Alaska",
    "Pacific/Honolulu": "Hawaii",
}


def _format_slot_for_voice(slot: AvailableSlot) -> str:
    """
    Turn a slot into natural speech, e.g.:
        'Thursday, April 23rd at 10 AM Eastern'
        'Friday, April 24th at 2:30 PM Pacific'
    """
    dt = slot.start
    weekday = dt.strftime("%A")
    month = dt.strftime("%B")
    day_num = dt.day
    # Ordinal suffix
    if 10 <= day_num % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day_num % 10, "th")

    hour = dt.hour
    minute = dt.minute
    ampm = "AM" if hour < 12 else "PM"
    hour_12 = hour % 12 or 12
    time_str = f"{hour_12}:{minute:02d} {ampm}" if minute else f"{hour_12} {ampm}"

    tz_short = _TZ_SHORT.get(slot.timezone, slot.timezone)
    return f"{weekday}, {month} {day_num}{suffix} at {time_str} {tz_short}"
