"""
Voice Context Builder — Cross-channel context injection for AI calls

Provides rich context for:
  1. Inbound callbacks: When a borrower calls back after voicemail/SMS, the AI
     knows who they are, what was discussed, and what they need.
  2. Outbound speed-to-lead: Personalized greeting with source, qualification
     progress, and any prior SMS conversation.
  3. Live transfer whisper: Compressed spoken briefing for the LO including
     cross-channel engagement history.
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TTS text sanitization (AGENT-007: prevent prompt/SSML injection)
# ---------------------------------------------------------------------------

# Pattern to strip SSML-like tags and common prompt-injection markers
_SSML_TAG_RE = re.compile(r"</?(?:speak|break|phoneme|prosody|say-as|sub|emphasis|audio|voice|p|s)\b[^>]*>", re.IGNORECASE)
_PROMPT_INJECTION_RE = re.compile(
    r"(?:system\s*:|ignore\s+previous|you\s+are\s+now|forget\s+(?:all|your)|"
    r"new\s+instructions|override|<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\])",
    re.IGNORECASE,
)


def _sanitize_tts_text(text_val: str, max_length: int = 200) -> str:
    """
    Sanitize text before injecting into TTS/whisper/prompt strings.

    - Strips SSML tags that could manipulate speech synthesis.
    - Removes prompt-injection patterns.
    - Strips non-printable / special control characters.
    - Limits length to ``max_length`` characters.
    """
    if not text_val:
        return ""
    # Remove SSML tags
    cleaned = _SSML_TAG_RE.sub("", text_val)
    # Remove prompt-injection patterns
    cleaned = _PROMPT_INJECTION_RE.sub("", cleaned)
    # Strip non-printable chars except basic whitespace
    cleaned = re.sub(r"[^\x20-\x7E\n\t]", "", cleaned)
    # Collapse excessive whitespace
    cleaned = re.sub(r"\s{3,}", "  ", cleaned).strip()
    # Truncate
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rsplit(" ", 1)[0] + "..."
    return cleaned


# ---------------------------------------------------------------------------
# Phone normalization (local copy to avoid circular imports)
# ---------------------------------------------------------------------------

def _normalize_phone(phone: str) -> str:
    """Normalize phone to last 10 digits for matching."""
    if not phone:
        return ""
    return "".join(filter(str.isdigit, phone))[-10:]


# ---------------------------------------------------------------------------
# Internal data-fetching helpers
# ---------------------------------------------------------------------------

def _find_lead_by_phone(
    db: Session,
    caller_phone: str,
    organization_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Look up the most recent lead matching a phone number."""
    phone_clean = _normalize_phone(caller_phone)
    if not phone_clean or len(phone_clean) < 10:
        return None

    try:
        params: Dict[str, Any] = {"phone_pattern": f"%{phone_clean}"}
        org_clause = ""
        if organization_id:
            org_clause = "AND l.organization_id = :org_id"
            params["org_id"] = organization_id

        row = db.execute(text(f"""
            SELECT l.id, l.first_name, l.last_name, l.email, l.phone,
                   l.stage, l.source, l.ai_score, l.sentiment,
                   l.loan_type, l.loan_amount, l.credit_score,
                   l.property_type, l.preapproval_amount,
                   l.next_action, l.notes, l.owner_id,
                   l.organization_id, l.last_contact,
                   l.debt_to_income, l.employment_status,
                   l.annual_income, l.first_time_buyer
            FROM leads l
            WHERE l.phone LIKE :phone_pattern
            {org_clause}
            ORDER BY l.last_contact DESC NULLS LAST, l.created_at DESC
            LIMIT 1
        """), params).fetchone()

        if not row:
            return None

        return {
            "id": row.id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "full_name": f"{row.first_name or ''} {row.last_name or ''}".strip() or None,
            "email": row.email,
            "phone": row.phone,
            "stage": row.stage,
            "source": row.source,
            "ai_score": row.ai_score,
            "sentiment": row.sentiment,
            "loan_type": row.loan_type,
            "loan_amount": float(row.loan_amount) if row.loan_amount else None,
            "credit_score": row.credit_score,
            "property_type": row.property_type,
            "preapproval_amount": float(row.preapproval_amount) if row.preapproval_amount else None,
            "next_action": row.next_action,
            "notes": row.notes,
            "owner_id": row.owner_id,
            "organization_id": row.organization_id,
            "last_contact": row.last_contact,
            "debt_to_income": float(row.debt_to_income) if row.debt_to_income else None,
            "employment_status": row.employment_status,
            "annual_income": float(row.annual_income) if row.annual_income else None,
            "first_time_buyer": row.first_time_buyer,
        }
    except Exception as e:
        logger.warning("Lead lookup by phone failed", extra={
            "organization_id": organization_id,
            "error": str(e),
        })
        return None


def _get_lead_by_id(
    db: Session,
    lead_id: int,
    organization_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch lead data by ID."""
    try:
        params: Dict[str, Any] = {"lid": lead_id}
        org_clause = ""
        if organization_id:
            org_clause = "AND l.organization_id = :org_id"
            params["org_id"] = organization_id

        row = db.execute(text(f"""
            SELECT l.id, l.first_name, l.last_name, l.email, l.phone,
                   l.stage, l.source, l.ai_score, l.sentiment,
                   l.loan_type, l.loan_amount, l.credit_score,
                   l.property_type, l.preapproval_amount,
                   l.next_action, l.notes, l.owner_id,
                   l.organization_id, l.last_contact,
                   l.debt_to_income, l.employment_status,
                   l.annual_income, l.first_time_buyer
            FROM leads l
            WHERE l.id = :lid
            {org_clause}
        """), params).fetchone()

        if not row:
            return None

        return {
            "id": row.id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "full_name": f"{row.first_name or ''} {row.last_name or ''}".strip() or None,
            "email": row.email,
            "phone": row.phone,
            "stage": row.stage,
            "source": row.source,
            "ai_score": row.ai_score,
            "sentiment": row.sentiment,
            "loan_type": row.loan_type,
            "loan_amount": float(row.loan_amount) if row.loan_amount else None,
            "credit_score": row.credit_score,
            "property_type": row.property_type,
            "preapproval_amount": float(row.preapproval_amount) if row.preapproval_amount else None,
            "next_action": row.next_action,
            "notes": row.notes,
            "owner_id": row.owner_id,
            "organization_id": row.organization_id,
            "last_contact": row.last_contact,
            "debt_to_income": float(row.debt_to_income) if row.debt_to_income else None,
            "employment_status": row.employment_status,
            "annual_income": float(row.annual_income) if row.annual_income else None,
            "first_time_buyer": row.first_time_buyer,
        }
    except Exception as e:
        logger.warning("Lead lookup by ID failed", extra={
            "lead_id": lead_id,
            "organization_id": organization_id,
            "error": str(e),
        })
        return None


def _get_recent_activities(
    db: Session,
    lead_id: int,
    organization_id: Optional[int] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Fetch recent activity log entries for a lead."""
    try:
        params: Dict[str, Any] = {"lid": lead_id, "lim": limit}
        org_clause = ""
        if organization_id:
            org_clause = "AND organization_id = :org_id"
            params["org_id"] = organization_id

        rows = db.execute(text(f"""
            SELECT type, content, created_at
            FROM activities
            WHERE lead_id = :lid {org_clause}
            ORDER BY created_at DESC
            LIMIT :lim
        """), params).fetchall()

        return [
            {
                "type": row.type,
                "content": (row.content or "")[:300],
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    except Exception as e:
        logger.debug("Activity lookup failed (non-fatal)", extra={
            "lead_id": lead_id,
            "organization_id": organization_id,
            "error": str(e),
        })
        return []


def _get_recent_sms(
    db: Session,
    phone: str,
    organization_id: Optional[int],
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Fetch recent SMS conversation messages for a phone number."""
    phone_clean = _normalize_phone(phone)
    if not phone_clean:
        return []

    try:
        params: Dict[str, Any] = {"phone_pattern": f"%{phone_clean}", "lim": limit}
        org_clause = ""
        if organization_id:
            org_clause = "AND sc.organization_id = :org_id"
            params["org_id"] = organization_id

        rows = db.execute(text(f"""
            SELECT scm.direction, scm.content, scm.created_at
            FROM sms_ai_conversation_messages scm
            JOIN sms_ai_conversations sc ON sc.id = scm.conversation_id
            WHERE sc.phone_number LIKE :phone_pattern
            {org_clause}
            ORDER BY scm.created_at DESC
            LIMIT :lim
        """), params).fetchall()

        return [
            {
                "direction": row.direction,
                "content": (row.content or "")[:200],
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in reversed(rows)  # Chronological order
        ]
    except Exception as e:
        logger.debug("SMS lookup failed (non-fatal)", extra={
            "organization_id": organization_id,
            "error": str(e),
        })
        return []


def _get_recent_voicemail_drops(
    db: Session,
    lead_id: int,
    organization_id: Optional[int] = None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """Fetch recent voicemail drops sent to a lead."""
    try:
        params: Dict[str, Any] = {"lid": lead_id, "lim": limit}
        org_clause = ""
        if organization_id:
            org_clause = "AND vd.organization_id = :org_id"
            params["org_id"] = organization_id

        rows = db.execute(text(f"""
            SELECT vd.status, vd.created_at,
                   vt.message_text, vt.category
            FROM voicemail_drops vd
            LEFT JOIN voicemail_templates vt ON vt.id = vd.template_id
            WHERE vd.lead_id = :lid {org_clause}
            ORDER BY vd.created_at DESC
            LIMIT :lim
        """), params).fetchall()

        return [
            {
                "status": row.status,
                "message_text": (row.message_text or "")[:200],
                "category": row.category,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    except Exception as e:
        logger.debug("Voicemail drop lookup failed (non-fatal)", extra={
            "lead_id": lead_id,
            "organization_id": organization_id,
            "error": str(e),
        })
        return []


def _get_recent_calls(
    db: Session,
    phone: str,
    organization_id: Optional[int],
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Fetch recent call records for a phone number."""
    phone_clean = _normalize_phone(phone)
    if not phone_clean:
        return []

    try:
        params: Dict[str, Any] = {"phone_pattern": f"%{phone_clean}", "lim": limit}
        org_clause = ""
        if organization_id:
            org_clause = "AND organization_id = :org_id"
            params["org_id"] = organization_id

        rows = db.execute(text(f"""
            SELECT direction, status, summary, duration, created_at
            FROM vapi_calls
            WHERE phone_number LIKE :phone_pattern
            {org_clause}
            ORDER BY created_at DESC
            LIMIT :lim
        """), params).fetchall()

        return [
            {
                "direction": row.direction,
                "status": row.status,
                "summary": (row.summary or "")[:200],
                "duration": row.duration,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    except Exception as e:
        logger.debug("Call history lookup failed (non-fatal)", extra={
            "organization_id": organization_id,
            "error": str(e),
        })
        return []


def _get_lo_name(db: Session, owner_id: int) -> Optional[str]:
    """Look up the LO's name by user ID."""
    try:
        row = db.execute(text("""
            SELECT first_name, last_name FROM users WHERE id = :uid
        """), {"uid": owner_id}).fetchone()
        if row:
            return f"{row.first_name or ''} {row.last_name or ''}".strip() or None
    except Exception as e:
        logger.debug("LO name lookup failed: %s", e)
    return None


# ---------------------------------------------------------------------------
# Context text formatters
# ---------------------------------------------------------------------------

def _summarize_last_interaction(
    activities: List[Dict[str, Any]],
    calls: List[Dict[str, Any]],
    sms_messages: List[Dict[str, Any]],
    voicemail_drops: List[Dict[str, Any]],
) -> str:
    """Build a one-sentence summary of the most recent interaction."""
    # Collect all interactions with timestamps
    interactions = []

    for a in activities:
        if a.get("created_at"):
            interactions.append({
                "type": a["type"],
                "content": a["content"],
                "when": a["created_at"],
            })

    for c in calls:
        if c.get("created_at"):
            summary_text = c.get("summary") or f"{c.get('direction', 'unknown')} call ({c.get('status', 'unknown')})"
            interactions.append({
                "type": f"{c.get('direction', '')} call",
                "content": summary_text,
                "when": c["created_at"],
            })

    for s in sms_messages:
        if s.get("created_at"):
            interactions.append({
                "type": f"{s.get('direction', '')} SMS",
                "content": s["content"],
                "when": s["created_at"],
            })

    for vm in voicemail_drops:
        if vm.get("created_at"):
            interactions.append({
                "type": "voicemail drop",
                "content": vm.get("message_text") or vm.get("category") or "voicemail left",
                "when": vm["created_at"],
            })

    if not interactions:
        return "No prior interactions on record."

    # Sort by timestamp descending
    interactions.sort(key=lambda x: x["when"], reverse=True)
    latest = interactions[0]

    # Format relative time
    try:
        ts = datetime.fromisoformat(latest["when"].replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - ts
        if age < timedelta(hours=1):
            time_str = f"{int(age.total_seconds() / 60)} minutes ago"
        elif age < timedelta(days=1):
            time_str = f"{int(age.total_seconds() / 3600)} hours ago"
        else:
            time_str = f"{age.days} day{'s' if age.days != 1 else ''} ago"
    except Exception:
        time_str = "recently"

    content_preview = latest["content"][:120] if latest["content"] else ""
    return f"Last interaction ({time_str}): {latest['type']} - {content_preview}"


def _format_qualification_status(lead: Dict[str, Any]) -> str:
    """Summarize qualification data into a brief status line."""
    parts = []

    stage = lead.get("stage")
    if stage:
        parts.append(f"Stage: {stage}")

    credit = lead.get("credit_score")
    if credit:
        parts.append(f"Credit: {credit}")

    loan_type = lead.get("loan_type")
    if loan_type:
        parts.append(f"Loan type: {loan_type}")

    loan_amount = lead.get("loan_amount")
    if loan_amount:
        parts.append(f"Amount: ${int(loan_amount):,}")

    dti = lead.get("debt_to_income")
    if dti:
        parts.append(f"DTI: {dti:.1f}%")

    employment = lead.get("employment_status")
    if employment:
        parts.append(f"Employment: {employment}")

    if lead.get("first_time_buyer"):
        parts.append("First-time buyer")

    ai_score = lead.get("ai_score")
    if ai_score and ai_score != 50:  # 50 is default/unscored
        parts.append(f"AI score: {ai_score}")

    return ". ".join(parts) if parts else "No qualification data yet."


def _extract_key_concerns(
    sms_messages: List[Dict[str, Any]],
    activities: List[Dict[str, Any]],
    lead: Dict[str, Any],
) -> str:
    """Extract key borrower concerns from conversation history."""
    concerns = []

    # Check sentiment
    sentiment = lead.get("sentiment")
    if sentiment and sentiment not in ("neutral", "unknown"):
        concerns.append(f"Sentiment: {sentiment}")

    # Check notes for keywords
    notes = lead.get("notes") or ""
    concern_keywords = [
        "concerned", "worried", "question", "rate", "payment", "closing",
        "timeline", "approval", "denied", "credit", "down payment",
        "affordability", "pre-approval", "rush", "urgent",
    ]
    for kw in concern_keywords:
        if kw.lower() in notes.lower():
            # Extract a snippet around the keyword
            idx = notes.lower().find(kw.lower())
            start = max(0, idx - 30)
            end = min(len(notes), idx + len(kw) + 50)
            snippet = notes[start:end].strip()
            if snippet:
                concerns.append(snippet)
                break  # One concern from notes is enough

    # Check inbound SMS for questions/concerns
    for msg in sms_messages:
        if msg.get("direction") == "inbound":
            content = msg.get("content", "").lower()
            if any(q in content for q in ["?", "when", "how", "why", "concerned", "worried", "help"]):
                concerns.append(f"SMS: {msg['content'][:100]}")
                break

    return "; ".join(concerns[:3]) if concerns else "None identified."


# ---------------------------------------------------------------------------
# SMS conversation summary for outbound context
# ---------------------------------------------------------------------------

def _summarize_sms_conversation(sms_messages: List[Dict[str, Any]]) -> Optional[str]:
    """Build a brief summary of prior SMS conversation."""
    if not sms_messages:
        return None

    parts = []
    for msg in sms_messages[-5:]:  # Last 5 messages
        direction_label = "Them" if msg.get("direction") == "inbound" else "Us"
        content = msg.get("content", "")[:100]
        parts.append(f"{direction_label}: {content}")

    if parts:
        return "Prior SMS conversation:\n" + "\n".join(parts)
    return None


# ===========================================================================
# PUBLIC API — Three context builders
# ===========================================================================

def build_inbound_context(
    db: Session,
    caller_phone: str,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Build context for an inbound call (e.g., borrower calling back).

    Returns:
        {
            "system_prompt_addition": str,  # Inject into Vapi system prompt
            "lead": dict | None,            # Lead data if found
            "has_context": bool,            # Whether we found a matching lead
        }
    """
    try:
        lead = _find_lead_by_phone(db, caller_phone, organization_id)
        if not lead:
            return {
                "system_prompt_addition": (
                    "This caller is not yet in the system. Warmly introduce yourself "
                    "and ask for their name and how you can help with their mortgage needs."
                ),
                "lead": None,
                "has_context": False,
            }

        lead_id = lead["id"]
        lead_name = lead["full_name"] or "the borrower"

        # Fetch cross-channel engagement data
        lead_org_id = lead.get("organization_id") or organization_id
        activities = _get_recent_activities(db, lead_id, organization_id=lead_org_id, limit=10)
        sms_messages = _get_recent_sms(db, caller_phone, organization_id, limit=5)
        voicemail_drops = _get_recent_voicemail_drops(db, lead_id, organization_id=lead_org_id, limit=3)
        calls = _get_recent_calls(db, caller_phone, organization_id, limit=5)

        # Build context components
        last_interaction = _summarize_last_interaction(
            activities, calls, sms_messages, voicemail_drops,
        )
        qualification = _format_qualification_status(lead)
        concerns = _extract_key_concerns(sms_messages, activities, lead)

        # LO name for personalization
        lo_name = None
        if lead.get("owner_id"):
            lo_name = _get_lo_name(db, lead["owner_id"])

        # Build the prompt addition
        prompt_lines = [
            f"\n--- CALLER CONTEXT (from CRM) ---",
            f"This is a callback from {lead_name}.",
        ]

        if lo_name:
            prompt_lines.append(f"Their loan officer is {lo_name}.")

        prompt_lines.append(f"{last_interaction}")
        prompt_lines.append(f"Qualification: {qualification}")

        if concerns != "None identified.":
            prompt_lines.append(f"Key concerns: {concerns}")

        # Voicemail context is critical for callbacks
        if voicemail_drops:
            latest_vm = voicemail_drops[0]
            vm_msg = latest_vm.get("message_text", "")
            if vm_msg:
                prompt_lines.append(
                    f"We recently left them a voicemail: \"{vm_msg[:150]}\""
                )
            prompt_lines.append(
                "They are likely calling back about this voicemail. "
                "Acknowledge it naturally, e.g. 'Thanks for returning our call.'"
            )

        # SMS conversation context
        if sms_messages:
            sms_summary = _summarize_sms_conversation(sms_messages)
            if sms_summary:
                prompt_lines.append(f"\n{sms_summary}")
            prompt_lines.append(
                "Reference the SMS conversation naturally if relevant, but don't "
                "recite it verbatim."
            )

        # Next action from AI
        if lead.get("next_action"):
            prompt_lines.append(
                f"Recommended next step: {lead['next_action'][:150]}"
            )

        prompt_lines.append(
            "Use this context to provide a personalized, informed experience. "
            "Do not dump all this info at once -- weave it in naturally."
        )
        prompt_lines.append("--- END CALLER CONTEXT ---\n")

        system_prompt_addition = "\n".join(prompt_lines)

        logger.info(
            "Built inbound context for lead %s (%s) — %d activities, %d SMS, %d VM drops",
            lead_id, lead_name, len(activities), len(sms_messages), len(voicemail_drops),
            extra={
                "lead_id": lead_id,
                "organization_id": lead_org_id,
                "activities_count": len(activities),
                "sms_count": len(sms_messages),
                "vm_drops_count": len(voicemail_drops),
            },
        )

        return {
            "system_prompt_addition": system_prompt_addition,
            "lead": lead,
            "has_context": True,
        }

    except Exception as e:
        logger.error("build_inbound_context failed (returning generic)", extra={
            "organization_id": organization_id,
            "error": str(e),
        }, exc_info=True)
        return {
            "system_prompt_addition": "",
            "lead": None,
            "has_context": False,
        }


def build_outbound_context(
    db: Session,
    lead_id: int,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Build context for an outbound speed-to-lead call.

    Returns:
        {
            "system_prompt": str,       # Full system prompt with context
            "first_message": str,       # Personalized first message/greeting
            "voicemail_message": str,   # Context-aware voicemail if they don't answer
            "lead": dict | None,
        }
    """
    try:
        lead = _get_lead_by_id(db, lead_id, organization_id)
        if not lead:
            return {
                "system_prompt": None,
                "first_message": None,
                "voicemail_message": None,
                "lead": None,
            }

        lead_name = _sanitize_tts_text(lead.get("full_name") or "there", max_length=80)
        first_name = _sanitize_tts_text(lead.get("first_name") or lead_name, max_length=60)
        source = lead.get("source")
        loan_type = lead.get("loan_type")
        phone = lead.get("phone") or ""

        # Fetch engagement history
        activities = _get_recent_activities(db, lead_id, organization_id=organization_id, limit=5)
        sms_messages = _get_recent_sms(db, phone, organization_id, limit=5)
        calls = _get_recent_calls(db, phone, organization_id, limit=3)

        # LO name
        lo_name = None
        if lead.get("owner_id"):
            raw_lo_name = _get_lo_name(db, lead["owner_id"])
            lo_name = _sanitize_tts_text(raw_lo_name, max_length=80) if raw_lo_name else None
        lo_display = lo_name or "your loan officer"

        # Build personalized first message
        greeting_parts = [f"Hi {first_name}!"]
        greeting_parts.append("This is Aria calling on behalf of")
        if lo_name:
            greeting_parts.append(f"{lo_name}, your loan officer.")
        else:
            greeting_parts.append("your loan officer at Perennia AI.")

        if source:
            source_display = source.replace("_", " ").title()
            greeting_parts.append(
                f"Thank you for your inquiry through {source_display}."
            )
        else:
            greeting_parts.append(
                "Thank you for your interest in mortgage options."
            )

        # If we've had SMS conversation, acknowledge it
        if sms_messages:
            greeting_parts.append(
                "I see we've been in touch via text. I wanted to follow up with a quick call."
            )

        greeting_parts.append("Do you have a moment to chat?")
        first_message = " ".join(greeting_parts)

        # Build enriched system prompt
        qualification = _format_qualification_status(lead)

        prompt_lines = [
            f"You are Aria, an AI assistant for a mortgage loan officer at Perennia AI. "
            f"You are making a speed-to-lead callback to {lead_name} who expressed "
            f"interest in mortgage services.",
        ]

        if source:
            prompt_lines.append(f"Lead source: {source.replace('_', ' ').title()}.")

        prompt_lines.append(f"\nKnown qualification data: {qualification}")

        # Include SMS conversation context
        if sms_messages:
            sms_summary = _summarize_sms_conversation(sms_messages)
            if sms_summary:
                prompt_lines.append(f"\n{sms_summary}")
            prompt_lines.append(
                "Build on what was discussed via SMS. Don't repeat questions "
                "they've already answered."
            )

        # Prior call attempts
        outbound_calls = [c for c in calls if c.get("direction") == "outbound"]
        if outbound_calls:
            prompt_lines.append(
                f"\nNote: We have made {len(outbound_calls)} prior call attempt(s) "
                f"to this borrower."
            )
            latest_call = outbound_calls[0]
            if latest_call.get("summary"):
                prompt_lines.append(
                    f"Last call summary: {latest_call['summary'][:150]}"
                )

        prompt_lines.append(
            f"\nYour goals:\n"
            f"1) Confirm the lead's interest and introduce yourself warmly.\n"
            f"2) Ask about their timeline, loan type, and property location "
            f"(skip questions where we already have answers).\n"
            f"3) Qualify: credit score range, employment, down payment "
            f"(skip what we already know).\n"
            f"4) Offer to schedule a consultation with {lo_display}.\n"
            f"5) If they want to schedule, confirm a time.\n\n"
            f"Be professional, warm, and concise. Do not pressure or rush them. "
            f"If they ask to be called back later, note the preferred time. "
            f"If they are not interested, thank them and end gracefully."
        )

        system_prompt = "\n".join(prompt_lines)

        # Build context-aware voicemail message
        vm_parts = [f"Hi {first_name}, this is a message from"]
        if lo_name:
            vm_parts.append(f"{lo_name}'s team at Perennia AI.")
        else:
            vm_parts.append("your loan officer's team at Perennia AI.")

        if source:
            vm_parts.append(
                f"We received your mortgage inquiry through {source.replace('_', ' ').title()}"
                f" and wanted to connect."
            )
        else:
            vm_parts.append(
                "We received your mortgage inquiry and wanted to connect."
            )

        if lo_name:
            vm_parts.append(
                f"{lo_name} will be reaching out shortly. Thank you!"
            )
        else:
            vm_parts.append("Your loan officer will be reaching out shortly. Thank you!")

        voicemail_message = " ".join(vm_parts)

        logger.info(
            "Built outbound context for lead %s (%s) — source=%s, %d SMS, %d prior calls",
            lead_id, lead_name, source, len(sms_messages), len(outbound_calls),
            extra={
                "lead_id": lead_id,
                "organization_id": organization_id,
                "source": source,
                "sms_count": len(sms_messages),
                "prior_calls": len(outbound_calls),
            },
        )

        return {
            "system_prompt": system_prompt,
            "first_message": first_message,
            "voicemail_message": voicemail_message,
            "lead": lead,
        }

    except Exception as e:
        logger.error("build_outbound_context failed (returning None)", extra={
            "lead_id": lead_id,
            "organization_id": organization_id,
            "error": str(e),
        }, exc_info=True)
        return {
            "system_prompt": None,
            "first_message": None,
            "voicemail_message": None,
            "lead": None,
        }


def _load_lead_with_engagement(
    db: Session,
    lead_id: int,
    organization_id: Optional[int],
) -> Optional[Dict[str, Any]]:
    """
    Load lead data and all cross-channel engagement history in a single pass.

    PERF-010: Consolidates what was previously multiple separate DB round-trips
    into a single function that can be called once and the result passed around.
    """
    lead = _get_lead_by_id(db, lead_id, organization_id)
    if not lead:
        return None

    phone = lead.get("phone") or ""
    lead_org_id = lead.get("organization_id") or organization_id

    lead["_engagement"] = {
        "sms_messages": _get_recent_sms(db, phone, organization_id, limit=5),
        "calls": _get_recent_calls(db, phone, organization_id, limit=5),
        "voicemail_drops": _get_recent_voicemail_drops(db, lead_id, organization_id=lead_org_id, limit=3),
        "activities": _get_recent_activities(db, lead_id, organization_id=lead_org_id, limit=10),
    }
    return lead


def build_transfer_whisper(
    db: Session,
    lead_id: int,
    organization_id: Optional[int] = None,
    current_call_summary: Optional[str] = None,
) -> str:
    """
    Build an enhanced whisper briefing for live transfer to an LO.

    The whisper is designed to be spoken in ~15 seconds via TTS,
    giving the LO maximum context before joining the call.

    Returns a TTS-friendly spoken text string.
    """
    try:
        # PERF-010: Single consolidated load of lead + engagement data
        lead = _load_lead_with_engagement(db, lead_id, organization_id)
        if not lead:
            if current_call_summary:
                safe_summary = _sanitize_tts_text(current_call_summary)
                return f"Incoming transfer. {safe_summary}"
            return "Incoming transfer. No lead data available."

        # AGENT-007: Sanitize all lead-sourced text before TTS injection
        lead_name = _sanitize_tts_text(lead.get("full_name") or "Unknown caller", max_length=80)

        # Use pre-loaded engagement data (no additional DB queries)
        engagement = lead.get("_engagement", {})
        sms_messages = engagement.get("sms_messages", [])
        voicemail_drops = engagement.get("voicemail_drops", [])

        # Build concise spoken briefing
        parts = [f"Incoming transfer from {lead_name}."]

        # Loan info (most important for LO)
        loan_type = lead.get("loan_type")
        loan_amount = lead.get("loan_amount")
        credit = lead.get("credit_score")

        if loan_type:
            parts.append(f"{loan_type.replace('_', ' ').title()} loan.")
        if loan_amount:
            parts.append(f"Amount: ${int(loan_amount):,}.")
        if credit:
            parts.append(f"Credit: {credit}.")

        # Property
        prop_type = lead.get("property_type")
        if prop_type:
            parts.append(f"Property: {prop_type.replace('_', ' ')}.")

        # Current call context (what the AI just discussed)
        if current_call_summary:
            summary_short = _sanitize_tts_text(current_call_summary, max_length=150)
            parts.append(f"In this call they discussed: {summary_short}.")

        # Cross-channel highlights (brief)
        if sms_messages:
            inbound_sms = [m for m in sms_messages if m.get("direction") == "inbound"]
            if inbound_sms:
                last_sms = _sanitize_tts_text(inbound_sms[-1]["content"], max_length=80)
                parts.append(f"Last text from them: {last_sms}.")

        if voicemail_drops:
            parts.append("We left a voicemail previously.")

        # Stage / sentiment
        stage = lead.get("stage")
        if stage and stage.upper() not in ("NEW", "UNKNOWN"):
            parts.append(f"Stage: {stage}.")

        sentiment = lead.get("sentiment")
        if sentiment and sentiment not in ("neutral", "unknown"):
            parts.append(f"Sentiment: {sentiment}.")

        # Key concerns from notes
        notes = lead.get("notes")
        if notes:
            first_sentence = _sanitize_tts_text(
                notes.split(".")[0].strip(), max_length=80,
            )
            if first_sentence:
                parts.append(f"Note: {first_sentence}.")

        whisper_text = " ".join(parts)

        # Cap total length for ~15 second TTS (approx 3 words/sec = 45 words)
        words = whisper_text.split()
        if len(words) > 55:
            whisper_text = " ".join(words[:55]) + "."

        logger.info(
            "Built transfer whisper for lead %s (%d words)",
            lead_id, len(whisper_text.split()),
            extra={
                "lead_id": lead_id,
                "organization_id": organization_id,
                "word_count": len(whisper_text.split()),
            },
        )

        return whisper_text

    except Exception as e:
        logger.error("build_transfer_whisper failed", extra={
            "lead_id": lead_id,
            "organization_id": organization_id,
            "error": str(e),
        }, exc_info=True)
        if current_call_summary:
            safe_summary = _sanitize_tts_text(current_call_summary)
            return f"Incoming transfer. {safe_summary}"
        return "Incoming transfer. No lead data available."
