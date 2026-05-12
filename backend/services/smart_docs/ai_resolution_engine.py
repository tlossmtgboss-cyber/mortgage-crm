"""
AI Resolution Engine for Application Completion Orchestrator (ACO)

Determines HOW to resolve each missing item on a mortgage application --
whether by SMS text conversation, manual data entry, processor-assistant (PA)
call, or borrower portal upload.  Also manages the AI-driven SMS conversation
flow with borrowers, including response parsing, auto-fill with audit trail,
escalation logic, and availability collection for scheduling PA calls.

Resolution methods:
    TEXT         - Quick question/answer via SMS  (1-2 message exchange)
    PORTAL       - Borrower uploads a document through the portal
    CALL         - Schedule a PA call for complex/interdependent items
    MANUAL_ENTRY - Internal staff fills from existing data sources

Key design decisions:
    - Every auto-fill is audit-logged with old_value, new_value, confidence, source
    - Sensitive fields (SSN, income, declarations) are NEVER auto-filled
    - Escalation triggers when borrower sentiment is frustrated for 2+ messages
    - TCPA consent is checked before any SMS outreach
    - All AI calls go through the resilient_ai_call wrapper (retry + circuit breaker)

Usage:
    from services.smart_docs.ai_resolution_engine import AIResolutionEngine

    engine = AIResolutionEngine(db=db, org_id="42", user_id="7")

    # Route items to resolution channels
    plan = await engine.route_missing_items(review_id=1, items=[...])

    # Generate intro SMS sequence
    msgs = await engine.generate_intro_sequence(
        loan_id="100", borrower_name="Jane",
        lo_name="Sarah Miller", company_name="The Tim Loss Team",
    )

    # Parse a borrower's free-text reply
    parsed = await engine.parse_borrower_response(
        question_context={...}, response_text="Yeah about 3500 a month"
    )
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

from database.models.app_completion import (
    MissingItem,
    BorrowerCommunicationLog,
    AppointmentCoordination,
    MissingItemStatus,
    ResolutionMethod,
    CommChannel,
    SenderType,
    MessageIntent,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional AI client
# ---------------------------------------------------------------------------
try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

from services.smart_docs.ai_resilience import resilient_ai_call


# =============================================================================
# CONSTANTS & CONFIGURATION
# =============================================================================

_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

# ---------------------------------------------------------------------------
# Text-resolvable criteria: items that can be collected via 1-2 SMS exchanges
# ---------------------------------------------------------------------------
TEXT_RESOLVABLE_CRITERIA = {
    "max_answer_length": 100,
    "max_messages_needed": 2,
    "maps_to_single_field": True,
    "no_regulatory_risk": True,
    "item_types": ["FIELD"],
    "excluded_sections": [
        "declarations",
        "government_monitoring",
        "acknowledgements",
    ],
}

# ---------------------------------------------------------------------------
# Call-required criteria: conditions that mandate a PA call
# ---------------------------------------------------------------------------
CALL_REQUIRED_CRITERIA = {
    "unresolved_count_threshold": 5,
    "interdependent_items": True,
    "exception_items": True,
    "complexity_indicators": [
        "self_employment",
        "multiple_entities",
        "reo_portfolio",
        "recent_job_change",
        "income_mismatch",
        "trust_vesting",
        "citizenship_ambiguity",
        "manual_underwrite",
        "non_occupant_co_borrower",
        "irrevocable_trust",
        "power_of_attorney",
    ],
}

# ---------------------------------------------------------------------------
# Field-path patterns that MUST NOT be auto-filled regardless of confidence
# ---------------------------------------------------------------------------
NEVER_AUTO_FILL_PATTERNS: Set[str] = {
    "borrower_income",
    "co_borrower_income",
    "borrower_ssn",
    "co_borrower_ssn",
    "credit_score",
    "amount",
    "rate",
    "monthly_income",
    "annual_income",
    "base_income",
    "overtime_income",
    "bonus_income",
    "commission_income",
    "self_employment_income",
}

# Prefix patterns (declarations.*, signatures.*)
NEVER_AUTO_FILL_PREFIXES: Tuple[str, ...] = (
    "declarations.",
    "signatures.",
    "government_monitoring.",
    "acknowledgements.",
    "hmda.",
)

# ---------------------------------------------------------------------------
# Confidence thresholds
# ---------------------------------------------------------------------------
CONFIDENCE_AUTO_FILL = 0.90
CONFIDENCE_CONFIRM = 0.70
CONFIDENCE_ESCALATE = 0.50

# ---------------------------------------------------------------------------
# Escalation thresholds
# ---------------------------------------------------------------------------
MAX_CONSECUTIVE_FRUSTRATED = 2
MAX_UNANSWERED_PROMPTS = 3
MAX_REMAINING_AFTER_TEXT = 3
MAX_LOW_CONFIDENCE_STREAK = 3

# ---------------------------------------------------------------------------
# Section-to-question mapping for common missing fields
# ---------------------------------------------------------------------------
FIELD_QUESTION_TEMPLATES: Dict[str, Dict[str, str]] = {
    # --- Borrower Identity / Demographics ---
    "borrower_suffix": {
        "question": "Do you have a suffix after your name, like Jr., Sr., or III?",
        "field_hint": "name suffix",
    },
    "borrower_email": {
        "question": "What's the best email address for you?",
        "field_hint": "email address",
    },
    "borrower_phone_home": {
        "question": "Do you have a home phone number, or is your cell the best one to use?",
        "field_hint": "home phone",
    },
    "borrower_marital_status": {
        "question": "What is your current marital status? (married, unmarried, or separated)",
        "field_hint": "marital status",
    },
    "borrower_dependents_count": {
        "question": "How many dependents do you have?",
        "field_hint": "number of dependents",
    },
    "borrower_dependents_ages": {
        "question": "What are the ages of your dependents?",
        "field_hint": "dependent ages",
    },
    "borrower_years_of_school": {
        "question": "How many years of school have you completed? (e.g. 12 for high school, 16 for bachelor's)",
        "field_hint": "years of schooling",
    },
    "borrower_citizenship_status": {
        "question": "Are you a US citizen, permanent resident, or on a visa?",
        "field_hint": "citizenship status",
    },

    # --- Current Address ---
    "current_address_years": {
        "question": "How long have you lived at your current address?",
        "field_hint": "years at address",
    },
    "current_address_months": {
        "question": "And how many months, in addition to years, at your current address?",
        "field_hint": "months at address",
    },
    "housing_status": {
        "question": "At your current address, do you own, rent, or live rent-free?",
        "field_hint": "own/rent/rent-free",
    },
    "monthly_rent": {
        "question": "What is your current monthly rent payment?",
        "field_hint": "monthly rent amount",
    },

    # --- Previous Address (if < 2 years at current) ---
    "previous_address": {
        "question": "Since you've been at your current address less than 2 years, what was your previous address?",
        "field_hint": "previous street address",
    },
    "previous_address_years": {
        "question": "How long did you live at your previous address?",
        "field_hint": "years at previous address",
    },

    # --- Employment ---
    "employer_name": {
        "question": "What is the name of your current employer?",
        "field_hint": "employer name",
    },
    "employer_address": {
        "question": "What is your employer's address?",
        "field_hint": "employer address",
    },
    "employer_phone": {
        "question": "What is your employer's phone number?",
        "field_hint": "employer phone",
    },
    "job_title": {
        "question": "What is your job title or position?",
        "field_hint": "job title",
    },
    "employment_start_date": {
        "question": "When did you start at your current job? (month/year is fine)",
        "field_hint": "employment start date",
    },
    "years_in_profession": {
        "question": "How many years have you been in your current line of work?",
        "field_hint": "years in profession",
    },

    # --- Property ---
    "property_type": {
        "question": "What type of property is this? (single family, condo, townhouse, 2-4 unit, or manufactured home)",
        "field_hint": "property type",
    },
    "occupancy_type": {
        "question": "Will this be your primary residence, a second home, or an investment property?",
        "field_hint": "occupancy type",
    },
    "property_use": {
        "question": "Will this property be purely residential, or is any part used for a business?",
        "field_hint": "property use",
    },
    "number_of_units": {
        "question": "How many units does the property have?",
        "field_hint": "number of units",
    },
    "year_built": {
        "question": "Do you know what year the property was built?",
        "field_hint": "year built",
    },

    # --- Loan Details ---
    "loan_purpose": {
        "question": "Is this a purchase, refinance, or cash-out refinance?",
        "field_hint": "loan purpose",
    },
    "down_payment_source": {
        "question": "Where is your down payment coming from? (savings, gift, sale of another property, etc.)",
        "field_hint": "down payment source",
    },

    # --- Real Estate Owned ---
    "reo_property_address": {
        "question": "What is the address of the other property you own?",
        "field_hint": "REO property address",
    },
    "reo_property_status": {
        "question": "For your other property, will you be keeping it, selling it, or renting it out?",
        "field_hint": "REO property status",
    },
    "reo_monthly_payment": {
        "question": "What is the monthly mortgage payment on your other property?",
        "field_hint": "REO monthly payment",
    },

    # --- Co-Borrower ---
    "co_borrower_email": {
        "question": "What is the best email address for your co-borrower?",
        "field_hint": "co-borrower email",
    },
    "co_borrower_phone": {
        "question": "What is the best phone number for your co-borrower?",
        "field_hint": "co-borrower phone number",
    },
    "co_borrower_employer": {
        "question": "Who is your co-borrower's current employer?",
        "field_hint": "co-borrower employer",
    },
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ResolutionPlan:
    """Complete resolution plan for a set of missing items."""
    review_id: int
    total_items: int
    text_items: List[Dict[str, Any]] = field(default_factory=list)
    portal_items: List[Dict[str, Any]] = field(default_factory=list)
    call_items: List[Dict[str, Any]] = field(default_factory=list)
    manual_items: List[Dict[str, Any]] = field(default_factory=list)
    call_recommended: bool = False
    call_reason: str = ""
    complexity_flags: List[str] = field(default_factory=list)
    estimated_text_minutes: float = 0.0
    estimated_call_minutes: float = 0.0


@dataclass
class ParsedResponse:
    """Structured result from parsing a borrower's free-text SMS reply."""
    parsed_value: str
    confidence: float
    field_path: str
    needs_confirmation: bool
    follow_up_needed: bool
    follow_up_question: str
    sentiment: str  # POSITIVE / NEUTRAL / NEGATIVE / FRUSTRATED
    escalate: bool
    raw_response: str = ""
    parsing_notes: str = ""


@dataclass
class AutoFillResult:
    """Result of attempting to auto-fill a field."""
    filled: bool
    field_path: str
    old_value: Optional[str]
    new_value: str
    confidence: float
    audit_id: str
    requires_review: bool = False
    blocked_reason: Optional[str] = None


@dataclass
class EscalationCheck:
    """Result of checking whether an SMS conversation should escalate."""
    should_escalate: bool
    reason: str
    recommended_action: str  # "continue_text" | "schedule_call" | "escalate_to_lo"
    remaining_text_items: int = 0
    frustrated_count: int = 0
    unanswered_count: int = 0


@dataclass
class TimeWindow:
    """A parsed availability window from borrower's response."""
    date: date
    start_time: time
    end_time: time
    raw_text: str
    confidence: float


# =============================================================================
# AI RESOLUTION ENGINE
# =============================================================================

class AIResolutionEngine:
    """
    Core intelligence for the Application Completion Orchestrator.

    Decides how to resolve each missing item, manages the SMS conversation
    flow, parses borrower responses with AI, handles escalation, and fills
    fields with a complete audit trail.
    """

    NEVER_AUTO_FILL_FIELDS = NEVER_AUTO_FILL_PATTERNS
    CONFIDENCE_THRESHOLDS = {
        "auto_fill": CONFIDENCE_AUTO_FILL,
        "confirm_with_borrower": CONFIDENCE_CONFIRM,
        "escalate": CONFIDENCE_ESCALATE,
    }

    def __init__(self, db: Session, org_id: str, user_id: str = None):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self._ai_client = None

    # ------------------------------------------------------------------
    # AI client (lazy init)
    # ------------------------------------------------------------------

    def _get_ai_client(self):
        """Lazily initialize the Anthropic client."""
        if self._ai_client is None and HAS_ANTHROPIC:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                self._ai_client = Anthropic(api_key=api_key)
        return self._ai_client

    # =================================================================
    # 1. RESOLUTION ROUTER
    # =================================================================

    async def route_missing_items(
        self,
        review_id: int,
        items: List[Dict[str, Any]],
    ) -> ResolutionPlan:
        """
        Route each missing item to the appropriate resolution method.

        Categories:
            TEXT         - Simple field fill via SMS (short answer, single field)
            PORTAL       - Document upload required
            CALL         - Complex / interdependent / exception items
            MANUAL_ENTRY - Fillable from existing data by staff

        Also detects complexity flags that mandate a PA call.
        """
        plan = ResolutionPlan(review_id=review_id, total_items=len(items))

        # --- Step 1: Detect global complexity flags ---
        all_tags = set()
        for item in items:
            tags = item.get("complexity_tags") or []
            all_tags.update(tags)

        for indicator in CALL_REQUIRED_CRITERIA["complexity_indicators"]:
            if indicator in all_tags:
                plan.complexity_flags.append(indicator)

        # --- Step 2: Classify each item ---
        for item in items:
            item_type = item.get("item_type", "FIELD")
            section = item.get("section", "")
            field_path = item.get("field_path", "")
            description = item.get("description", "")
            resolution_method = self._classify_single_item(
                item_type=item_type,
                section=section,
                field_path=field_path,
                description=description,
                complexity_tags=item.get("complexity_tags") or [],
            )

            routed = {
                "item_id": item.get("id"),
                "field_path": field_path,
                "section": section,
                "description": description,
                "item_type": item_type,
                "resolution_method": resolution_method,
                "priority": item.get("priority", "NORMAL"),
            }

            if resolution_method == "TEXT":
                plan.text_items.append(routed)
            elif resolution_method == "PORTAL":
                plan.portal_items.append(routed)
            elif resolution_method == "CALL":
                plan.call_items.append(routed)
            else:
                plan.manual_items.append(routed)

        # --- Step 3: Evaluate call recommendation ---
        remaining_non_text = len(plan.call_items) + len(plan.portal_items)
        if (
            remaining_non_text > CALL_REQUIRED_CRITERIA["unresolved_count_threshold"]
            or plan.complexity_flags
            or any(i.get("item_type") == "EXCEPTION" for i in items)
        ):
            plan.call_recommended = True
            reasons = []
            if plan.complexity_flags:
                reasons.append(
                    f"complexity flags: {', '.join(plan.complexity_flags)}"
                )
            if remaining_non_text > CALL_REQUIRED_CRITERIA["unresolved_count_threshold"]:
                reasons.append(
                    f"{remaining_non_text} items best handled on a call"
                )
            if any(i.get("item_type") == "EXCEPTION" for i in items):
                reasons.append("exception items require verbal discussion")
            plan.call_reason = "; ".join(reasons)

        # --- Step 4: Time estimates ---
        plan.estimated_text_minutes = len(plan.text_items) * 1.5
        plan.estimated_call_minutes = max(
            15.0,
            (len(plan.call_items) + len(plan.portal_items)) * 3.0,
        )

        logger.info(
            "Resolution plan for review %s: %d text, %d portal, %d call, %d manual "
            "(call_recommended=%s)",
            review_id,
            len(plan.text_items),
            len(plan.portal_items),
            len(plan.call_items),
            len(plan.manual_items),
            plan.call_recommended,
        )

        return plan

    def _classify_single_item(
        self,
        item_type: str,
        section: str,
        field_path: str,
        description: str,
        complexity_tags: List[str],
    ) -> str:
        """
        Classify a single missing item into a resolution method.

        Returns one of: "TEXT", "PORTAL", "CALL", "MANUAL_ENTRY".
        """
        # Documents always need portal upload
        if item_type in ("DOCUMENT", "DOC"):
            return "PORTAL"

        # Exceptions and stipulations always require a call
        if item_type in ("EXCEPTION", "STIPULATION", "CONDITION"):
            return "CALL"

        # Excluded sections cannot be collected by text
        section_lower = (section or "").lower()
        for excluded in TEXT_RESOLVABLE_CRITERIA["excluded_sections"]:
            if excluded in section_lower:
                return "CALL"

        # Complexity tags mandate a call
        for tag in complexity_tags:
            if tag in CALL_REQUIRED_CRITERIA["complexity_indicators"]:
                return "CALL"

        # Simple FIELD type with a known template -> text resolvable
        if item_type == "FIELD":
            field_key = field_path.split(".")[-1] if field_path else ""
            if field_key in FIELD_QUESTION_TEMPLATES:
                return "TEXT"
            # Even without a template, short factual fields are text-resolvable
            if self._is_short_factual_field(field_path, description):
                return "TEXT"

        # Default: items that don't clearly fit text or portal go to call
        return "CALL"

    def _is_short_factual_field(self, field_path: str, description: str) -> bool:
        """Heuristic: can this field be answered with a short factual response?"""
        short_field_patterns = [
            r"phone", r"email", r"name", r"address", r"date",
            r"years?", r"months?", r"count", r"number",
            r"type", r"status", r"title",
        ]
        combined = f"{field_path} {description}".lower()
        for pattern in short_field_patterns:
            if re.search(pattern, combined):
                # But not if it smells like income, SSN, or declarations
                if self._is_protected_field(field_path):
                    return False
                return True
        return False

    def _is_protected_field(self, field_path: str) -> bool:
        """Check if a field path matches protected patterns."""
        fp_lower = (field_path or "").lower()
        if fp_lower in NEVER_AUTO_FILL_PATTERNS:
            return True
        for prefix in NEVER_AUTO_FILL_PREFIXES:
            if fp_lower.startswith(prefix):
                return True
        return False

    # =================================================================
    # 2. SMS CONVERSATION MANAGER
    # =================================================================

    async def generate_intro_sequence(
        self,
        loan_id: str,
        borrower_name: str,
        lo_name: str,
        company_name: str,
        agent_name: str = "Alex",
    ) -> List[Dict[str, Any]]:
        """
        Generate the introductory SMS sequence (4 messages).

        Phase 1 establishes trust: introduce the PA, deliver a vCard,
        and set expectations for the text-based Q&A.

        Returns a list of message dicts with 'content', 'delay_seconds',
        'intent', and 'expects_response' fields.
        """
        first_name = (borrower_name or "").split()[0] if borrower_name else "there"

        messages = [
            {
                "sequence": 1,
                "content": (
                    f"Hi {first_name}, this is {agent_name} with {lo_name}'s "
                    f"team at {company_name}. I'm helping review your application "
                    f"and next steps so we can keep everything moving smoothly."
                ),
                "delay_seconds": 0,
                "intent": MessageIntent.INTRODUCTION.value
                    if hasattr(MessageIntent, "INTRODUCTION")
                    else "introduction",
                "expects_response": False,
            },
            {
                "sequence": 2,
                "content": (
                    "I'm sending over our contact card now. Please save it to "
                    "your phone and reply SAVED once it's done. That way anytime "
                    "our team reaches out, you'll know it's us."
                ),
                "delay_seconds": 8,
                "intent": MessageIntent.VCARD_DELIVERY.value
                    if hasattr(MessageIntent, "VCARD_DELIVERY")
                    else "vcard_delivery",
                "expects_response": True,
                "expected_response_pattern": r"(?i)\bsaved?\b",
            },
            {
                "sequence": 3,
                "content": "[VCARD_ATTACHMENT]",
                "delay_seconds": 2,
                "intent": "vcard_attachment",
                "expects_response": False,
                "is_media": True,
            },
            {
                "sequence": 4,
                "content": (
                    f"Perfect \u2014 thank you, {first_name}. I reviewed your application "
                    f"and there are just a few items we need to finish up. Some we can "
                    f"handle right here by text, and if needed I can help coordinate "
                    f"a quick call with {lo_name}'s team."
                ),
                "delay_seconds": 0,
                "intent": MessageIntent.TRANSITION_TO_QUESTIONS.value
                    if hasattr(MessageIntent, "TRANSITION_TO_QUESTIONS")
                    else "transition_to_questions",
                "expects_response": False,
                "trigger_on": "borrower_replied_saved",
            },
        ]

        logger.info(
            "Generated intro sequence for loan %s, borrower '%s'",
            loan_id, first_name,
        )
        return messages

    async def generate_question_message(
        self,
        item: Dict[str, Any],
        borrower_name: str = "",
    ) -> str:
        """
        Generate a friendly, conversational SMS question for a missing item.

        Uses the FIELD_QUESTION_TEMPLATES lookup first. Falls back to AI
        generation for fields without a template.
        """
        field_path = item.get("field_path", "")
        field_key = field_path.split(".")[-1] if field_path else ""
        description = item.get("description", "")
        first_name = (borrower_name or "").split()[0] if borrower_name else ""

        # 1. Try template lookup
        template = FIELD_QUESTION_TEMPLATES.get(field_key)
        if template:
            question = template["question"]
            if first_name and not question.lower().startswith(first_name.lower()):
                question = f"Quick question \u2014 {question}"
            else:
                question = f"Quick question \u2014 {question}"
            return question

        # 2. AI-generated question for non-templated fields
        client = self._get_ai_client()
        if client is None:
            # Fallback: generic question
            return (
                f"Quick question \u2014 we're missing the {description or field_key} "
                f"on your application. Could you provide that for us?"
            )

        prompt = (
            f"You are a friendly mortgage processor assistant texting a borrower. "
            f"Generate a SHORT, conversational SMS question (under 160 characters) "
            f"to collect this missing application field:\n\n"
            f"Field: {field_path}\n"
            f"Description: {description}\n"
            f"Borrower first name: {first_name or 'the borrower'}\n\n"
            f"Rules:\n"
            f"- Sound natural and human, not robotic\n"
            f"- Keep it under 160 characters\n"
            f"- Don't mention 'application' or 'form' \u2014 just ask the question\n"
            f"- Start with 'Quick question \u2014' or similar casual opener\n"
            f"- No emojis\n\n"
            f"Respond with ONLY the message text, nothing else."
        )

        response = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": prompt}],
            model=_ANTHROPIC_MODEL,
            max_tokens=200,
            operation_name="generate_question_message",
            org_id=self.org_id,
        )

        if response and response.content:
            generated = response.content[0].text.strip().strip('"').strip("'")
            # Ensure it's not too long for SMS
            if len(generated) <= 300:
                return generated

        # Final fallback
        return (
            f"Quick question \u2014 we're missing the {description or field_key} "
            f"on your application. Could you provide that?"
        )

    # =================================================================
    # 3. RESPONSE PARSER
    # =================================================================

    async def parse_borrower_response(
        self,
        question_context: Dict[str, Any],
        response_text: str,
    ) -> ParsedResponse:
        """
        Use AI to extract structured data from a borrower's free-text SMS reply.

        The question_context should include:
            - field_path: where to store the answer
            - field_hint: what kind of data we're looking for
            - question_text: the question that was asked
            - expected_format: optional format hint (e.g. "date", "number", "address")
        """
        field_path = question_context.get("field_path", "")
        field_hint = question_context.get("field_hint", "")
        question_text = question_context.get("question_text", "")
        expected_format = question_context.get("expected_format", "text")

        # Handle obvious non-answers first
        response_lower = response_text.strip().lower()

        # Check for call-me / human-request patterns
        call_patterns = [
            r"\bcall\s+me\b", r"\btalk\s+to\s+(someone|a\s+person|human)\b",
            r"\bprefer\s+(a\s+)?call\b", r"\bjust\s+call\b",
            r"\bcan\s+(someone|you)\s+call\b", r"\bphone\s+me\b",
        ]
        for pattern in call_patterns:
            if re.search(pattern, response_lower):
                return ParsedResponse(
                    parsed_value="",
                    confidence=0.0,
                    field_path=field_path,
                    needs_confirmation=False,
                    follow_up_needed=False,
                    follow_up_question="",
                    sentiment="NEUTRAL",
                    escalate=True,
                    raw_response=response_text,
                    parsing_notes="Borrower requested a phone call",
                )

        # Check for stop / opt-out signals
        stop_patterns = [r"\bstop\b", r"\bopt\s*out\b", r"\bunsubscribe\b"]
        for pattern in stop_patterns:
            if re.search(pattern, response_lower):
                return ParsedResponse(
                    parsed_value="",
                    confidence=0.0,
                    field_path=field_path,
                    needs_confirmation=False,
                    follow_up_needed=False,
                    follow_up_question="",
                    sentiment="NEGATIVE",
                    escalate=True,
                    raw_response=response_text,
                    parsing_notes="Borrower opted out of SMS communication",
                )

        # Use AI for parsing
        client = self._get_ai_client()
        if client is None:
            return self._rule_based_parse(
                question_context, response_text, field_path
            )

        prompt = (
            f"You are parsing a borrower's SMS reply to extract mortgage application data.\n\n"
            f"QUESTION ASKED: {question_text}\n"
            f"FIELD WE NEED: {field_path} ({field_hint})\n"
            f"EXPECTED FORMAT: {expected_format}\n"
            f"BORROWER'S REPLY: {response_text}\n\n"
            f"Extract the answer and respond in STRICT JSON:\n"
            f'{{\n'
            f'  "parsed_value": "the extracted/normalized answer",\n'
            f'  "confidence": 0.0 to 1.0,\n'
            f'  "needs_confirmation": true if the answer is ambiguous,\n'
            f'  "follow_up_needed": true if more info is needed,\n'
            f'  "follow_up_question": "question to ask if follow_up_needed, else empty string",\n'
            f'  "sentiment": "POSITIVE" or "NEUTRAL" or "NEGATIVE" or "FRUSTRATED",\n'
            f'  "parsing_notes": "brief note on what was extracted and any concerns"\n'
            f'}}\n\n'
            f"Rules:\n"
            f"- Normalize values (e.g. 'three thousand five hundred' -> '3500')\n"
            f"- For dates, normalize to MM/YYYY or MM/DD/YYYY\n"
            f"- For phone numbers, normalize to digits only\n"
            f"- confidence 0.9+ means clear, unambiguous answer\n"
            f"- confidence 0.7-0.89 means likely correct but could confirm\n"
            f"- confidence below 0.7 means uncertain\n"
            f"- Set sentiment based on tone (short/curt = NEUTRAL, frustrated = FRUSTRATED)\n"
            f"- If the reply is completely unrelated, set confidence to 0.0\n"
            f"- Respond with ONLY the JSON, no markdown formatting"
        )

        response = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": prompt}],
            model=_ANTHROPIC_MODEL,
            max_tokens=500,
            operation_name="parse_borrower_response",
            org_id=self.org_id,
        )

        if response and response.content:
            raw_json = response.content[0].text.strip()
            try:
                # Strip markdown code fences if present
                if raw_json.startswith("```"):
                    raw_json = re.sub(
                        r"^```(?:json)?\s*", "", raw_json
                    )
                    raw_json = re.sub(r"\s*```$", "", raw_json)

                parsed = json.loads(raw_json)

                return ParsedResponse(
                    parsed_value=str(parsed.get("parsed_value", "")),
                    confidence=float(parsed.get("confidence", 0.0)),
                    field_path=field_path,
                    needs_confirmation=bool(parsed.get("needs_confirmation", False)),
                    follow_up_needed=bool(parsed.get("follow_up_needed", False)),
                    follow_up_question=str(parsed.get("follow_up_question", "")),
                    sentiment=str(parsed.get("sentiment", "NEUTRAL")).upper(),
                    escalate=False,
                    raw_response=response_text,
                    parsing_notes=str(parsed.get("parsing_notes", "")),
                )
            except (json.JSONDecodeError, ValueError, KeyError) as exc:
                logger.warning(
                    "Failed to parse AI response as JSON: %s (raw: %s)",
                    exc, raw_json[:200],
                )

        # Fallback to rule-based parsing
        return self._rule_based_parse(question_context, response_text, field_path)

    def _rule_based_parse(
        self,
        question_context: Dict[str, Any],
        response_text: str,
        field_path: str,
    ) -> ParsedResponse:
        """Fallback parser when AI is unavailable."""
        response_stripped = response_text.strip()
        expected_format = question_context.get("expected_format", "text")

        confidence = 0.60  # default for rule-based
        parsed_value = response_stripped
        needs_confirmation = True

        # Simple numeric extraction
        if expected_format in ("number", "count", "years", "months"):
            numbers = re.findall(r"\d+\.?\d*", response_stripped)
            if numbers:
                parsed_value = numbers[0]
                confidence = 0.75

        # Date extraction
        elif expected_format == "date":
            date_match = re.search(
                r"(\d{1,2})[/\-.](\d{1,2})?[/\-.]?(\d{2,4})?",
                response_stripped,
            )
            if date_match:
                parsed_value = date_match.group(0)
                confidence = 0.70

        # Phone extraction
        elif expected_format == "phone":
            digits = re.sub(r"\D", "", response_stripped)
            if len(digits) >= 10:
                parsed_value = digits[-10:]
                confidence = 0.80

        # Email extraction
        elif expected_format == "email":
            email_match = re.search(
                r"[\w.+-]+@[\w-]+\.[\w.-]+", response_stripped
            )
            if email_match:
                parsed_value = email_match.group(0).lower()
                confidence = 0.85

        # Yes/no boolean
        elif expected_format == "boolean":
            if re.search(r"\b(yes|yeah|yep|yup|correct|right)\b", response_stripped.lower()):
                parsed_value = "Yes"
                confidence = 0.85
            elif re.search(r"\b(no|nope|nah|negative)\b", response_stripped.lower()):
                parsed_value = "No"
                confidence = 0.85

        # Detect frustration signals
        sentiment = "NEUTRAL"
        frustration_signals = [
            r"\bwhy\s+do\s+you\s+need\b", r"\bthis\s+is\s+(ridiculous|stupid)\b",
            r"\balready\s+(sent|gave|provided)\b", r"\bhow\s+many\s+more\b",
            r"\b(ugh|smh|wtf)\b", r"[!?]{3,}",
        ]
        for pattern in frustration_signals:
            if re.search(pattern, response_stripped, re.IGNORECASE):
                sentiment = "FRUSTRATED"
                break

        return ParsedResponse(
            parsed_value=parsed_value,
            confidence=confidence,
            field_path=field_path,
            needs_confirmation=needs_confirmation,
            follow_up_needed=confidence < CONFIDENCE_CONFIRM,
            follow_up_question=(
                "I want to make sure I have that right. Could you clarify?"
                if confidence < CONFIDENCE_CONFIRM
                else ""
            ),
            sentiment=sentiment,
            escalate=False,
            raw_response=response_text,
            parsing_notes="Parsed with rule-based fallback (AI unavailable)",
        )

    # =================================================================
    # 4. ESCALATION LOGIC
    # =================================================================

    async def check_escalation_needed(
        self,
        loan_id: str,
        conversation_history: List[Dict[str, Any]],
        remaining_text_items: int = 0,
    ) -> EscalationCheck:
        """
        Evaluate whether the SMS conversation should escalate to a PA call.

        Escalation triggers:
            1. Borrower explicitly requests a call
            2. Sentiment is FRUSTRATED for 2+ consecutive messages
            3. Borrower stops responding after 2-3 prompts
            4. AI confidence drops below threshold consistently
            5. More than 3 items remain after text resolution attempt
        """
        frustrated_streak = 0
        unanswered_count = 0
        low_confidence_streak = 0
        borrower_requested_call = False

        # Walk conversation history in chronological order
        for entry in conversation_history:
            sender = entry.get("sender", "")
            sentiment = entry.get("sentiment", "NEUTRAL")
            confidence = entry.get("confidence")
            escalate_flag = entry.get("escalate", False)

            if sender == "borrower":
                unanswered_count = 0  # they responded

                if escalate_flag:
                    borrower_requested_call = True

                if sentiment == "FRUSTRATED":
                    frustrated_streak += 1
                else:
                    frustrated_streak = 0

                if confidence is not None and confidence < CONFIDENCE_ESCALATE:
                    low_confidence_streak += 1
                else:
                    low_confidence_streak = 0

            elif sender == "system":
                # Count consecutive unanswered prompts
                if entry.get("expects_response", False):
                    unanswered_count += 1

        # --- Evaluate triggers ---

        # Trigger 1: Explicit call request
        if borrower_requested_call:
            return EscalationCheck(
                should_escalate=True,
                reason="Borrower requested a phone call",
                recommended_action="schedule_call",
                remaining_text_items=remaining_text_items,
                frustrated_count=frustrated_streak,
                unanswered_count=unanswered_count,
            )

        # Trigger 2: Frustrated sentiment streak
        if frustrated_streak >= MAX_CONSECUTIVE_FRUSTRATED:
            return EscalationCheck(
                should_escalate=True,
                reason=(
                    f"Borrower frustrated for {frustrated_streak} consecutive messages"
                ),
                recommended_action="schedule_call",
                remaining_text_items=remaining_text_items,
                frustrated_count=frustrated_streak,
                unanswered_count=unanswered_count,
            )

        # Trigger 3: Unresponsive borrower
        if unanswered_count >= MAX_UNANSWERED_PROMPTS:
            return EscalationCheck(
                should_escalate=True,
                reason=(
                    f"Borrower has not responded to {unanswered_count} consecutive prompts"
                ),
                recommended_action="escalate_to_lo",
                remaining_text_items=remaining_text_items,
                frustrated_count=frustrated_streak,
                unanswered_count=unanswered_count,
            )

        # Trigger 4: Consistent low confidence
        if low_confidence_streak >= MAX_LOW_CONFIDENCE_STREAK:
            return EscalationCheck(
                should_escalate=True,
                reason=(
                    f"AI parsing confidence below threshold for "
                    f"{low_confidence_streak} consecutive responses"
                ),
                recommended_action="schedule_call",
                remaining_text_items=remaining_text_items,
                frustrated_count=frustrated_streak,
                unanswered_count=unanswered_count,
            )

        # Trigger 5: Too many items remaining
        if remaining_text_items > MAX_REMAINING_AFTER_TEXT:
            return EscalationCheck(
                should_escalate=True,
                reason=(
                    f"{remaining_text_items} items still unresolved after text attempts"
                ),
                recommended_action="schedule_call",
                remaining_text_items=remaining_text_items,
                frustrated_count=frustrated_streak,
                unanswered_count=unanswered_count,
            )

        # No escalation needed
        return EscalationCheck(
            should_escalate=False,
            reason="Conversation progressing normally",
            recommended_action="continue_text",
            remaining_text_items=remaining_text_items,
            frustrated_count=frustrated_streak,
            unanswered_count=unanswered_count,
        )

    # =================================================================
    # 5. AVAILABILITY COLLECTION
    # =================================================================

    async def generate_availability_request(
        self,
        borrower_name: str,
        call_items_count: int = 0,
    ) -> str:
        """
        Generate the SMS message asking the borrower for availability
        to schedule a PA call.
        """
        first_name = (borrower_name or "").split()[0] if borrower_name else "there"

        if call_items_count > 0:
            return (
                f"{first_name}, some of these items would be fastest to review "
                f"together on a quick call with our team \u2014 probably about "
                f"{self._estimate_call_duration(call_items_count)} minutes. "
                f"What times are usually best for you today or tomorrow?"
            )
        else:
            return (
                f"{first_name}, it would help to hop on a quick call to finish "
                f"up a few things. What times work best for you today or tomorrow?"
            )

    def _estimate_call_duration(self, item_count: int) -> int:
        """Estimate call duration in minutes based on item count."""
        base_minutes = 10  # intro + wrap-up
        per_item_minutes = 2
        total = base_minutes + (item_count * per_item_minutes)
        # Round to nearest 5
        return max(10, ((total + 4) // 5) * 5)

    async def parse_availability_response(
        self,
        response_text: str,
        reference_date: Optional[date] = None,
    ) -> List[TimeWindow]:
        """
        Parse borrower availability like 'after 3', 'tomorrow morning',
        'anytime before noon', 'between 2 and 4 pm' into structured time windows.
        """
        if reference_date is None:
            reference_date = date.today()

        client = self._get_ai_client()
        if client is None:
            return self._rule_based_availability_parse(response_text, reference_date)

        today_str = reference_date.strftime("%A, %B %d, %Y")
        tomorrow_str = (reference_date + timedelta(days=1)).strftime("%A, %B %d, %Y")

        prompt = (
            f"Parse this borrower's availability message into time windows.\n\n"
            f"Today is: {today_str}\n"
            f"Tomorrow is: {tomorrow_str}\n"
            f"Borrower said: \"{response_text}\"\n\n"
            f"Return a JSON array of availability windows:\n"
            f"[\n"
            f'  {{"date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM", '
            f'"raw_text": "the relevant phrase"}}\n'
            f"]\n\n"
            f"Rules:\n"
            f'- "after 3" means 15:00 to 17:00\n'
            f'- "morning" means 09:00 to 12:00\n'
            f'- "afternoon" means 12:00 to 17:00\n'
            f'- "evening" or "after work" means 17:00 to 19:00\n'
            f'- "anytime" means 09:00 to 18:00\n'
            f'- "before noon" means 09:00 to 12:00\n'
            f'- "lunch" or "around noon" means 11:30 to 13:00\n'
            f'- "between X and Y" means exactly that range\n'
            f'- If they say "today" or no day, use today\'s date\n'
            f'- If they say "tomorrow", use tomorrow\'s date\n'
            f"- Return ONLY the JSON array, no markdown"
        )

        response = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": prompt}],
            model=_ANTHROPIC_MODEL,
            max_tokens=500,
            operation_name="parse_availability_response",
            org_id=self.org_id,
        )

        if response and response.content:
            raw_json = response.content[0].text.strip()
            try:
                if raw_json.startswith("```"):
                    raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json)
                    raw_json = re.sub(r"\s*```$", "", raw_json)

                windows_raw = json.loads(raw_json)
                windows = []
                for w in windows_raw:
                    try:
                        w_date = date.fromisoformat(w["date"])
                        w_start = time.fromisoformat(w["start_time"])
                        w_end = time.fromisoformat(w["end_time"])
                        windows.append(TimeWindow(
                            date=w_date,
                            start_time=w_start,
                            end_time=w_end,
                            raw_text=w.get("raw_text", response_text),
                            confidence=0.85,
                        ))
                    except (ValueError, KeyError) as exc:
                        logger.warning("Skipping invalid time window: %s (%s)", w, exc)

                if windows:
                    return windows
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "Failed to parse availability JSON: %s", exc
                )

        # Fallback
        return self._rule_based_availability_parse(response_text, reference_date)

    def _rule_based_availability_parse(
        self,
        response_text: str,
        reference_date: date,
    ) -> List[TimeWindow]:
        """Rule-based fallback for parsing availability responses."""
        windows = []
        text_lower = response_text.lower().strip()

        # Determine day reference
        is_tomorrow = "tomorrow" in text_lower
        target_date = (
            reference_date + timedelta(days=1) if is_tomorrow else reference_date
        )

        # "after X" pattern
        after_match = re.search(r"after\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text_lower)
        if after_match:
            hour = int(after_match.group(1))
            minute = int(after_match.group(2) or 0)
            ampm = after_match.group(3)
            if ampm == "am" and hour == 12:
                hour = 0
            elif ampm == "pm" and hour != 12:
                hour += 12
            elif ampm is None and hour < 8:
                hour += 12  # assume PM for small numbers
            start = time(hour, minute)
            end = time(min(hour + 2, 19), 0)
            windows.append(TimeWindow(
                date=target_date, start_time=start, end_time=end,
                raw_text=response_text, confidence=0.65,
            ))
            return windows

        # "before X" or "before noon" pattern
        before_match = re.search(
            r"before\s+(?:(\d{1,2})(?::(\d{2}))?\s*(am|pm)?|noon)",
            text_lower,
        )
        if before_match:
            if "noon" in before_match.group(0):
                end = time(12, 0)
            else:
                hour = int(before_match.group(1))
                minute = int(before_match.group(2) or 0)
                ampm = before_match.group(3)
                if ampm == "pm" and hour != 12:
                    hour += 12
                end = time(hour, minute)
            windows.append(TimeWindow(
                date=target_date, start_time=time(9, 0), end_time=end,
                raw_text=response_text, confidence=0.65,
            ))
            return windows

        # "between X and Y" pattern
        between_match = re.search(
            r"between\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+and\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
            text_lower,
        )
        if between_match:
            start_h = int(between_match.group(1))
            start_m = int(between_match.group(2) or 0)
            start_ampm = between_match.group(3)
            end_h = int(between_match.group(4))
            end_m = int(between_match.group(5) or 0)
            end_ampm = between_match.group(6)

            if start_ampm == "pm" and start_h != 12:
                start_h += 12
            elif start_ampm is None and end_ampm == "pm" and start_h < 12:
                start_h += 12  # "between 2 and 4 pm" => both PM
            if end_ampm == "pm" and end_h != 12:
                end_h += 12
            elif end_ampm is None and start_h > end_h:
                end_h += 12

            windows.append(TimeWindow(
                date=target_date,
                start_time=time(start_h, start_m),
                end_time=time(min(end_h, 23), end_m),
                raw_text=response_text,
                confidence=0.70,
            ))
            return windows

        # "morning" / "afternoon" / "evening" keywords
        if "morning" in text_lower:
            windows.append(TimeWindow(
                date=target_date, start_time=time(9, 0), end_time=time(12, 0),
                raw_text=response_text, confidence=0.60,
            ))
        elif "afternoon" in text_lower:
            windows.append(TimeWindow(
                date=target_date, start_time=time(12, 0), end_time=time(17, 0),
                raw_text=response_text, confidence=0.60,
            ))
        elif "evening" in text_lower or "after work" in text_lower:
            windows.append(TimeWindow(
                date=target_date, start_time=time(17, 0), end_time=time(19, 0),
                raw_text=response_text, confidence=0.55,
            ))
        elif "anytime" in text_lower or "whenever" in text_lower:
            windows.append(TimeWindow(
                date=target_date, start_time=time(9, 0), end_time=time(18, 0),
                raw_text=response_text, confidence=0.50,
            ))

        # If we couldn't parse anything, return a generic business-hours window
        if not windows:
            windows.append(TimeWindow(
                date=target_date, start_time=time(9, 0), end_time=time(17, 0),
                raw_text=response_text, confidence=0.30,
            ))

        return windows

    # =================================================================
    # 6. AUTO-FILL LOGIC WITH AUDIT
    # =================================================================

    async def auto_fill_field(
        self,
        loan_id: str,
        field_path: str,
        value: str,
        confidence: float,
        source: str,
    ) -> AutoFillResult:
        """
        Auto-fill a field on the loan application with a complete audit trail.

        Rules:
            - confidence >= 0.90 AND non-material field: auto-fill allowed
            - 0.70-0.89: fill but flag for review
            - < 0.70: do NOT auto-fill
            - NEVER auto-fill: income figures, SSN, declarations, signatures
            - ALWAYS log: field_path, old_value, new_value, confidence, source, ts

        Returns an AutoFillResult with the audit record ID.
        """
        audit_id = str(uuid.uuid4())[:12].upper()

        # --- Gate 1: Protected field check ---
        if self._is_protected_field(field_path):
            logger.warning(
                "Blocked auto-fill of protected field %s on loan %s (source=%s)",
                field_path, loan_id, source,
            )
            return AutoFillResult(
                filled=False,
                field_path=field_path,
                old_value=None,
                new_value=value,
                confidence=confidence,
                audit_id=audit_id,
                requires_review=True,
                blocked_reason=(
                    f"Field '{field_path}' is in the protected/never-auto-fill list"
                ),
            )

        # --- Gate 2: Confidence threshold ---
        if confidence < CONFIDENCE_CONFIRM:
            logger.info(
                "Confidence %.2f too low to fill %s on loan %s",
                confidence, field_path, loan_id,
            )
            return AutoFillResult(
                filled=False,
                field_path=field_path,
                old_value=None,
                new_value=value,
                confidence=confidence,
                audit_id=audit_id,
                requires_review=False,
                blocked_reason=(
                    f"Confidence {confidence:.2f} below minimum threshold "
                    f"{CONFIDENCE_CONFIRM}"
                ),
            )

        # --- Retrieve current value ---
        old_value = await self._get_field_value(loan_id, field_path)

        # --- Gate 3: Don't overwrite existing non-empty values ---
        if old_value and old_value.strip():
            logger.info(
                "Field %s already has value on loan %s; skipping auto-fill",
                field_path, loan_id,
            )
            return AutoFillResult(
                filled=False,
                field_path=field_path,
                old_value=old_value,
                new_value=value,
                confidence=confidence,
                audit_id=audit_id,
                requires_review=False,
                blocked_reason="Field already has a value; will not overwrite",
            )

        # --- Determine if review is needed ---
        requires_review = confidence < CONFIDENCE_AUTO_FILL

        # --- Perform the fill ---
        fill_success = await self._set_field_value(loan_id, field_path, value)

        if not fill_success:
            return AutoFillResult(
                filled=False,
                field_path=field_path,
                old_value=old_value,
                new_value=value,
                confidence=confidence,
                audit_id=audit_id,
                requires_review=False,
                blocked_reason="Failed to write value to database",
            )

        # --- Write audit record ---
        await self._write_auto_fill_audit(
            audit_id=audit_id,
            loan_id=loan_id,
            field_path=field_path,
            old_value=old_value,
            new_value=value,
            confidence=confidence,
            source=source,
            requires_review=requires_review,
        )

        logger.info(
            "Auto-filled %s on loan %s: '%s' -> '%s' (confidence=%.2f, "
            "review=%s, audit=%s)",
            field_path, loan_id, old_value or "", value,
            confidence, requires_review, audit_id,
        )

        return AutoFillResult(
            filled=True,
            field_path=field_path,
            old_value=old_value,
            new_value=value,
            confidence=confidence,
            audit_id=audit_id,
            requires_review=requires_review,
        )

    async def _get_field_value(
        self,
        loan_id: str,
        field_path: str,
    ) -> Optional[str]:
        """
        Retrieve the current value of a field on a loan.

        Uses a generic column lookup on the loans table for top-level fields,
        or queries loan_application_data JSON for nested paths.
        """
        try:
            # Try direct column first (e.g. "borrower_email" -> loans.borrower_email)
            top_level_field = field_path.split(".")[-1]
            # Whitelist column name against the Loan model to prevent SQL injection
            from database.models import Loan
            allowed_columns = {c.name for c in Loan.__table__.columns}
            if top_level_field not in allowed_columns:
                # Not a valid column — skip to JSON fallback
                raise ValueError(f"Invalid field: {top_level_field}")
            # Defense-in-depth: reject anything that isn't a plain identifier
            if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", top_level_field):
                raise ValueError(f"Invalid identifier: {top_level_field}")
            # Column name is validated; safe to interpolate as an identifier
            result = self.db.execute(
                text(
                    f"SELECT {top_level_field} FROM loans "
                    "WHERE id = :loan_id AND organization_id = :org_id"
                ),
                {
                    "loan_id": loan_id,
                    "org_id": self.org_id,
                },
            ).first()
            if result and result[0] is not None:
                return str(result[0])
        except Exception:
            pass

        # Fallback: check loan_application_data JSON column
        try:
            result = self.db.execute(
                text(
                    "SELECT loan_application_data->:field_path "
                    "FROM loans "
                    "WHERE id = :loan_id AND organization_id = :org_id"
                ),
                {
                    "field_path": field_path,
                    "loan_id": loan_id,
                    "org_id": self.org_id,
                },
            ).first()
            if result and result[0] is not None:
                return str(result[0]).strip('"')
        except Exception:
            pass

        return None

    async def _set_field_value(
        self,
        loan_id: str,
        field_path: str,
        value: str,
    ) -> bool:
        """
        Set a field value on a loan. Tries direct column update first,
        then falls back to JSON path update in loan_application_data.
        """
        try:
            top_level_field = field_path.split(".")[-1]
            # Whitelist column name against the Loan model to prevent SQL injection
            from database.models import Loan
            allowed_columns = {c.name for c in Loan.__table__.columns}
            if top_level_field not in allowed_columns:
                raise ValueError(f"Invalid field: {top_level_field}")
            # Defense-in-depth: reject anything that isn't a plain identifier
            if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", top_level_field):
                raise ValueError(f"Invalid identifier: {top_level_field}")
            # Column name is validated; safe to interpolate as an identifier
            self.db.execute(
                text(
                    f"UPDATE loans SET {top_level_field} = :value "
                    "WHERE id = :loan_id AND organization_id = :org_id"
                ),
                {
                    "value": value,
                    "loan_id": loan_id,
                    "org_id": self.org_id,
                },
            )
            self.db.flush()
            return True
        except Exception as exc:
            logger.debug(
                "Direct column update failed for %s: %s; trying JSON path",
                field_path, exc,
            )
            self.db.rollback()

        # Fallback: JSONB update
        try:
            self.db.execute(
                text(
                    "UPDATE loans "
                    "SET loan_application_data = jsonb_set("
                    "  COALESCE(loan_application_data, '{}'::jsonb), "
                    "  :json_path, to_jsonb(:value::text)"
                    ") "
                    "WHERE id = :loan_id AND organization_id = :org_id"
                ),
                {
                    "json_path": "{" + field_path.replace(".", ",") + "}",
                    "value": value,
                    "loan_id": loan_id,
                    "org_id": self.org_id,
                },
            )
            self.db.flush()
            return True
        except Exception as exc:
            logger.error(
                "Failed to set field %s on loan %s: %s",
                field_path, loan_id, exc,
            )
            self.db.rollback()
            return False

    async def _write_auto_fill_audit(
        self,
        audit_id: str,
        loan_id: str,
        field_path: str,
        old_value: Optional[str],
        new_value: str,
        confidence: float,
        source: str,
        requires_review: bool,
    ) -> None:
        """Write an audit record for an auto-fill action."""
        try:
            self.db.execute(
                text("""
                    INSERT INTO aco_auto_fill_audit (
                        audit_id, loan_id, organization_id, field_path,
                        old_value, new_value, confidence, source,
                        requires_review, filled_by_user_id, created_at
                    ) VALUES (
                        :audit_id, :loan_id, :org_id, :field_path,
                        :old_value, :new_value, :confidence, :source,
                        :requires_review, :user_id, :now
                    )
                """),
                {
                    "audit_id": audit_id,
                    "loan_id": loan_id,
                    "org_id": self.org_id,
                    "field_path": field_path,
                    "old_value": old_value,
                    "new_value": new_value,
                    "confidence": confidence,
                    "source": source,
                    "requires_review": requires_review,
                    "user_id": self.user_id,
                    "now": datetime.now(timezone.utc),
                },
            )
            self.db.flush()
        except Exception as exc:
            logger.error(
                "Failed to write auto-fill audit record %s: %s",
                audit_id, exc,
            )

    # =================================================================
    # 7. CONFIRMATION MESSAGE GENERATION
    # =================================================================

    async def generate_confirmation_message(
        self,
        field_hint: str,
        parsed_value: str,
    ) -> str:
        """
        Generate a short confirmation SMS for a parsed value that needs
        borrower verification (confidence between 0.70 and 0.90).
        """
        return (
            f"Just to confirm \u2014 I have your {field_hint} as: {parsed_value}. "
            f"Is that correct? (yes/no)"
        )

    async def generate_wrap_up_message(
        self,
        borrower_name: str,
        items_resolved: int,
        items_remaining: int,
        call_scheduled: bool = False,
    ) -> str:
        """
        Generate the closing message after text resolution phase completes.
        """
        first_name = (borrower_name or "").split()[0] if borrower_name else "there"

        if items_remaining == 0:
            return (
                f"That's everything, {first_name}! Your application is now complete "
                f"and we'll keep things moving from here. We'll be in touch with "
                f"any updates. Thank you!"
            )

        if call_scheduled:
            return (
                f"Thanks, {first_name} \u2014 we got {items_resolved} items taken care of. "
                f"We have a call scheduled to go over the remaining items with "
                f"our team. You'll get a calendar invite shortly. Talk soon!"
            )

        if items_remaining > 0:
            return (
                f"Thanks, {first_name} \u2014 we knocked out {items_resolved} items. "
                f"There are still {items_remaining} items that need a document upload "
                f"or a quick call. Our team will follow up with next steps. "
                f"Thank you for your time!"
            )

        return f"Thank you, {first_name}! Our team will follow up with next steps."

    # =================================================================
    # 8. CONVERSATION STATE HELPERS
    # =================================================================

    async def log_communication(
        self,
        loan_id: str,
        review_id: int,
        channel: str,
        sender_type: str,
        message_text: str,
        intent: str,
        item_id: Optional[int] = None,
        parsed_response: Optional[ParsedResponse] = None,
    ) -> Optional[int]:
        """
        Log an SMS message to the borrower communication log.

        Returns the log entry ID.
        """
        try:
            result = self.db.execute(
                text("""
                    INSERT INTO aco_borrower_communication_log (
                        loan_id, review_id, organization_id, channel,
                        sender_type, message_text, intent, item_id,
                        parsed_value, confidence, sentiment, created_at
                    ) VALUES (
                        :loan_id, :review_id, :org_id, :channel,
                        :sender_type, :message_text, :intent, :item_id,
                        :parsed_value, :confidence, :sentiment, :now
                    )
                    RETURNING id
                """),
                {
                    "loan_id": loan_id,
                    "review_id": review_id,
                    "org_id": self.org_id,
                    "channel": channel,
                    "sender_type": sender_type,
                    "message_text": message_text,
                    "intent": intent,
                    "item_id": item_id,
                    "parsed_value": (
                        parsed_response.parsed_value if parsed_response else None
                    ),
                    "confidence": (
                        parsed_response.confidence if parsed_response else None
                    ),
                    "sentiment": (
                        parsed_response.sentiment if parsed_response else None
                    ),
                    "now": datetime.now(timezone.utc),
                },
            )
            self.db.flush()
            row = result.first()
            return row[0] if row else None
        except Exception as exc:
            logger.error("Failed to log communication: %s", exc)
            return None

    async def get_conversation_history(
        self,
        loan_id: str,
        review_id: int,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve the conversation history for escalation checks."""
        try:
            rows = self.db.execute(
                text("""
                    SELECT
                        id, channel, sender_type, message_text, intent,
                        item_id, parsed_value, confidence, sentiment,
                        created_at
                    FROM aco_borrower_communication_log
                    WHERE loan_id = :loan_id
                        AND review_id = :review_id
                        AND organization_id = :org_id
                    ORDER BY created_at ASC
                    LIMIT :limit
                """),
                {
                    "loan_id": loan_id,
                    "review_id": review_id,
                    "org_id": self.org_id,
                    "limit": limit,
                },
            ).fetchall()

            history = []
            for row in rows:
                history.append({
                    "id": row[0],
                    "channel": row[1],
                    "sender": row[2],
                    "message": row[3],
                    "intent": row[4],
                    "item_id": row[5],
                    "parsed_value": row[6],
                    "confidence": float(row[7]) if row[7] is not None else None,
                    "sentiment": row[8],
                    "created_at": row[9].isoformat() if row[9] else None,
                    "expects_response": row[4] in (
                        "question", "confirmation", "availability_request",
                    ),
                    "escalate": False,
                })
            return history
        except Exception as exc:
            logger.error("Failed to get conversation history: %s", exc)
            return []

    # =================================================================
    # 9. BATCH RESOLUTION ORCHESTRATOR
    # =================================================================

    async def execute_text_resolution_batch(
        self,
        loan_id: str,
        review_id: int,
        text_items: List[Dict[str, Any]],
        borrower_name: str = "",
    ) -> Dict[str, Any]:
        """
        Prepare the full text resolution batch: generate all question messages
        in priority order, ready for sequential delivery by the conversation
        manager.

        Returns a plan dict with ordered questions and metadata.
        """
        # Sort by priority (CRITICAL > HIGH > NORMAL > LOW)
        priority_order = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3}
        sorted_items = sorted(
            text_items,
            key=lambda x: priority_order.get(x.get("priority", "NORMAL"), 2),
        )

        questions = []
        for item in sorted_items:
            question_text = await self.generate_question_message(
                item, borrower_name
            )
            field_key = (item.get("field_path", "").split(".")[-1]
                         if item.get("field_path") else "")
            template = FIELD_QUESTION_TEMPLATES.get(field_key, {})

            questions.append({
                "item_id": item.get("item_id") or item.get("id"),
                "field_path": item.get("field_path", ""),
                "field_hint": template.get("field_hint", item.get("description", "")),
                "question_text": question_text,
                "expected_format": self._infer_expected_format(
                    item.get("field_path", "")
                ),
                "priority": item.get("priority", "NORMAL"),
            })

        return {
            "loan_id": loan_id,
            "review_id": review_id,
            "total_questions": len(questions),
            "questions": questions,
            "estimated_duration_minutes": len(questions) * 1.5,
        }

    def _infer_expected_format(self, field_path: str) -> str:
        """Infer the expected response format from the field path."""
        fp = (field_path or "").lower()

        if any(kw in fp for kw in ("email",)):
            return "email"
        if any(kw in fp for kw in ("phone", "fax")):
            return "phone"
        if any(kw in fp for kw in ("date", "start", "end")):
            return "date"
        if any(kw in fp for kw in ("count", "number", "years", "months", "units")):
            return "number"
        if any(kw in fp for kw in ("address", "street", "city", "zip")):
            return "address"
        if any(kw in fp for kw in ("type", "status", "purpose")):
            return "enum"
        return "text"

    # =================================================================
    # 10. PORTAL UPLOAD INSTRUCTIONS
    # =================================================================

    async def generate_portal_upload_message(
        self,
        borrower_name: str,
        portal_items: List[Dict[str, Any]],
        portal_url: str = "",
    ) -> str:
        """
        Generate an SMS message listing documents the borrower needs to
        upload through the portal, with a link.
        """
        first_name = (borrower_name or "").split()[0] if borrower_name else "there"
        count = len(portal_items)

        if not portal_url:
            portal_url = os.getenv("APP_URL", "https://app.perenniaai.com")
            portal_url += "/portal/documents"

        if count == 1:
            desc = portal_items[0].get("description", "a document")
            return (
                f"{first_name}, we also need you to upload your {desc}. "
                f"You can do that here: {portal_url}"
            )

        doc_list = ", ".join(
            item.get("description", "document") for item in portal_items[:5]
        )
        if count > 5:
            doc_list += f", and {count - 5} more"

        return (
            f"{first_name}, we need {count} documents uploaded: {doc_list}. "
            f"You can upload them here: {portal_url}"
        )

    # =================================================================
    # 11. SENTIMENT SUMMARY
    # =================================================================

    async def summarize_conversation_sentiment(
        self,
        conversation_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Summarize the overall sentiment and engagement of the conversation
        for the LO dashboard.
        """
        sentiments = []
        response_times = []
        total_borrower_messages = 0
        total_system_messages = 0

        for i, entry in enumerate(conversation_history):
            if entry.get("sender") == "borrower":
                total_borrower_messages += 1
                if entry.get("sentiment"):
                    sentiments.append(entry["sentiment"])
            elif entry.get("sender") == "system":
                total_system_messages += 1

        sentiment_counts = {}
        for s in sentiments:
            sentiment_counts[s] = sentiment_counts.get(s, 0) + 1

        # Determine overall sentiment
        if not sentiments:
            overall = "UNKNOWN"
        elif sentiment_counts.get("FRUSTRATED", 0) >= 2:
            overall = "FRUSTRATED"
        elif sentiment_counts.get("NEGATIVE", 0) > sentiment_counts.get("POSITIVE", 0):
            overall = "NEGATIVE"
        elif sentiment_counts.get("POSITIVE", 0) > 0:
            overall = "POSITIVE"
        else:
            overall = "NEUTRAL"

        return {
            "overall_sentiment": overall,
            "sentiment_breakdown": sentiment_counts,
            "total_borrower_messages": total_borrower_messages,
            "total_system_messages": total_system_messages,
            "engagement_ratio": (
                round(total_borrower_messages / total_system_messages, 2)
                if total_system_messages > 0 else 0.0
            ),
        }
