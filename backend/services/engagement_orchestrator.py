"""
Engagement Orchestrator — Master decision engine for lead engagement.

Decides WHAT to send, WHEN to send it, and on WHICH CHANNEL, then dispatches
to the appropriate service (call, SMS, email, voicemail).

This is the brain that ties together speed-to-lead calls, SMS intelligence,
email tracking, AMD voicemail drops, and drip campaigns into a single coherent
engagement strategy per lead.

Trigger events drive sequences:
  new_lead              → speed-to-lead call + SMS fallback
  no_answer             → voicemail drop + SMS follow-up
  voicemail_dropped     → SMS follow-up 15 min later
  sms_no_response_24h   → email follow-up
  email_opened          → escalate to SMS/call
  call_completed        → post-call email + task creation
  appointment_set       → borrower prep sequence
  appointment_missed    → re-engagement sequence
  rate_drop             → rate alert on preferred channel
  document_needed       → multi-channel doc request
  stale_7d              → re-engagement nudge
  stale_30d             → long-term nurture switch
  qualification_complete → appointment push
  deal_breaker_found    → turn-down sequence with alternatives
  loan_funded           → post-close referral sequence

Usage::

    from services.engagement_orchestrator import orchestrate_lead_engagement

    result = await orchestrate_lead_engagement(
        db=db, lead_id=123, organization_id=1,
        trigger_event="new_lead",
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Valid trigger events
# ---------------------------------------------------------------------------

VALID_TRIGGERS = {
    "new_lead",
    "no_answer",
    "voicemail_dropped",
    "sms_no_response_24h",
    "email_opened",
    "call_completed",
    "appointment_set",
    "appointment_missed",
    "rate_drop",
    "document_needed",
    "stale_7d",
    "stale_30d",
    "qualification_complete",
    "deal_breaker_found",
    "loan_funded",
}

# Channel priority by time-of-day bucket (borrower local time)
# morning = 8-12, afternoon = 12-17, evening = 17-21
CHANNEL_TIME_MATRIX = {
    "morning":   ["call", "sms", "email"],
    "afternoon": ["call", "sms", "email"],
    "evening":   ["sms", "email"],
    "quiet":     [],  # No outbound during quiet hours
}

# Default delays for sequenced follow-ups (minutes)
SEQUENCE_DELAYS = {
    "voicemail_dropped":     15,     # SMS follow-up after VM
    "sms_no_response_24h":   0,      # Immediate email
    "email_opened":          5,      # Quick escalation
    "stale_7d":              0,      # Immediate nudge
    "stale_30d":             0,      # Immediate nurture switch
    "appointment_missed":    30,     # Wait 30 min then re-engage
    "call_completed":        5,      # Quick post-call email
    "appointment_set":       0,      # Immediate prep email
    "rate_drop":             0,      # Immediate alert
    "document_needed":       0,      # Immediate request
    "qualification_complete": 0,     # Immediate next action
    "deal_breaker_found":    0,      # Immediate turn-down
    "loan_funded":           1440,   # Wait 24h for referral ask
}


# ---------------------------------------------------------------------------
# Table initialization (engagement_events)
# ---------------------------------------------------------------------------

_tables_initialized = False


def _ensure_engagement_tables(db: Session) -> None:
    """Create engagement_events table if it doesn't exist."""
    global _tables_initialized
    if _tables_initialized:
        return

    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS engagement_events (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                lead_id INTEGER NOT NULL,
                trigger_event VARCHAR(60) NOT NULL,
                channel_chosen VARCHAR(20),
                channel_reason TEXT,
                action_taken TEXT,
                action_result TEXT,
                action_metadata JSONB DEFAULT '{}'::jsonb,
                scheduled_next_at TIMESTAMPTZ,
                scheduled_next_trigger VARCHAR(60),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_eng_events_org_lead
            ON engagement_events (organization_id, lead_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_eng_events_lead_created
            ON engagement_events (lead_id, created_at DESC)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_eng_events_scheduled
            ON engagement_events (scheduled_next_at)
            WHERE scheduled_next_at IS NOT NULL
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_eng_events_trigger
            ON engagement_events (trigger_event, created_at DESC)
        """))
        db.commit()
        _tables_initialized = True
    except Exception as e:
        db.rollback()
        logger.error("Engagement tables init failed — events will be lost until restart: %s", e, exc_info=True)
        _tables_initialized = True  # Don't retry every request


# ---------------------------------------------------------------------------
# Context loaders
# ---------------------------------------------------------------------------

def _load_lead_context(db: Session, lead_id: int, organization_id: int) -> Optional[Dict[str, Any]]:
    """Load lead data + channel preferences for engagement decisions."""
    row = db.execute(text("""
        SELECT l.id, l.first_name, l.last_name, l.name, l.phone, l.email,
               l.stage, l.source, l.owner_id, l.ai_score, l.loan_type,
               l.preferred_communication, l.last_contact, l.organization_id,
               l.state AS lead_state
        FROM leads l
        WHERE l.id = :lid AND l.organization_id = :org_id
    """), {"lid": lead_id, "org_id": organization_id}).fetchone()

    if not row:
        return None

    ctx: Dict[str, Any] = {
        "lead_id": row.id,
        "first_name": row.first_name or "",
        "last_name": row.last_name or "",
        "name": row.name or f"{row.first_name or ''} {row.last_name or ''}".strip() or "there",
        "phone": row.phone,
        "email": row.email,
        "stage": (row.stage or "New").upper(),
        "source": row.source,
        "owner_id": row.owner_id,
        "ai_score": row.ai_score or 50,
        "loan_type": row.loan_type,
        "preferred_communication": row.preferred_communication,
        "last_contact": row.last_contact,
        "organization_id": row.organization_id,
        "lead_state": row.lead_state,
    }

    # Load channel preferences
    pref_row = db.execute(text("""
        SELECT preferred_channels, do_not_email, do_not_sms, do_not_call,
               quiet_hours_start, quiet_hours_end, timezone,
               sms_consent, call_consent, email_opt_in,
               max_contacts_per_day, max_contacts_per_week
        FROM channel_preferences
        WHERE lead_id = :lid AND organization_id = :org_id
        LIMIT 1
    """), {"lid": lead_id, "org_id": organization_id}).fetchone()

    if pref_row:
        ctx["preferred_channels"] = pref_row.preferred_channels or ["email", "sms", "call"]
        ctx["do_not_email"] = pref_row.do_not_email or False
        ctx["do_not_sms"] = pref_row.do_not_sms or False
        ctx["do_not_call"] = pref_row.do_not_call or False
        ctx["quiet_hours_start"] = pref_row.quiet_hours_start or "21:00"
        ctx["quiet_hours_end"] = pref_row.quiet_hours_end or "08:00"
        ctx["timezone"] = pref_row.timezone or "America/New_York"
        ctx["sms_consent"] = pref_row.sms_consent or False
        ctx["call_consent"] = pref_row.call_consent or False
        ctx["email_opt_in"] = pref_row.email_opt_in if pref_row.email_opt_in is not None else True
        ctx["max_contacts_per_day"] = pref_row.max_contacts_per_day or 5
        ctx["max_contacts_per_week"] = pref_row.max_contacts_per_week or 15
    else:
        ctx["preferred_channels"] = ["email", "sms", "call"]
        ctx["do_not_email"] = False
        ctx["do_not_sms"] = False
        ctx["do_not_call"] = False
        ctx["quiet_hours_start"] = "21:00"
        ctx["quiet_hours_end"] = "08:00"
        ctx["timezone"] = "America/New_York"
        ctx["sms_consent"] = False
        ctx["call_consent"] = False
        ctx["email_opt_in"] = True
        ctx["max_contacts_per_day"] = 5
        ctx["max_contacts_per_week"] = 15

    return ctx


def _load_recent_engagement(db: Session, lead_id: int, organization_id: int, hours: int = 48) -> List[Dict]:
    """Load recent engagement events for fatigue and pattern analysis."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = db.execute(text("""
        SELECT trigger_event, channel_chosen, action_taken, action_result,
               created_at
        FROM engagement_events
        WHERE lead_id = :lid AND organization_id = :org_id
          AND created_at >= :cutoff
        ORDER BY created_at DESC
        LIMIT 50
    """), {"lid": lead_id, "org_id": organization_id, "cutoff": cutoff}).fetchall()

    return [
        {
            "trigger_event": r.trigger_event,
            "channel_chosen": r.channel_chosen,
            "action_taken": r.action_taken,
            "action_result": r.action_result,
            "created_at": r.created_at,
        }
        for r in rows
    ]


def _count_contacts_today(db: Session, lead_id: int, organization_id: int) -> int:
    """Count engagement actions dispatched today for fatigue prevention."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    row = db.execute(text("""
        SELECT COUNT(*) AS cnt FROM engagement_events
        WHERE lead_id = :lid AND organization_id = :org_id
          AND created_at >= :today
          AND action_result IS NOT NULL
    """), {"lid": lead_id, "org_id": organization_id, "today": today_start}).fetchone()
    return row.cnt if row else 0


def _count_contacts_this_week(db: Session, lead_id: int, organization_id: int) -> int:
    """Count engagement actions this calendar week."""
    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    row = db.execute(text("""
        SELECT COUNT(*) AS cnt FROM engagement_events
        WHERE lead_id = :lid AND organization_id = :org_id
          AND created_at >= :week_start
          AND action_result IS NOT NULL
    """), {"lid": lead_id, "org_id": organization_id, "week_start": week_start}).fetchone()
    return row.cnt if row else 0


# ---------------------------------------------------------------------------
# Compliance & channel selection
# ---------------------------------------------------------------------------

def _get_time_bucket(tz_str: str) -> str:
    """Return time-of-day bucket for the lead's local time."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_str)
        local_hour = datetime.now(tz).hour
    except Exception as _exc:  # noqa: BLE001
        logger.exception("unhandled exception")
        local_hour = datetime.now(timezone.utc).hour  # Fallback to UTC

    if local_hour < 8 or local_hour >= 21:
        return "quiet"
    elif local_hour < 12:
        return "morning"
    elif local_hour < 17:
        return "afternoon"
    else:
        return "evening"


def _check_compliance(
    db: Session,
    ctx: Dict[str, Any],
    channel: str,
) -> Tuple[bool, str]:
    """
    Run compliance checks for a specific channel.
    Returns (allowed, reason).
    """
    lead_id = ctx["lead_id"]
    org_id = ctx["organization_id"]
    phone = ctx.get("phone")
    email = ctx.get("email")

    # Channel-specific DNC flags
    if channel == "call" and ctx.get("do_not_call"):
        return False, "do_not_call flag set"
    if channel == "sms" and ctx.get("do_not_sms"):
        return False, "do_not_sms flag set"
    if channel == "email" and ctx.get("do_not_email"):
        return False, "do_not_email flag set"

    # Missing contact info
    if channel in ("call", "sms") and not phone:
        return False, f"no phone number for {channel}"
    if channel == "email" and not email:
        return False, "no email address"

    # TCPA consent checks — automated calls/SMS require prior express consent
    if channel == "call" and not ctx.get("call_consent"):
        return False, "no call_consent on file (TCPA)"
    if channel == "sms" and not ctx.get("sms_consent"):
        return False, "no sms_consent on file (TCPA)"

    # Email opt-in check
    if channel == "email" and not ctx.get("email_opt_in", True):
        return False, "email opt-in is false"

    # SMS compliance gate
    if channel == "sms":
        try:
            from integrations.sms_compliance_gate import check_sms_compliance
            result = check_sms_compliance(
                db=db,
                to_phone=phone,
                message_body="(compliance pre-check)",
                lead_id=lead_id,
                organization_id=org_id,
                bypass_quiet_hours=False,
            )
            if not result.allowed:
                return False, f"sms_compliance: {result.reason}"
        except Exception as e:
            logger.debug("SMS compliance gate unavailable: %s", e)

    # Call DNC + TCPA check
    if channel == "call":
        try:
            from telephony.compliance import ComplianceChecker
            checker = ComplianceChecker(db, organization_id=org_id)
            is_dnc, dnc_reason = checker.check_dnc(phone)
            if is_dnc:
                return False, f"dnc: {dnc_reason}"
            is_allowed, hours_reason = checker.check_calling_hours(phone)
            if not is_allowed:
                return False, f"calling_hours: {hours_reason}"
        except Exception as e:
            logger.debug("Telephony compliance check unavailable: %s", e)

    # Quiet hours (all channels except email)
    if channel in ("call", "sms"):
        time_bucket = _get_time_bucket(ctx.get("timezone", "America/New_York"))
        if time_bucket == "quiet":
            return False, "quiet hours active"

    return True, "passed"


def _select_channel(
    db: Session,
    ctx: Dict[str, Any],
    trigger_event: str,
    recent_engagement: List[Dict],
) -> Tuple[Optional[str], str]:
    """
    Select the optimal channel for this engagement.

    Returns (channel, reason) where channel is "call"|"sms"|"email"|"voicemail"|None.
    """
    # Some triggers have a fixed channel
    fixed_channel_triggers = {
        "voicemail_dropped": ("sms", "SMS follow-up after voicemail drop"),
        "sms_no_response_24h": ("email", "email escalation after SMS non-response"),
        "email_opened": ("sms", "SMS escalation after email open — strike while hot"),
        "call_completed": ("email", "post-call summary email"),
        "appointment_set": ("email", "appointment confirmation email"),
        "loan_funded": ("email", "post-close referral email"),
        "deal_breaker_found": ("email", "turn-down letter with alternatives"),
    }

    if trigger_event in fixed_channel_triggers:
        channel, reason = fixed_channel_triggers[trigger_event]
        allowed, block_reason = _check_compliance(db, ctx, channel)
        if allowed:
            return channel, reason
        # Fall through to dynamic selection if fixed channel is blocked
        logger.info(
            "Fixed channel %s blocked for lead %s: %s — trying alternatives",
            channel, ctx["lead_id"], block_reason,
        )

    # Trigger-specific override: no_answer should try voicemail first
    if trigger_event == "no_answer":
        allowed, _ = _check_compliance(db, ctx, "call")
        if allowed:
            return "voicemail", "voicemail drop after no-answer"

    # Dynamic channel selection
    tz = ctx.get("timezone", "America/New_York")
    time_bucket = _get_time_bucket(tz)
    time_channels = CHANNEL_TIME_MATRIX.get(time_bucket, [])

    # Lead's preferred channel order (from channel_preferences)
    preferred = ctx.get("preferred_channels", ["email", "sms", "call"])

    # Lead's demonstrated preference from stated preference field
    stated_pref = ctx.get("preferred_communication")
    if stated_pref:
        pref_map = {
            "phone": "call", "call": "call",
            "text": "sms", "sms": "sms",
            "email": "email",
        }
        mapped = pref_map.get(stated_pref.lower())
        if mapped and mapped not in preferred[:1]:
            # Move stated preference to front
            preferred = [mapped] + [c for c in preferred if c != mapped]

    # Adjust based on pipeline stage
    stage = ctx.get("stage", "NEW")
    if stage in ("NEW", "CONTACTED"):
        # New leads: prefer call for immediacy
        if "call" not in preferred[:2]:
            preferred = ["call"] + [c for c in preferred if c != "call"]
    elif stage in ("NURTURE", "STALE", "DEAD"):
        # Nurture leads: prefer email/SMS, avoid call fatigue
        preferred = [c for c in preferred if c != "call"] + ["call"]

    # Check if we already called today (avoid repeat calls)
    called_today = any(
        e.get("channel_chosen") == "call"
        and e.get("action_result") not in ("blocked", "failed", None)
        for e in recent_engagement
        if e.get("created_at") and e["created_at"].date() == datetime.now(timezone.utc).date()
    )
    if called_today and trigger_event not in ("new_lead", "rate_drop"):
        preferred = [c for c in preferred if c != "call"] + ["call"]

    # Try channels in priority order, respecting time-of-day and compliance
    for channel in preferred:
        if channel not in time_channels and channel != "email":
            continue
        allowed, block_reason = _check_compliance(db, ctx, channel)
        if allowed:
            reason = (
                f"selected {channel}: preferred={preferred}, time={time_bucket}, "
                f"stage={stage}, called_today={called_today}"
            )
            return channel, reason

    # Last resort: email is almost always available
    if "email" not in preferred:
        allowed, _ = _check_compliance(db, ctx, "email")
        if allowed:
            return "email", "fallback to email — all preferred channels blocked"

    return None, "all channels blocked or unavailable"


# ---------------------------------------------------------------------------
# Dispatch functions (call actual services)
# ---------------------------------------------------------------------------

async def _dispatch_call(
    db: Session,
    ctx: Dict[str, Any],
    trigger_event: str,
) -> Dict[str, Any]:
    """Dispatch an AI outbound call via Vapi (speed-to-lead pattern)."""
    try:
        from routes.speed_to_lead_call_routes import _initiate_vapi_call, _format_e164

        phone_e164 = _format_e164(ctx["phone"])
        if not phone_e164:
            return {"success": False, "error": "invalid phone for E.164"}

        lead_name = ctx.get("name") or "there"
        result = await _initiate_vapi_call(
            phone_e164=phone_e164,
            lead_name=lead_name,
            lead_id=ctx["lead_id"],
            organization_id=ctx["organization_id"],
            owner_id=ctx.get("owner_id"),
        )
        return result
    except Exception as e:
        logger.exception("Call dispatch failed for lead %s", ctx["lead_id"])
        return {"success": False, "error": str(e)}


async def _dispatch_sms(
    db: Session,
    ctx: Dict[str, Any],
    trigger_event: str,
) -> Dict[str, Any]:
    """Dispatch an SMS via the centralized Telnyx chokepoint (with compliance)."""
    phone = ctx.get("phone", "")

    # Build message body based on trigger
    body = _build_sms_body(ctx, trigger_event)

    try:
        from telephony.sms import send_sms_verified_async

        result = await send_sms_verified_async(
            to=phone,
            text=body,
            db=db,
            lead_id=ctx.get("lead_id"),
            organization_id=ctx.get("organization_id"),
        )
        if result.get("status") == "sent":
            return {"success": True, "channel": "sms", "message_preview": body[:80]}
        else:
            reason = result.get("reason", "unknown")
            logger.warning("SMS dispatch blocked for lead %s: %s", ctx.get("lead_id"), reason)
            return {"success": False, "error": reason}
    except Exception as e:
        logger.exception("SMS dispatch error for lead %s", ctx.get("lead_id"))
        return {"success": False, "error": str(e)}


def _build_sms_body(ctx: Dict[str, Any], trigger_event: str) -> str:
    """Build trigger-appropriate SMS body text."""
    first_name = ctx.get("first_name") or "there"

    bodies = {
        "new_lead": (
            f"Hi {first_name}! Thanks for your interest in mortgage options. "
            f"A loan officer will be reaching out shortly. "
            f"Reply STOP to opt out."
        ),
        "no_answer": (
            f"Hi {first_name}, we just tried to reach you about your mortgage inquiry. "
            f"Feel free to call us back or reply here. Reply STOP to opt out."
        ),
        "voicemail_dropped": (
            f"Hi {first_name}, we left you a voicemail about your mortgage options. "
            f"Reply here if you'd like to chat or have any questions! Reply STOP to opt out."
        ),
        "email_opened": (
            f"Hi {first_name}, just following up on the email we sent. "
            f"Would you like to schedule a quick call to discuss your options? "
            f"Reply STOP to opt out."
        ),
        "appointment_missed": (
            f"Hi {first_name}, we missed you at your scheduled consultation. "
            f"No worries — would you like to reschedule? Reply with a time that works. "
            f"Reply STOP to opt out."
        ),
        "rate_drop": (
            f"Hi {first_name}, rates just dropped! This could lower your payment. "
            f"Want a quick savings estimate? Reply YES or call us. Reply STOP to opt out."
        ),
        "document_needed": (
            f"Hi {first_name}, we need a few documents to keep your loan moving. "
            f"Check your email for details, or reply here for help. Reply STOP to opt out."
        ),
        "stale_7d": (
            f"Hi {first_name}, just checking in on your mortgage search. "
            f"We're here whenever you're ready. Any questions? Reply STOP to opt out."
        ),
        "stale_30d": (
            f"Hi {first_name}, it's been a while since we connected. "
            f"Rates have changed — want a fresh look at your options? Reply STOP to opt out."
        ),
        "qualification_complete": (
            f"Hi {first_name}, great news — your qualification info is complete! "
            f"Let's set up a time to review your options. Reply STOP to opt out."
        ),
    }

    return bodies.get(trigger_event, (
        f"Hi {first_name}, your loan officer has an update for you. "
        f"Reply here or give us a call. Reply STOP to opt out."
    ))


async def _dispatch_email(
    db: Session,
    ctx: Dict[str, Any],
    trigger_event: str,
) -> Dict[str, Any]:
    """Dispatch an email using the AI email composer + delivery service."""
    email = ctx.get("email")
    if not email:
        return {"success": False, "error": "no email address"}

    # Map trigger to email template category/key
    template_map = {
        "new_lead": ("purchase", "pre_approval_intro"),
        "sms_no_response_24h": ("purchase", "rate_environment"),
        "call_completed": ("purchase", "pre_approval_intro"),
        "appointment_set": ("appointment", "confirmation"),
        "appointment_missed": ("appointment", "no_show_followup"),
        "rate_drop": ("refinance", "rate_alert"),
        "document_needed": ("purchase", "pre_approval_intro"),
        "stale_7d": ("purchase", "rate_environment"),
        "stale_30d": ("purchase", "market_update"),
        "deal_breaker_found": ("purchase", "rate_environment"),
        "loan_funded": ("post_close", "referral_ask"),
        "qualification_complete": ("purchase", "pre_approval_intro"),
    }

    category, template_key = template_map.get(trigger_event, ("purchase", "rate_environment"))

    # Build lead and LO data dicts for the composer
    lead_data = {
        "first_name": ctx.get("first_name") or ctx.get("name") or "there",
        "last_name": ctx.get("last_name", ""),
        "email": email,
        "loan_type": ctx.get("loan_type", "purchase"),
        "state": ctx.get("lead_state", ""),
        "source": ctx.get("source", ""),
    }

    # Load LO info
    lo_data = _load_lo_data(db, ctx.get("owner_id"))
    org_config = _load_org_email_config(db, ctx["organization_id"])

    try:
        from services.ai_email_composer import AIEmailComposer
        composer = AIEmailComposer()
        email_content = await composer.compose_email(
            template_category=category,
            template_key=template_key,
            lead_data=lead_data,
            lo_data=lo_data,
            org_config=org_config,
            custom_context=f"Trigger: {trigger_event}",
        )
    except Exception as e:
        logger.warning("AI email composer failed, using basic template: %s", e)
        email_content = {
            "subject": f"Update on your mortgage — {ctx.get('first_name', '')}",
            "html_body": (
                f"<p>Hi {ctx.get('first_name', 'there')},</p>"
                f"<p>Your loan officer has an update for you regarding your mortgage. "
                f"Please reach out at your convenience.</p>"
                f"<p>Best regards</p>"
            ),
            "plain_body": (
                f"Hi {ctx.get('first_name', 'there')}, your loan officer has an "
                f"update for you regarding your mortgage. Please reach out at your convenience."
            ),
        }

    # Send via email delivery service
    try:
        from services.email_delivery_service import EmailDeliveryService
        service = EmailDeliveryService(db)
        result = await service.send_email(
            to=email,
            subject=email_content["subject"],
            html_body=email_content["html_body"],
            from_email=lo_data.get("email", "noreply@perenniaai.com"),
            organization_id=str(ctx["organization_id"]),
        )
        if result.success:
            return {"success": True, "channel": "email", "subject": email_content["subject"]}
        else:
            return {"success": False, "error": f"email_delivery: {result.error}"}
    except Exception as e:
        logger.exception("Email dispatch error for lead %s", ctx["lead_id"])
        return {"success": False, "error": str(e)}


async def _dispatch_voicemail(
    db: Session,
    ctx: Dict[str, Any],
    trigger_event: str,
) -> Dict[str, Any]:
    """Dispatch a ringless voicemail drop via Slybroadcast."""
    phone = ctx.get("phone")
    if not phone:
        return {"success": False, "error": "no phone number"}

    try:
        from routes.amd_voicemail_routes import trigger_slybroadcast_drop, _get_org_amd_config

        config = _get_org_amd_config(db, ctx["organization_id"])
        if not config.default_vm_audio_url:
            return {"success": False, "error": "no voicemail audio URL configured"}

        result = await trigger_slybroadcast_drop(
            phone_number=phone,
            audio_url=config.default_vm_audio_url,
            caller_id=config.caller_id,
            organization_id=ctx["organization_id"],
        )
        return result
    except Exception as e:
        logger.exception("Voicemail dispatch error for lead %s", ctx["lead_id"])
        return {"success": False, "error": str(e)}


def _load_lo_data(db: Session, owner_id: Optional[int]) -> Dict[str, Any]:
    """Load loan officer data for email composition."""
    if not owner_id:
        return {"name": "Your Loan Officer", "email": "noreply@perenniaai.com", "nmls": ""}

    try:
        row = db.execute(text("""
            SELECT first_name, last_name, email, nmls_id, phone
            FROM users WHERE id = :uid
        """), {"uid": owner_id}).fetchone()
        if row:
            return {
                "name": f"{row.first_name or ''} {row.last_name or ''}".strip() or "Your Loan Officer",
                "email": row.email or "noreply@perenniaai.com",
                "nmls": row.nmls_id or "",
                "phone": row.phone or "",
            }
    except Exception as e:
        logger.debug("Failed to load LO data for user %s: %s", owner_id, e)

    return {"name": "Your Loan Officer", "email": "noreply@perenniaai.com", "nmls": ""}


def _load_org_email_config(db: Session, organization_id: int) -> Dict[str, Any]:
    """Load organization email config for compliance footer."""
    try:
        row = db.execute(text("""
            SELECT name, address, city, state, zip_code, phone, website
            FROM organizations WHERE id = :org_id
        """), {"org_id": organization_id}).fetchone()
        if row:
            return {
                "company_name": row.name or "The Tim Loss Team",
                "address": row.address or "",
                "city": row.city or "",
                "state": row.state or "",
                "zip_code": row.zip_code or "",
                "phone": row.phone or "",
                "website": row.website or "",
            }
    except Exception as e:
        logger.debug("Failed to load org email config: %s", e)

    return {"company_name": "The Tim Loss Team"}


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------

def _check_channel_fatigue(
    db: Session,
    lead_id: int,
    organization_id: int,
    channel: str,
    window_minutes: int = 30,
) -> Tuple[bool, Optional[str]]:
    """
    DATA-003: Check if a message was already sent on the same channel within the
    dedup window (default 30 min).  Prevents drip-sequence and orchestrator
    from double-tapping the same lead on the same channel.

    Returns (is_fatigued: bool, last_event_trigger: Optional[str]).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    try:
        row = db.execute(text("""
            SELECT trigger_event, created_at
            FROM engagement_events
            WHERE lead_id = :lid
              AND organization_id = :org_id
              AND channel_chosen = :channel
              AND action_result NOT IN ('blocked', 'failed', 'skipped')
              AND created_at >= :cutoff
            ORDER BY created_at DESC
            LIMIT 1
        """), {
            "lid": lead_id,
            "org_id": organization_id,
            "channel": channel,
            "cutoff": cutoff,
        }).fetchone()

        if row:
            return True, row.trigger_event
    except Exception as e:
        logger.warning("Channel fatigue check failed: %s", e)

    return False, None


def _check_idempotency(
    db: Session,
    lead_id: int,
    organization_id: int,
    trigger_event: str,
    window_seconds: int = 60,
) -> bool:
    """
    DATA-004: Return True if the exact same (lead_id, organization_id,
    trigger_event) already fired within the dedup window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    try:
        row = db.execute(text("""
            SELECT id FROM engagement_events
            WHERE lead_id = :lid
              AND organization_id = :org_id
              AND trigger_event = :trigger
              AND created_at >= :cutoff
            LIMIT 1
        """), {
            "lid": lead_id,
            "org_id": organization_id,
            "trigger": trigger_event,
            "cutoff": cutoff,
        }).fetchone()
        return row is not None
    except Exception as e:
        logger.warning("Idempotency check failed: %s", e)
        return False


def _log_engagement_event(
    db: Session,
    organization_id: int,
    lead_id: int,
    trigger_event: str,
    channel_chosen: Optional[str],
    channel_reason: str,
    action_taken: Optional[str],
    action_result: Optional[str],
    scheduled_next_at: Optional[datetime] = None,
    scheduled_next_trigger: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> None:
    """Insert an engagement event for audit trail and queue processing."""
    try:
        db.execute(text("""
            INSERT INTO engagement_events
                (organization_id, lead_id, trigger_event, channel_chosen,
                 channel_reason, action_taken, action_result, action_metadata,
                 scheduled_next_at, scheduled_next_trigger, created_at)
            VALUES
                (:org_id, :lid, :trigger, :channel, :reason, :action,
                 :result, :meta::jsonb, :next_at, :next_trigger, :now)
        """), {
            "org_id": organization_id,
            "lid": lead_id,
            "trigger": trigger_event,
            "channel": channel_chosen,
            "reason": channel_reason[:500] if channel_reason else None,
            "action": action_taken,
            "result": action_result,
            "meta": json.dumps(metadata or {}, default=str)[:2000],
            "next_at": scheduled_next_at,
            "next_trigger": scheduled_next_trigger,
            "now": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as e:
        logger.warning("Failed to log engagement event: %s", e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass


def _log_activity(
    db: Session,
    lead_id: int,
    organization_id: int,
    owner_id: Optional[int],
    activity_type: str,
    content: str,
) -> None:
    """Log to the activities table for CRM timeline visibility."""
    try:
        db.execute(text("""
            INSERT INTO activities (lead_id, organization_id, user_id, type, content, created_at)
            VALUES (:lid, :org_id, :uid, :atype, :content, :now)
        """), {
            "lid": lead_id,
            "org_id": organization_id,
            "uid": owner_id,
            "atype": activity_type,
            "content": content[:2000],
            "now": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as e:
        logger.debug("Failed to log activity: %s", e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Sequence scheduling (next touchpoint)
# ---------------------------------------------------------------------------

def _determine_next_touchpoint(
    trigger_event: str,
    channel_used: Optional[str],
    action_result: Optional[str],
) -> Tuple[Optional[str], Optional[int]]:
    """
    Determine the next trigger event and delay (minutes) in the sequence.

    Returns (next_trigger, delay_minutes) or (None, None) if sequence is complete.
    """
    if action_result and "fail" in action_result.lower():
        # Don't schedule follow-ups for failed dispatches
        return None, None

    sequences = {
        # trigger_event -> (next_trigger, delay_minutes)
        "new_lead": {
            "call": ("no_answer", 0),         # Handled by call outcome, not timer
            "sms": ("sms_no_response_24h", 1440),
            "email": ("sms_no_response_24h", 1440),
            "voicemail": ("voicemail_dropped", 0),
        },
        "no_answer": {
            "voicemail": ("voicemail_dropped", 0),
            "sms": ("sms_no_response_24h", 1440),
            "email": ("sms_no_response_24h", 1440),
        },
        "voicemail_dropped": {
            "sms": ("sms_no_response_24h", 1440),
            "email": ("sms_no_response_24h", 1440),
        },
        "sms_no_response_24h": {
            "email": ("stale_7d", 10080),   # 7 days
        },
        "email_opened": {
            "sms": ("sms_no_response_24h", 1440),
            "call": None,  # Human took over
        },
        "stale_7d": {
            "sms": ("stale_30d", 33120),    # 23 more days
            "email": ("stale_30d", 33120),
        },
        "appointment_set": {
            "email": None,  # Sequence complete; scheduler handles reminders
        },
        "appointment_missed": {
            "sms": ("stale_7d", 10080),
            "email": ("stale_7d", 10080),
        },
        "call_completed": {
            "email": None,  # Post-call email sent; await response
        },
        "rate_drop": {
            "sms": ("sms_no_response_24h", 1440),
            "email": ("sms_no_response_24h", 1440),
        },
        "document_needed": {
            "email": ("stale_7d", 4320),  # Re-request in 3 days
            "sms": ("stale_7d", 4320),
        },
        # Terminal triggers — no follow-up
        "qualification_complete": {},
        "deal_breaker_found": {},
        "loan_funded": {},
        "stale_30d": {},  # Enters long-term drip; orchestrator done
    }

    trigger_map = sequences.get(trigger_event, {})
    if not trigger_map:
        return None, None

    next_info = trigger_map.get(channel_used)
    if next_info is None:
        return None, None

    return next_info


# ---------------------------------------------------------------------------
# Create task for LO
# ---------------------------------------------------------------------------

def _create_lo_task(
    db: Session,
    lead_id: int,
    organization_id: int,
    owner_id: Optional[int],
    task_type: str,
    description: str,
    due_minutes: int = 60,
) -> None:
    """Create a task for the loan officer in the CRM task system."""
    if not owner_id:
        return

    due_at = datetime.now(timezone.utc) + timedelta(minutes=due_minutes)
    try:
        db.execute(text("""
            INSERT INTO tasks (
                lead_id, organization_id, assigned_to, title, description,
                status, priority, due_date, created_at
            ) VALUES (
                :lid, :org_id, :uid, :title, :desc,
                'pending', 'high', :due, :now
            )
        """), {
            "lid": lead_id,
            "org_id": organization_id,
            "uid": owner_id,
            "title": f"Follow up: {task_type}",
            "desc": description[:1000],
            "due": due_at,
            "now": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as e:
        logger.debug("Failed to create LO task: %s", e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass


# ===========================================================================
# PUBLIC API
# ===========================================================================

async def orchestrate_lead_engagement(
    db: Session,
    lead_id: int,
    organization_id: int,
    trigger_event: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Master engagement decision engine.

    1. Load lead engagement context (preferred channel, response patterns, timezone)
    2. Check compliance (DNC, opt-out, quiet hours, TCPA)
    3. Choose optimal channel
    4. Choose optimal timing
    5. Dispatch to appropriate service
    6. Log the orchestration decision
    7. Schedule the next touchpoint

    Returns dict with keys:
        trigger, channel, action, result, next_trigger, next_at, reason
    """
    _ensure_engagement_tables(db)

    if trigger_event not in VALID_TRIGGERS:
        logger.warning("Unknown trigger event: %s", trigger_event)
        return {"error": f"unknown trigger: {trigger_event}", "trigger": trigger_event}

    # 0a. DATA-004: Idempotency — reject duplicate trigger within 60s
    if _check_idempotency(db, lead_id, organization_id, trigger_event, window_seconds=60):
        logger.info(
            "Duplicate trigger deduplicated",
            extra={
                "lead_id": lead_id,
                "organization_id": organization_id,
                "trigger_event": trigger_event,
            },
        )
        return {"status": "deduplicated", "trigger": trigger_event}

    # 1. Load context
    ctx = _load_lead_context(db, lead_id, organization_id)
    if not ctx:
        logger.warning("Lead %s not found in org %s", lead_id, organization_id)
        return {"error": "lead_not_found", "trigger": trigger_event}

    # Check terminal stages — don't engage
    terminal_stages = {"FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY"}
    if ctx["stage"] in terminal_stages and trigger_event not in ("loan_funded",):
        logger.info("Lead %s in terminal stage %s — skipping %s", lead_id, ctx["stage"], trigger_event)
        _log_engagement_event(
            db, organization_id, lead_id, trigger_event,
            None, f"terminal stage: {ctx['stage']}", "skipped", "terminal_stage",
        )
        return {"trigger": trigger_event, "action": "skipped", "reason": f"terminal stage: {ctx['stage']}"}

    # 2. Load engagement history for fatigue + pattern analysis
    recent = _load_recent_engagement(db, lead_id, organization_id)

    # 3. Fatigue check
    contacts_today = _count_contacts_today(db, lead_id, organization_id)
    max_daily = ctx.get("max_contacts_per_day", 5)
    if contacts_today >= max_daily and trigger_event not in ("new_lead", "rate_drop", "document_needed"):
        logger.info("Lead %s hit daily contact limit (%s/%s)", lead_id, contacts_today, max_daily)
        # Schedule for tomorrow morning instead
        tomorrow_8am = (
            datetime.now(timezone.utc).replace(hour=13, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
        )  # 13:00 UTC ~ 8am ET
        _log_engagement_event(
            db, organization_id, lead_id, trigger_event,
            None, f"daily limit reached ({contacts_today}/{max_daily})",
            "deferred", "fatigue_limit",
            scheduled_next_at=tomorrow_8am,
            scheduled_next_trigger=trigger_event,
        )
        return {
            "trigger": trigger_event,
            "action": "deferred",
            "reason": f"daily contact limit ({contacts_today}/{max_daily})",
            "next_at": tomorrow_8am.isoformat(),
        }

    contacts_week = _count_contacts_this_week(db, lead_id, organization_id)
    max_weekly = ctx.get("max_contacts_per_week", 15)
    if contacts_week >= max_weekly and trigger_event not in ("new_lead", "document_needed"):
        logger.info("Lead %s hit weekly contact limit (%s/%s)", lead_id, contacts_week, max_weekly)
        _log_engagement_event(
            db, organization_id, lead_id, trigger_event,
            None, f"weekly limit reached ({contacts_week}/{max_weekly})",
            "deferred", "fatigue_limit_weekly",
        )
        return {
            "trigger": trigger_event,
            "action": "deferred",
            "reason": f"weekly contact limit ({contacts_week}/{max_weekly})",
        }

    # 4. Select channel
    channel, channel_reason = _select_channel(db, ctx, trigger_event, recent)

    # OBS-008: Log every channel selection decision with structured fields
    logger.info(
        "Engagement channel selected",
        extra={
            "lead_id": lead_id,
            "organization_id": organization_id,
            "trigger_event": trigger_event,
            "channel_chosen": channel,
            "reason": channel_reason,
        },
    )

    if not channel:
        _log_engagement_event(
            db, organization_id, lead_id, trigger_event,
            None, channel_reason, "skipped", "no_channel_available",
        )
        return {
            "trigger": trigger_event,
            "action": "skipped",
            "reason": channel_reason,
        }

    # 4b. DATA-003: Channel fatigue — skip if same channel used in last 30 min
    is_fatigued, last_trigger = _check_channel_fatigue(
        db, lead_id, organization_id, channel, window_minutes=30,
    )
    if is_fatigued and trigger_event not in ("new_lead", "document_needed"):
        logger.info(
            "Channel fatigue — skipping duplicate channel",
            extra={
                "lead_id": lead_id,
                "organization_id": organization_id,
                "trigger_event": trigger_event,
                "channel_chosen": channel,
                "reason": f"channel {channel} used by trigger '{last_trigger}' within 30 min",
            },
        )
        _log_engagement_event(
            db, organization_id, lead_id, trigger_event,
            channel, f"channel_fatigue: {channel} used by '{last_trigger}' within 30 min",
            "skipped", "channel_fatigue",
        )
        return {
            "trigger": trigger_event,
            "channel": channel,
            "action": "skipped",
            "reason": f"channel fatigue: {channel} already used within 30 min (last: {last_trigger})",
        }

    # 5. Determine timing
    delay_minutes = SEQUENCE_DELAYS.get(trigger_event, 0)
    if delay_minutes > 0 and trigger_event not in ("new_lead",):
        # Schedule for later instead of dispatching now
        scheduled_at = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
        _log_engagement_event(
            db, organization_id, lead_id, trigger_event,
            channel, channel_reason, "scheduled", "delayed",
            scheduled_next_at=scheduled_at,
            scheduled_next_trigger=trigger_event,
            metadata=metadata,
        )
        return {
            "trigger": trigger_event,
            "channel": channel,
            "action": "scheduled",
            "reason": channel_reason,
            "scheduled_at": scheduled_at.isoformat(),
        }

    # 6. Dispatch to service
    dispatch_result: Dict[str, Any]
    action_taken = f"dispatch_{channel}"

    if channel == "call":
        dispatch_result = await _dispatch_call(db, ctx, trigger_event)
    elif channel == "sms":
        dispatch_result = await _dispatch_sms(db, ctx, trigger_event)
    elif channel == "email":
        # PERF-006: TODO — The Microsoft Graph OAuth token used for email
        # dispatch may be expired (tokens last ~60 min and are non-refreshable
        # in the current implementation).  The actual refresh/re-auth logic
        # lives in services.email_delivery_service.EmailDeliveryService and
        # services.los_integration.encompass_oauth_service.  If email dispatch
        # starts returning 401s, the Graph token needs to be re-acquired there.
        dispatch_result = await _dispatch_email(db, ctx, trigger_event)
    elif channel == "voicemail":
        dispatch_result = await _dispatch_voicemail(db, ctx, trigger_event)
    else:
        dispatch_result = {"success": False, "error": f"unknown channel: {channel}"}

    action_result = "success" if dispatch_result.get("success") else f"failed: {dispatch_result.get('error', 'unknown')}"

    # OBS-008: Log every dispatch decision with structured fields
    logger.info(
        "Engagement action dispatched",
        extra={
            "lead_id": lead_id,
            "organization_id": organization_id,
            "trigger_event": trigger_event,
            "channel_chosen": channel,
            "action_taken": action_taken,
            "action_result": action_result,
            "reason": channel_reason,
        },
    )

    # 7. Handle trigger-specific side effects
    if trigger_event == "call_completed" and channel == "email":
        _create_lo_task(
            db, lead_id, organization_id, ctx.get("owner_id"),
            "post-call review",
            f"Review call with {ctx.get('name', 'lead')} and update pipeline stage.",
            due_minutes=60,
        )

    if trigger_event == "appointment_missed":
        _create_lo_task(
            db, lead_id, organization_id, ctx.get("owner_id"),
            "missed appointment",
            f"{ctx.get('name', 'Lead')} missed their appointment. Re-engagement sent — follow up personally.",
            due_minutes=120,
        )

    # 8. Update lead.last_contact
    if dispatch_result.get("success"):
        try:
            db.execute(text("""
                UPDATE leads SET last_contact = :now WHERE id = :lid AND organization_id = :org_id
            """), {"now": datetime.now(timezone.utc), "lid": lead_id, "org_id": organization_id})
            db.commit()
        except Exception as e:
            logger.warning(
                "Failed to update last_contact for lead %s: %s", lead_id, e,
            )
            try:
                db.rollback()
            except Exception as _exc:  # noqa: BLE001
                pass

    # 9. Determine and schedule next touchpoint
    next_trigger, next_delay = _determine_next_touchpoint(trigger_event, channel, action_result)
    scheduled_next_at = None
    if next_trigger and next_delay:
        scheduled_next_at = datetime.now(timezone.utc) + timedelta(minutes=next_delay)

    # 10. Log the event with full decision explanation for fair lending audit
    _log_engagement_event(
        db, organization_id, lead_id, trigger_event,
        channel, channel_reason, action_taken, action_result,
        scheduled_next_at=scheduled_next_at,
        scheduled_next_trigger=next_trigger,
        metadata={
            **(metadata or {}),
            **dispatch_result,
            "decision_factors": {
                "ai_score": ctx.get("ai_score"),
                "stage": ctx.get("stage"),
                "preferred_channels": ctx.get("preferred_channels"),
                "contacts_today": contacts_today,
                "contacts_week": contacts_week,
                "time_bucket": _get_time_bucket(ctx.get("timezone", "America/New_York")),
                "consent": {
                    "sms": ctx.get("sms_consent"),
                    "call": ctx.get("call_consent"),
                    "email": ctx.get("email_opt_in"),
                },
            },
        },
    )

    # 11. Log CRM activity
    _log_activity(
        db, lead_id, organization_id, ctx.get("owner_id"),
        "engagement",
        f"Engagement orchestrator: {trigger_event} → {channel} ({action_result})",
    )

    result = {
        "trigger": trigger_event,
        "channel": channel,
        "action": action_taken,
        "result": action_result,
        "reason": channel_reason,
    }
    if next_trigger:
        result["next_trigger"] = next_trigger
        result["next_at"] = scheduled_next_at.isoformat() if scheduled_next_at else None

    return result


async def get_next_best_action(
    db: Session,
    lead_id: int,
    organization_id: int,
) -> Dict[str, Any]:
    """
    Analyze all prior engagement, response patterns, and pipeline stage
    to recommend what the AI should do next for this lead.

    Returns:
        {
            "action": "call"|"sms"|"email"|"wait",
            "reason": str,
            "optimal_time": datetime_iso_str,
            "content_suggestion": str,
        }
    """
    _ensure_engagement_tables(db)

    ctx = _load_lead_context(db, lead_id, organization_id)
    if not ctx:
        return {"action": "wait", "reason": "lead not found", "optimal_time": None, "content_suggestion": ""}

    # Terminal stage check
    terminal_stages = {"FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY"}
    if ctx["stage"] in terminal_stages:
        return {
            "action": "wait",
            "reason": f"lead in terminal stage: {ctx['stage']}",
            "optimal_time": None,
            "content_suggestion": "",
        }

    recent = _load_recent_engagement(db, lead_id, organization_id, hours=168)  # 7 days
    contacts_today = _count_contacts_today(db, lead_id, organization_id)

    # Fatigue check
    if contacts_today >= ctx.get("max_contacts_per_day", 5):
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        return {
            "action": "wait",
            "reason": f"daily contact limit reached ({contacts_today})",
            "optimal_time": tomorrow.replace(hour=14, minute=0).isoformat(),
            "content_suggestion": "Resume outreach tomorrow morning.",
        }

    # Determine what's been tried recently
    channels_used_48h = [e["channel_chosen"] for e in recent if e.get("created_at") and
                         e["created_at"] > datetime.now(timezone.utc) - timedelta(hours=48)]
    last_event = recent[0] if recent else None

    # How long since last contact?
    last_contact = ctx.get("last_contact")
    days_since_contact = None
    if last_contact:
        if isinstance(last_contact, datetime):
            days_since_contact = (datetime.now(timezone.utc) - last_contact.replace(tzinfo=timezone.utc)).days
        else:
            days_since_contact = None

    # Decision logic
    stage = ctx["stage"]
    tz = ctx.get("timezone", "America/New_York")
    time_bucket = _get_time_bucket(tz)

    # New leads with no engagement: call immediately
    if not recent and stage in ("NEW", "CONTACTED"):
        if time_bucket in ("morning", "afternoon") and ctx.get("phone"):
            return {
                "action": "call",
                "reason": "new lead with no prior engagement — speed-to-lead call",
                "optimal_time": datetime.now(timezone.utc).isoformat(),
                "content_suggestion": "Introduce yourself, qualify interest, offer consultation.",
            }
        else:
            return {
                "action": "sms",
                "reason": "new lead, outside calling hours — SMS introduction",
                "optimal_time": datetime.now(timezone.utc).isoformat(),
                "content_suggestion": "Quick intro text with offer to connect.",
            }

    # If last action was a call that went unanswered — SMS follow-up
    if last_event and last_event.get("trigger_event") in ("new_lead", "no_answer") and \
       last_event.get("channel_chosen") in ("call", "voicemail"):
        if "sms" not in channels_used_48h:
            return {
                "action": "sms",
                "reason": "call went unanswered — SMS follow-up recommended",
                "optimal_time": datetime.now(timezone.utc).isoformat(),
                "content_suggestion": "Mention you tried calling and offer alternative contact.",
            }

    # If SMS was sent but no response within 24h — email
    if last_event and last_event.get("channel_chosen") == "sms" and "email" not in channels_used_48h:
        if last_event.get("created_at"):
            hours_since = (datetime.now(timezone.utc) - last_event["created_at"]).total_seconds() / 3600
            if hours_since >= 24:
                return {
                    "action": "email",
                    "reason": "SMS sent 24h+ ago with no response — email follow-up",
                    "optimal_time": datetime.now(timezone.utc).isoformat(),
                    "content_suggestion": "Detailed email with loan options and CTA.",
                }

    # Stale lead check
    if days_since_contact and days_since_contact >= 30:
        return {
            "action": "email",
            "reason": f"lead stale for {days_since_contact} days — long-term nurture email",
            "optimal_time": datetime.now(timezone.utc).isoformat(),
            "content_suggestion": "Market update, rate environment changes, soft re-engagement.",
        }
    elif days_since_contact and days_since_contact >= 7:
        channel = "sms" if time_bucket != "quiet" else "email"
        return {
            "action": channel,
            "reason": f"lead quiet for {days_since_contact} days — re-engagement nudge",
            "optimal_time": datetime.now(timezone.utc).isoformat(),
            "content_suggestion": "Check-in message, ask if they have questions.",
        }

    # Active pipeline: recommend waiting if recently contacted
    if days_since_contact is not None and days_since_contact < 2:
        next_time = datetime.now(timezone.utc) + timedelta(days=2)
        return {
            "action": "wait",
            "reason": f"recently contacted {days_since_contact} day(s) ago — avoid fatigue",
            "optimal_time": next_time.replace(hour=14, minute=0).isoformat(),
            "content_suggestion": "Wait for borrower response before next outreach.",
        }

    # Default: SMS is the safest general-purpose channel
    return {
        "action": "sms",
        "reason": "default recommendation based on lead profile",
        "optimal_time": datetime.now(timezone.utc).isoformat(),
        "content_suggestion": "Personalized check-in based on their loan type and stage.",
    }


async def process_engagement_queue(
    db: Session,
    organization_id: int,
    batch_size: int = 100,
) -> Dict[str, Any]:
    """
    Batch processor: find all leads with pending engagement actions
    (scheduled_next_at <= now) and process each one through the orchestrator.

    PERF-005: Uses LIMIT-based pagination to avoid loading unbounded rows.
    Each chunk fetches at most ``batch_size`` (default 100) rows, processes
    them, then fetches the next chunk until none remain.

    Respects rate limits: max 1 call/sec, max 1 SMS/sec.

    Returns:
        {
            "processed": int,
            "succeeded": int,
            "failed": int,
            "deferred": int,
            "details": list,
        }
    """
    _ensure_engagement_tables(db)

    now = datetime.now(timezone.utc)
    stats: Dict[str, Any] = {"processed": 0, "succeeded": 0, "failed": 0, "deferred": 0, "details": []}

    # PERF-005: Paginate in chunks — each iteration fetches at most batch_size rows
    while True:
        # Fetch one chunk with row-level locking to prevent duplicate processing
        rows = db.execute(text("""
            SELECT id, lead_id, scheduled_next_trigger, scheduled_next_at
            FROM engagement_events
            WHERE id IN (
                SELECT DISTINCT ON (lead_id) id
                FROM engagement_events
                WHERE organization_id = :org_id
                  AND scheduled_next_at IS NOT NULL
                  AND scheduled_next_at <= :now
                  AND scheduled_next_trigger IS NOT NULL
                ORDER BY lead_id, scheduled_next_at ASC
                LIMIT :batch
            )
            FOR UPDATE SKIP LOCKED
        """), {"org_id": organization_id, "now": now, "batch": batch_size}).fetchall()

        if not rows:
            break

        logger.info("Engagement queue chunk: %d pending actions for org %s", len(rows), organization_id)

        for row in rows:
            lead_id = row.lead_id
            trigger = row.scheduled_next_trigger
            event_id = row.id

            try:
                result = await orchestrate_lead_engagement(
                    db=db,
                    lead_id=lead_id,
                    organization_id=organization_id,
                    trigger_event=trigger,
                    metadata={"source": "queue_processor", "parent_event_id": event_id},
                )

                stats["processed"] += 1
                action = result.get("action", "unknown")

                if result.get("result") and "success" in result["result"]:
                    stats["succeeded"] += 1
                elif action == "deferred":
                    stats["deferred"] += 1
                elif result.get("error") or (result.get("result") and "fail" in result.get("result", "")):
                    stats["failed"] += 1
                else:
                    stats["succeeded"] += 1

                stats["details"].append({
                    "lead_id": lead_id,
                    "trigger": trigger,
                    "result": result.get("result") or result.get("action"),
                })

                # Clear the scheduled_next fields on the source event to prevent re-processing
                try:
                    db.execute(text("""
                        UPDATE engagement_events
                        SET scheduled_next_at = NULL, scheduled_next_trigger = NULL
                        WHERE id = :eid
                    """), {"eid": event_id})
                    db.commit()
                except Exception as _exc:  # noqa: BLE001
                    logger.exception("unhandled exception")
                    try:
                        db.rollback()
                    except Exception as _exc:  # noqa: BLE001
                        pass

            except Exception as e:
                logger.exception("Queue processing failed for lead %s trigger %s", lead_id, trigger)
                stats["processed"] += 1
                stats["failed"] += 1
                stats["details"].append({"lead_id": lead_id, "trigger": trigger, "error": str(e)})

            # Rate limiting: 1 second between dispatches
            await asyncio.sleep(1.0)

        # If we got fewer rows than batch_size, there are no more to process
        if len(rows) < batch_size:
            break

    logger.info(
        "Engagement queue complete: processed=%d succeeded=%d failed=%d deferred=%d",
        stats["processed"], stats["succeeded"], stats["failed"], stats["deferred"],
    )

    return stats
