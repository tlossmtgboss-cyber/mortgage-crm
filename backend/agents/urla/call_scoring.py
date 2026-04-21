"""
Perennia AI — URLA Call Scoring Engine
======================================
Scores URLA voice agent calls on three dimensions:
  1. Compliance (0-100): Required disclosures, consent capture, demographic notice
  2. Data Quality (0-100): Required field completeness, validation pass rate
  3. Conversation Quality (0-100): Empathy, pacing, clarity, error recovery

Each dimension starts at 100 and deducts points for violations. The overall
score is a weighted average: compliance 40%, data quality 35%, conversation 25%.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field

from .models import (
    ApplicationChannel,
    CallTranscriptEntry,
    URLAApplication,
)


# =============================================================================
# SCORING MODELS
# =============================================================================

class ComplianceFlagSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class ComplianceFlag(BaseModel):
    code: str           # e.g., "MISSING_DEMOGRAPHICS_NOTICE"
    severity: ComplianceFlagSeverity
    description: str
    section: str        # Which URLA section
    remediation: str    # What to do about it


class URLACallScore(BaseModel):
    compliance_score: float = Field(ge=0, le=100)
    data_quality_score: float = Field(ge=0, le=100)
    conversation_quality_score: float = Field(ge=0, le=100)
    overall_score: float = Field(ge=0, le=100)
    compliance_flags: List[ComplianceFlag] = Field(default_factory=list)
    data_gaps: List[str] = Field(default_factory=list)
    quality_notes: List[str] = Field(default_factory=list)
    scored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# CONSTANTS — phrases and patterns used by the compliance scanner
# =============================================================================

# Keywords from the HMDA / Reg B demographic notice that must appear before
# Section 8 questions.  We check for a meaningful subset, not an exact reading.
_DEMOGRAPHICS_NOTICE_KEYWORDS = [
    "federal government",
    "voluntary",
    "equal credit",
    "fair housing",
    "does not affect",
]

# Phrases that indicate the agent is giving rate or qualification advice —
# strictly forbidden for an unlicensed AI intake agent.
_FORBIDDEN_RATE_PHRASES = [
    r"you(?:'ll| will) (?:qualify|be approved)",
    r"your rate (?:will|would|should) be",
    r"you(?:'re| are) (?:looking at|getting) (?:a |about )?\d",
    r"i(?:'d| would) recommend (?:a |the )?(?:fha|va|conventional|usda)",
    r"you should (?:go with|choose|take)",
    r"you(?:'ll| will) get (?:a |about )?\d",
    r"based on (?:your|that).{0,30}you(?:'ll| will) qualify",
]
_FORBIDDEN_RATE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _FORBIDDEN_RATE_PHRASES]

# Full SSN pattern: 9 consecutive digits (possibly with separators) spoken aloud
# by the agent — borrower speaking their own SSN is fine, agent reading it back
# in full is the violation.
_FULL_SSN_PATTERN = re.compile(
    r"\b\d{3}[\s\-]?\d{2}[\s\-]?\d{4}\b"
)

# Empathy markers — presence of at least some of these indicates good bedside manner.
_EMPATHY_MARKERS = [
    "i understand",
    "no rush",
    "take your time",
    "no worries",
    "that's okay",
    "that is okay",
    "completely normal",
    "i appreciate",
    "thank you for sharing",
    "i hear you",
    "totally understandable",
    "no pressure",
]

# Section read-back / confirmation phrases the agent should use.
_CONFIRMATION_PHRASES = [
    "does that sound right",
    "is that correct",
    "does that look right",
    "can you confirm",
    "let me read that back",
    "just to confirm",
    "to make sure i have that right",
    "let me verify",
    "is that accurate",
]

# All nine URLA sections the agent should confirm.
_ALL_SECTIONS = [
    "1a", "1b", "2", "3", "4", "5", "6", "7", "8",
]


# =============================================================================
# EMAIL / PHONE VALIDATORS (lightweight, for data quality only)
# =============================================================================

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_E164_RE = re.compile(r"^\+\d{10,15}$")


# =============================================================================
# MAIN SCORING FUNCTION
# =============================================================================

def score_urla_call(
    app: URLAApplication,
    transcript: Optional[List[CallTranscriptEntry]] = None,
) -> URLACallScore:
    """
    Score a completed (or partially completed) URLA voice call.

    Parameters
    ----------
    app : URLAApplication
        The application state at the end of the call.
    transcript : list[CallTranscriptEntry] | None
        Override transcript.  Falls back to ``app.transcript`` if not provided.

    Returns
    -------
    URLACallScore
    """
    turns = transcript if transcript is not None else app.transcript

    compliance_score, compliance_flags = _score_compliance(app, turns)
    data_quality_score, data_gaps = _score_data_quality(app)
    conversation_score, quality_notes = _score_conversation_quality(turns)

    overall = (
        compliance_score * 0.40
        + data_quality_score * 0.35
        + conversation_score * 0.25
    )
    # Clamp to [0, 100]
    overall = max(0.0, min(100.0, round(overall, 1)))

    return URLACallScore(
        compliance_score=round(compliance_score, 1),
        data_quality_score=round(data_quality_score, 1),
        conversation_quality_score=round(conversation_score, 1),
        overall_score=overall,
        compliance_flags=compliance_flags,
        data_gaps=data_gaps,
        quality_notes=quality_notes,
    )


# =============================================================================
# COMPLIANCE (0-100, deduction model)
# =============================================================================

def _score_compliance(
    app: URLAApplication,
    turns: List[CallTranscriptEntry],
) -> tuple[float, List[ComplianceFlag]]:
    """100 points minus deductions for compliance violations."""
    score = 100.0
    flags: List[ComplianceFlag] = []

    agent_turns = [t for t in turns if t.speaker == "agent"]
    agent_text_all = " ".join(t.text for t in agent_turns).lower()

    # -------------------------------------------------------------------
    # 1. Demographics notice not read before Section 8 (-30, CRITICAL)
    # -------------------------------------------------------------------
    demographics_notice_found = _demographics_notice_was_read(turns)
    if not demographics_notice_found:
        score -= 30
        flags.append(ComplianceFlag(
            code="MISSING_DEMOGRAPHICS_NOTICE",
            severity=ComplianceFlagSeverity.CRITICAL,
            description=(
                "The government monitoring notice (Reg B / HMDA) was not detected "
                "in the transcript before Section 8 demographic questions."
            ),
            section="Section 8",
            remediation=(
                "The agent must read the full demographic notice verbatim before "
                "asking ethnicity, race, or sex questions.  Re-contact the borrower "
                "if the notice was not delivered."
            ),
        ))

    # -------------------------------------------------------------------
    # 2. Verbal consent not captured (-25, CRITICAL)
    # -------------------------------------------------------------------
    s6 = app.section_6
    if not s6 or not s6.verbal_consent_given:
        score -= 25
        flags.append(ComplianceFlag(
            code="MISSING_VERBAL_CONSENT",
            severity=ComplianceFlagSeverity.CRITICAL,
            description="Verbal consent (Section 6 acknowledgment) was not captured.",
            section="Section 6",
            remediation=(
                "The borrower must verbally acknowledge the application disclosures "
                "before the application can be submitted. Schedule a follow-up call."
            ),
        ))
    # -------------------------------------------------------------------
    # 3. Verbal consent captured but no recording URL (-15, WARNING)
    # -------------------------------------------------------------------
    elif s6 and s6.verbal_consent_given and not s6.verbal_consent_recording_url:
        score -= 15
        flags.append(ComplianceFlag(
            code="CONSENT_NO_RECORDING_URL",
            severity=ComplianceFlagSeverity.WARNING,
            description=(
                "Verbal consent was captured but no call recording URL was attached."
            ),
            section="Section 6",
            remediation=(
                "Attach the call recording URL to the consent record for audit "
                "trail purposes.  Check Vapi/Telnyx call logs for the recording."
            ),
        ))

    # -------------------------------------------------------------------
    # 4. Application channel not set to TELEPHONE (-10, WARNING)
    # -------------------------------------------------------------------
    _check_application_channel(app, flags)
    channel_ok = _application_channel_is_telephone(app)
    if not channel_ok:
        score -= 10

    # -------------------------------------------------------------------
    # 5. Rate/qualification advice given by agent (-20, CRITICAL)
    # -------------------------------------------------------------------
    forbidden_hits = _scan_for_forbidden_advice(agent_turns)
    if forbidden_hits:
        score -= 20
        flags.append(ComplianceFlag(
            code="RATE_QUALIFICATION_ADVICE",
            severity=ComplianceFlagSeverity.CRITICAL,
            description=(
                f"Agent may have given rate or qualification advice. "
                f"Detected {len(forbidden_hits)} potential violation(s): "
                + "; ".join(f'"{h}"' for h in forbidden_hits[:3])
            ),
            section="General",
            remediation=(
                "The AI agent is not a licensed MLO and must never advise on "
                "rates, qualifications, or loan product selection. Review the "
                "flagged transcript segments and retrain the prompt if needed."
            ),
        ))

    # -------------------------------------------------------------------
    # 6. SSN readback in full by agent (-15, WARNING)
    # -------------------------------------------------------------------
    ssn_violations = _scan_agent_ssn_readback(agent_turns)
    if ssn_violations:
        score -= 15
        flags.append(ComplianceFlag(
            code="SSN_FULL_READBACK",
            severity=ComplianceFlagSeverity.WARNING,
            description=(
                f"Agent read back a full SSN ({len(ssn_violations)} occurrence(s)). "
                "SSN should only be confirmed digit-by-digit or by last 4."
            ),
            section="Section 1a",
            remediation=(
                "Agent must mask SSN during readback (e.g., 'ending in 6789'). "
                "Update voice prompt to enforce masking."
            ),
        ))

    return max(0.0, score), flags


def _demographics_notice_was_read(turns: List[CallTranscriptEntry]) -> bool:
    """
    Check whether the agent read the demographics notice BEFORE asking
    Section 8 questions.  We look for at least 3 of the 5 key phrases
    from the notice in agent turns that precede any demographic question.
    """
    if not turns:
        return False

    # Find the first turn where the agent mentions ethnicity/race/sex
    # (i.e., Section 8 questions have started).
    section_8_start_idx: Optional[int] = None
    for idx, t in enumerate(turns):
        if t.speaker != "agent":
            continue
        lower = t.text.lower()
        if any(kw in lower for kw in ["ethnicity", "hispanic", "latino", "race", "sex ", "gender"]):
            section_8_start_idx = idx
            break

    if section_8_start_idx is None:
        # Section 8 was never discussed in the transcript.  The data quality
        # scorer already penalizes for missing Section 8 data, so we give the
        # benefit of the doubt here rather than double-penalizing.
        return True

    # Collect all agent text BEFORE the Section 8 start
    pre_section_8_text = " ".join(
        t.text.lower() for t in turns[:section_8_start_idx] if t.speaker == "agent"
    )

    # Count how many notice keywords appear
    matches = sum(1 for kw in _DEMOGRAPHICS_NOTICE_KEYWORDS if kw in pre_section_8_text)
    return matches >= 3


def _check_application_channel(
    app: URLAApplication,
    flags: List[ComplianceFlag],
) -> None:
    """Append a WARNING flag if any borrower's application_channel != TELEPHONE."""
    for borrower in app.borrowers:
        s8 = borrower.section_8
        if not s8:
            continue
        channel = s8.application_channel
        # ApplicationChannel values are stored as strings when use_enum_values=True
        if channel and str(channel) != ApplicationChannel.TELEPHONE.value:
            flags.append(ComplianceFlag(
                code="WRONG_APPLICATION_CHANNEL",
                severity=ComplianceFlagSeverity.WARNING,
                description=(
                    f"Borrower {borrower.borrower_id} application_channel is "
                    f"'{channel}' but this was a voice call (should be TELEPHONE)."
                ),
                section="Section 8",
                remediation="Set application_channel to TELEPHONE for phone-based intakes.",
            ))


def _application_channel_is_telephone(app: URLAApplication) -> bool:
    """Return True if all borrowers with Section 8 have channel == TELEPHONE."""
    for borrower in app.borrowers:
        s8 = borrower.section_8
        if not s8:
            continue
        if str(s8.application_channel) != ApplicationChannel.TELEPHONE.value:
            return False
    return True


def _scan_for_forbidden_advice(agent_turns: List[CallTranscriptEntry]) -> List[str]:
    """Return list of matched text snippets where agent may have given rate/qual advice."""
    hits: List[str] = []
    for turn in agent_turns:
        for pattern in _FORBIDDEN_RATE_PATTERNS:
            m = pattern.search(turn.text)
            if m:
                # Extract a window around the match for context
                start = max(0, m.start() - 20)
                end = min(len(turn.text), m.end() + 20)
                snippet = turn.text[start:end].strip()
                hits.append(snippet)
    return hits


def _scan_agent_ssn_readback(agent_turns: List[CallTranscriptEntry]) -> List[str]:
    """Return list of full SSN patterns found in agent speech."""
    hits: List[str] = []
    for turn in agent_turns:
        for m in _FULL_SSN_PATTERN.finditer(turn.text):
            # Verify it's actually 9 digits (not a phone number fragment or date)
            digits_only = re.sub(r"\D", "", m.group())
            if len(digits_only) == 9:
                hits.append(m.group())
    return hits


# =============================================================================
# DATA QUALITY (0-100, deduction model)
# =============================================================================

def _score_data_quality(app: URLAApplication) -> tuple[float, List[str]]:
    """100 points minus deductions for missing/invalid data."""
    score = 100.0
    gaps: List[str] = []

    # -------------------------------------------------------------------
    # 1. Use validate_complete() — each error is -10
    # -------------------------------------------------------------------
    validation_errors = app.validate_complete()
    for error in validation_errors:
        score -= 10
        gaps.append(error)

    # -------------------------------------------------------------------
    # 2. Email format validation
    # -------------------------------------------------------------------
    primary = app.primary_borrower()
    if primary and primary.section_1a and primary.section_1a.email:
        if not _EMAIL_RE.match(primary.section_1a.email):
            score -= 5
            gaps.append(f"Primary borrower email '{primary.section_1a.email}' appears invalid.")
    elif primary and primary.section_1a and not primary.section_1a.email:
        score -= 5
        gaps.append("Primary borrower email is missing.")

    # -------------------------------------------------------------------
    # 3. Phone format validation
    # -------------------------------------------------------------------
    if primary and primary.section_1a:
        s1a = primary.section_1a
        has_any_phone = False
        for phone_field, label in [
            (s1a.home_phone, "home phone"),
            (s1a.cell_phone, "cell phone"),
            (s1a.work_phone, "work phone"),
        ]:
            if phone_field:
                has_any_phone = True
                if not _PHONE_E164_RE.match(phone_field):
                    score -= 3
                    gaps.append(f"Primary borrower {label} '{phone_field}' is not valid E.164 format.")
        if not has_any_phone:
            score -= 5
            gaps.append("Primary borrower has no phone number on file.")

    # -------------------------------------------------------------------
    # 4. Income sources have amounts > 0
    # -------------------------------------------------------------------
    if primary and primary.section_1b and not primary.section_1b.does_not_apply:
        income_fields = [
            primary.section_1b.base_monthly,
            primary.section_1b.overtime_monthly,
            primary.section_1b.bonus_monthly,
            primary.section_1b.commission_monthly,
            primary.section_1b.military_entitlements_monthly,
            primary.section_1b.other_monthly,
        ]
        total_income = sum(v for v in income_fields if v is not None and v > 0)
        if total_income == 0:
            score -= 10
            gaps.append("Employment income listed but all income amounts are zero.")

    if primary and primary.section_1e and not primary.section_1e.does_not_apply:
        for src in primary.section_1e.sources:
            if src.monthly_amount is not None and src.monthly_amount <= 0:
                score -= 5
                gaps.append(
                    f"Other income source '{src.source_type}' has amount <= 0."
                )

    # -------------------------------------------------------------------
    # 5. Assets have values > 0
    # -------------------------------------------------------------------
    if app.section_2:
        for asset in app.section_2.assets:
            if asset.cash_or_market_value is not None and asset.cash_or_market_value <= 0:
                score -= 5
                gaps.append(
                    f"Asset '{asset.asset_type}' at "
                    f"'{asset.financial_institution or 'unknown institution'}' "
                    f"has value <= 0."
                )

    # -------------------------------------------------------------------
    # 6. Address completeness on subject property
    # -------------------------------------------------------------------
    if app.section_4 and app.section_4.section_4a:
        s4a = app.section_4.section_4a
        addr = s4a.subject_property_address
        if addr:
            missing_fields = []
            if not addr.street:
                missing_fields.append("street")
            if not addr.city:
                missing_fields.append("city")
            if not addr.state:
                missing_fields.append("state")
            if not addr.zip_code:
                missing_fields.append("zip_code")
            if missing_fields:
                score -= 5
                gaps.append(
                    f"Subject property address incomplete: missing {', '.join(missing_fields)}."
                )

    return max(0.0, score), gaps


# =============================================================================
# CONVERSATION QUALITY (0-100, deduction model)
# =============================================================================

def _score_conversation_quality(
    turns: List[CallTranscriptEntry],
) -> tuple[float, List[str]]:
    """100 points minus deductions for conversation quality issues."""
    score = 100.0
    notes: List[str] = []

    if not turns:
        notes.append("No transcript available for conversation quality scoring.")
        return 0.0, notes

    agent_turns = [t for t in turns if t.speaker == "agent"]
    if not agent_turns:
        notes.append("No agent turns found in transcript.")
        return 0.0, notes

    # -------------------------------------------------------------------
    # 1. Questions per agent turn — more than 3 in one turn: -5 each
    # -------------------------------------------------------------------
    overloaded_turns = 0
    for turn in agent_turns:
        question_count = turn.text.count("?")
        if question_count > 3:
            overloaded_turns += 1
    if overloaded_turns > 0:
        deduction = overloaded_turns * 5
        score -= deduction
        notes.append(
            f"{overloaded_turns} agent turn(s) had more than 3 questions "
            f"(machine-gunning). Deducted {deduction} points."
        )

    # -------------------------------------------------------------------
    # 2. Empathy markers — absence: -10
    # -------------------------------------------------------------------
    all_agent_text = " ".join(t.text.lower() for t in agent_turns)
    empathy_found = any(marker in all_agent_text for marker in _EMPATHY_MARKERS)
    if not empathy_found:
        score -= 10
        notes.append(
            "No empathy markers detected in agent speech (e.g., 'I understand', "
            "'take your time', 'no rush'). Deducted 10 points."
        )

    # -------------------------------------------------------------------
    # 3. Average agent response length — too long (>200 words): -5
    # -------------------------------------------------------------------
    word_counts = [len(t.text.split()) for t in agent_turns]
    avg_words = sum(word_counts) / len(word_counts) if word_counts else 0
    if avg_words > 200:
        score -= 5
        notes.append(
            f"Average agent response length is {avg_words:.0f} words (limit 200). "
            f"Responses may be too verbose for voice. Deducted 5 points."
        )

    # -------------------------------------------------------------------
    # 4. Readback/confirmation per section — missing: -5 each
    # -------------------------------------------------------------------
    confirmed_sections = _detect_confirmed_sections(agent_turns)
    # We only penalize for sections that were actually covered in the transcript
    covered_sections = _detect_covered_sections(turns)
    for section in covered_sections:
        if section not in confirmed_sections:
            score -= 5
            notes.append(
                f"No readback/confirmation detected for Section {section}. "
                f"Deducted 5 points."
            )

    # -------------------------------------------------------------------
    # 5. Call duration — under 10 min for a complete app: -10 (too rushed)
    # -------------------------------------------------------------------
    duration_minutes = _call_duration_minutes(turns)
    if duration_minutes is not None and duration_minutes > 0:
        # Only flag if the call covered a substantial portion of the application
        if len(covered_sections) >= 5 and duration_minutes < 10:
            score -= 10
            notes.append(
                f"Call duration was {duration_minutes:.1f} minutes for "
                f"{len(covered_sections)} sections. Under 10 minutes suggests "
                f"the call was too rushed. Deducted 10 points."
            )
        # Informational note about duration regardless
        if duration_minutes > 0:
            notes.append(f"Call duration: {duration_minutes:.1f} minutes.")

    return max(0.0, score), notes


def _detect_confirmed_sections(agent_turns: List[CallTranscriptEntry]) -> set[str]:
    """
    Detect which sections the agent read back and confirmed.
    Returns a set of section identifiers like {"1a", "2", "5"}.
    """
    confirmed: set[str] = set()
    # Build a per-turn index so we can associate confirmations with sections
    for turn in agent_turns:
        lower = turn.text.lower()
        has_confirmation = any(phrase in lower for phrase in _CONFIRMATION_PHRASES)
        if not has_confirmation:
            continue
        # Try to identify which section this confirmation belongs to
        for section in _ALL_SECTIONS:
            # Check for explicit section references
            if f"section {section}" in lower:
                confirmed.add(section)
            # Check for contextual clues per section
            elif section == "1a" and any(kw in lower for kw in ["name", "address", "date of birth", "social security", "ssn"]):
                confirmed.add(section)
            elif section == "1b" and any(kw in lower for kw in ["employment", "employer", "income", "salary"]):
                confirmed.add(section)
            elif section == "2" and any(kw in lower for kw in ["asset", "liabilit", "bank account", "checking", "savings"]):
                confirmed.add(section)
            elif section == "3" and any(kw in lower for kw in ["real estate", "property you own", "properties"]):
                confirmed.add(section)
            elif section == "4" and any(kw in lower for kw in ["loan amount", "property", "purchase", "refinanc"]):
                confirmed.add(section)
            elif section == "5" and any(kw in lower for kw in ["declaration", "judgment", "bankruptcy", "foreclosure"]):
                confirmed.add(section)
            elif section == "6" and any(kw in lower for kw in ["consent", "acknowledge", "agree"]):
                confirmed.add(section)
            elif section == "7" and any(kw in lower for kw in ["military", "service", "veteran", "active duty"]):
                confirmed.add(section)
            elif section == "8" and any(kw in lower for kw in ["demographic", "ethnicity", "race"]):
                confirmed.add(section)
    return confirmed


def _detect_covered_sections(turns: List[CallTranscriptEntry]) -> set[str]:
    """
    Detect which URLA sections were substantively discussed during the call.
    Returns a set of section identifiers.
    """
    covered: set[str] = set()
    all_text = " ".join(t.text.lower() for t in turns)

    section_keywords: Dict[str, List[str]] = {
        "1a": ["first name", "last name", "social security", "ssn", "date of birth", "mailing address", "marital status"],
        "1b": ["employer", "employment", "where do you work", "job title", "salary", "base pay", "income"],
        "2": ["bank account", "checking", "savings", "assets", "liabilities", "credit card", "debt"],
        "3": ["own any", "real estate", "other properties", "rental property"],
        "4": ["loan amount", "property address", "purchase price", "home you're buying", "refinanc"],
        "5": ["declaration", "bankruptcy", "foreclosure", "judgment", "delinquent", "lawsuit"],
        "6": ["consent", "acknowledge", "verbal agreement", "do you agree"],
        "7": ["military", "served", "veteran", "active duty", "national guard"],
        "8": ["ethnicity", "race", "hispanic", "demographic", "gender", "sex "],
    }

    for section, keywords in section_keywords.items():
        if any(kw in all_text for kw in keywords):
            covered.add(section)

    return covered


def _call_duration_minutes(turns: List[CallTranscriptEntry]) -> Optional[float]:
    """
    Calculate call duration from first to last transcript timestamp.
    Returns None if timestamps are unavailable or identical.
    """
    if len(turns) < 2:
        return None

    first_ts = turns[0].timestamp
    last_ts = turns[-1].timestamp

    if first_ts is None or last_ts is None:
        return None

    delta = last_ts - first_ts
    total_seconds = delta.total_seconds()

    if total_seconds <= 0:
        return None

    return total_seconds / 60.0
