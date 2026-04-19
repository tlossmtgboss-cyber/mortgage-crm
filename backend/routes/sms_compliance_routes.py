"""
SMS Compliance Routes — A2P 10DLC STOP/HELP keyword handling

Handles inbound SMS webhooks from Telnyx to process:
  - STOP / STOPALL / UNSUBSCRIBE / CANCEL / END / QUIT → opt-out, add to DNC
  - HELP / INFO → reply with company info and opt-out instructions
  - START / YES / UNSTOP → opt back in, remove from DNC

Maintains a per-org SMS consent/opt-out table for TCPA compliance.
"""

import json
import os
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
import httpx

from db import get_db
from middleware.webhook_verification import require_telnyx_webhook

logger = logging.getLogger(__name__)


def _get_current_user():
    """Lazy import to avoid circular dependency."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible


router = APIRouter(prefix="/api/v1/sms", tags=["SMS Compliance"])

# ---------------------------------------------------------------------------
# Keyword sets (case-insensitive)
# ---------------------------------------------------------------------------

STOP_KEYWORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
HELP_KEYWORDS = {"help", "info"}
START_KEYWORDS = {"start", "yes", "unstop", "subscribe"}

# ---------------------------------------------------------------------------
# Auto-reply templates (must comply with carrier requirements)
# ---------------------------------------------------------------------------

STOP_REPLY = (
    "You have been unsubscribed and will no longer receive messages from us. "
    "Reply START to re-subscribe."
)

HELP_REPLY = (
    "Perennia AI Mortgage Assistant. "
    "For help, contact support@perenniaai.com or call (843) 383-8956. "
    "Reply STOP to opt out of messages. Msg & data rates may apply."
)

START_REPLY = (
    "You have been re-subscribed to messages from Perennia AI. "
    "Reply STOP to opt out at any time. Msg & data rates may apply."
)


# ---------------------------------------------------------------------------
# Telnyx SMS send helper
# ---------------------------------------------------------------------------

async def _send_sms(to: str, from_: str, body: str, messaging_profile_id: str = ""):
    """Send an SMS reply via the centralized Telnyx chokepoint.

    These are compliance-route auto-responses (STOP/START confirmations),
    so we bypass the compliance gate — the recipient just opted out/in and
    the confirmation is legally required.
    """
    try:
        from telephony.sms import send_sms_verified_async

        result = await send_sms_verified_async(
            to=to,
            from_=from_,
            text=body,
            messaging_profile_id=messaging_profile_id or None,
            bypass_compliance=True,  # Opt-out confirmations are legally required
        )
        if result.get("status") == "sent":
            logger.info("SMS reply sent to ***%s", to[-4:] if to else "?")
        else:
            logger.error("SMS reply failed for ***%s: %s", to[-4:] if to else "?", result.get("reason", "unknown"))
    except Exception as e:
        logger.exception("Failed to send SMS reply to %s: %s", to[-4:] if to else "?", e)


# ---------------------------------------------------------------------------
# Opt-out / opt-in persistence
# ---------------------------------------------------------------------------

def _opt_out(db: Session, phone: str, org_id: Optional[int], keyword: str):
    """Record an SMS opt-out (STOP). Upserts into sms_opt_outs table."""
    try:
        now = datetime.now(timezone.utc)
        db.execute(text("""
            INSERT INTO sms_opt_outs (phone_number, opt_out_keyword, organization_id,
                active, opted_out_at)
            VALUES (:phone, :kw, :org_id, TRUE, :now)
            ON CONFLICT (phone_number) DO UPDATE SET
                active = TRUE, opted_out_at = EXCLUDED.opted_out_at,
                opt_out_keyword = EXCLUDED.opt_out_keyword,
                organization_id = COALESCE(EXCLUDED.organization_id, sms_opt_outs.organization_id)
        """), {"phone": phone, "kw": keyword, "org_id": org_id, "now": now})
        db.commit()
        logger.info("SMS opt-out recorded: ***%s keyword=%s org=%s", phone[-4:], keyword, org_id)
    except Exception as e:
        logger.exception("Failed to record opt-out for ***%s: %s", phone[-4:], e)
        db.rollback()
        raise  # Opt-out MUST succeed or visibly fail — TCPA violation if silently ignored


def _opt_in(db: Session, phone: str, org_id: Optional[int], keyword: str):
    """Record an SMS opt-in (START). Deactivate opt-out flag."""
    try:
        now = datetime.now(timezone.utc)
        if org_id:
            db.execute(text("""
                UPDATE sms_opt_outs SET active = FALSE, opted_in_at = :now
                WHERE phone_number = :phone
                  AND (organization_id = :org_id OR organization_id IS NULL)
            """), {"now": now, "phone": phone, "org_id": org_id})
        else:
            db.execute(text("""
                UPDATE sms_opt_outs SET active = FALSE, opted_in_at = :now
                WHERE phone_number = :phone
            """), {"now": now, "phone": phone})
        db.commit()
        logger.info("SMS opt-in recorded: ***%s keyword=%s org=%s", phone[-4:], keyword, org_id)
    except Exception as e:
        logger.exception("Failed to record opt-in for ***%s: %s", phone[-4:], e)
        db.rollback()
        raise  # Opt-in must succeed or visibly fail — caller needs to know


def is_opted_out(db: Session, phone: str, org_id: Optional[int]) -> bool:
    """Check if a phone number has opted out of SMS for this org."""
    if org_id:
        row = db.execute(text("""
            SELECT id FROM sms_opt_outs
            WHERE phone_number = :phone AND active = TRUE
              AND (organization_id = :org_id OR organization_id IS NULL)
            LIMIT 1
        """), {"phone": phone, "org_id": org_id}).fetchone()
    else:
        row = db.execute(text("""
            SELECT id FROM sms_opt_outs
            WHERE phone_number = :phone AND active = TRUE
            LIMIT 1
        """), {"phone": phone}).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Resolve org from Telnyx "to" number
# ---------------------------------------------------------------------------

def _resolve_org(db: Session, to_number: str) -> Optional[int]:
    """Try to find the organization that owns the receiving phone number."""
    # Check agent_telephony_settings or verified_caller_ids
    row = db.execute(text("""
        SELECT organization_id FROM verified_caller_ids
        WHERE phone_number = :phone LIMIT 1
    """), {"phone": to_number}).fetchone()
    if row:
        return row.organization_id

    # Fallback: check the Telnyx from number in org settings
    row = db.execute(text("""
        SELECT organization_id FROM agent_telephony_settings
        WHERE business_caller_id = :phone LIMIT 1
    """), {"phone": to_number}).fetchone()
    if row:
        return row.organization_id

    return None


# ---------------------------------------------------------------------------
# Inbound SMS webhook (Telnyx)
# ---------------------------------------------------------------------------

@router.post("/inbound-webhook")
async def sms_inbound_webhook(
    request: Request,
    raw_body: bytes = Depends(require_telnyx_webhook),
    db: Session = Depends(get_db),
):
    """
    Telnyx inbound SMS webhook handler.

    Processes STOP/HELP/START keywords for A2P 10DLC compliance.
    Non-keyword messages are logged but not processed here.
    Webhook signature is verified by require_telnyx_webhook dependency.
    """
    payload = json.loads(raw_body)
    event_data = payload.get("data", {})
    event_type = event_data.get("event_type", "")

    if event_type != "message.received":
        return JSONResponse({"status": "ignored"})

    event_payload = event_data.get("payload", {})
    from_number = event_payload.get("from", {}).get("phone_number", "")
    to_number = event_payload.get("to", [{}])[0].get("phone_number", "") if event_payload.get("to") else ""
    message_text = (event_payload.get("text", "") or "").strip()

    if not from_number or not message_text:
        return JSONResponse({"status": "ignored"})

    keyword = message_text.lower().strip()
    org_id = _resolve_org(db, to_number)

    logger.info(
        "Inbound SMS: from=***%s to=%s text=%r org=%s",
        from_number[-4:], to_number[-4:] if to_number else "?", keyword[:20], org_id,
    )

    # Log all inbound SMS for audit
    try:
        db.execute(text("""
            INSERT INTO sms_inbound_log (from_phone, to_phone, message_text, keyword_detected,
                organization_id, created_at)
            VALUES (:from_ph, :to_ph, :msg, :kw, :org_id, :now)
        """), {
            "from_ph": from_number, "to_ph": to_number,
            "msg": message_text[:500], "kw": keyword if keyword in STOP_KEYWORDS | HELP_KEYWORDS | START_KEYWORDS else None,
            "org_id": org_id, "now": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception:
        db.rollback()

    # ── STOP keywords ──
    if keyword in STOP_KEYWORDS:
        try:
            _opt_out(db, from_number, org_id, keyword)
        except Exception:
            # Still send the legally-required STOP confirmation
            await _send_sms(to=from_number, from_=to_number, body=STOP_REPLY)
            # Return 500 so Telnyx retries the webhook — opt-out MUST persist
            return JSONResponse(
                {"status": "error", "detail": "opt-out failed to persist"},
                status_code=500,
            )
        await _send_sms(to=from_number, from_=to_number, body=STOP_REPLY)
        return JSONResponse({"status": "opt_out", "keyword": keyword})

    # ── HELP keywords ──
    if keyword in HELP_KEYWORDS:
        await _send_sms(to=from_number, from_=to_number, body=HELP_REPLY)
        return JSONResponse({"status": "help_sent", "keyword": keyword})

    # ── START keywords ──
    if keyword in START_KEYWORDS:
        try:
            _opt_in(db, from_number, org_id, keyword)
        except Exception:
            await _send_sms(to=from_number, from_=to_number, body=START_REPLY)
            return JSONResponse(
                {"status": "error", "detail": "opt-in failed to persist"},
                status_code=500,
            )
        await _send_sms(to=from_number, from_=to_number, body=START_REPLY)
        return JSONResponse({"status": "opt_in", "keyword": keyword})

    # Non-keyword message — not handled here
    return JSONResponse({"status": "not_keyword"})


# ---------------------------------------------------------------------------
# Check opt-out status (for use by other services before sending SMS)
# ---------------------------------------------------------------------------

class OptOutCheckRequest(BaseModel):
    phone: str
    organization_id: int


@router.post("/check-opt-out")
async def check_opt_out_status(
    body: OptOutCheckRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Check if a phone number has opted out of SMS."""
    user_org = getattr(current_user, "organization_id", None) if current_user else None
    if not current_user or not user_org:
        raise HTTPException(status_code=401, detail="Authentication required")
    if body.organization_id != user_org:
        raise HTTPException(status_code=403, detail="Cannot check opt-out for another organization")
    opted = is_opted_out(db, body.phone, body.organization_id)
    return {"phone": body.phone, "opted_out": opted}


# ---------------------------------------------------------------------------
# Admin: List opt-outs for an org
# ---------------------------------------------------------------------------

@router.get("/opt-outs")
async def list_opt_outs(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """List opted-out phone numbers for the current org."""
    org_id = getattr(current_user, "organization_id", None) if current_user else None
    if not org_id:
        raise HTTPException(status_code=401, detail="Auth required")

    rows = db.execute(text("""
        SELECT phone_number, opted_out_at, opt_out_keyword
        FROM sms_opt_outs
        WHERE organization_id = :org_id AND active = TRUE
        ORDER BY opted_out_at DESC
        LIMIT :lim
    """), {"org_id": org_id, "lim": limit}).fetchall()

    return {
        "opt_outs": [
            {
                "phone": r[0],
                "opted_out_at": r[1].isoformat() if r[1] else None,
                "keyword": r[2],
            }
            for r in rows
        ],
        "count": len(rows),
    }
