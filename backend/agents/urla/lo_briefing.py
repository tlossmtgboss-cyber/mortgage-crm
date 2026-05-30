"""
Perennia AI — URLA LO Briefing Generator
=========================================
Generates a comprehensive loan officer briefing from a completed URLA
voice agent session. Designed to give the LO everything they need for
their kickoff call — borrower profile, financial snapshot, red flags,
missing items, and recommended talking points.

Two modes:
  1. Rule-based (fast, no LLM) — extracts structured data from the application
  2. LLM-enhanced (richer) — uses Claude to analyze transcript for nuance
"""
from __future__ import annotations

import html
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from .models import (
    Borrower,
    CallTranscriptEntry,
    Section1b_CurrentEmployment,
    URLAApplication,
)


logger = logging.getLogger("urla.lo_briefing")


# =============================================================================
# BRIEFING MODEL
# =============================================================================

class LOBriefing(BaseModel):
    loan_id: str
    generated_at: datetime

    # Borrower snapshot
    borrower_name: str
    borrower_phone: str
    borrower_email: Optional[str] = None
    co_borrower_name: Optional[str] = None

    # Financial snapshot
    loan_purpose: str
    loan_amount: str  # formatted currency
    property_address: str
    property_value: str
    occupancy_type: str
    total_monthly_income: str
    total_monthly_debts: str
    estimated_dti: Optional[str] = None  # debt-to-income ratio
    total_assets: str

    # Employment summary
    employment_summary: str

    # Key findings
    executive_summary: str
    red_flags: List[str] = Field(default_factory=list)
    missing_items: List[str] = Field(default_factory=list)
    stated_concerns: List[str] = Field(default_factory=list)

    # Recommendations
    recommended_talking_points: List[str] = Field(default_factory=list)
    va_eligible: bool = False

    # Declarations summary (only flag "yes" answers)
    declaration_flags: List[str] = Field(default_factory=list)

    # Call metadata
    call_duration_minutes: Optional[float] = None
    sections_completed: List[str] = Field(default_factory=list)
    sections_remaining: List[str] = Field(default_factory=list)


# =============================================================================
# CONSTANTS
# =============================================================================

_ALL_SECTIONS = URLAApplication.TRACKABLE_SECTIONS

# DTI thresholds
_DTI_WARNING = Decimal("43")   # QM threshold
_DTI_CRITICAL = Decimal("50")  # Hard stop for most programs

_ZERO = Decimal("0")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _format_currency(amount: Optional[Decimal]) -> str:
    """Format a Decimal as '$425,000' or '$0' for None."""
    if amount is None:
        return "$0"
    # Round to nearest cent, then format
    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # Strip trailing zeros after decimal for whole-dollar amounts
    if rounded == rounded.to_integral_value():
        return f"${int(rounded):,}"
    return f"${rounded:,.2f}"


def _summarize_employment(borrower: Borrower) -> str:
    """One-line employment summary from Section 1b."""
    s1b = borrower.section_1b
    if not s1b:
        # Check other income
        if borrower.section_1e and borrower.section_1e.sources:
            sources = [s.source_type for s in borrower.section_1e.sources]
            return f"Income from other sources: {', '.join(str(s).replace('_', ' ').title() for s in sources)}"
        return "No employment or income information collected"

    if s1b.does_not_apply:
        return "Not currently employed (marked N/A)"

    parts = []
    if s1b.position_title:
        parts.append(s1b.position_title)
    if s1b.employer_name:
        if s1b.self_employed:
            parts.append(f"(self-employed at {s1b.employer_name})")
        else:
            parts.append(f"at {s1b.employer_name}")

    if s1b.start_date:
        from datetime import date as _date
        today = _date.today()
        months = (today.year - s1b.start_date.year) * 12 + (today.month - s1b.start_date.month)
        years = months // 12
        remaining_months = months % 12
        if years > 0:
            tenure = f"{years}y {remaining_months}m" if remaining_months else f"{years}y"
        else:
            tenure = f"{remaining_months}m"
        parts.append(f"({tenure})")

    total_monthly = _total_employment_income(s1b)
    if total_monthly > _ZERO:
        parts.append(f"- {_format_currency(total_monthly)}/mo")

    return " ".join(parts) if parts else "Employment information incomplete"


def _total_employment_income(s1b: Section1b_CurrentEmployment) -> Decimal:
    """Sum all income components from Section 1b."""
    total = _ZERO
    for field in (
        s1b.base_monthly,
        s1b.overtime_monthly,
        s1b.bonus_monthly,
        s1b.commission_monthly,
        s1b.military_entitlements_monthly,
        s1b.other_monthly,
    ):
        if field is not None:
            total += field
    if s1b.self_employment_monthly_income_loss is not None:
        total += s1b.self_employment_monthly_income_loss
    return total


def _total_monthly_income(app: URLAApplication) -> Decimal:
    """Total monthly income across all borrowers and income sources."""
    total = _ZERO
    for borrower in app.borrowers:
        # Primary employment (Section 1b)
        if borrower.section_1b and not borrower.section_1b.does_not_apply:
            total += _total_employment_income(borrower.section_1b)

        # Additional employment (Section 1c)
        if borrower.section_1c:
            for emp in borrower.section_1c.employments:
                if not emp.does_not_apply:
                    total += _total_employment_income(emp)

        # Other income (Section 1e)
        if borrower.section_1e and not borrower.section_1e.does_not_apply:
            for src in borrower.section_1e.sources:
                total += src.monthly_amount
    return total


def _total_monthly_debts(app: URLAApplication) -> Decimal:
    """Total monthly debt payments from Section 2 liabilities."""
    total = _ZERO
    if not app.section_2:
        return total
    for liability in app.section_2.liabilities:
        if not liability.to_be_paid_off_at_closing:
            total += liability.monthly_payment
    for other in app.section_2.other_liabilities:
        total += other.monthly_payment
    return total


def _total_assets(app: URLAApplication) -> Decimal:
    """Total asset value from Section 2."""
    total = _ZERO
    if not app.section_2:
        return total
    for asset in app.section_2.assets:
        total += asset.cash_or_market_value
    for credit in app.section_2.other_credits:
        total += credit.amount
    return total


def _calculate_dti(app: URLAApplication) -> Optional[Decimal]:
    """Debt-to-income ratio as a percentage. Returns None if income is zero."""
    income = _total_monthly_income(app)
    if income <= _ZERO:
        return None
    debts = _total_monthly_debts(app)
    return (debts / income * Decimal("100")).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )


def _extract_declaration_flags(borrower: Borrower) -> List[str]:
    """Return plain-English descriptions for any Section 5 declarations answered 'yes'."""
    flags: List[str] = []
    s5 = borrower.section_5
    if not s5:
        return flags

    prefix = ""
    if not borrower.is_primary and borrower.section_1a:
        name = f"{borrower.section_1a.first_name or ''} {borrower.section_1a.last_name or ''}".strip()
        prefix = f"[{name}] " if name else f"[{borrower.borrower_id}] "

    # 5a — Property and Money
    s5a = s5.section_5a
    if s5a:
        _check_flag(flags, s5a.had_ownership_interest_last_3_years,
                     f"{prefix}Had ownership interest in a property in last 3 years")
        _check_flag(flags, s5a.family_business_relationship_with_seller,
                     f"{prefix}Family/business relationship with seller")
        _check_flag(flags, s5a.borrowing_money_for_transaction,
                     f"{prefix}Borrowing money for this transaction "
                     f"({_format_currency(s5a.borrowed_amount) if s5a.borrowed_amount else 'amount unknown'})")
        _check_flag(flags, s5a.applying_for_other_mortgage_before_closing,
                     f"{prefix}Applying for another mortgage before closing")
        _check_flag(flags, s5a.applying_for_new_credit_before_closing,
                     f"{prefix}Applying for new credit before closing")
        _check_flag(flags, s5a.property_subject_to_lien,
                     f"{prefix}Property subject to a lien")

    # 5b — Finances
    s5b = s5.section_5b
    if s5b:
        _check_flag(flags, s5b.co_signer_on_undisclosed_debt,
                     f"{prefix}Co-signer on undisclosed debt")
        _check_flag(flags, s5b.outstanding_judgments,
                     f"{prefix}Outstanding judgments")
        _check_flag(flags, s5b.currently_delinquent_on_federal_debt,
                     f"{prefix}Currently delinquent on federal debt")
        _check_flag(flags, s5b.party_to_lawsuit,
                     f"{prefix}Party to a lawsuit")
        _check_flag(flags, s5b.conveyed_title_in_lieu_of_foreclosure_last_7_years,
                     f"{prefix}Conveyed title in lieu of foreclosure (last 7 years)")
        _check_flag(flags, s5b.short_sale_or_pre_foreclosure_last_7_years,
                     f"{prefix}Short sale or pre-foreclosure (last 7 years)")
        _check_flag(flags, s5b.foreclosed_last_7_years,
                     f"{prefix}Foreclosed in last 7 years")
        if s5b.declared_bankruptcy_last_7_years:
            types = ", ".join(s5b.bankruptcy_types) if s5b.bankruptcy_types else "type unknown"
            flags.append(f"{prefix}Declared bankruptcy in last 7 years ({types})")

    return flags


def _check_flag(flags: List[str], value: Optional[bool], description: str) -> None:
    """Append description to flags if value is True."""
    if value is True:
        flags.append(description)


def _borrower_full_name(borrower: Borrower) -> str:
    """Extract full name from Section 1a."""
    s1a = borrower.section_1a
    if not s1a:
        return "Unknown"
    parts = [s1a.first_name or "", s1a.middle_name or "", s1a.last_name or ""]
    if s1a.suffix:
        parts.append(s1a.suffix)
    name = " ".join(p for p in parts if p)
    return name or "Unknown"


def _format_address(addr) -> str:
    """Format an Address model to a single string."""
    if not addr:
        return "Not provided"
    parts = [addr.street]
    if addr.unit:
        parts.append(f"Unit {addr.unit}")
    parts.append(f"{addr.city}, {addr.state} {addr.zip_code}")
    return ", ".join(parts)


def _is_va_eligible(borrower: Borrower) -> bool:
    """Determine VA eligibility from Section 7."""
    s7 = borrower.section_7
    if not s7:
        return False
    return bool(
        s7.served_in_military
        or s7.currently_active_duty
        or s7.retired_discharged_separated
        or s7.non_activated_reserve_national_guard
        or s7.surviving_spouse
    )


def _compute_call_duration(transcript: List[CallTranscriptEntry]) -> Optional[float]:
    """Duration in minutes from first to last transcript entry."""
    if len(transcript) < 2:
        return None
    first = transcript[0].timestamp
    last = transcript[-1].timestamp
    delta = last - first
    minutes = delta.total_seconds() / 60.0
    return round(minutes, 1) if minutes > 0 else None


def _sections_remaining(completed: List[str]) -> List[str]:
    """Return section names not yet in the completed list."""
    completed_upper = {s.upper() for s in completed}
    return [s for s in _ALL_SECTIONS if s not in completed_upper]


def _identify_red_flags(
    app: URLAApplication,
    dti: Optional[Decimal],
    declaration_flags: List[str],
) -> List[str]:
    """Identify issues the LO should investigate."""
    flags: List[str] = []

    # High DTI
    if dti is not None:
        if dti >= _DTI_CRITICAL:
            flags.append(
                f"DTI ratio is {dti}% — exceeds 50% threshold. "
                "May not qualify for most conventional/FHA programs without compensating factors."
            )
        elif dti >= _DTI_WARNING:
            flags.append(
                f"DTI ratio is {dti}% — above QM 43% threshold. "
                "Will need compensating factors or non-QM program."
            )

    # Bankruptcy / foreclosure / lawsuit from declarations
    for df in declaration_flags:
        lower = df.lower()
        if "bankruptcy" in lower:
            flags.append(f"DECLARATION: {df} — verify seasoning period and discharge docs.")
        elif "foreclos" in lower:
            flags.append(f"DECLARATION: {df} — verify waiting period satisfaction.")
        elif "short sale" in lower:
            flags.append(f"DECLARATION: {df} — verify waiting period per program guidelines.")
        elif "lawsuit" in lower:
            flags.append(f"DECLARATION: {df} — obtain details and legal documentation.")
        elif "delinquent on federal" in lower:
            flags.append(f"DECLARATION: {df} — federal debt delinquency is a hard stop for FHA/VA/USDA.")
        elif "judgment" in lower:
            flags.append(f"DECLARATION: {df} — must be satisfied or on payment plan for most programs.")

    # Self-employment without verification
    primary = app.primary_borrower()
    if primary and primary.section_1b and primary.section_1b.self_employed:
        flags.append(
            "Self-employed borrower — will need 2 years of tax returns and YTD P&L."
        )

    # Employment gap
    if primary and primary.section_1b and primary.section_1b.start_date:
        from datetime import date as _date
        months_at_job = (
            (_date.today().year - primary.section_1b.start_date.year) * 12
            + (_date.today().month - primary.section_1b.start_date.month)
        )
        if months_at_job < 24 and (not primary.section_1d or primary.section_1d.does_not_apply):
            flags.append(
                f"Less than 2 years at current employer ({months_at_job} months) "
                "and no previous employment on file. Need 2-year history."
            )

    # Low assets relative to loan amount
    s4a = app.section_4.section_4a if app.section_4 else None
    total_asset_value = _total_assets(app)
    if s4a and s4a.loan_amount and total_asset_value > _ZERO:
        # If total liquid assets < 2% of loan amount, flag thin reserves
        two_pct = s4a.loan_amount * Decimal("0.02")
        if total_asset_value < two_pct:
            flags.append(
                f"Total verified assets ({_format_currency(total_asset_value)}) are less than "
                f"2% of loan amount ({_format_currency(s4a.loan_amount)}). Reserves may be insufficient."
            )

    # Non-primary occupancy
    if s4a and s4a.occupancy:
        occ = s4a.occupancy
        if occ in ("INVESTMENT", "SECOND_HOME"):
            flags.append(
                f"Property occupancy is {occ.replace('_', ' ').title()} — "
                "higher rate pricing and stricter DTI/reserve requirements apply."
            )

    # Borrowing money for transaction
    if primary and primary.section_5 and primary.section_5.section_5a:
        s5a = primary.section_5.section_5a
        if s5a.borrowing_money_for_transaction:
            flags.append(
                "Borrower indicated they are borrowing money for this transaction — "
                "source of funds documentation required."
            )

    return flags


def _generate_talking_points(
    app: URLAApplication,
    briefing_data: dict,
    dti: Optional[Decimal],
    red_flags: List[str],
    missing_items: List[str],
    va_eligible: bool,
) -> List[str]:
    """Generate recommended talking points for the LO's kickoff call."""
    points: List[str] = []

    # Always start with rapport
    primary = app.primary_borrower()
    if primary and primary.section_1a:
        first = primary.section_1a.first_name or "the borrower"
        points.append(f"Thank {first} for completing the application over the phone with Aria.")

    # Loan purpose context
    s4a = app.section_4.section_4a if app.section_4 else None
    if s4a and s4a.loan_purpose:
        purpose = str(s4a.loan_purpose).replace("_", " ").lower()
        points.append(f"Confirm the {purpose} details and timeline expectations.")

    # Missing items
    if missing_items:
        points.append(
            f"Collect {len(missing_items)} missing item(s): "
            + "; ".join(missing_items[:3])
            + ("..." if len(missing_items) > 3 else "")
        )

    # DTI discussion
    if dti is not None and dti >= _DTI_WARNING:
        points.append(
            "Discuss debt reduction strategies or compensating factors to address DTI."
        )

    # VA eligibility
    if va_eligible:
        points.append(
            "Borrower appears VA eligible — discuss VA loan benefits "
            "(no PMI, competitive rates, no down payment)."
        )

    # Red flags needing documentation
    doc_flags = [f for f in red_flags if "DECLARATION" in f]
    if doc_flags:
        points.append(
            "Review declaration disclosures and request supporting documentation."
        )

    # Self-employment
    if any("self-employed" in f.lower() for f in red_flags):
        points.append(
            "Discuss tax return documentation requirements and P&L preparation."
        )

    # Rate lock discussion
    if s4a and s4a.loan_amount:
        points.append("Discuss rate lock timing and current rate options.")

    # Next steps
    points.append("Set expectations for the processing timeline and document collection.")

    return points


# =============================================================================
# RULE-BASED BRIEFING GENERATOR
# =============================================================================

def generate_lo_briefing(
    app: URLAApplication,
    score: Optional[Any] = None,
) -> LOBriefing:
    """
    Generate a comprehensive LO briefing using rule-based extraction only.

    Args:
        app: Completed (or partially completed) URLAApplication.
        score: Optional application scoring data (reserved for future use).

    Returns:
        LOBriefing with all structured data extracted from the application.
    """
    primary = app.primary_borrower()

    # --- Borrower snapshot ---
    borrower_name = _borrower_full_name(primary) if primary else "Unknown"
    borrower_phone = app.caller_phone
    borrower_email = None
    if primary and primary.section_1a and primary.section_1a.email:
        borrower_email = primary.section_1a.email

    co_borrower_name = None
    co_borrowers = [b for b in app.borrowers if not b.is_primary]
    if co_borrowers:
        co_borrower_name = _borrower_full_name(co_borrowers[0])

    # --- Loan / property snapshot ---
    s4a = app.section_4.section_4a if app.section_4 else None
    loan_purpose = str(s4a.loan_purpose).replace("_", " ").title() if s4a and s4a.loan_purpose else "Not specified"
    loan_amount = _format_currency(s4a.loan_amount) if s4a else "$0"
    property_address = _format_address(s4a.subject_property_address) if s4a else "Not provided"
    property_value = _format_currency(s4a.property_value) if s4a else "$0"
    occupancy_type = (
        str(s4a.occupancy).replace("_", " ").title()
        if s4a and s4a.occupancy
        else "Not specified"
    )

    # --- Financial snapshot ---
    monthly_income = _total_monthly_income(app)
    monthly_debts = _total_monthly_debts(app)
    total_assets_val = _total_assets(app)
    dti = _calculate_dti(app)

    # --- Employment ---
    employment_summary = _summarize_employment(primary) if primary else "No borrower data"

    # --- Declarations ---
    all_declaration_flags: List[str] = []
    for borrower in app.borrowers:
        all_declaration_flags.extend(_extract_declaration_flags(borrower))

    # --- VA eligibility ---
    va_eligible = any(_is_va_eligible(b) for b in app.borrowers)

    # --- Missing items ---
    missing_items = app.validate_complete()

    # --- Red flags ---
    red_flags = _identify_red_flags(app, dti, all_declaration_flags)

    # --- Sections completed / remaining ---
    sections_completed = list(app.completed_sections)
    sections_remaining = _sections_remaining(app.completed_sections)

    # --- Call duration ---
    call_duration = _compute_call_duration(app.transcript)

    # --- Executive summary ---
    executive_summary = _build_executive_summary(
        borrower_name=borrower_name,
        co_borrower_name=co_borrower_name,
        loan_purpose=loan_purpose,
        loan_amount=loan_amount,
        property_address=property_address,
        dti=dti,
        va_eligible=va_eligible,
        red_flag_count=len(red_flags),
        missing_count=len(missing_items),
        sections_completed=sections_completed,
    )

    # Build partial data dict for talking points generation
    briefing_data = {
        "borrower_name": borrower_name,
        "loan_purpose": loan_purpose,
    }

    talking_points = _generate_talking_points(
        app, briefing_data, dti, red_flags, missing_items, va_eligible
    )

    return LOBriefing(
        loan_id=app.loan_id,
        generated_at=datetime.now(timezone.utc),
        borrower_name=borrower_name,
        borrower_phone=borrower_phone,
        borrower_email=borrower_email,
        co_borrower_name=co_borrower_name,
        loan_purpose=loan_purpose,
        loan_amount=loan_amount,
        property_address=property_address,
        property_value=property_value,
        occupancy_type=occupancy_type,
        total_monthly_income=_format_currency(monthly_income),
        total_monthly_debts=_format_currency(monthly_debts),
        estimated_dti=f"{dti}%" if dti is not None else None,
        total_assets=_format_currency(total_assets_val),
        employment_summary=employment_summary,
        executive_summary=executive_summary,
        red_flags=red_flags,
        missing_items=missing_items,
        stated_concerns=[],  # Rule-based mode cannot extract concerns from transcript
        recommended_talking_points=talking_points,
        va_eligible=va_eligible,
        declaration_flags=all_declaration_flags,
        call_duration_minutes=call_duration,
        sections_completed=sections_completed,
        sections_remaining=sections_remaining,
    )


def _build_executive_summary(
    borrower_name: str,
    co_borrower_name: Optional[str],
    loan_purpose: str,
    loan_amount: str,
    property_address: str,
    dti: Optional[Decimal],
    va_eligible: bool,
    red_flag_count: int,
    missing_count: int,
    sections_completed: List[str],
) -> str:
    """Build a concise executive summary paragraph."""
    parts = []

    # Who
    who = borrower_name
    if co_borrower_name:
        who += f" and {co_borrower_name}"
    parts.append(f"{who} — {loan_purpose} for {loan_amount}.")

    # Property
    if property_address != "Not provided":
        parts.append(f"Property: {property_address}.")

    # DTI
    if dti is not None:
        if dti >= _DTI_CRITICAL:
            parts.append(f"Estimated DTI: {dti}% (ABOVE 50% — HIGH RISK).")
        elif dti >= _DTI_WARNING:
            parts.append(f"Estimated DTI: {dti}% (above QM threshold).")
        else:
            parts.append(f"Estimated DTI: {dti}%.")

    # VA
    if va_eligible:
        parts.append("VA eligible.")

    # Status
    completion = len(sections_completed)
    total = len(_ALL_SECTIONS)
    parts.append(f"Application {completion}/{total} sections complete.")

    # Flags / missing
    alerts = []
    if red_flag_count > 0:
        alerts.append(f"{red_flag_count} red flag(s)")
    if missing_count > 0:
        alerts.append(f"{missing_count} missing item(s)")
    if alerts:
        parts.append(f"Action needed: {', '.join(alerts)}.")

    return " ".join(parts)


# =============================================================================
# LLM-ENHANCED BRIEFING
# =============================================================================

async def generate_enhanced_briefing(
    app: URLAApplication,
    score: Optional[Any] = None,
) -> LOBriefing:
    """
    Generate an LLM-enhanced LO briefing. Starts with the rule-based briefing,
    then uses Claude to analyze the call transcript for nuance — stated concerns,
    hesitation, questions about rates, emotional signals, and anything the rules
    cannot catch.

    Args:
        app: Completed (or partially completed) URLAApplication.
        score: Optional application scoring data (reserved for future use).

    Returns:
        LOBriefing enriched with transcript-derived insights.
    """
    # Start with rule-based extraction
    briefing = generate_lo_briefing(app, score)

    # If there is no transcript, nothing to enhance
    if not app.transcript:
        logger.info("No transcript available — returning rule-based briefing only.")
        return briefing

    # Build the transcript text for Claude
    transcript_text = _format_transcript_for_llm(app.transcript)

    try:
        llm_insights = await _call_claude_for_insights(transcript_text, briefing)
    except Exception as e:
        logger.exception("LLM enhancement failed — returning rule-based briefing: %s", e)
        return briefing

    # Merge LLM insights into the briefing
    if llm_insights.get("stated_concerns"):
        briefing.stated_concerns = llm_insights["stated_concerns"]

    if llm_insights.get("additional_red_flags"):
        for flag in llm_insights["additional_red_flags"]:
            if flag not in briefing.red_flags:
                briefing.red_flags.append(flag)

    if llm_insights.get("additional_talking_points"):
        for point in llm_insights["additional_talking_points"]:
            if point not in briefing.recommended_talking_points:
                briefing.recommended_talking_points.append(point)

    if llm_insights.get("enhanced_summary"):
        briefing.executive_summary = llm_insights["enhanced_summary"]

    return briefing


def _format_transcript_for_llm(transcript: List[CallTranscriptEntry]) -> str:
    """Format transcript entries into a readable text block for Claude."""
    lines: List[str] = []
    for entry in transcript:
        speaker = "BORROWER" if entry.speaker.lower() == "borrower" else "AGENT"
        ts = entry.timestamp.strftime("%H:%M:%S") if entry.timestamp else ""
        lines.append(f"[{ts}] {speaker}: {entry.text}")
    return "\n".join(lines)


async def _call_claude_for_insights(
    transcript_text: str,
    briefing: LOBriefing,
) -> dict:
    """
    Call the Anthropic Messages API via httpx to extract nuanced insights
    from the call transcript.

    Returns a dict with keys: stated_concerns, additional_red_flags,
    additional_talking_points, enhanced_summary.
    """
    import json
    import httpx

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping LLM enhancement.")
        return {}

    prompt = f"""You are an expert mortgage underwriting analyst reviewing a call transcript
between an AI voice agent (Aria) and a mortgage borrower. The AI agent was collecting a
URLA 1003 mortgage application over the phone.

Here is the rule-based briefing already generated:
- Borrower: {briefing.borrower_name}
- Loan: {briefing.loan_purpose} for {briefing.loan_amount}
- Property: {briefing.property_address}
- DTI: {briefing.estimated_dti or 'Unknown'}
- Red flags already identified: {json.dumps(briefing.red_flags)}
- Missing items: {json.dumps(briefing.missing_items)}

CALL TRANSCRIPT:
{transcript_text}

Analyze this transcript and return a JSON object with EXACTLY these keys:
{{
  "stated_concerns": ["list of things the borrower explicitly expressed worry or uncertainty about"],
  "additional_red_flags": ["any red flags you notice from the conversation that are NOT already in the existing red flags list — e.g., hesitation about income, contradictory statements, reluctance to provide information"],
  "additional_talking_points": ["specific conversation points the LO should raise based on what the borrower said or asked about — e.g., if they asked about rates, PMI, closing costs, timeline"],
  "enhanced_summary": "A 2-3 sentence executive summary that incorporates both the structured data AND the conversational nuance. Write as if briefing a loan officer before their first call with this borrower."
}}

Rules:
- Only include genuinely useful insights. Do not pad lists with generic advice.
- stated_concerns must come from what the BORROWER actually said, not what you infer.
- additional_red_flags must be net-new, not duplicates of existing flags.
- Write in concise, professional mortgage industry language.
- Return ONLY valid JSON, no markdown formatting."""

    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }

    body = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()

    data = resp.json()
    # Extract the text content from the Claude response
    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text = block["text"]
            break

    if not text:
        logger.warning("Empty response from Claude — no enhancement applied.")
        return {}

    # Parse JSON from response (strip markdown fences if present)
    text = text.strip()
    if text.startswith("```"):
        # Remove ```json and ``` wrappers
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        )

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse Claude JSON response: %s", e)
        return {}

    # Validate expected keys
    return {
        "stated_concerns": result.get("stated_concerns", []),
        "additional_red_flags": result.get("additional_red_flags", []),
        "additional_talking_points": result.get("additional_talking_points", []),
        "enhanced_summary": result.get("enhanced_summary", ""),
    }


# =============================================================================
# TEXT FORMATTER
# =============================================================================

def format_briefing_as_text(briefing: LOBriefing) -> str:
    """Format the briefing as a clean text document suitable for email or display."""
    lines: List[str] = []
    divider = "=" * 60

    lines.append(divider)
    lines.append("LOAN OFFICER BRIEFING")
    lines.append(divider)
    lines.append(f"Loan ID: {briefing.loan_id}")
    lines.append(f"Generated: {briefing.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
    if briefing.call_duration_minutes:
        lines.append(f"Call Duration: {briefing.call_duration_minutes} minutes")
    lines.append("")

    # Executive Summary
    lines.append("EXECUTIVE SUMMARY")
    lines.append("-" * 40)
    lines.append(briefing.executive_summary)
    lines.append("")

    # Borrower Info
    lines.append("BORROWER INFORMATION")
    lines.append("-" * 40)
    lines.append(f"  Name:    {briefing.borrower_name}")
    lines.append(f"  Phone:   {briefing.borrower_phone}")
    if briefing.borrower_email:
        lines.append(f"  Email:   {briefing.borrower_email}")
    if briefing.co_borrower_name:
        lines.append(f"  Co-Borrower: {briefing.co_borrower_name}")
    lines.append("")

    # Loan Details
    lines.append("LOAN & PROPERTY")
    lines.append("-" * 40)
    lines.append(f"  Purpose:     {briefing.loan_purpose}")
    lines.append(f"  Amount:      {briefing.loan_amount}")
    lines.append(f"  Property:    {briefing.property_address}")
    lines.append(f"  Value:       {briefing.property_value}")
    lines.append(f"  Occupancy:   {briefing.occupancy_type}")
    if briefing.va_eligible:
        lines.append("  VA Eligible: Yes")
    lines.append("")

    # Financial Snapshot
    lines.append("FINANCIAL SNAPSHOT")
    lines.append("-" * 40)
    lines.append(f"  Monthly Income:  {briefing.total_monthly_income}")
    lines.append(f"  Monthly Debts:   {briefing.total_monthly_debts}")
    if briefing.estimated_dti:
        lines.append(f"  Est. DTI:        {briefing.estimated_dti}")
    lines.append(f"  Total Assets:    {briefing.total_assets}")
    lines.append(f"  Employment:      {briefing.employment_summary}")
    lines.append("")

    # Red Flags
    if briefing.red_flags:
        lines.append("RED FLAGS")
        lines.append("-" * 40)
        for i, flag in enumerate(briefing.red_flags, 1):
            lines.append(f"  {i}. {flag}")
        lines.append("")

    # Declaration Flags
    if briefing.declaration_flags:
        lines.append("DECLARATION ALERTS")
        lines.append("-" * 40)
        for flag in briefing.declaration_flags:
            lines.append(f"  * {flag}")
        lines.append("")

    # Missing Items
    if briefing.missing_items:
        lines.append("MISSING ITEMS")
        lines.append("-" * 40)
        for item in briefing.missing_items:
            lines.append(f"  [ ] {item}")
        lines.append("")

    # Stated Concerns (LLM-enhanced only)
    if briefing.stated_concerns:
        lines.append("BORROWER CONCERNS (from call)")
        lines.append("-" * 40)
        for concern in briefing.stated_concerns:
            lines.append(f"  - {concern}")
        lines.append("")

    # Talking Points
    if briefing.recommended_talking_points:
        lines.append("RECOMMENDED TALKING POINTS")
        lines.append("-" * 40)
        for i, point in enumerate(briefing.recommended_talking_points, 1):
            lines.append(f"  {i}. {point}")
        lines.append("")

    # Completion Status
    lines.append("APPLICATION STATUS")
    lines.append("-" * 40)
    lines.append(f"  Completed: {', '.join(briefing.sections_completed) if briefing.sections_completed else 'None'}")
    if briefing.sections_remaining:
        lines.append(f"  Remaining: {', '.join(briefing.sections_remaining)}")
    lines.append("")
    lines.append(divider)

    return "\n".join(lines)


# =============================================================================
# HTML FORMATTER
# =============================================================================

def format_briefing_as_html(briefing: LOBriefing) -> str:
    """Format the briefing as styled HTML suitable for email dispatch."""
    h = html.escape  # alias for readability

    # Color tokens
    c_primary = "#1a365d"       # Navy
    c_accent = "#2b6cb0"        # Blue
    c_danger = "#c53030"        # Red
    c_warning = "#d69e2e"       # Amber
    c_success = "#38a169"       # Green
    c_muted = "#718096"         # Gray
    c_bg = "#f7fafc"            # Light background
    c_border = "#e2e8f0"        # Border

    def section_header(title: str) -> str:
        return (
            f'<tr><td style="padding:16px 20px 8px;font-size:14px;font-weight:700;'
            f'color:{c_primary};text-transform:uppercase;letter-spacing:0.5px;'
            f'border-bottom:2px solid {c_accent};">{h(title)}</td></tr>'
        )

    def kv_row(label: str, value: str) -> str:
        return (
            f'<tr><td style="padding:4px 20px;font-size:14px;">'
            f'<span style="color:{c_muted};min-width:140px;display:inline-block;">{h(label)}</span> '
            f'<strong>{h(value)}</strong></td></tr>'
        )

    def bullet_list(items: List[str], color: str = "#2d3748") -> str:
        rows = ""
        for item in items:
            rows += (
                f'<tr><td style="padding:2px 20px 2px 36px;font-size:14px;color:{color};">'
                f'&bull; {h(item)}</td></tr>'
            )
        return rows

    def numbered_list(items: List[str], color: str = "#2d3748") -> str:
        rows = ""
        for i, item in enumerate(items, 1):
            rows += (
                f'<tr><td style="padding:2px 20px 2px 36px;font-size:14px;color:{color};">'
                f'{i}. {h(item)}</td></tr>'
            )
        return rows

    def badge(text: str, bg: str, fg: str = "#fff") -> str:
        return (
            f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
            f'font-size:12px;font-weight:600;background:{bg};color:{fg};">{h(text)}</span>'
        )

    parts: List[str] = []

    # Wrapper
    parts.append(
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="max-width:640px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'
        f'Segoe UI,Roboto,Helvetica Neue,Arial,sans-serif;background:{c_bg};border:1px solid {c_border};'
        f'border-radius:8px;overflow:hidden;">'
    )

    # Header
    parts.append(
        f'<tr><td style="background:{c_primary};padding:20px;color:#fff;">'
        f'<div style="font-size:20px;font-weight:700;">Loan Officer Briefing</div>'
        f'<div style="font-size:13px;opacity:0.8;margin-top:4px;">'
        f'Loan {h(briefing.loan_id)} &middot; '
        f'{briefing.generated_at.strftime("%B %d, %Y at %H:%M UTC")}'
    )
    if briefing.call_duration_minutes:
        parts.append(f' &middot; {briefing.call_duration_minutes} min call')
    parts.append('</div></td></tr>')

    # Executive Summary
    summary_bg = c_bg
    if briefing.red_flags:
        summary_bg = "#fff5f5"  # Light red tint
    parts.append(
        f'<tr><td style="padding:16px 20px;background:{summary_bg};font-size:14px;'
        f'line-height:1.5;border-bottom:1px solid {c_border};">'
        f'{h(briefing.executive_summary)}</td></tr>'
    )

    # Borrower Info
    parts.append(section_header("Borrower Information"))
    parts.append(kv_row("Name", briefing.borrower_name))
    parts.append(kv_row("Phone", briefing.borrower_phone))
    if briefing.borrower_email:
        parts.append(kv_row("Email", briefing.borrower_email))
    if briefing.co_borrower_name:
        parts.append(kv_row("Co-Borrower", briefing.co_borrower_name))

    # Loan & Property
    parts.append(section_header("Loan & Property"))
    parts.append(kv_row("Purpose", briefing.loan_purpose))
    parts.append(kv_row("Amount", briefing.loan_amount))
    parts.append(kv_row("Property", briefing.property_address))
    parts.append(kv_row("Value", briefing.property_value))
    parts.append(kv_row("Occupancy", briefing.occupancy_type))
    if briefing.va_eligible:
        parts.append(
            f'<tr><td style="padding:4px 20px;">'
            f'{badge("VA ELIGIBLE", c_success)}</td></tr>'
        )

    # Financial Snapshot
    parts.append(section_header("Financial Snapshot"))
    parts.append(kv_row("Monthly Income", briefing.total_monthly_income))
    parts.append(kv_row("Monthly Debts", briefing.total_monthly_debts))
    if briefing.estimated_dti:
        dti_color = "#2d3748"
        dti_val = briefing.estimated_dti
        try:
            dti_num = Decimal(dti_val.replace("%", ""))
            if dti_num >= _DTI_CRITICAL:
                dti_color = c_danger
            elif dti_num >= _DTI_WARNING:
                dti_color = c_warning
            else:
                dti_color = c_success
        except Exception:
            pass
        parts.append(
            f'<tr><td style="padding:4px 20px;font-size:14px;">'
            f'<span style="color:{c_muted};min-width:140px;display:inline-block;">Est. DTI</span> '
            f'<strong style="color:{dti_color};">{h(dti_val)}</strong></td></tr>'
        )
    parts.append(kv_row("Total Assets", briefing.total_assets))
    parts.append(kv_row("Employment", briefing.employment_summary))

    # Red Flags
    if briefing.red_flags:
        parts.append(section_header(f"Red Flags ({len(briefing.red_flags)})"))
        parts.append(bullet_list(briefing.red_flags, c_danger))

    # Declaration Flags
    if briefing.declaration_flags:
        parts.append(section_header("Declaration Alerts"))
        parts.append(bullet_list(briefing.declaration_flags, c_warning))

    # Missing Items
    if briefing.missing_items:
        parts.append(section_header(f"Missing Items ({len(briefing.missing_items)})"))
        parts.append(bullet_list(briefing.missing_items, c_muted))

    # Stated Concerns
    if briefing.stated_concerns:
        parts.append(section_header("Borrower Concerns (from call)"))
        parts.append(bullet_list(briefing.stated_concerns, c_accent))

    # Talking Points
    if briefing.recommended_talking_points:
        parts.append(section_header("Recommended Talking Points"))
        parts.append(numbered_list(briefing.recommended_talking_points))

    # Completion Status
    parts.append(section_header("Application Status"))
    completed_count = len(briefing.sections_completed)
    total = len(_ALL_SECTIONS)
    pct = int((completed_count / total) * 100) if total else 0

    # Progress bar
    parts.append(
        f'<tr><td style="padding:8px 20px;">'
        f'<div style="background:{c_border};border-radius:4px;height:8px;overflow:hidden;">'
        f'<div style="background:{c_success if pct >= 80 else c_accent};height:100%;'
        f'width:{pct}%;border-radius:4px;"></div></div>'
        f'<div style="font-size:12px;color:{c_muted};margin-top:4px;">'
        f'{completed_count}/{total} sections ({pct}% complete)</div>'
        f'</td></tr>'
    )

    if briefing.sections_remaining:
        parts.append(
            f'<tr><td style="padding:4px 20px;font-size:13px;color:{c_muted};">'
            f'Remaining: {h(", ".join(briefing.sections_remaining))}</td></tr>'
        )

    # Footer
    parts.append(
        f'<tr><td style="padding:16px 20px;font-size:12px;color:{c_muted};'
        f'text-align:center;border-top:1px solid {c_border};">'
        f'Generated by Perennia AI &middot; Aria URLA Voice Agent</td></tr>'
    )

    parts.append('</table>')

    return "\n".join(parts)
