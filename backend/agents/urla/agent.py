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

from livekit.agents import Agent, RunContext, function_tool

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
    ):
        super().__init__(instructions=SYSTEM_PROMPT)
        self.tenant_id = tenant_id
        self.caller_phone = caller_phone
        self.state = state
        self.loan_officer = loan_officer
        self._active_loan_id: Optional[str] = None
        # Cache of slots offered to the caller; indexed 1..N for voice readback
        self._offered_slots: List[AvailableSlot] = []
        # Rate-limit counters for list-append tools (Fix I4)
        self._tool_call_counts: Dict[str, int] = {}

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

    def _assert_section_reachable(self, target_section: str) -> None:
        """
        Ensure the target section is reachable from the current position.
        Allows going back to completed sections (corrections) or advancing
        to the current/next section, but not skipping ahead.
        """
        if not self._active_loan_id:
            return  # No app loaded yet; lifecycle tools handle this
        # Will be checked against the live app state
        # Deferred to actual call so we don't need async here
        pass

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

        self._active_loan_id = app.loan_id
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
        Logs the context so the LO sees what's been collected so far.
        """
        app = await self._load()
        logger.info(
            "Human transfer requested",
            extra={
                "loan_id": app.loan_id,
                "reason": reason,
                "progress": app.progress_summary(),
            },
        )
        # In production: emit an event to your telephony/dispatch system here.
        return (
            "Of course. I'll connect you with a loan officer now. Everything "
            "we've covered so far is saved, so you won't have to repeat yourself."
        )

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
        section.first_name = first_name
        section.middle_name = middle_name
        section.last_name = last_name
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
                street=current_street,
                city=current_city,
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
            employer_name=employer_name,
            position_title=position_title,
            start_date=V.parse_date(start_date),
            employer_address=Address(
                street=employer_street,
                city=employer_city,
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
        app.section_2.other_credits.append(
            OtherCredit(
                credit_type=credit_type,
                amount=Decimal(str(amount)),
                description=description,
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
                creditor_name=creditor_name,
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
        app.section_3.properties.append(
            PropertyOwned(
                address=Address(
                    street=street, city=city,
                    state=V.parse_state(state), zip_code=zip_code,
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
        app.section_3.properties[property_index].mortgages.append(
            REOMortgage(
                creditor_name=creditor_name,
                monthly_payment=Decimal(str(monthly_payment)),
                unpaid_balance=Decimal(str(unpaid_balance)),
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
                street=subject_street, city=subject_city,
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
        return (
            f"Got it: ${loan_amount:,.0f} {loan_purpose.lower()} on "
            f"{subject_street}, {subject_city}. "
            f"Are you taking out any other new mortgages on this property, "
            f"like a piggyback second?"
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
        recording_url: Optional[str] = None,
    ) -> str:
        """
        Record the caller's verbal 'I agree' to the acknowledgments disclosure.
        This is required before finalize.
        """
        await self._assert_section_reachable_async("SECTION_6")
        app = await self._load()
        app.section_6 = Section6_Acknowledgments(
            verbal_consent_given=consent_given,
            verbal_consent_timestamp=datetime.now(timezone.utc) if consent_given else None,
            verbal_consent_recording_url=recording_url,
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
        Validate, serialize, and push the application to BytePro. Call ONLY
        after the caller has confirmed the final summary is accurate.

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

        result: PushResult = await push_to_bytepro(app, self.loan_officer)

        if not result.success:
            logger.error(
                "BytePro push failed",
                extra={"loan_id": app.loan_id, "error": result.error},
            )
            return (
                "I've saved everything on our side, but there was a hiccup "
                "sending it to our loan system. A loan officer will be "
                f"notified right away. Your loan ID is {_spell_loan_id(app.loan_id)} "
                "for reference."
            )

        # Record BytePro submission on the application
        app.bytepro_loan_number = result.bytepro_loan_number
        app.bytepro_submitted_at = datetime.now(timezone.utc)
        await self.state.finalize(app)  # sets is_finalized, transitions to LO_KICKOFF_BOOKING

        logger.info(
            "URLA finalized",
            extra={
                "loan_id": app.loan_id,
                "bytepro_loan_number": result.bytepro_loan_number,
            },
        )

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

        lo_first = self.loan_officer.name.split()[0] if self.loan_officer.name else "your loan officer"
        return (
            f"Application submitted. Your BytePro reference is "
            f"{result.bytepro_loan_number}, and your Perennia loan ID is "
            f"{_spell_loan_id(app.loan_id)}. "
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
