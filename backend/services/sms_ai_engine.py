"""SMS AI Personality & Response Variation Engine.

Replaces canned template responses with Claude-generated, context-aware,
compliance-checked SMS messages that adapt tone to the borrower and never
repeat themselves.

Usage:
    from services.sms_ai_engine import (
        generate_sms_response,
        detect_borrower_tone,
        should_escalate_to_human,
        generate_proactive_message,
    )

    result = await generate_sms_response(db, conversation_id, "What rate can I get?", lead_id, org_id)
    # result = {"response": "...", "compliance_ok": True, "tone": "friendly", ...}
"""

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple, Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── In-memory TTL cache for persona config (PERF-003) ───────────────
_persona_cache: Dict[int, Tuple[float, Dict]] = {}
_PERSONA_CACHE_TTL = 300  # 5 minutes

# ── Prompt injection patterns (AGENT-004) ────────────────────────────
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?above", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"^system\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^assistant\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^human\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"disregard\s+(all\s+)?prior", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"override\s+(system|prompt)", re.IGNORECASE),
    re.compile(r"pretend\s+(you('re|\s+are)\s+)", re.IGNORECASE),
]

# Max chars per borrower-sourced field injected into prompts
_MAX_FIELD_LEN = 500

# Max total chars for conversation history in Claude messages
_MAX_HISTORY_CHARS = 3000
_MAX_HISTORY_MESSAGES = 10

# Fallback response when Claude API times out (PERF-002)
_TIMEOUT_FALLBACK = "Thanks for your message! Let me look into that and get back to you shortly."

# Claude model for SMS generation — Sonnet for speed + cost efficiency on short messages
SMS_MODEL = "claude-sonnet-4-6"
SMS_MAX_TOKENS = 200  # SMS-sized output

# ── Compliance constants ──────────────────────────────────────────────
# ECOA-prohibited topics (Equal Credit Opportunity Act)
ECOA_PROHIBITED_PATTERNS = [
    r"\b(race|racial|ethnicity|ethnic)\b",
    r"\b(religion|religious|church|mosque|synagogue|temple)\b",
    r"\b(sex|gender|sexual orientation|transgender)\b",
    r"\b(national origin|nationality|country of origin|immigrant|immigration)\b",
    r"\b(marital status|married|divorced|spouse|husband|wife)\b",
    r"\bage\b(?!\s*of\s*(loan|property|home|house))",  # "age" unless "age of loan/property"
    r"\b(handicap|disability|disabled)\b",
    r"\b(familial status|pregnant|children|kids|family planning)\b",
]

# Rate quote patterns — must never quote specific rates
RATE_QUOTE_PATTERNS = [
    r"\d+\.?\d*\s*%",                         # "6.5%", "7%"
    r"rate\s*(is|of|at|would be)\s*\d",        # "rate is 6", "rate of 7"
    r"\$\d{1,3}(,?\d{3})*\s*(per|a)\s*month",  # "$2,100 per month" (specific payment quotes)
]

_ECOA_RE = [re.compile(p, re.IGNORECASE) for p in ECOA_PROHIBITED_PATTERNS]
_RATE_RE = [re.compile(p, re.IGNORECASE) for p in RATE_QUOTE_PATTERNS]


# ── Prompt injection sanitizer (AGENT-004) ───────────────────────────
def _sanitize_for_prompt(text: Optional[str], max_len: int = _MAX_FIELD_LEN) -> str:
    """Sanitize borrower-sourced text before injecting into system prompts.

    Strips prompt-injection patterns, limits length, and removes control chars.
    """
    if not text:
        return ""
    # Truncate to max length
    sanitized = str(text)[:max_len]
    # Strip known injection patterns
    for pattern in _INJECTION_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    # Remove control characters (except newline/tab)
    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", sanitized)
    return sanitized.strip()


# ── Anthropic client accessor ─────────────────────────────────────────
def _get_async_client():
    """Lazily import the shared async Anthropic client."""
    try:
        from agents.anthropic_client import get_async_anthropic_client
        return get_async_anthropic_client()
    except Exception as e:
        logger.error("Failed to get async Anthropic client: %s", e, extra={"error": str(e)})
        return None


# ══════════════════════════════════════════════════════════════════════
#  1. MAIN RESPONSE GENERATOR
# ══════════════════════════════════════════════════════════════════════

async def generate_sms_response(
    db: Session,
    conversation_id: str,
    inbound_message: str,
    lead_id: Optional[int] = None,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Generate an AI-driven SMS response with personality variation.

    Loads full context (conversation history, lead data, org persona,
    cross-channel interactions), builds a Claude prompt, validates the
    response for compliance, and returns the final text.

    Returns:
        {
            "response": str,
            "compliance_ok": bool,
            "compliance_flags": list,
            "tone": str,
            "escalate": bool,
            "escalate_reason": str | None,
        }
    """
    try:
        # ── TCPA: Verify SMS consent before generating AI response ──
        if lead_id and organization_id:
            try:
                from sqlalchemy import text as _text
                consent_row = db.execute(_text("""
                    SELECT sms_consent FROM channel_preferences
                    WHERE lead_id = :lid AND organization_id = :oid
                    LIMIT 1
                """), {"lid": lead_id, "oid": organization_id}).fetchone()
                if consent_row and consent_row.sms_consent is False:
                    logger.warning(
                        "SMS AI response blocked: no sms_consent for lead %s",
                        lead_id,
                        extra={"organization_id": organization_id, "conversation_id": conversation_id, "lead_id": lead_id},
                    )
                    return {
                        "response": "",
                        "compliance_ok": False,
                        "compliance_flags": ["NO_SMS_CONSENT"],
                        "tone": "professional",
                        "escalate": False,
                        "escalate_reason": None,
                    }
            except Exception as e:
                logger.debug(
                    "Consent check skipped: %s",
                    e,
                    extra={"organization_id": organization_id, "conversation_id": conversation_id, "lead_id": lead_id},
                )

        # ── a. Load conversation history (last 15 messages) ───────
        history = _load_conversation_history(db, conversation_id, limit=15)

        # ── b. Load lead context ──────────────────────────────────
        lead_ctx = _load_lead_context(db, lead_id) if lead_id else {}

        # ── c. Load org persona config ────────────────────────────
        persona = _load_org_persona(db, organization_id) if organization_id else {}

        # ── d. Load cross-channel context ─────────────────────────
        channel_ctx = _load_cross_channel_context(db, lead_id, organization_id) if lead_id else ""

        # ── Detect borrower tone ──────────────────────────────────
        borrower_msgs = [m for m in history if m.get("role") == "user"]
        tone = detect_borrower_tone(borrower_msgs[-3:] if len(borrower_msgs) >= 3 else borrower_msgs)

        # ── Check if we should escalate ───────────────────────────
        escalate, escalate_reason = should_escalate_to_human(history, {
            "tone": tone,
            "lead_context": lead_ctx,
        })

        if escalate:
            lo_name = lead_ctx.get("lo_name", "your loan officer")
            fallback = f"I want to make sure you get the best help possible. Let me connect you with {lo_name} directly. They'll reach out shortly!"
            return {
                "response": fallback,
                "compliance_ok": True,
                "compliance_flags": [],
                "tone": tone,
                "escalate": True,
                "escalate_reason": escalate_reason,
            }

        # ── e. Build system prompt ────────────────────────────────
        system_prompt = _build_system_prompt(
            persona=persona,
            lead_ctx=lead_ctx,
            channel_ctx=channel_ctx,
            tone=tone,
            history=history,
        )

        # ── f. Call Claude ────────────────────────────────────────
        messages = _build_claude_messages(history, inbound_message)
        response_text = await _call_claude(system_prompt, messages)

        # ── g. Validate compliance ────────────────────────────────
        compliance_ok, flags = _validate_compliance(response_text)

        if not compliance_ok:
            logger.warning(
                "SMS compliance violation detected, falling back to template",
                extra={
                    "organization_id": organization_id,
                    "conversation_id": conversation_id,
                    "lead_id": lead_id,
                    "flags": flags,
                    "original_response": response_text[:100],
                },
            )
            response_text = _get_fallback_response(lead_ctx, history)
            compliance_ok = True
            flags = []

        # ── h. Return ────────────────────────────────────────────
        return {
            "response": response_text,
            "compliance_ok": compliance_ok,
            "compliance_flags": flags,
            "tone": tone,
            "escalate": False,
            "escalate_reason": None,
        }

    except Exception as e:
        logger.exception(
            "SMS AI engine error, falling back to template",
            extra={"conversation_id": conversation_id, "organization_id": organization_id, "lead_id": lead_id, "error": str(e)},
        )
        fallback = _get_fallback_response(
            _load_lead_context(db, lead_id) if lead_id else {},
            [],
        )
        return {
            "response": fallback,
            "compliance_ok": True,
            "compliance_flags": [],
            "tone": "professional",
            "escalate": False,
            "escalate_reason": None,
        }


# ══════════════════════════════════════════════════════════════════════
#  2. BORROWER TONE DETECTION
# ══════════════════════════════════════════════════════════════════════

def detect_borrower_tone(messages: List[Dict]) -> str:
    """Analyze the last few borrower messages to detect communication tone.

    Returns one of: hostile, friendly, professional, skeptical, frustrated, brief, detailed
    """
    if not messages:
        return "professional"

    texts = [m.get("content", "") for m in messages if m.get("content")]
    if not texts:
        return "professional"

    combined = " ".join(texts).lower()
    avg_len = sum(len(t) for t in texts) / len(texts)

    # ── Hostile signals (rude, crude, abusive — stronger than frustrated) ──
    hostile_words = [
        "fuck", "shit", "damn", "ass", "bitch", "idiot", "stupid",
        "dumb", "moron", "trash", "garbage", "suck", "pathetic",
        "incompetent", "useless", "joke", "clown",
    ]
    hostile_count = sum(1 for w in hostile_words if w in combined)
    if hostile_count >= 1:
        return "hostile"

    # ── Frustrated signals ────────────────────────────────────────
    frustration_words = [
        "annoyed", "frustrated", "angry", "upset", "ridiculous",
        "terrible", "worst", "hate", "waste", "unacceptable",
        "stop texting", "leave me alone", "go away",
    ]
    exclamation_count = sum(t.count("!") for t in texts)
    caps_ratio = sum(1 for c in combined if c.isupper()) / max(len(combined), 1)

    if any(w in combined for w in frustration_words) or exclamation_count >= 3 or caps_ratio > 0.5:
        return "frustrated"

    # ── Skeptical signals ─────────────────────────────────────────
    skeptical_words = [
        "really", "sure about", "doubt", "scam", "legit",
        "prove", "why should", "sounds too good", "catch",
        "hidden", "fine print", "trust",
    ]
    question_count = sum(t.count("?") for t in texts)

    if any(w in combined for w in skeptical_words) or question_count >= 3:
        return "skeptical"

    # ── Friendly signals ──────────────────────────────────────────
    friendly_words = [
        "thanks", "thank you", "awesome", "great", "love",
        "appreciate", "perfect", "excited", "wonderful", "cool",
        "lol", "haha", ":)", "!",
    ]
    friendly_count = sum(1 for w in friendly_words if w in combined)

    if friendly_count >= 2:
        return "friendly"

    # ── Brief vs detailed ─────────────────────────────────────────
    if avg_len < 20:
        return "brief"
    if avg_len > 100:
        return "detailed"

    return "professional"


# ══════════════════════════════════════════════════════════════════════
#  3. HUMAN ESCALATION DETECTION
# ══════════════════════════════════════════════════════════════════════

def should_escalate_to_human(
    conversation_history: List[Dict],
    context: Optional[Dict] = None,
) -> Tuple[bool, Optional[str]]:
    """Determine if the conversation should be handed off to a human.

    Returns:
        (should_escalate: bool, reason: str | None)
    """
    context = context or {}
    borrower_msgs = [m for m in conversation_history if m.get("role") == "user"]
    all_texts = [m.get("content", "").lower() for m in borrower_msgs]

    # ── Borrower explicitly asked for a human 2+ times ────────────
    human_request_patterns = [
        r"\b(talk to|speak to|speak with|connect me|transfer me|real person|human|actual person|live agent|your manager|supervisor)\b",
    ]
    human_re = [re.compile(p, re.IGNORECASE) for p in human_request_patterns]
    human_request_count = sum(
        1 for text in all_texts
        if any(r.search(text) for r in human_re)
    )
    if human_request_count >= 2:
        return True, "borrower_requested_human"

    # ── 3+ frustrated/negative messages ───────────────────────────
    tone = context.get("tone", "")
    if tone == "frustrated":
        negative_count = 0
        frustration_signals = [
            "annoyed", "frustrated", "angry", "upset", "ridiculous",
            "stop", "leave me alone", "go away", "unacceptable",
        ]
        for text in all_texts[-5:]:
            if any(w in text for w in frustration_signals):
                negative_count += 1
        if negative_count >= 3:
            return True, "sustained_frustration"

    # ── 10+ turns without qualification progress ──────────────────
    if len(conversation_history) >= 20:  # 10 turns = 20 messages (inbound + outbound)
        lead_ctx = context.get("lead_context", {})
        qualification = lead_ctx.get("qualification_summary", "")
        # If still in early stage after many turns, no progress
        if not qualification or qualification.count("Unknown") >= 3:
            return True, "no_progress_after_10_turns"

    # ── Low confidence on complex question ────────────────────────
    # Check if last few messages contained questions the AI couldn't classify
    complex_patterns = [
        r"\b(lawsuit|legal|attorney|sue|foreclosure|bankruptcy|divorce settlement)\b",
        r"\b(tax lien|irs|garnishment|child support order|court order)\b",
        r"\b(complaint|report you|bbb|cfpb|attorney general)\b",
    ]
    complex_re = [re.compile(p, re.IGNORECASE) for p in complex_patterns]
    last_3 = all_texts[-3:] if len(all_texts) >= 3 else all_texts
    for text in last_3:
        if any(r.search(text) for r in complex_re):
            return True, "complex_question_requires_human"

    return False, None


# ══════════════════════════════════════════════════════════════════════
#  4. PROACTIVE MESSAGE GENERATOR
# ══════════════════════════════════════════════════════════════════════

async def generate_proactive_message(
    db: Session,
    lead_id: int,
    trigger_type: str,
    trigger_data: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Generate an AI-varied proactive outbound text for a specific trigger.

    Supported trigger_type values:
        - rate_alert
        - follow_up
        - appointment_reminder
        - milestone

    Returns:
        {"response": str, "trigger_type": str, "compliance_ok": bool}
    """
    trigger_data = trigger_data or {}
    lead_ctx = _load_lead_context(db, lead_id)
    name = lead_ctx.get("first_name") or lead_ctx.get("name", "there")
    lo_name = lead_ctx.get("lo_name", "your loan officer")
    loan_type = lead_ctx.get("loan_type", "mortgage")

    # ── Build per-trigger prompt ──────────────────────────────────
    trigger_prompts = {
        "rate_alert": (
            f"Generate a short, friendly SMS (under 160 chars) to {name} about a favorable rate movement. "
            f"Their loan officer is {lo_name}. Mention their estimated payment dropped. "
            f"Savings amount: {trigger_data.get('savings_amount', 'some')}. "
            f"Ask if they want to discuss. Sound excited but not pushy. Vary your phrasing."
        ),
        "follow_up": (
            f"Generate a short, warm SMS check-in (under 160 chars) to {name} about their {loan_type} plans. "
            f"Their loan officer is {lo_name}. Ask if they have questions. "
            f"Be casual, not salesy. Vary your phrasing each time."
        ),
        "appointment_reminder": (
            f"Generate an SMS reminder (under 300 chars) for {name} about their upcoming call with {lo_name}. "
            f"Appointment time: {trigger_data.get('appointment_time', 'tomorrow')}. "
            f"Documents to prepare: {trigger_data.get('doc_list', 'recent pay stubs and bank statements')}. "
            f"Be helpful and encouraging. Vary your phrasing."
        ),
        "milestone": (
            f"Generate a celebratory SMS (under 200 chars) to {name} about a loan milestone. "
            f"Milestone: {trigger_data.get('milestone', 'appraisal completed')}. "
            f"Their loan officer is {lo_name} and will follow up with details. "
            f"Sound genuinely happy for them. Vary your phrasing."
        ),
    }

    prompt_instruction = trigger_prompts.get(trigger_type)
    if not prompt_instruction:
        logger.warning("Unknown proactive trigger type: %s", trigger_type, extra={"lead_id": lead_id, "trigger_type": trigger_type})
        return {
            "response": f"Hi {name}, just checking in! Reach out anytime if you have questions.",
            "trigger_type": trigger_type,
            "compliance_ok": True,
        }

    system = (
        "You are a mortgage assistant sending an SMS on behalf of a loan officer. "
        "RULES: Never quote specific interest rates or percentages. "
        "Never ask about race, religion, sex, national origin, marital status, age. "
        "Sound human and natural. Use contractions. Be concise."
    )

    try:
        client = _get_async_client()
        if not client:
            raise RuntimeError("Anthropic client unavailable")

        from agents.anthropic_client import cached_system_block
        resp = await asyncio.wait_for(
            client.messages.create(
                model=SMS_MODEL,
                max_tokens=SMS_MAX_TOKENS,
                system=cached_system_block(system),
                messages=[{"role": "user", "content": prompt_instruction}],
            ),
            timeout=15.0,
        )

        text = resp.content[0].text.strip()
        # Strip any wrapping quotes the model might add
        text = text.strip('"').strip("'")

        compliance_ok, flags = _validate_compliance(text)
        if not compliance_ok:
            logger.warning(
                "Proactive message failed compliance, using fallback",
                extra={"lead_id": lead_id, "trigger_type": trigger_type, "flags": flags},
            )
            text = _proactive_fallback(trigger_type, name, lo_name, trigger_data)

        return {
            "response": text,
            "trigger_type": trigger_type,
            "compliance_ok": True,
        }

    except Exception as e:
        logger.exception("Proactive message generation failed: %s", e, extra={"lead_id": lead_id, "trigger_type": trigger_type})
        text = _proactive_fallback(trigger_type, name, lo_name, trigger_data)
        return {
            "response": text,
            "trigger_type": trigger_type,
            "compliance_ok": True,
        }


# ══════════════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════

def _load_conversation_history(
    db: Session, conversation_id: str, limit: int = 15,
) -> List[Dict]:
    """Load recent messages from the sms_conversations thread."""
    try:
        from database.models.sms_conversation import SMSAIConversationMessage
        messages = (
            db.query(SMSAIConversationMessage)
            .filter(SMSAIConversationMessage.conversation_id == conversation_id)
            .order_by(SMSAIConversationMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        # Reverse to chronological order
        messages = messages[::-1]
        return [
            {
                "role": "user" if m.direction == "inbound" else "assistant",
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]
    except Exception as e:
        logger.error(
            "Failed to load conversation history",
            extra={"conversation_id": conversation_id, "error": str(e)},
            exc_info=True,
        )
        return []


def _load_lead_context(db: Session, lead_id: Optional[int]) -> Dict:
    """Load lead details for prompt context."""
    if not lead_id:
        return {}

    try:
        from database.models.lead_loan import Lead
        from database.models.core import User

        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return {}

        ctx: Dict[str, Any] = {
            "name": lead.name or "",
            "first_name": lead.first_name or (lead.name or "").split()[0] if lead.name else "",
            "stage": lead.stage or "New",
            "loan_type": lead.loan_type or "",
            "loan_purpose": getattr(lead, "loan_purpose", None) or lead.loan_type or "",
            "credit_score": lead.credit_score,
            "employment_status": lead.employment_status or "",
            "loan_amount": str(lead.loan_amount) if lead.loan_amount else "",
            "property_type": lead.property_type or "",
            "source": lead.source or "",
            "ai_score": lead.ai_score,
            "sentiment": lead.sentiment or "neutral",
        }

        # Build qualification summary
        qual_parts = []
        if lead.loan_type:
            qual_parts.append(f"Loan type: {lead.loan_type}")
        if lead.credit_score:
            qual_parts.append(f"Credit: {lead.credit_score}")
        if lead.employment_status:
            qual_parts.append(f"Employment: {lead.employment_status}")
        if lead.loan_amount:
            qual_parts.append(f"Amount: ${lead.loan_amount:,.0f}")
        if lead.property_type:
            qual_parts.append(f"Property: {lead.property_type}")

        unknown_count = sum(1 for k in ["loan_type", "credit_score", "employment_status", "loan_amount"] if not getattr(lead, k, None))
        if unknown_count > 0:
            qual_parts.append(f"{unknown_count} qualification field(s) still unknown")

        ctx["qualification_summary"] = " | ".join(qual_parts) if qual_parts else "No qualification data yet"

        # Get assigned LO name
        if lead.owner_id:
            lo = db.query(User).filter(User.id == lead.owner_id).first()
            if lo:
                ctx["lo_name"] = lo.full_name or f"{lo.first_name or ''} {lo.last_name or ''}".strip() or "your loan officer"
                ctx["lo_nmls"] = lo.nmls_number or lo.nmls_id or ""
            else:
                ctx["lo_name"] = "your loan officer"
                ctx["lo_nmls"] = ""
        else:
            ctx["lo_name"] = "your loan officer"
            ctx["lo_nmls"] = ""

        return ctx

    except Exception as e:
        logger.error(
            "Failed to load lead context: %s",
            e,
            extra={"lead_id": lead_id, "error": str(e)},
            exc_info=True,
        )
        return {}


def _load_org_persona(db: Session, organization_id: Optional[int]) -> Dict:
    """Load AI persona and org branding from script_customization config.

    Results are cached in-memory for 5 minutes per org to avoid hitting
    the DB on every inbound SMS (PERF-003).
    """
    if not organization_id:
        return _default_persona()

    # Check TTL cache first
    now = time.monotonic()
    cached = _persona_cache.get(organization_id)
    if cached:
        cached_at, cached_result = cached
        if now - cached_at < _PERSONA_CACHE_TTL:
            return cached_result

    try:
        from services.script_customization_service import get_script_customization_service
        svc = get_script_customization_service()
        config = svc.get_config(db, str(organization_id))

        persona = config.get("persona", {})
        result = {
            "ai_name": persona.get("name", "Aria"),
            "personality": persona.get("personality", "professional, warm, knowledgeable"),
            "greeting_style": persona.get("greeting_style", "friendly"),
        }

        # Get org name and NMLS from Organization table
        from database.models.core import Organization
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if org:
            result["company_name"] = org.name or ""
        else:
            result["company_name"] = ""

        # Store in cache
        _persona_cache[organization_id] = (now, result)
        return result

    except Exception as e:
        logger.error(
            "Failed to load org persona",
            extra={"organization_id": organization_id},
            exc_info=True,
        )
        return _default_persona()


def _default_persona() -> Dict:
    return {
        "ai_name": "Aria",
        "personality": "professional, warm, knowledgeable",
        "greeting_style": "friendly",
        "company_name": "",
    }


def _load_cross_channel_context(
    db: Session, lead_id: Optional[int], organization_id: Optional[int],
) -> str:
    """Load recent calls and emails for cross-channel awareness."""
    if not lead_id:
        return "No cross-channel history available."

    parts = []

    try:
        # Recent call logs
        from database.models.dialer import CallLog
        calls = (
            db.query(CallLog)
            .filter(CallLog.lead_id == lead_id)
            .order_by(CallLog.created_at.desc())
            .limit(3)
            .all()
        )
        if calls:
            call_summaries = []
            for c in calls:
                outcome = c.outcome.value if c.outcome else "unknown"
                when = c.created_at.strftime("%b %d") if c.created_at else "recently"
                summary = c.ai_note_summary or c.notes or ""
                call_summaries.append(f"Call on {when}: {outcome}" + (f" - {summary[:80]}" if summary else ""))
            parts.append("Recent calls: " + "; ".join(call_summaries))
    except Exception as e:
        logger.debug("Could not load call history: %s", e)

    try:
        # Recent emails
        from database.models.communication import EmailMessage
        emails = (
            db.query(EmailMessage)
            .filter(EmailMessage.lead_id == lead_id)
            .order_by(EmailMessage.created_at.desc())
            .limit(3)
            .all()
        )
        if emails:
            email_summaries = []
            for em in emails:
                direction = em.direction or "unknown"
                when = em.created_at.strftime("%b %d") if em.created_at else "recently"
                subj = em.subject or "no subject"
                email_summaries.append(f"{direction.title()} email on {when}: \"{subj[:50]}\"")
            parts.append("Recent emails: " + "; ".join(email_summaries))
    except Exception as e:
        logger.debug("Could not load email history: %s", e)

    try:
        # Recent activities
        from database.models.communication import Activity
        activities = (
            db.query(Activity)
            .filter(Activity.lead_id == lead_id)
            .order_by(Activity.created_at.desc())
            .limit(5)
            .all()
        )
        if activities:
            act_summaries = []
            for a in activities:
                atype = a.type.value if a.type else "note"
                when = a.created_at.strftime("%b %d") if a.created_at else "recently"
                content_preview = (a.content or "")[:60]
                act_summaries.append(f"{atype} on {when}" + (f": {content_preview}" if content_preview else ""))
            parts.append("Recent activity: " + "; ".join(act_summaries))
    except Exception as e:
        logger.debug("Could not load activity history: %s", e)

    return "\n".join(parts) if parts else "No cross-channel history available."


def _build_system_prompt(
    persona: Dict,
    lead_ctx: Dict,
    channel_ctx: str,
    tone: str,
    history: List[Dict],
) -> str:
    """Construct the Claude system prompt with full context.

    All borrower-sourced fields are sanitized to prevent prompt injection (AGENT-004).
    """
    ai_name = _sanitize_for_prompt(persona.get("ai_name", "Aria"), max_len=50)
    company_name = _sanitize_for_prompt(persona.get("company_name", ""), max_len=100)
    personality = _sanitize_for_prompt(persona.get("personality", "professional, warm, knowledgeable"), max_len=200)
    borrower_name = _sanitize_for_prompt(
        lead_ctx.get("first_name") or lead_ctx.get("name", "the borrower"), max_len=100
    )
    loan_purpose = _sanitize_for_prompt(
        lead_ctx.get("loan_purpose") or lead_ctx.get("loan_type") or "mortgage", max_len=100
    )
    lo_name = _sanitize_for_prompt(lead_ctx.get("lo_name", "your loan officer"), max_len=100)
    lo_nmls = _sanitize_for_prompt(lead_ctx.get("lo_nmls", ""), max_len=20)
    qualification_summary = _sanitize_for_prompt(lead_ctx.get("qualification_summary", "No qualification data yet"))
    stage = _sanitize_for_prompt(lead_ctx.get("stage", "New"), max_len=50)
    channel_ctx = _sanitize_for_prompt(channel_ctx)

    # Determine next question to ask based on missing qualification data
    next_question = _determine_next_question(lead_ctx)

    # Determine conversation stage from lead stage
    convo_stage = _map_lead_stage_to_convo_stage(stage)

    # Build the list of previous outbound messages to avoid repetition
    prev_outbound = [m["content"] for m in history if m.get("role") == "assistant"]
    avoid_block = ""
    if prev_outbound:
        recent = prev_outbound[-5:]  # last 5 outbound messages
        avoid_block = "\n\nPREVIOUS RESPONSES YOU'VE SENT (do NOT repeat these verbatim):\n" + "\n".join(
            f"- \"{msg[:120]}\"" for msg in recent
        )

    # Tone instruction
    tone_instructions = {
        "friendly": "Match their friendly, upbeat energy. Be warm and fun — throw in a little humor if it fits.",
        "professional": "Keep it professional but approachable. Clear, informative, with a touch of personality.",
        "skeptical": "Be extra transparent and reassuring. Acknowledge their concerns directly. No hard sell. Let your competence speak.",
        "frustrated": "Be empathetic but not robotic about it. Vary your empathy — 'That's rough' or 'Yeah, that's not okay' instead of 'I understand your frustration' on repeat. Offer concrete help or a human connection.",
        "hostile": "Stay classy. Don't match their energy, don't lecture. Be helpful and unbothered. Kill them with kindness and competence. If they won't engage, offer to have their LO reach out when they're ready.",
        "brief": "Keep your response very short — they prefer brevity. One sentence if possible.",
        "detailed": "They like detail — feel free to use the full 300 character limit with helpful information.",
    }
    tone_instruction = tone_instructions.get(tone, tone_instructions["professional"])

    nmls_line = f" (NMLS# {lo_nmls})" if lo_nmls else ""
    company_line = f" at {company_name}" if company_name else ""

    is_first_message = len([m for m in history if m.get("role") == "assistant"]) == 0

    first_msg_rule = ""

    prompt = f"""You are {ai_name}, a mortgage assistant{company_line}{nmls_line}.
You are texting {borrower_name} about their {loan_purpose} mortgage inquiry.
Your personality: {personality}

WHO YOU ARE IN TEXT:
You're warm, witty, and real. You text like a smart friend who happens to know mortgages — \
not like a corporate chatbot. You use humor naturally (never forced), you're quick on your feet, \
and you make people feel like they're talking to someone who actually cares. \
If someone is rude or crude over text, you stay classy — don't match their energy, \
don't get passive-aggressive. Just stay helpful, unbothered, and professional. \
If they keep being hostile, offer to have {lo_name} reach out directly.

RULES:
- Keep responses under 160 characters when possible (SMS-friendly)
- For detailed questions, you may use up to 300 characters max
- Sound natural and human — use contractions, casual language, and personality
- Never send the exact same response you've sent before in this conversation
- Never quote specific interest rates, APRs, or percentage numbers
- Never ask about race, religion, sex, national origin, marital status, age (ECOA)
- If asked if you're AI, honestly say yes and offer to connect with {lo_name}
- Your goal: qualify the borrower and set an appointment with {lo_name}{first_msg_rule}

BORROWER TONE: {tone}
TONE INSTRUCTION: {tone_instruction}

QUALIFICATION STATUS:
{qualification_summary}

CROSS-CHANNEL CONTEXT:
{channel_ctx}

CONVERSATION STAGE: {convo_stage}
NEXT QUESTION TO ASK: {next_question}{avoid_block}

Respond with ONLY the SMS text. No quotes, no explanation, no prefix."""

    return prompt


def _build_claude_messages(
    history: List[Dict], inbound_message: str,
) -> List[Dict]:
    """Convert conversation history + new inbound into Claude messages format.

    Enforces a token budget to prevent unbounded context growth (AGENT-002).
    Keeps the most recent messages, truncating oldest first. The inbound
    message is always included in full.
    """
    # Cap history to most recent N messages before processing
    capped_history = history[-_MAX_HISTORY_MESSAGES:] if len(history) > _MAX_HISTORY_MESSAGES else history

    # Enforce character budget on history (rough token estimate: 1 token ~ 4 chars)
    total_chars = 0
    budget_history: List[Dict] = []
    for msg in reversed(capped_history):
        content = msg.get("content", "")
        if not content:
            continue
        msg_chars = len(content)
        if total_chars + msg_chars > _MAX_HISTORY_CHARS:
            # Truncate this message to fit remaining budget
            remaining = _MAX_HISTORY_CHARS - total_chars
            if remaining > 50:  # Only include if meaningful content remains
                budget_history.append({"role": msg.get("role", "user"), "content": content[-remaining:]})
                total_chars += remaining
            break
        budget_history.append(msg)
        total_chars += msg_chars
    # Restore chronological order
    budget_history.reverse()

    messages = []
    for msg in budget_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not content:
            continue
        # Claude API requires alternating user/assistant; merge consecutive same-role
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n" + content
        else:
            messages.append({"role": role, "content": content})

    # Add the new inbound message
    if messages and messages[-1]["role"] == "user":
        messages[-1]["content"] += "\n" + inbound_message
    else:
        messages.append({"role": "user", "content": inbound_message})

    # Ensure the conversation starts with a user message (Claude requirement)
    if messages and messages[0]["role"] != "user":
        messages.insert(0, {"role": "user", "content": "(conversation started by AI outreach)"})

    return messages


async def _call_claude(system_prompt: str, messages: List[Dict]) -> str:
    """Call the Claude API and return the response text.

    Includes a 15-second timeout (PERF-002) to avoid blocking SMS responses
    when the upstream LLM is slow or unavailable. Returns a safe fallback
    on timeout instead of raising.
    """
    client = _get_async_client()
    if not client:
        raise RuntimeError("Anthropic async client not available")

    from agents.anthropic_client import cached_system_block
    start = time.monotonic()
    try:
        resp = await asyncio.wait_for(
            client.messages.create(
                model=SMS_MODEL,
                max_tokens=SMS_MAX_TOKENS,
                system=cached_system_block(system_prompt),
                messages=messages,
            ),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start
        logger.error(
            "Claude API timeout after %.1fs for SMS generation — returning fallback",
            elapsed,
        )
        return _TIMEOUT_FALLBACK
    finally:
        elapsed = time.monotonic() - start
        if elapsed > 5.0:
            logger.warning("Claude API slow response: %.1fs", elapsed)

    text = resp.content[0].text.strip()
    # Strip wrapping quotes the model sometimes adds
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1]
    return text


def _validate_compliance(text: str) -> Tuple[bool, List[str]]:
    """Check response for ECOA violations and rate quotes.

    Returns (is_ok, list_of_flags).
    """
    flags = []

    for pattern in _ECOA_RE:
        match = pattern.search(text)
        if match:
            flags.append(f"ECOA_VIOLATION: '{match.group()}' found")

    for pattern in _RATE_RE:
        match = pattern.search(text)
        if match:
            flags.append(f"RATE_QUOTE: '{match.group()}' found")

    return (len(flags) == 0, flags)


def _determine_next_question(lead_ctx: Dict) -> str:
    """Figure out which qualifying question to ask next based on what's missing."""
    questions = [
        ("loan_type", "What type of loan they're looking for (purchase, refinance, etc.)"),
        ("loan_amount", "What loan amount or purchase price they're considering"),
        ("credit_score", "Their approximate credit score range"),
        ("employment_status", "Their employment situation"),
        ("property_type", "What type of property they're interested in"),
    ]

    for field, question in questions:
        value = lead_ctx.get(field)
        if not value:
            return question

    return "Try to set an appointment with the loan officer — all key qualification questions answered"


def _map_lead_stage_to_convo_stage(stage: str) -> str:
    """Map CRM lead stage to a conversation-friendly stage label."""
    stage_upper = (stage or "").upper()

    if stage_upper in ("NEW", ""):
        return "greeting — introduce yourself and start qualifying"
    if stage_upper in ("CONTACTED", "ATTEMPTED_CONTACT"):
        return "qualifying — gathering loan details"
    if stage_upper in ("QUALIFIED", "PRE_QUALIFIED", "PRE-QUALIFIED"):
        return "scheduling — try to book an appointment with the LO"
    if stage_upper in ("APPLICATION", "DISCLOSED", "PROCESSING"):
        return "nurturing — borrower is in process, keep them informed and engaged"
    if stage_upper in ("NURTURE",):
        return "re-engagement — warm them back up, check if circumstances changed"
    if stage_upper in ("DEAD", "DOES_NOT_QUALIFY", "WITHDRAWN"):
        return "closed — be polite, leave door open for future"

    return "qualifying — gathering loan details"


def _get_fallback_response(lead_ctx: Dict, history: List[Dict]) -> str:
    """Template fallback when Claude is unavailable or compliance fails."""
    name = lead_ctx.get("first_name") or "there"
    lo_name = lead_ctx.get("lo_name", "your loan officer")
    msg_count = len([m for m in history if m.get("role") == "assistant"])

    fallbacks = [
        f"Hi {name}! Thanks for reaching out. I'd love to help with your mortgage questions. What are you looking for?",
        f"Thanks for the info, {name}! Let me connect you with {lo_name} who can give you personalized guidance.",
        f"Great question, {name}! {lo_name} would be the best person to walk you through the details. Want me to set up a quick call?",
        f"Appreciate your interest, {name}! Would you like to schedule a time to chat with {lo_name}?",
    ]

    # Rotate through fallbacks based on message count to avoid repetition
    return fallbacks[msg_count % len(fallbacks)]


def _proactive_fallback(
    trigger_type: str,
    name: str,
    lo_name: str,
    trigger_data: Dict,
) -> str:
    """Fallback templates for proactive messages when Claude is unavailable."""
    fallbacks = {
        "rate_alert": f"Hey {name}, rates just moved in a favorable direction! Want to chat with {lo_name} about what this means for you?",
        "follow_up": f"Hi {name}, just checking in on your mortgage plans. Any questions I can help with?",
        "appointment_reminder": f"Reminder: your call with {lo_name} is {trigger_data.get('appointment_time', 'coming up soon')}. Looking forward to it!",
        "milestone": f"Great news, {name}! Your loan hit a milestone. {lo_name} will be in touch with details soon.",
    }
    return fallbacks.get(trigger_type, f"Hi {name}, reaching out to see how things are going. Let us know if you need anything!")
