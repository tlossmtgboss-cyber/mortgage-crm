import logging
import os
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

MODEL_VERSION = os.getenv("SMS_AI_MODEL_VERSION", "claude-sonnet-4-20250514")

SYSTEM_PROMPT = (
    "You are Aria, an AI assistant for a mortgage loan officer. "
    "Generate a professional, warm SMS response to this borrower message. "
    "Keep it under 160 characters when possible, max 320. "
    "Be helpful and action-oriented. Never discuss rates, fees, or make "
    "commitments the LO hasn't approved. If unsure, suggest the LO call them directly."
)

CATEGORY_KEYWORDS = {
    "scheduling": ["schedule", "appointment", "meet", "meeting", "calendar", "available", "time", "when can", "set up"],
    "question": ["what", "how", "why", "can you", "do i", "is there", "tell me", "explain", "?"],
    "follow_up": ["checking in", "follow up", "following up", "any update", "status", "haven't heard", "waiting"],
    "rate_inquiry": ["rate", "rates", "interest", "apr", "points", "lock", "pricing"],
    "document_request": ["document", "documents", "doc", "docs", "upload", "send you", "paperwork", "tax", "w2", "paystub", "bank statement"],
    "greeting": ["hello", "hi", "hey", "good morning", "good afternoon", "good evening", "thanks", "thank you", "appreciate"],
    "complaint": ["unhappy", "frustrated", "disappointed", "upset", "angry", "terrible", "worst", "complain", "unacceptable", "ridiculous"],
    "general": [],
}

PRIORITY_KEYWORDS = {
    "urgent": ["asap", "emergency", "urgent", "help", "immediately", "right now", "critical"],
    "high": ["rate", "rates", "document", "docs", "question", "concerned", "worried", "issue", "problem"],
    "low": ["hello", "hi", "hey", "thanks", "thank you", "appreciate", "good morning", "good afternoon"],
}

WELL_UNDERSTOOD_CATEGORIES = {"scheduling", "greeting", "document_request", "follow_up"}


def classify_message(inbound_message: str) -> Tuple[str, str]:
    msg_lower = inbound_message.lower().strip()

    best_category = "general"
    best_score = 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        if not keywords:
            continue
        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > best_score:
            best_score = score
            best_category = category

    priority = "normal"
    for p_level in ["urgent", "high", "low"]:
        if any(kw in msg_lower for kw in PRIORITY_KEYWORDS[p_level]):
            priority = p_level
            break

    if best_score == 0 and len(msg_lower) > 20:
        try:
            from anthropic import Anthropic
            client = Anthropic()
            response = client.messages.create(
                model=MODEL_VERSION,
                max_tokens=100,
                messages=[{"role": "user", "content": f"Classify this SMS from a mortgage borrower into exactly one category: scheduling, question, follow_up, rate_inquiry, document_request, greeting, complaint, general. Also classify priority: urgent, high, normal, low. Reply with JSON only: {{\"category\": \"...\", \"priority\": \"...\"}}\n\nMessage: {inbound_message}"}],
                system="You are a message classifier. Respond with valid JSON only.",
            )
            parsed = json.loads(response.content[0].text)
            best_category = parsed.get("category", "general")
            priority = parsed.get("priority", "normal")
        except Exception as e:
            logger.exception("Claude classification failed, using keyword result: %s", e)

    return best_category, priority


def generate_recommendation(db: Session, task_id: int, organization_id: int) -> dict:
    row = db.execute(
        text("SELECT id, phone_number, lead_id, inbound_message, category, priority FROM sms_tasks WHERE id = :tid AND organization_id = :oid"),
        {"tid": task_id, "oid": organization_id},
    ).mappings().first()

    if not row:
        return {"recommendation": None, "confidence": 0, "reasoning": "Task not found", "category": None}

    phone_number = row["phone_number"]
    lead_id = row["lead_id"]
    inbound_message = row["inbound_message"]
    category = row["category"] or "general"
    priority = row["priority"] or "normal"

    if not category or category == "general":
        category, priority = classify_message(inbound_message)
        db.execute(
            text("UPDATE sms_tasks SET category = :cat, priority = :pri WHERE id = :tid"),
            {"cat": category, "pri": priority, "tid": task_id},
        )

    context_prompt = _build_context_prompt(db, phone_number, lead_id, organization_id)
    patterns = _get_similar_patterns(db, category, organization_id)

    confidence = 30
    has_patterns = False
    has_lead_context = False
    has_conversation_history = False

    if patterns:
        high_success = [p for p in patterns if p.get("success_rate", 0) > 0.7]
        if high_success:
            confidence += 20
            has_patterns = True

    if "Lead:" in context_prompt:
        confidence += 15
        has_lead_context = True

    if "Conversation History:" in context_prompt:
        confidence += 10
        has_conversation_history = True

    if category in WELL_UNDERSTOOD_CATEGORIES:
        confidence += 15

    confidence = min(confidence, 95)

    pattern_section = ""
    if patterns:
        examples = "\n".join(f"- \"{p['response_template']}\" (success: {p['success_rate']:.0%})" for p in patterns[:3])
        pattern_section = f"\n\nSuccessful response templates for {category} messages:\n{examples}"

    prompt = f"""Inbound SMS from borrower: "{inbound_message}"

Category: {category}
Priority: {priority}

{context_prompt}{pattern_section}

Generate a single SMS reply. No quotes, no explanation, just the message text."""

    try:
        from anthropic import Anthropic
        client = Anthropic()
        response = client.messages.create(
            model=MODEL_VERSION,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
            system=SYSTEM_PROMPT,
        )
        recommendation = response.content[0].text.strip().strip('"').strip("'")
    except Exception as e:
        logger.exception("Claude API failed for task %d: %s", task_id, e)
        recommendation = "Thanks for reaching out! Your loan officer will get back to you shortly."
        confidence = 10
        category = category or "general"

    now = datetime.now(timezone.utc)
    reasoning_parts = []
    if has_lead_context:
        reasoning_parts.append("lead context available")
    if has_conversation_history:
        reasoning_parts.append("conversation history found")
    if has_patterns:
        reasoning_parts.append("matched high-success patterns")
    reasoning_parts.append(f"category={category}")
    reasoning = "; ".join(reasoning_parts)

    db.execute(
        text("""
            UPDATE sms_tasks
            SET ai_recommendation = :rec,
                ai_confidence = :conf,
                ai_reasoning = :reasoning,
                ai_model_version = :model,
                ai_generated_at = :gen_at,
                category = :cat,
                priority = :pri,
                updated_at = :now
            WHERE id = :tid AND organization_id = :oid
        """),
        {
            "rec": recommendation,
            "conf": confidence,
            "reasoning": reasoning,
            "model": MODEL_VERSION,
            "gen_at": now,
            "cat": category,
            "pri": priority,
            "now": now,
            "tid": task_id,
            "oid": organization_id,
        },
    )

    db.execute(
        text("""
            INSERT INTO sms_ai_audit_log (organization_id, task_id, action, details, created_at)
            VALUES (:oid, :tid, :action, :details, :now)
        """),
        {
            "oid": organization_id,
            "tid": task_id,
            "action": "recommendation_generated",
            "details": json.dumps({
                "model": MODEL_VERSION,
                "confidence": confidence,
                "category": category,
                "priority": priority,
                "message_length": len(inbound_message),
                "recommendation_length": len(recommendation),
                "has_patterns": has_patterns,
                "has_lead_context": has_lead_context,
                "has_conversation_history": has_conversation_history,
            }),
            "now": now,
        },
    )

    db.commit()

    return {
        "recommendation": recommendation,
        "confidence": confidence,
        "reasoning": reasoning,
        "category": category,
    }


def regenerate_recommendation(db: Session, task_id: int, organization_id: int, feedback: str = "") -> dict:
    row = db.execute(
        text("SELECT id, phone_number, lead_id, inbound_message, category, priority, ai_recommendation, ai_reasoning FROM sms_tasks WHERE id = :tid AND organization_id = :oid"),
        {"tid": task_id, "oid": organization_id},
    ).mappings().first()

    if not row:
        return {"recommendation": None, "confidence": 0, "reasoning": "Task not found", "category": None}

    phone_number = row["phone_number"]
    lead_id = row["lead_id"]
    inbound_message = row["inbound_message"]
    category = row["category"] or "general"
    priority = row["priority"] or "normal"
    previous_recommendation = row["ai_recommendation"]

    context_prompt = _build_context_prompt(db, phone_number, lead_id, organization_id)
    patterns = _get_similar_patterns(db, category, organization_id)

    confidence = 30
    has_patterns = False
    has_lead_context = False
    has_conversation_history = False

    if patterns:
        high_success = [p for p in patterns if p.get("success_rate", 0) > 0.7]
        if high_success:
            confidence += 20
            has_patterns = True

    if "Lead:" in context_prompt:
        confidence += 15
        has_lead_context = True
    if "Conversation History:" in context_prompt:
        confidence += 10
        has_conversation_history = True
    if category in WELL_UNDERSTOOD_CATEGORIES:
        confidence += 15
    confidence = min(confidence, 95)

    pattern_section = ""
    if patterns:
        examples = "\n".join(f"- \"{p['response_template']}\" (success: {p['success_rate']:.0%})" for p in patterns[:3])
        pattern_section = f"\n\nSuccessful response templates for {category} messages:\n{examples}"

    feedback_section = ""
    if previous_recommendation:
        feedback_section = f"\n\nPrevious AI recommendation (rejected): \"{previous_recommendation}\""
    if feedback:
        feedback_section += f"\nUser feedback: {feedback}"

    prompt = f"""Inbound SMS from borrower: "{inbound_message}"

Category: {category}
Priority: {priority}

{context_prompt}{pattern_section}{feedback_section}

Generate a new, improved SMS reply incorporating the feedback. No quotes, no explanation, just the message text."""

    try:
        from anthropic import Anthropic
        client = Anthropic()
        response = client.messages.create(
            model=MODEL_VERSION,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
            system=SYSTEM_PROMPT,
        )
        recommendation = response.content[0].text.strip().strip('"').strip("'")
    except Exception as e:
        logger.exception("Claude API failed for regeneration of task %d: %s", task_id, e)
        recommendation = "Thanks for reaching out! Your loan officer will get back to you shortly."
        confidence = 10

    now = datetime.now(timezone.utc)
    reasoning_parts = ["regenerated"]
    if feedback:
        reasoning_parts.append(f"feedback: {feedback[:100]}")
    if has_lead_context:
        reasoning_parts.append("lead context available")
    if has_conversation_history:
        reasoning_parts.append("conversation history found")
    if has_patterns:
        reasoning_parts.append("matched high-success patterns")
    reasoning = "; ".join(reasoning_parts)

    db.execute(
        text("""
            UPDATE sms_tasks
            SET ai_recommendation = :rec,
                ai_confidence = :conf,
                ai_reasoning = :reasoning,
                ai_model_version = :model,
                ai_generated_at = :gen_at,
                updated_at = :now
            WHERE id = :tid AND organization_id = :oid
        """),
        {
            "rec": recommendation,
            "conf": confidence,
            "reasoning": reasoning,
            "model": MODEL_VERSION,
            "gen_at": now,
            "now": now,
            "tid": task_id,
            "oid": organization_id,
        },
    )

    db.execute(
        text("""
            INSERT INTO sms_ai_audit_log (organization_id, task_id, action, details, created_at)
            VALUES (:oid, :tid, :action, :details, :now)
        """),
        {
            "oid": organization_id,
            "tid": task_id,
            "action": "recommendation_regenerated",
            "details": json.dumps({
                "model": MODEL_VERSION,
                "confidence": confidence,
                "category": category,
                "feedback": feedback[:200] if feedback else None,
                "previous_recommendation_length": len(previous_recommendation) if previous_recommendation else 0,
            }),
            "now": now,
        },
    )

    db.commit()

    return {
        "recommendation": recommendation,
        "confidence": confidence,
        "reasoning": reasoning,
        "category": category,
    }


def _build_context_prompt(db: Session, phone_number: str, lead_id: Optional[int], organization_id: int) -> str:
    from telephony.phone_utils import normalize_phone
    phone_number = normalize_phone(phone_number)

    parts = []

    lead_row = None
    if lead_id:
        lead_row = db.execute(
            text("SELECT first_name, last_name, email, stage FROM leads WHERE id = :lid AND organization_id = :oid"),
            {"lid": lead_id, "oid": organization_id},
        ).mappings().first()
    elif phone_number:
        lead_row = db.execute(
            text("SELECT id, first_name, last_name, email, stage FROM leads WHERE phone = :phone AND organization_id = :oid LIMIT 1"),
            {"phone": phone_number, "oid": organization_id},
        ).mappings().first()
        if lead_row:
            lead_id = lead_row["id"]

    if lead_row:
        name = f"{lead_row['first_name'] or ''} {lead_row['last_name'] or ''}".strip()
        parts.append(f"Lead: {name or 'Unknown'}")
        if lead_row.get("email"):
            parts.append(f"Email: {lead_row['email']}")
        if lead_row.get("stage"):
            parts.append(f"Loan Stage: {lead_row['stage']}")

    if lead_id:
        notes = db.execute(
            text("SELECT content FROM lead_notes WHERE lead_id = :lid ORDER BY created_at DESC LIMIT 3"),
            {"lid": lead_id},
        ).mappings().all()
        if notes:
            note_texts = [n["content"][:100] for n in notes]
            parts.append(f"Recent Notes: {'; '.join(note_texts)}")

        loan_row = db.execute(
            text("SELECT loan_amount, loan_type, stage, property_address FROM loans WHERE lead_id = :lid AND organization_id = :oid AND stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN') ORDER BY created_at DESC LIMIT 1"),
            {"lid": lead_id, "oid": organization_id},
        ).mappings().first()
        if loan_row:
            loan_parts = []
            if loan_row.get("loan_type"):
                loan_parts.append(f"Type: {loan_row['loan_type']}")
            if loan_row.get("loan_amount"):
                loan_parts.append(f"Amount: ${loan_row['loan_amount']:,.0f}")
            if loan_row.get("stage"):
                loan_parts.append(f"Stage: {loan_row['stage']}")
            if loan_row.get("property_address"):
                loan_parts.append(f"Property: {loan_row['property_address']}")
            if loan_parts:
                parts.append(f"Active Loan: {', '.join(loan_parts)}")

    messages = db.execute(
        text("SELECT direction, body, created_at FROM sms_panel_messages WHERE phone = :phone AND organization_id = :oid ORDER BY created_at DESC LIMIT 10"),
        {"phone": phone_number, "oid": organization_id},
    ).mappings().all()
    if messages:
        history_lines = []
        for m in reversed(messages):
            direction = "Borrower" if m["direction"] == "inbound" else "LO"
            ts = m["created_at"].strftime("%m/%d %H:%M") if m["created_at"] else ""
            body = (m["body"] or "")[:120]
            history_lines.append(f"[{ts}] {direction}: {body}")
        parts.append(f"Conversation History:\n" + "\n".join(history_lines))

    return "\n".join(parts)


def _get_similar_patterns(db: Session, category: str, organization_id: int, limit: int = 5) -> List[dict]:
    rows = db.execute(
        text("""
            SELECT response_template, success_rate, times_used, category
            FROM sms_response_patterns
            WHERE organization_id = :oid AND category = :cat
            ORDER BY success_rate DESC, times_used DESC
            LIMIT :lim
        """),
        {"oid": organization_id, "cat": category, "lim": limit},
    ).mappings().all()

    return [dict(r) for r in rows]
