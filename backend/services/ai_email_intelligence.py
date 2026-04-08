"""
AI Email Intelligence Engine — hyper-personalized, context-aware email composition and timing.

The most intelligent outbound email system in mortgage:
  - compose_contextual_email: Claude-powered emails that read ALL lead context
  - determine_optimal_send_time: ML-style send-time optimization per lead
  - generate_follow_up_sequence: 3-email drip with unique angles per message
  - score_email_engagement: Per-lead engagement analytics and trend detection

All AI generation uses Claude claude-sonnet-4-20250514 via the Anthropic SDK.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, and_, desc, case
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Circuit breaker for Claude API (AGENT-005)
# ---------------------------------------------------------------------------
_circuit_consecutive_failures: int = 0
_circuit_open_until: float = 0.0  # monotonic timestamp
_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_COOLDOWN_SECONDS = 60.0


def _circuit_record_failure() -> None:
    """Record a Claude API failure and potentially open the circuit."""
    global _circuit_consecutive_failures, _circuit_open_until
    _circuit_consecutive_failures += 1
    if _circuit_consecutive_failures >= _CIRCUIT_FAILURE_THRESHOLD:
        _circuit_open_until = time.monotonic() + _CIRCUIT_COOLDOWN_SECONDS
        logger.warning(
            "Circuit breaker OPEN — %d consecutive Claude failures, skipping calls for %ds",
            _circuit_consecutive_failures,
            int(_CIRCUIT_COOLDOWN_SECONDS),
        )


def _circuit_record_success() -> None:
    """Reset the circuit breaker on a successful call."""
    global _circuit_consecutive_failures, _circuit_open_until
    _circuit_consecutive_failures = 0
    _circuit_open_until = 0.0


def _circuit_is_open() -> bool:
    """Return True if the circuit breaker is tripped and still in cooldown."""
    if _circuit_consecutive_failures < _CIRCUIT_FAILURE_THRESHOLD:
        return False
    if time.monotonic() >= _circuit_open_until:
        # Cooldown elapsed — allow a probe request
        return False
    return True


# ---------------------------------------------------------------------------
# ECOA compliance validation for AI-generated email content (COMP-004)
# ---------------------------------------------------------------------------
_ECOA_PROHIBITED_PATTERNS = [
    r"\b(race|racial|ethnicity|ethnic)\b",
    r"\b(religion|religious|church|mosque|synagogue|temple)\b",
    r"\b(sex|gender|sexual orientation|transgender)\b",
    r"\b(national origin|nationality|country of origin|immigrant|immigration)\b",
    r"\b(marital status|married|divorced|spouse|husband|wife)\b",
    r"\bage\b(?!\s*of\s*(loan|property|home|house))",
    r"\b(handicap|disability|disabled)\b",
    r"\b(familial status|pregnant|children|kids|family planning)\b",
]
_ECOA_RE = [re.compile(p, re.IGNORECASE) for p in _ECOA_PROHIBITED_PATTERNS]


def _validate_ecoa_compliance(text: str) -> Tuple[bool, List[str]]:
    """Check AI-generated email content for ECOA-prohibited demographic references.

    Returns (is_compliant, list_of_violations).
    """
    violations: List[str] = []
    for pattern in _ECOA_RE:
        match = pattern.search(text)
        if match:
            violations.append(f"ECOA_VIOLATION: '{match.group()}' found")
    return (len(violations) == 0), violations


# ---------------------------------------------------------------------------
# Token budget enforcement (AGENT-006)
# ---------------------------------------------------------------------------
_MAX_PROMPT_CHARS = 6000


def _enforce_token_budget(system_prompt: str, user_prompt: str) -> Tuple[str, str]:
    """Truncate prompts if combined length exceeds the character budget.

    System prompt gets priority (kept intact up to 60% of budget).
    User prompt fills the remainder. Truncation is at line boundaries where
    possible.
    """
    total = len(system_prompt) + len(user_prompt)
    if total <= _MAX_PROMPT_CHARS:
        return system_prompt, user_prompt

    sys_budget = int(_MAX_PROMPT_CHARS * 0.6)
    if len(system_prompt) > sys_budget:
        system_prompt = system_prompt[:sys_budget].rsplit("\n", 1)[0] + "\n[...truncated]"

    remaining = _MAX_PROMPT_CHARS - len(system_prompt)
    if len(user_prompt) > remaining:
        user_prompt = user_prompt[:remaining].rsplit("\n", 1)[0] + "\n[...truncated]"

    return system_prompt, user_prompt

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS_COMPOSE = 2048
MAX_TOKENS_SEQUENCE = 4096

# Industry benchmarks for optimal send times (hour in local time)
BENCHMARK_BEST_DAYS = {1, 2, 3}  # Tue, Wed, Thu (0=Mon)
BENCHMARK_BEST_HOURS = range(10, 14)  # 10am - 1pm
BENCHMARK_FALLBACK_HOUR = 10
BENCHMARK_FALLBACK_WEEKDAY = 1  # Tuesday

# Trigger event types
TRIGGER_RATE_DROP = "rate_drop"
TRIGGER_STALE_LEAD = "stale_lead"
TRIGGER_POST_CALL_FOLLOWUP = "post_call_followup"
TRIGGER_DOCUMENT_REMINDER = "document_reminder"
TRIGGER_PRE_APPROVAL_READY = "pre_approval_ready"
TRIGGER_CLOSING_PREP = "closing_prep"

VALID_TRIGGERS = {
    TRIGGER_RATE_DROP,
    TRIGGER_STALE_LEAD,
    TRIGGER_POST_CALL_FOLLOWUP,
    TRIGGER_DOCUMENT_REMINDER,
    TRIGGER_PRE_APPROVAL_READY,
    TRIGGER_CLOSING_PREP,
}


# ---------------------------------------------------------------------------
# Internal helpers — data gathering
# ---------------------------------------------------------------------------


def _safe_decimal(val) -> Optional[float]:
    """Convert Decimal/numeric to float safely for JSON serialization."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _get_lead_full_context(db: Session, lead_id: int, organization_id: int) -> Optional[Dict[str, Any]]:
    """Load comprehensive lead context: demographics, loan data, activities, stage history."""
    from database.models.lead_loan import Lead

    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.organization_id == organization_id,
    ).first()

    if not lead:
        return None

    ctx: Dict[str, Any] = {
        "lead_id": lead.id,
        "first_name": lead.first_name or (lead.name.split()[0] if lead.name else ""),
        "last_name": lead.last_name or "",
        "full_name": lead.name or "",
        "email": lead.email or "",
        "phone": lead.phone or "",
        "stage": lead.stage or "",
        "source": lead.source or "",
        "ai_score": lead.ai_score,
        "sentiment": lead.sentiment or "neutral",
        "next_action": lead.next_action or "",
        "loan_type": lead.loan_type or lead.loan_purpose or "",
        "loan_amount": _safe_decimal(lead.loan_amount),
        "credit_score": lead.credit_score,
        "debt_to_income": _safe_decimal(lead.debt_to_income),
        "property_type": lead.property_type or "",
        "property_value": _safe_decimal(lead.property_value),
        "down_payment": _safe_decimal(lead.down_payment),
        "interest_rate": _safe_decimal(lead.interest_rate),
        "monthly_payment": _safe_decimal(lead.monthly_payment),
        "preapproval_amount": _safe_decimal(lead.preapproval_amount),
        "employment_status": lead.employment_status or "",
        "annual_income": _safe_decimal(lead.annual_income),
        "first_time_buyer": lead.first_time_buyer or False,
        "city": getattr(lead, "city", "") or "",
        "state": getattr(lead, "state", "") or "",
        "closing_date": lead.closing_date.isoformat() if lead.closing_date else None,
        "lock_date": lead.lock_date.isoformat() if lead.lock_date else None,
        "lock_expiration": lead.lock_expiration.isoformat() if lead.lock_expiration else None,
        "last_contact": lead.last_contact.isoformat() if lead.last_contact else None,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "preferred_communication": lead.preferred_communication or "",
        "buying_timeline": lead.buying_timeline_category.value if lead.buying_timeline_category else "",
        "borrower_risk_profile": lead.borrower_risk_profile.value if lead.borrower_risk_profile else "",
        "target_payment": _safe_decimal(lead.target_payment),
        "expected_purchase_date": lead.expected_purchase_date.isoformat() if lead.expected_purchase_date else None,
        "program": lead.program or "",
    }

    return ctx


def _get_recent_activities(db: Session, lead_id: int, organization_id: Optional[int] = None, limit: int = 10) -> List[Dict[str, str]]:
    """Fetch the N most recent activities for a lead."""
    try:
        from database.models.communication import Activity
        filters = [Activity.lead_id == lead_id]
        if organization_id is not None:
            filters.append(Activity.organization_id == organization_id)
        activities = (
            db.query(Activity)
            .filter(*filters)
            .order_by(desc(Activity.created_at))
            .limit(limit)
            .all()
        )
        return [
            {
                "type": a.type.value if hasattr(a.type, "value") else str(a.type),
                "content": (a.content or "")[:200],
                "date": a.created_at.isoformat() if a.created_at else "",
            }
            for a in activities
        ]
    except Exception as e:
        logger.debug(
            "Could not fetch activities for lead %s: %s", lead_id, e,
            extra={"lead_id": lead_id, "organization_id": organization_id},
        )
        return []


def _get_outstanding_documents(db: Session, lead_id: int, organization_id: int) -> List[str]:
    """Return list of document types that are still needed for the lead's loan file."""
    try:
        from database.models.document import Document
        from database.enums import DocumentType

        # All possible required doc types for a standard mortgage
        standard_docs = {
            DocumentType.W2, DocumentType.PAYSTUB, DocumentType.TAX_RETURN_1040,
            DocumentType.BANK_STATEMENT, DocumentType.DRIVERS_LICENSE,
            DocumentType.HOMEOWNERS_INSURANCE, DocumentType.PURCHASE_CONTRACT,
        }

        existing = (
            db.query(Document.doc_type)
            .filter(
                Document.borrower_id == lead_id,
                Document.organization_id == organization_id,
                Document.status == "active",
            )
            .distinct()
            .all()
        )
        existing_types = {row[0] for row in existing}
        missing = standard_docs - existing_types
        return [dt.value for dt in missing]
    except Exception as e:
        logger.debug(
            "Could not check documents for lead %s: %s", lead_id, e,
            extra={"lead_id": lead_id, "organization_id": organization_id},
        )
        return ["Pay stubs (most recent 30 days)", "W-2s (last 2 years)", "Bank statements (last 2 months)", "Government-issued photo ID"]


def _get_rate_environment(db: Session, organization_id: int) -> Optional[Dict[str, Any]]:
    """Try to fetch current rate snapshot data if available."""
    try:
        # Check for rate data in org settings or a rate cache
        from database.models.core import Organization
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if org and org.settings:
            rates = org.settings.get("current_rates") or org.settings.get("rate_snapshot")
            if rates:
                return rates
    except Exception as e:
        logger.debug(
            "Could not fetch rate environment: %s", e,
            extra={"organization_id": organization_id},
        )
    return None


def _get_lo_context(db: Session, organization_id: int, user_id: Optional[int] = None) -> Dict[str, str]:
    """Build loan officer and company context for email signatures."""
    lo = {"full_name": "", "first_name": "", "nmls": "", "email": "", "company_name": "", "primary_color": "#1a73e8"}

    try:
        from database.models.core import Organization, User

        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if org:
            lo["company_name"] = org.name or ""
            lo["primary_color"] = org.booking_primary_color or "#1a73e8"

        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                lo["full_name"] = user.full_name or ""
                lo["first_name"] = user.first_name or ""
                lo["nmls"] = user.nmls_number or ""
                lo["email"] = user.email or ""
                # If user is in a branch with a company name, prefer that
                if user.branch_id:
                    from database.models.core import Branch
                    branch = db.query(Branch).filter(Branch.id == user.branch_id).first()
                    if branch and branch.company:
                        lo["company_name"] = branch.company
    except Exception as e:
        logger.debug(
            "Could not load LO context: %s", e,
            extra={"organization_id": organization_id},
        )

    return lo


def _get_email_tracking_history(db: Session, lead_id: int, organization_id: Optional[int] = None) -> Dict[str, Any]:
    """Aggregate email tracking events (opens, clicks) for a lead."""
    history: Dict[str, Any] = {
        "total_sent": 0,
        "total_opens": 0,
        "total_clicks": 0,
        "open_timestamps": [],
        "click_timestamps": [],
        "subjects_opened": [],
        "subjects_sent": [],
    }

    try:
        from database.models.communication import EmailMessage as EmailMessageModel
        from database.models.email_tracking import EmailTrackingEvent

        # Get all outbound emails for this lead
        email_filters = [
            EmailMessageModel.lead_id == lead_id,
            EmailMessageModel.direction == "outbound",
        ]
        if organization_id is not None:
            email_filters.append(EmailMessageModel.organization_id == organization_id)
        emails = (
            db.query(EmailMessageModel)
            .filter(*email_filters)
            .order_by(desc(EmailMessageModel.created_at))
            .all()
        )

        history["total_sent"] = len(emails)
        history["subjects_sent"] = [e.subject for e in emails if e.subject]

        # Gather tracking IDs from meta_data
        tracking_ids = []
        tracking_id_to_subject = {}
        for email in emails:
            if email.meta_data and isinstance(email.meta_data, dict):
                tid = email.meta_data.get("tracking_id")
                if tid:
                    tracking_ids.append(tid)
                    tracking_id_to_subject[tid] = email.subject

        if tracking_ids:
            events = (
                db.query(EmailTrackingEvent)
                .filter(EmailTrackingEvent.tracking_id.in_(tracking_ids))
                .order_by(EmailTrackingEvent.created_at)
                .all()
            )

            for ev in events:
                if ev.event_type == "open":
                    history["total_opens"] += 1
                    if ev.created_at:
                        history["open_timestamps"].append(ev.created_at.isoformat())
                    subj = tracking_id_to_subject.get(ev.tracking_id)
                    if subj and subj not in history["subjects_opened"]:
                        history["subjects_opened"].append(subj)
                elif ev.event_type == "click":
                    history["total_clicks"] += 1
                    if ev.created_at:
                        history["click_timestamps"].append(ev.created_at.isoformat())

    except Exception as e:
        logger.debug(
            "Could not aggregate email tracking for lead %s: %s", lead_id, e,
            extra={"lead_id": lead_id, "organization_id": organization_id},
        )

    return history


def _get_sms_response_times(db: Session, lead_id: int, organization_id: Optional[int] = None) -> List[datetime]:
    """Return timestamps of inbound SMS responses from the lead."""
    try:
        from database.models.communication import SMSMessage
        filters = [
            SMSMessage.lead_id == lead_id,
            SMSMessage.direction == "inbound",
        ]
        if organization_id is not None:
            filters.append(SMSMessage.organization_id == organization_id)
        msgs = (
            db.query(SMSMessage.created_at)
            .filter(*filters)
            .order_by(SMSMessage.created_at)
            .all()
        )
        return [m[0] for m in msgs if m[0]]
    except Exception as e:
        logger.debug(
            "Could not fetch SMS response times for lead %s: %s", lead_id, e,
            extra={"lead_id": lead_id, "organization_id": organization_id},
        )
        return []


# ---------------------------------------------------------------------------
# Claude AI call helper
# ---------------------------------------------------------------------------


async def _call_claude(system_prompt: str, user_prompt: str, max_tokens: int = MAX_TOKENS_COMPOSE) -> str:
    """Send a prompt to Claude and return the raw text response.

    Includes circuit-breaker gating (AGENT-005), token-budget enforcement
    (AGENT-006), and a 30-second asyncio timeout (PERF-004).

    Raises RuntimeError on failure so callers can fall back to templates.
    """
    # AGENT-005: circuit breaker check
    if _circuit_is_open():
        raise RuntimeError("Circuit breaker OPEN — Claude API calls suspended after consecutive failures")

    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic SDK not installed")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    # AGENT-006: enforce token budget before sending
    system_prompt, user_prompt = _enforce_token_budget(system_prompt, user_prompt)

    async def _do_call() -> str:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text.strip()

    try:
        # PERF-004: 30-second timeout for email composition
        result = await asyncio.wait_for(_do_call(), timeout=30.0)
        _circuit_record_success()
        return result
    except asyncio.TimeoutError:
        _circuit_record_failure()
        raise RuntimeError("Claude API timeout after 30s for email composition")
    except Exception:
        _circuit_record_failure()
        raise


def _parse_json_response(raw: str) -> Dict[str, Any]:
    """Parse a Claude response that should be JSON, handling code fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# Fallback templates (used when Claude is unavailable)
# ---------------------------------------------------------------------------


_FALLBACK_TEMPLATES: Dict[str, Dict[str, str]] = {
    TRIGGER_RATE_DROP: {
        "subject": "Rates Have Moved — Here's What It Means for You, {first_name}",
        "body_html": (
            "<p>Hi {first_name},</p>"
            "<p>Mortgage rates have shifted recently, and depending on your situation, "
            "this could mean meaningful savings on your monthly payment.</p>"
            "<p>I'd love to run a quick analysis for you — it only takes a few minutes "
            "and could save you thousands over the life of your loan.</p>"
            "<p>Want me to put together some numbers?</p>"
            "<p>Best regards,<br>{lo_name}<br>NMLS# {nmls}<br>{company_name}</p>"
        ),
    },
    TRIGGER_STALE_LEAD: {
        "subject": "Just Checking In, {first_name}",
        "body_html": (
            "<p>Hi {first_name},</p>"
            "<p>It's been a little while since we last connected, and I wanted to "
            "check in. There's no pressure at all — I'm here whenever you're ready.</p>"
            "<p>If anything has changed in your situation or if you have questions, "
            "I'm just a reply away.</p>"
            "<p>Best regards,<br>{lo_name}<br>NMLS# {nmls}<br>{company_name}</p>"
        ),
    },
    TRIGGER_POST_CALL_FOLLOWUP: {
        "subject": "Following Up on Our Conversation, {first_name}",
        "body_html": (
            "<p>Hi {first_name},</p>"
            "<p>Thank you for taking the time to speak with me. I wanted to follow up "
            "and make sure you have everything you need.</p>"
            "<p>If any questions come up, don't hesitate to reach out. I'm here to help "
            "make this process as smooth as possible.</p>"
            "<p>Best regards,<br>{lo_name}<br>NMLS# {nmls}<br>{company_name}</p>"
        ),
    },
    TRIGGER_DOCUMENT_REMINDER: {
        "subject": "Quick Reminder: Documents Needed, {first_name}",
        "body_html": (
            "<p>Hi {first_name},</p>"
            "<p>I wanted to send a friendly reminder that we still need a few documents "
            "to keep your loan file moving forward.</p>"
            "<p>The sooner we receive these, the sooner we can move to the next step. "
            "If you have any trouble locating them, I'm happy to help.</p>"
            "<p>Best regards,<br>{lo_name}<br>NMLS# {nmls}<br>{company_name}</p>"
        ),
    },
    TRIGGER_PRE_APPROVAL_READY: {
        "subject": "Great News — Your Pre-Approval Is Ready, {first_name}!",
        "body_html": (
            "<p>Hi {first_name},</p>"
            "<p>Congratulations! Your pre-approval is complete. This puts you in a strong "
            "position as you begin your home search.</p>"
            "<p>I'll be here to guide you through the next steps. Let's connect soon to "
            "discuss your options.</p>"
            "<p>Best regards,<br>{lo_name}<br>NMLS# {nmls}<br>{company_name}</p>"
        ),
    },
    TRIGGER_CLOSING_PREP: {
        "subject": "Getting Ready for Closing Day, {first_name}",
        "body_html": (
            "<p>Hi {first_name},</p>"
            "<p>We're getting close to the finish line! I wanted to share a few things "
            "to help you prepare for closing day.</p>"
            "<p>I'll be in touch with more details soon. If you have any questions in the "
            "meantime, don't hesitate to reach out.</p>"
            "<p>Best regards,<br>{lo_name}<br>NMLS# {nmls}<br>{company_name}</p>"
        ),
    },
}


def _render_fallback(trigger: str, variables: Dict[str, str]) -> Dict[str, str]:
    """Render a fallback template with variable substitution."""
    template = _FALLBACK_TEMPLATES.get(trigger, _FALLBACK_TEMPLATES[TRIGGER_STALE_LEAD])
    subject = template["subject"]
    body = template["body_html"]
    for key, val in variables.items():
        subject = subject.replace("{" + key + "}", str(val or ""))
        body = body.replace("{" + key + "}", str(val or ""))
    return {"subject": subject, "body_html": body}


def _wrap_html_email(body_html: str, primary_color: str = "#1a73e8") -> str:
    """Wrap email body in a professional HTML envelope with responsive styling."""
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<style>'
        'body { font-family: Arial, Helvetica, sans-serif; max-width: 600px; '
        'margin: 0 auto; padding: 20px; color: #333; font-size: 15px; line-height: 1.6; }'
        f'a {{ color: {primary_color}; text-decoration: none; }}'
        'a:hover { text-decoration: underline; }'
        '.signature { margin-top: 24px; padding-top: 16px; border-top: 1px solid #e0e0e0; '
        'font-size: 13px; color: #666; line-height: 1.5; }'
        '.footer { margin-top: 30px; padding-top: 15px; border-top: 1px solid #e0e0e0; '
        'font-size: 11px; color: #888; line-height: 1.6; }'
        '.highlight { font-weight: bold; color: #111; }'
        f'.cta {{ display: inline-block; padding: 10px 24px; background-color: {primary_color}; '
        'color: #fff !important; border-radius: 6px; text-decoration: none; font-weight: 600; '
        'margin: 12px 0; }}'
        'ul { padding-left: 20px; }'
        'li { margin-bottom: 6px; }'
        '</style>'
        '</head><body>'
        f'{body_html}'
        '</body></html>'
    )


def _build_compliance_footer(lo_name: str, nmls: str, company_name: str) -> str:
    """CAN-SPAM compliant footer."""
    return (
        '<div class="footer">'
        f'<p>{company_name}{f" | NMLS# {nmls}" if nmls else ""}</p>'
        '<p>Equal Housing Lender | Equal Housing Opportunity</p>'
        '</div>'
    )


# ---------------------------------------------------------------------------
# Public API: compose_contextual_email
# ---------------------------------------------------------------------------


async def compose_contextual_email(
    db: Session,
    lead_id: int,
    organization_id: int,
    trigger_event: str,
    user_id: Optional[int] = None,
    extra_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Generate a hyper-personalized email using full lead context and Claude AI.

    Args:
        db: SQLAlchemy session.
        lead_id: Target lead.
        organization_id: Tenant scope.
        trigger_event: One of VALID_TRIGGERS.
        user_id: The LO sending the email (for signature context).
        extra_context: Optional overrides (e.g., specific rate data, call notes).

    Returns:
        {"subject": str, "body_html": str} ready to send.
    """
    if trigger_event not in VALID_TRIGGERS:
        raise ValueError(f"Invalid trigger_event '{trigger_event}'. Must be one of: {', '.join(sorted(VALID_TRIGGERS))}")

    # ---- Gather all context ----
    lead_ctx = _get_lead_full_context(db, lead_id, organization_id)
    if not lead_ctx:
        raise ValueError(f"Lead {lead_id} not found in organization {organization_id}")

    lo = _get_lo_context(db, organization_id, user_id)
    activities = _get_recent_activities(db, lead_id, organization_id=organization_id, limit=8)
    email_history = _get_email_tracking_history(db, lead_id, organization_id=organization_id)
    rate_env = _get_rate_environment(db, organization_id)

    # Trigger-specific context
    trigger_specific = {}
    if trigger_event == TRIGGER_DOCUMENT_REMINDER:
        trigger_specific["missing_documents"] = _get_outstanding_documents(db, lead_id, organization_id)
    if trigger_event == TRIGGER_RATE_DROP and extra_context:
        trigger_specific["rate_data"] = extra_context.get("rate_data", {})
    if trigger_event == TRIGGER_POST_CALL_FOLLOWUP and extra_context:
        trigger_specific["call_notes"] = extra_context.get("call_notes", "")
        trigger_specific["action_items"] = extra_context.get("action_items", [])

    # Merge extra context
    if extra_context:
        trigger_specific.update({k: v for k, v in extra_context.items() if k not in trigger_specific})

    # ---- Build the prompt ----
    trigger_descriptions = {
        TRIGGER_RATE_DROP: (
            "Rates have dropped. Write an email that references specific numbers if available. "
            "Calculate estimated monthly payment savings. Create urgency without being pushy. "
            "If the lead has a loan amount, compute a rough payment at the new rate."
        ),
        TRIGGER_STALE_LEAD: (
            "This lead has gone quiet. Reference their last interaction date and what was discussed. "
            "Acknowledge the pause without guilt-tripping. Offer a fresh reason to re-engage — "
            "a market update, a new program, or simply a check-in. Keep it under 100 words."
        ),
        TRIGGER_POST_CALL_FOLLOWUP: (
            "Following up after a phone call. Summarize what was discussed (use call notes if available). "
            "List specific action items and next steps. Include any promised information. "
            "Make the borrower feel heard and organized."
        ),
        TRIGGER_DOCUMENT_REMINDER: (
            "Documents are still needed. List EXACTLY which documents are missing. "
            "Explain briefly why each is needed. Be helpful, not nagging. "
            "Offer to help if they're having trouble locating anything."
        ),
        TRIGGER_PRE_APPROVAL_READY: (
            "The borrower's pre-approval is complete. Congratulate them genuinely. "
            "Explain what pre-approval means for their home search. Set clear expectations "
            "for next steps. Mention the pre-approval amount if available."
        ),
        TRIGGER_CLOSING_PREP: (
            "Closing is approaching. Provide a clear checklist of what they need for closing day: "
            "cashier's check/wire details, government ID, any remaining documents. "
            "Explain what to expect on closing day. Build excitement — they're about to own a home!"
        ),
    }

    system_prompt = (
        f"You are the AI email engine for {lo['company_name'] or 'a mortgage company'}. "
        f"You write emails on behalf of loan officer {lo['full_name']}.\n\n"
        "YOUR GOAL: Write the most effective, personalized mortgage email possible. "
        "Every email should feel like it was hand-crafted by a thoughtful loan officer who "
        "truly knows the borrower's situation.\n\n"
        "PERSONALIZATION RULES:\n"
        "- Use the borrower's first name naturally (not just in the greeting)\n"
        "- Reference specific details from their file: loan amount, property type, location, stage\n"
        "- If they have a credit score, tailor program recommendations accordingly\n"
        "- If they're a first-time buyer, use encouraging language and explain things clearly\n"
        "- Reference their engagement history — don't send a 'nice to meet you' to someone you've emailed 5 times\n"
        "- Match tone to their sentiment score: enthusiastic for positive leads, reassuring for nervous ones\n\n"
        "COMPLIANCE RULES (MUST FOLLOW):\n"
        "- Never promise or guarantee a specific interest rate (can mention current market ranges)\n"
        f"- Include LO signature: {lo['full_name']}, NMLS# {lo['nmls']}, {lo['company_name']}\n"
        "- Include Equal Housing Lender in the footer\n"
        "- Never reference race, sex, religion, national origin, marital status, age, or disability (ECOA)\n"
        "- No kickback language or undisclosed referral arrangements (RESPA)\n"
        "- Do not make claims about guaranteed approval or guaranteed rates\n\n"
        "FORMAT RULES:\n"
        "- Body should be 80-200 words (concise but substantive)\n"
        "- Use HTML tags: <p>, <ul>, <li>, <strong>, <br>\n"
        '- Include a signature block in a <div class="signature"> tag\n'
        '- Include a compliance footer in a <div class="footer"> tag with Equal Housing Lender\n'
        "- Subject line should be personal and specific — avoid generic subjects\n"
        "- If including a call-to-action link placeholder, use class=\"cta\"\n\n"
        "OUTPUT: Return ONLY a JSON object:\n"
        '{"subject": "...", "body_html": "..."}\n'
        "No markdown, no explanation, just the JSON."
    )

    # Build rich user prompt
    context_parts = [
        f"TRIGGER: {trigger_event}",
        f"INSTRUCTIONS: {trigger_descriptions[trigger_event]}",
        "",
        "=== LEAD CONTEXT ===",
        f"Name: {lead_ctx['first_name']} {lead_ctx['last_name']}",
        f"Stage: {lead_ctx['stage']}",
        f"Source: {lead_ctx['source'] or 'Unknown'}",
        f"AI Score: {lead_ctx['ai_score']}/100",
        f"Sentiment: {lead_ctx['sentiment']}",
        f"Loan type: {lead_ctx['loan_type'] or 'Not specified'}",
        f"Loan amount: ${lead_ctx['loan_amount']:,.0f}" if lead_ctx['loan_amount'] else "Loan amount: Not specified",
        f"Credit score: {lead_ctx['credit_score']}" if lead_ctx['credit_score'] else "Credit score: Not specified",
        f"Property type: {lead_ctx['property_type'] or 'Not specified'}",
        f"Location: {lead_ctx['city']}{', ' + lead_ctx['state'] if lead_ctx['state'] else ''}",
        f"First-time buyer: {'Yes' if lead_ctx['first_time_buyer'] else 'No'}",
        f"Employment: {lead_ctx['employment_status'] or 'Not specified'}",
        f"Pre-approval amount: ${lead_ctx['preapproval_amount']:,.0f}" if lead_ctx['preapproval_amount'] else "",
        f"Target payment: ${lead_ctx['target_payment']:,.0f}/mo" if lead_ctx['target_payment'] else "",
        f"Down payment: ${lead_ctx['down_payment']:,.0f}" if lead_ctx['down_payment'] else "",
        f"Last contact: {lead_ctx['last_contact'] or 'No record'}",
        f"Lead created: {lead_ctx['created_at'] or 'Unknown'}",
        f"Preferred communication: {lead_ctx['preferred_communication'] or 'Not specified'}",
        f"Buying timeline: {lead_ctx['buying_timeline'] or 'Not specified'}",
        f"Closing date: {lead_ctx['closing_date']}" if lead_ctx.get('closing_date') else "",
        f"Lock date: {lead_ctx['lock_date']}" if lead_ctx.get('lock_date') else "",
        f"Program: {lead_ctx['program']}" if lead_ctx.get('program') else "",
    ]

    # Filter empty lines
    context_parts = [p for p in context_parts if p]

    if activities:
        context_parts.append("\n=== RECENT ACTIVITY (most recent first) ===")
        for act in activities[:6]:
            context_parts.append(f"- [{act['date'][:10]}] {act['type']}: {act['content']}")

    if email_history["total_sent"] > 0:
        context_parts.append(f"\n=== EMAIL HISTORY ===")
        context_parts.append(f"Total emails sent: {email_history['total_sent']}")
        context_parts.append(f"Opens: {email_history['total_opens']}")
        context_parts.append(f"Clicks: {email_history['total_clicks']}")
        if email_history["subjects_sent"]:
            context_parts.append(f"Recent subjects: {', '.join(email_history['subjects_sent'][:5])}")
        if email_history["subjects_opened"]:
            context_parts.append(f"Opened subjects: {', '.join(email_history['subjects_opened'][:3])}")

    if rate_env:
        context_parts.append(f"\n=== RATE ENVIRONMENT ===")
        context_parts.append(json.dumps(rate_env, indent=2, default=str))

    if trigger_specific:
        context_parts.append(f"\n=== TRIGGER-SPECIFIC CONTEXT ===")
        for k, v in trigger_specific.items():
            if isinstance(v, list):
                context_parts.append(f"{k}: {', '.join(str(i) for i in v)}")
            else:
                context_parts.append(f"{k}: {v}")

    context_parts.append(f"\n=== LOAN OFFICER ===")
    context_parts.append(f"Name: {lo['full_name']}")
    context_parts.append(f"NMLS#: {lo['nmls']}")
    context_parts.append(f"Company: {lo['company_name']}")

    user_prompt = "\n".join(context_parts)

    # ---- Call Claude ----
    _log_extra = {"lead_id": lead_id, "organization_id": organization_id}
    try:
        raw = await _call_claude(system_prompt, user_prompt, MAX_TOKENS_COMPOSE)
        parsed = _parse_json_response(raw)
        subject = parsed.get("subject", "")
        body_html = parsed.get("body_html", "")

        if not subject or not body_html:
            raise ValueError("Empty subject or body from AI")

        # COMP-004: ECOA compliance check on AI-generated content
        ecoa_ok, ecoa_violations = _validate_ecoa_compliance(subject + " " + body_html)
        if not ecoa_ok:
            logger.warning(
                "ECOA violation in AI-composed email — falling back to template: %s",
                ecoa_violations,
                extra=_log_extra,
            )
            raise ValueError(f"ECOA compliance failure: {ecoa_violations}")

        # Wrap in HTML envelope
        full_html = _wrap_html_email(body_html, lo["primary_color"])

        logger.info(
            "AI contextual email composed: lead=%s trigger=%s subject='%s'",
            lead_id, trigger_event, subject[:60],
            extra=_log_extra,
        )

        return {"subject": subject, "body_html": full_html}

    except Exception as e:
        logger.warning(
            "AI email composition failed for lead=%s trigger=%s: %s — using fallback",
            lead_id, trigger_event, e,
            extra=_log_extra,
        )
        # Fallback to template
        variables = {
            "first_name": lead_ctx["first_name"],
            "last_name": lead_ctx["last_name"],
            "lo_name": lo["full_name"],
            "nmls": lo["nmls"],
            "company_name": lo["company_name"],
        }
        fallback = _render_fallback(trigger_event, variables)
        footer = _build_compliance_footer(lo["full_name"], lo["nmls"], lo["company_name"])
        full_html = _wrap_html_email(fallback["body_html"] + footer, lo["primary_color"])
        return {"subject": fallback["subject"], "body_html": full_html}


# ---------------------------------------------------------------------------
# Public API: determine_optimal_send_time
# ---------------------------------------------------------------------------


async def determine_optimal_send_time(
    db: Session,
    lead_id: int,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Analyze engagement patterns and return the optimal send time for a lead.

    Returns:
        {
            "optimal_datetime": ISO string of the recommended send time,
            "confidence": float 0-1,
            "reasoning": str explaining the recommendation,
            "timezone": str timezone used,
        }
    """
    now = datetime.now(timezone.utc)

    # Determine lead's timezone (from org → default America/Chicago)
    lead_tz_name = "America/Chicago"
    if organization_id:
        try:
            from database.models.core import Organization
            org = db.query(Organization).filter(Organization.id == organization_id).first()
            if org and org.timezone:
                lead_tz_name = org.timezone
        except Exception as e:
            logger.debug(
                "Could not determine timezone for org %s: %s", organization_id, e,
                extra={"lead_id": lead_id, "organization_id": organization_id},
            )

    # ---- Signal 1: Past email open times ----
    open_hours: List[int] = []
    open_weekdays: List[int] = []
    email_history = _get_email_tracking_history(db, lead_id, organization_id=organization_id)

    for ts_str in email_history.get("open_timestamps", []):
        try:
            ts = datetime.fromisoformat(ts_str)
            open_hours.append(ts.hour)
            open_weekdays.append(ts.weekday())
        except (ValueError, TypeError):
            continue

    # ---- Signal 2: SMS response times ----
    sms_hours: List[int] = []
    sms_weekdays: List[int] = []
    sms_times = _get_sms_response_times(db, lead_id, organization_id=organization_id)
    for ts in sms_times:
        sms_hours.append(ts.hour)
        sms_weekdays.append(ts.weekday())

    # ---- Scoring algorithm ----
    # Weight: personal open data > personal SMS data > industry benchmark
    hour_scores: Dict[int, float] = {h: 0.0 for h in range(24)}
    day_scores: Dict[int, float] = {d: 0.0 for d in range(7)}
    confidence = 0.3  # Base confidence (benchmark only)

    # Industry benchmark (low weight)
    for h in BENCHMARK_BEST_HOURS:
        hour_scores[h] += 1.0
    for d in BENCHMARK_BEST_DAYS:
        day_scores[d] += 1.0

    # SMS response times (medium weight)
    if sms_hours:
        confidence = max(confidence, 0.5)
        for h in sms_hours:
            hour_scores[h] += 2.0
        for d in sms_weekdays:
            day_scores[d] += 2.0

    # Email open times (highest weight — direct signal)
    if open_hours:
        confidence = min(0.9, 0.5 + len(open_hours) * 0.05)
        for h in open_hours:
            hour_scores[h] += 3.0
        for d in open_weekdays:
            day_scores[d] += 3.0

    # Find the best hour and day
    best_hour = max(hour_scores, key=hour_scores.get)  # type: ignore[arg-type]
    best_day = max(day_scores, key=day_scores.get)  # type: ignore[arg-type]

    # Clamp to business hours (7am - 8pm)
    if best_hour < 7:
        best_hour = BENCHMARK_FALLBACK_HOUR
    elif best_hour > 20:
        best_hour = BENCHMARK_FALLBACK_HOUR

    # Find the next occurrence of best_day at best_hour
    days_ahead = (best_day - now.weekday()) % 7
    if days_ahead == 0 and now.hour >= best_hour:
        days_ahead = 7  # Already past that time today, move to next week

    target = now.replace(hour=best_hour, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)

    # Don't schedule in the past or more than 7 days out
    if target <= now:
        target = now + timedelta(hours=1)
    if target > now + timedelta(days=7):
        target = now + timedelta(days=1)
        target = target.replace(hour=best_hour, minute=0, second=0, microsecond=0)

    # Build reasoning
    reasoning_parts = []
    if open_hours:
        reasoning_parts.append(
            f"Lead typically opens emails around {best_hour}:00 "
            f"(based on {len(open_hours)} tracked opens)"
        )
    if sms_hours:
        reasoning_parts.append(
            f"SMS responses cluster around {max(set(sms_hours), key=sms_hours.count)}:00"
        )
    if not open_hours and not sms_hours:
        reasoning_parts.append(
            "No personal engagement data available; using industry benchmarks "
            "(Tue-Thu, 10am-2pm)"
        )

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    reasoning_parts.append(f"Recommended: {day_names[best_day]} at {best_hour}:00")

    return {
        "optimal_datetime": target.isoformat(),
        "confidence": round(confidence, 2),
        "reasoning": ". ".join(reasoning_parts),
        "timezone": lead_tz_name,
        "best_hour": best_hour,
        "best_day": day_names[best_day],
        "signals_used": {
            "email_opens": len(open_hours),
            "sms_responses": len(sms_hours),
            "benchmark_applied": not open_hours and not sms_hours,
        },
    }


# ---------------------------------------------------------------------------
# Public API: generate_follow_up_sequence
# ---------------------------------------------------------------------------


async def generate_follow_up_sequence(
    db: Session,
    lead_id: int,
    organization_id: int,
    trigger: str,
    user_id: Optional[int] = None,
    extra_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Generate a 3-email follow-up sequence where each email is unique.

    Returns:
        [
            {"sequence_number": 1, "send_at": ISO string, "delay_hours": 0, "subject": ..., "body_html": ...},
            {"sequence_number": 2, "send_at": ISO string, "delay_hours": 48, "subject": ..., "body_html": ...},
            {"sequence_number": 3, "send_at": ISO string, "delay_hours": 168, "subject": ..., "body_html": ...},
        ]
    """
    if trigger not in VALID_TRIGGERS:
        raise ValueError(f"Invalid trigger '{trigger}'")

    # Gather context
    lead_ctx = _get_lead_full_context(db, lead_id, organization_id)
    if not lead_ctx:
        raise ValueError(f"Lead {lead_id} not found in organization {organization_id}")

    lo = _get_lo_context(db, organization_id, user_id)
    activities = _get_recent_activities(db, lead_id, organization_id=organization_id, limit=5)
    email_history = _get_email_tracking_history(db, lead_id, organization_id=organization_id)

    # Determine send times
    optimal = await determine_optimal_send_time(db, lead_id, organization_id)
    base_time = datetime.fromisoformat(optimal["optimal_datetime"])

    send_times = [
        base_time,                              # Email 1: optimal time
        base_time + timedelta(hours=48),        # Email 2: 48h later if no open
        base_time + timedelta(days=7),          # Email 3: 7 days later if still no engagement
    ]

    system_prompt = (
        f"You are the AI email sequencing engine for {lo['company_name'] or 'a mortgage company'}. "
        f"Write a 3-email follow-up sequence on behalf of loan officer {lo['full_name']}.\n\n"
        "SEQUENCE STRATEGY:\n"
        "- Email 1 (immediate): Primary outreach tied to the trigger event. Warmest, most detailed.\n"
        "- Email 2 (48h, if no open): Different subject line to avoid spam filters. "
        "Shorter, punchier. New angle or value proposition. Don't repeat Email 1.\n"
        "- Email 3 (7 days, if no engagement): Completely different approach. "
        "Could be a market insight, a story, a simple one-line check-in, or a 'closing the loop' message. "
        "Must feel fresh, not like a third nag.\n\n"
        "Each email should stand alone — the recipient may not have seen previous ones.\n\n"
        "COMPLIANCE RULES:\n"
        "- Never promise or guarantee specific rates\n"
        f"- All emails must include LO signature: {lo['full_name']}, NMLS# {lo['nmls']}, {lo['company_name']}\n"
        "- Equal Housing Lender in footer\n"
        "- No ECOA-prohibited references\n\n"
        "FORMAT:\n"
        "- Email 1: 100-200 words\n"
        "- Email 2: 60-100 words\n"
        "- Email 3: 40-80 words\n"
        "- Use HTML tags (<p>, <ul>, <li>, <strong>)\n"
        '- Each email needs a <div class="signature"> and <div class="footer">\n\n'
        "OUTPUT: Return ONLY a JSON array of 3 objects:\n"
        '[{"subject": "...", "body_html": "..."}, {"subject": "...", "body_html": "..."}, {"subject": "...", "body_html": "..."}]\n'
        "No markdown, no explanation."
    )

    context_parts = [
        f"TRIGGER: {trigger}",
        f"Borrower: {lead_ctx['first_name']} {lead_ctx['last_name']}",
        f"Stage: {lead_ctx['stage']}",
        f"Loan type: {lead_ctx['loan_type'] or 'Not specified'}",
        f"Loan amount: ${lead_ctx['loan_amount']:,.0f}" if lead_ctx['loan_amount'] else "Loan amount: Unknown",
        f"Credit score: {lead_ctx['credit_score']}" if lead_ctx['credit_score'] else "",
        f"Property: {lead_ctx['property_type'] or 'Unknown'} in {lead_ctx['city']}{', ' + lead_ctx['state'] if lead_ctx['state'] else ''}",
        f"First-time buyer: {'Yes' if lead_ctx['first_time_buyer'] else 'No'}",
        f"Sentiment: {lead_ctx['sentiment']}",
        f"AI Score: {lead_ctx['ai_score']}/100",
        f"Last contact: {lead_ctx['last_contact'] or 'No record'}",
        f"Emails already sent: {email_history['total_sent']}",
        f"Opens: {email_history['total_opens']}, Clicks: {email_history['total_clicks']}",
    ]

    if activities:
        context_parts.append("\nRecent activity:")
        for act in activities[:4]:
            context_parts.append(f"  - [{act['date'][:10]}] {act['type']}: {act['content']}")

    if extra_context:
        context_parts.append("\nAdditional context:")
        for k, v in extra_context.items():
            context_parts.append(f"  {k}: {v}")

    context_parts.append(f"\nLO: {lo['full_name']}, NMLS# {lo['nmls']}, {lo['company_name']}")

    user_prompt = "\n".join([p for p in context_parts if p])

    # ---- Call Claude for the full sequence ----
    _log_extra = {"lead_id": lead_id, "organization_id": organization_id}
    try:
        raw = await _call_claude(system_prompt, user_prompt, MAX_TOKENS_SEQUENCE)
        parsed = _parse_json_response(raw)

        if not isinstance(parsed, list) or len(parsed) < 3:
            raise ValueError(f"Expected 3-item array, got {type(parsed).__name__} with {len(parsed) if isinstance(parsed, list) else 0} items")

        sequence = []
        for i, email_data in enumerate(parsed[:3]):
            subject = email_data.get("subject", f"Following up — {lead_ctx['first_name']}")
            body_html = email_data.get("body_html", "")

            if not body_html:
                raise ValueError(f"Empty body_html in email {i + 1}")

            # COMP-004: ECOA compliance check on each sequence email
            ecoa_ok, ecoa_violations = _validate_ecoa_compliance(subject + " " + body_html)
            if not ecoa_ok:
                logger.warning(
                    "ECOA violation in AI sequence email %d — falling back to templates: %s",
                    i + 1, ecoa_violations,
                    extra=_log_extra,
                )
                raise ValueError(f"ECOA compliance failure in email {i + 1}: {ecoa_violations}")

            full_html = _wrap_html_email(body_html, lo["primary_color"])

            sequence.append({
                "sequence_number": i + 1,
                "send_at": send_times[i].isoformat(),
                "delay_hours": [0, 48, 168][i],
                "subject": subject,
                "body_html": full_html,
                "stop_condition": [
                    "Send immediately or at optimal time",
                    "Send only if Email 1 was not opened within 48 hours",
                    "Send only if no engagement (opens or clicks) within 7 days",
                ][i],
            })

        logger.info(
            "AI follow-up sequence generated: lead=%s trigger=%s emails=%d",
            lead_id, trigger, len(sequence),
            extra=_log_extra,
        )
        return sequence

    except Exception as e:
        logger.warning(
            "AI sequence generation failed for lead=%s trigger=%s: %s — building fallback sequence",
            lead_id, trigger, e,
            extra=_log_extra,
        )

        # Fallback: generate 3 emails from templates with variation
        variables = {
            "first_name": lead_ctx["first_name"],
            "last_name": lead_ctx["last_name"],
            "lo_name": lo["full_name"],
            "nmls": lo["nmls"],
            "company_name": lo["company_name"],
        }
        footer = _build_compliance_footer(lo["full_name"], lo["nmls"], lo["company_name"])

        fallback_sequence = []
        fallback_triggers = [trigger, TRIGGER_STALE_LEAD, TRIGGER_STALE_LEAD]
        fallback_subjects_override = [
            None,
            f"Did you see my previous email, {lead_ctx['first_name']}?",
            f"One more thought, {lead_ctx['first_name']}",
        ]

        for i in range(3):
            fb = _render_fallback(fallback_triggers[i], variables)
            subject = fallback_subjects_override[i] or fb["subject"]
            full_html = _wrap_html_email(fb["body_html"] + footer, lo["primary_color"])

            fallback_sequence.append({
                "sequence_number": i + 1,
                "send_at": send_times[i].isoformat(),
                "delay_hours": [0, 48, 168][i],
                "subject": subject,
                "body_html": full_html,
                "stop_condition": [
                    "Send immediately or at optimal time",
                    "Send only if Email 1 was not opened within 48 hours",
                    "Send only if no engagement (opens or clicks) within 7 days",
                ][i],
            })

        return fallback_sequence


# ---------------------------------------------------------------------------
# Public API: score_email_engagement
# ---------------------------------------------------------------------------


async def score_email_engagement(
    db: Session,
    lead_id: int,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Compute comprehensive email engagement analytics for a lead.

    Returns:
        {
            "lead_id": int,
            "total_sent": int,
            "total_opens": int,
            "total_clicks": int,
            "unique_opens": int,
            "open_rate": float (0-100),
            "click_rate": float (0-100),
            "response_rate": float (0-100),
            "best_subject_lines": list of subject lines that were opened,
            "preferred_time": {"hour": int, "day": str} or null,
            "engagement_trend": "increasing" | "decreasing" | "flat" | "insufficient_data",
            "engagement_score": int (0-100),
            "recommendations": list of actionable strings,
        }
    """
    email_history = _get_email_tracking_history(db, lead_id, organization_id=organization_id)

    total_sent = email_history["total_sent"]
    total_opens = email_history["total_opens"]
    total_clicks = email_history["total_clicks"]
    subjects_opened = email_history.get("subjects_opened", [])
    open_timestamps = email_history.get("open_timestamps", [])

    # Count inbound emails from this lead as "responses"
    total_responses = 0
    try:
        from database.models.communication import EmailMessage as EmailMessageModel
        response_filters = [
            EmailMessageModel.lead_id == lead_id,
            EmailMessageModel.direction == "inbound",
        ]
        if organization_id is not None:
            response_filters.append(EmailMessageModel.organization_id == organization_id)
        total_responses = (
            db.query(func.count(EmailMessageModel.id))
            .filter(*response_filters)
            .scalar() or 0
        )
    except Exception as e:
        logger.debug(
            "Could not count inbound emails for lead %s: %s", lead_id, e,
            extra={"lead_id": lead_id, "organization_id": organization_id},
        )

    # Compute rates
    open_rate = (total_opens / total_sent * 100) if total_sent > 0 else 0.0
    click_rate = (total_clicks / total_sent * 100) if total_sent > 0 else 0.0
    response_rate = (total_responses / total_sent * 100) if total_sent > 0 else 0.0

    # Preferred time analysis
    preferred_time = None
    if open_timestamps:
        open_hours = []
        open_weekdays = []
        for ts_str in open_timestamps:
            try:
                ts = datetime.fromisoformat(ts_str)
                open_hours.append(ts.hour)
                open_weekdays.append(ts.weekday())
            except (ValueError, TypeError):
                continue

        if open_hours:
            mode_hour = max(set(open_hours), key=open_hours.count)
            mode_day = max(set(open_weekdays), key=open_weekdays.count)
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            preferred_time = {"hour": mode_hour, "day": day_names[mode_day]}

    # Engagement trend — compare first half vs second half of open timestamps
    engagement_trend = "insufficient_data"
    if len(open_timestamps) >= 4:
        mid = len(open_timestamps) // 2
        first_half_count = mid
        second_half_count = len(open_timestamps) - mid

        # Parse timestamps and check recency
        try:
            parsed_opens = sorted([datetime.fromisoformat(ts) for ts in open_timestamps])
            first_half = parsed_opens[:mid]
            second_half = parsed_opens[mid:]

            if first_half and second_half:
                first_span = (first_half[-1] - first_half[0]).total_seconds() or 1
                second_span = (second_half[-1] - second_half[0]).total_seconds() or 1

                first_rate = first_half_count / first_span
                second_rate = second_half_count / second_span

                if second_rate > first_rate * 1.2:
                    engagement_trend = "increasing"
                elif second_rate < first_rate * 0.8:
                    engagement_trend = "decreasing"
                else:
                    engagement_trend = "flat"
        except (ValueError, TypeError):
            pass

    # Composite engagement score (0-100)
    # Weighted: open_rate (40%), click_rate (30%), response_rate (20%), trend (10%)
    trend_bonus = {"increasing": 10, "flat": 5, "decreasing": 0, "insufficient_data": 3}
    engagement_score = min(100, int(
        (min(open_rate, 100) * 0.4)
        + (min(click_rate, 100) * 0.3)
        + (min(response_rate, 100) * 0.2)
        + trend_bonus.get(engagement_trend, 0)
    ))

    # Generate recommendations
    recommendations: List[str] = []
    if total_sent == 0:
        recommendations.append("No emails sent yet. Start with a personalized welcome email.")
    elif total_sent > 0 and total_opens == 0:
        recommendations.append("No opens detected. Try a more compelling subject line or different send time.")
        recommendations.append("Consider A/B testing subject lines with different angles.")
    elif open_rate < 20 and total_sent >= 3:
        recommendations.append(f"Open rate is low ({open_rate:.0f}%). Experiment with subject line personalization.")
    elif open_rate >= 40:
        recommendations.append(f"Strong open rate ({open_rate:.0f}%). This lead is engaged with email.")

    if total_opens > 0 and total_clicks == 0:
        recommendations.append("Lead opens emails but never clicks. Add clearer CTAs or simplify the ask.")

    if total_responses > 0:
        recommendations.append(f"Lead has replied to {total_responses} email(s) — high engagement. Prioritize this lead.")

    if engagement_trend == "decreasing":
        recommendations.append("Engagement is declining. Consider switching to a different channel (SMS, call).")
    elif engagement_trend == "increasing":
        recommendations.append("Engagement is trending up. Maintain the current cadence and approach.")

    if preferred_time:
        recommendations.append(
            f"Best time to reach this lead: {preferred_time['day']}s around {preferred_time['hour']}:00."
        )

    if subjects_opened:
        recommendations.append(f"Top-performing subject lines: {', '.join(subjects_opened[:3])}")

    result = {
        "lead_id": lead_id,
        "total_sent": total_sent,
        "total_opens": total_opens,
        "total_clicks": total_clicks,
        "total_responses": total_responses,
        "open_rate": round(open_rate, 1),
        "click_rate": round(click_rate, 1),
        "response_rate": round(response_rate, 1),
        "best_subject_lines": subjects_opened[:5],
        "preferred_time": preferred_time,
        "engagement_trend": engagement_trend,
        "engagement_score": engagement_score,
        "recommendations": recommendations,
    }

    logger.info(
        "Email engagement scored: lead=%s sent=%d opens=%d score=%d trend=%s",
        lead_id, total_sent, total_opens, engagement_score, engagement_trend,
        extra={"lead_id": lead_id, "organization_id": organization_id},
    )

    return result


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "compose_contextual_email",
    "determine_optimal_send_time",
    "generate_follow_up_sequence",
    "score_email_engagement",
    "_validate_ecoa_compliance",
    "VALID_TRIGGERS",
    "TRIGGER_RATE_DROP",
    "TRIGGER_STALE_LEAD",
    "TRIGGER_POST_CALL_FOLLOWUP",
    "TRIGGER_DOCUMENT_REMINDER",
    "TRIGGER_PRE_APPROVAL_READY",
    "TRIGGER_CLOSING_PREP",
]
