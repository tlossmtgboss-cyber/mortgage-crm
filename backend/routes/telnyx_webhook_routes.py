"""
Telnyx Webhook Routes

Handles all Telnyx webhook callbacks including:
- Call Control events (initiated, ringing, answered, hangup)
- AMD (Answering Machine Detection) events
- SMS delivery status events
- Recording events
"""

import hmac
import os
import json
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from database import get_db, SessionLocal
from middleware.webhook_verification import require_telnyx_webhook as _require_telnyx_webhook_strict

_TELNYX_IP_PREFIXES = ("192.76.120.", "185.246.41.", "103.115.244.")


def _extract_origin_ip(request: Request) -> str:
    """Get real client IP, preferring Cloudflare header since API is behind CF."""
    for header in ("cf-connecting-ip", "x-real-ip"):
        val = request.headers.get(header, "").strip()
        if val:
            return val
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


async def require_telnyx_webhook(request: Request) -> bytes:
    """Telnyx webhook verification with IP-based fallback.

    Ed25519 verification fails in production because Cloudflare (in front of
    api.perenniaai.com) can modify request body bytes. Falls back to IP
    verification using cf-connecting-ip header for the real origin IP.
    """
    try:
        return await _require_telnyx_webhook_strict(request)
    except HTTPException as exc:
        if exc.status_code in (401, 503):
            origin_ip = _extract_origin_ip(request)
            if any(origin_ip.startswith(p) for p in _TELNYX_IP_PREFIXES):
                body = await request.body()
                logger.warning(
                    "Telnyx Ed25519 failed — allowing via IP fallback. "
                    "ip=%s, body_len=%d", origin_ip, len(body),
                )
                return body
            logger.warning(
                "Telnyx webhook IP fallback failed: origin_ip=%s not in Telnyx range. "
                "cf_ip=%s, xff=%s, client=%s",
                origin_ip,
                request.headers.get("cf-connecting-ip", ""),
                request.headers.get("x-forwarded-for", ""),
                request.client.host if request.client else "",
            )
        raise

# Call Intelligence Integration (optional — degrades gracefully if unavailable)
try:
    from services.call_intelligence.integration import CallIntelligenceIntegration
    CALL_INTELLIGENCE_ENABLED = True
except ImportError:
    CALL_INTELLIGENCE_ENABLED = False
    CallIntelligenceIntegration = None
from telephony.providers.telnyx.webhooks import (
    parse_telnyx_webhook,
    TelnyxCallEvent,
    TelnyxAMDEvent,
    TelnyxSMSEvent,
    TelnyxEventType,
    map_telnyx_status_to_legacy,
    map_telnyx_amd_to_legacy,
)
from telephony.providers.telnyx.texml import TeXMLResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/telnyx", tags=["Telnyx Webhooks"])

# API base URL for callbacks
API_BASE_URL = os.getenv("API_URL") or os.getenv("PRODUCTION_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
if API_BASE_URL and not API_BASE_URL.startswith("http"):
    API_BASE_URL = f"https://{API_BASE_URL}"
if not API_BASE_URL:
    API_BASE_URL = "https://api.perenniaai.com"


def _validate_texml_request(request: Request):
    """Validate TeXML callback requests using a shared secret or Telnyx signature."""
    api_key = request.headers.get("X-API-Key", "")
    expected = os.environ.get("TEXML_CALLBACK_SECRET", "")
    if not expected or not api_key or not hmac.compare_digest(api_key, expected):
        raise HTTPException(status_code=403, detail="Invalid callback authentication")


# =============================================================================
# Inbound Call Routing — Transfer to Aria AI receptionist
# =============================================================================

ARIA_DID = os.getenv("ARIA_DID", "")
ARIA_TRANSFER_NUMBER = os.getenv("ARIA_TRANSFER_NUMBER", "+18434169589")


async def _route_inbound_to_livekit(
    call_control_id: str, from_number: str, to_number: str, db: Session,
):
    """Route an inbound call to Aria by transferring to the AI receptionist number.

    Answer → transfer to Vapi AI number → Aria answers directly.
    No hold message, no callback — caller is bridged seamlessly.
    Uses httpx.AsyncClient to avoid blocking the event loop.
    """
    telnyx_key = os.getenv("TELNYX_API_KEY", "")
    if not telnyx_key:
        logger.error("[AriaInbound] TELNYX_API_KEY not set")
        return

    logger.warning("[AriaInbound] Routing ...%s to Aria", from_number[-4:] if from_number else "?")

    headers = {
        "Authorization": f"Bearer {telnyx_key}",
        "Content-Type": "application/json",
    }
    base_url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions"

    async with httpx.AsyncClient(timeout=15) as client:
        # Step 1: Answer the inbound call immediately
        try:
            resp = await client.post(f"{base_url}/answer", headers=headers, json={})
            logger.warning(f"[AriaInbound] Answer: {resp.status_code}")
            if resp.status_code >= 400:
                logger.error(f"[AriaInbound] Answer failed: {resp.text[:300]}")
                return
        except Exception as e:
            logger.error(f"[AriaInbound] Answer failed: {e}", exc_info=True)
            return

        # Step 2: Transfer to Aria AI receptionist number (Vapi-backed)
        transfer_to = ARIA_TRANSFER_NUMBER
        if not transfer_to:
            logger.error("[AriaInbound] ARIA_TRANSFER_NUMBER not configured")
            try:
                await client.post(
                    f"{base_url}/speak",
                    headers=headers,
                    json={
                        "payload": "I'm sorry, I'm unable to connect you right now. Please try again shortly.",
                        "voice": "female",
                        "language": "en-US",
                    },
                )
                await asyncio.sleep(4)
                await client.post(f"{base_url}/hangup", headers=headers, json={})
            except Exception:
                pass
            return

        try:
            resp = await client.post(
                f"{base_url}/transfer",
                headers=headers,
                json={
                    "to": transfer_to,
                    "from": to_number,
                    "timeout_secs": 30,
                },
            )
            if resp.status_code < 400:
                logger.warning(
                    "[AriaInbound] Transferred ...%s to Aria at %s (status=%s)",
                    from_number[-4:] if from_number else "?",
                    transfer_to[-4:],
                    resp.status_code,
                )
            else:
                logger.error(
                    "[AriaInbound] Transfer failed (%s): %s",
                    resp.status_code, resp.text[:300],
                )
                await client.post(
                    f"{base_url}/speak",
                    headers=headers,
                    json={
                        "payload": "I'm sorry, I'm unable to connect you right now. Please try again shortly.",
                        "voice": "female",
                        "language": "en-US",
                    },
                )
                await asyncio.sleep(4)
                await client.post(f"{base_url}/hangup", headers=headers, json={})
        except Exception as e:
            logger.error(f"[AriaInbound] Transfer failed: {e}", exc_info=True)


# =============================================================================
# Main Webhook Handler
# =============================================================================

_idem_table_checked = False


def _ensure_idempotency_table(db: Session):
    global _idem_table_checked
    if _idem_table_checked:
        return
    try:
        db.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS webhook_idempotency (
                id SERIAL PRIMARY KEY,
                idempotency_key VARCHAR(255) UNIQUE NOT NULL,
                provider VARCHAR(50) NOT NULL,
                event_type VARCHAR(100),
                event_id VARCHAR(255),
                status VARCHAR(20) NOT NULL DEFAULT 'processing',
                response_code INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        db.execute(sa_text("CREATE INDEX IF NOT EXISTS ix_webhook_idem_key ON webhook_idempotency (idempotency_key)"))
        db.commit()
        _idem_table_checked = True
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.debug("Idempotency table creation skipped: %s", e)
        _idem_table_checked = True


@router.post("/webhook")
async def handle_telnyx_webhook(
    request: Request,
    raw_body: bytes = Depends(require_telnyx_webhook),
    db: Session = Depends(get_db),
):
    """
    Main Telnyx webhook handler.
    Routes events to appropriate handlers based on event type.
    Signature verification is handled by the require_telnyx_webhook dependency.
    """
    _ensure_idempotency_table(db)

    # Parse webhook payload from the already-verified raw body
    try:
        payload = json.loads(raw_body)
    except Exception as e:
        logger.error(f"Failed to parse Telnyx webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Early log before any DB operations — guaranteed to appear
    _raw_data = payload.get("data", {})
    _raw_payload = _raw_data.get("payload", {})
    _raw_event_type = _raw_data.get("event_type", "unknown")
    _raw_direction = _raw_payload.get("direction", "n/a")
    _raw_from = _raw_payload.get("from", "n/a")
    _raw_to = _raw_payload.get("to", "n/a")
    _raw_ccid = _raw_payload.get("call_control_id", "n/a")
    _raw_hangup = _raw_payload.get("hangup_cause", "")
    _raw_sip = _raw_payload.get("sip_hangup_cause", "")
    _mask = lambda n: f"...{n[-4:]}" if isinstance(n, str) and len(n) > 4 else n
    logger.warning(
        f"[WEBHOOK-ENTRY] type={_raw_event_type} dir={_raw_direction} "
        f"from={_mask(_raw_from)} to={_mask(_raw_to)} ccid={str(_raw_ccid)[:25]}"
        + (f" hangup={_raw_hangup} sip={_raw_sip}" if _raw_hangup else "")
    )

    if _raw_event_type == "message.finalized" and isinstance(_raw_to, list):
        for _to_entry in _raw_to:
            if isinstance(_to_entry, dict) and _to_entry.get("status") in ("delivery_failed", "sending_failed"):
                _errs = _raw_payload.get("errors", [])
                logger.error(
                    "[SMS-DELIVERY-FAILED] to=%s status=%s errors=%s carrier=%s payload_keys=%s",
                    _to_entry.get("phone_number", "?"),
                    _to_entry.get("status"),
                    _errs,
                    _to_entry.get("carrier"),
                    list(_raw_payload.keys()),
                )

    # Webhook idempotency — best-effort dedup via database.
    # Wrapped in try/except so a missing table never blocks webhook processing.
    webhook_event_id = payload.get("data", {}).get("id", "")
    event_type_raw = payload.get("data", {}).get("event_type", "")
    idem_key = None
    try:
        if webhook_event_id:
            from database.models.webhook_idempotency import WebhookIdempotencyRecord
            from middleware.webhook_idempotency import _build_idempotency_key, mark_processed, mark_failed

            idem_key = _build_idempotency_key("telnyx", event_type_raw, webhook_event_id, raw_body)
            existing = db.query(WebhookIdempotencyRecord).filter(
                WebhookIdempotencyRecord.idempotency_key == idem_key,
                WebhookIdempotencyRecord.status == "processed",
            ).first()
            if existing:
                logger.info(f"Duplicate webhook {webhook_event_id}, skipping")
                return {"status": "duplicate", "event_id": webhook_event_id}

            db.add(WebhookIdempotencyRecord(
                idempotency_key=idem_key,
                provider="telnyx",
                event_type=event_type_raw,
                event_id=webhook_event_id,
                status="processing",
            ))
            db.flush()
    except Exception as idem_err:
        # Table missing or DB error — skip idempotency, process webhook anyway
        idem_key = None
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("Webhook idempotency check skipped: %s", idem_err)

    # Parse into typed event
    event = parse_telnyx_webhook(payload)
    event_type = event.event_type

    logger.info(
        f"Telnyx webhook received: {event_type}, "
        f"direction={getattr(event, 'direction', 'n/a')}, "
        f"from={getattr(event, 'from_number', 'n/a')}, "
        f"call_control_id={getattr(event, 'call_control_id', 'n/a')[:20] if getattr(event, 'call_control_id', None) else 'n/a'}"
    )

    # Route to appropriate handler
    try:
        if event_type == TelnyxEventType.CALL_INITIATED:
            # Inbound calls → route to Aria via LiveKit outbound SIP callback
            if hasattr(event, "direction") and event.direction in ("incoming", "inbound"):
                if event.from_number and event.call_control_id:
                    try:
                        await _route_inbound_to_livekit(
                            event.call_control_id, event.from_number,
                            getattr(event, "to_number", ""), db,
                        )
                    except Exception as e:
                        logger.error(f"Inbound routing failed: {e}")
                if idem_key:
                    try:
                        mark_processed(db, idem_key, response_code=200)
                    except Exception as e:
                        logger.warning(f"Failed to mark webhook as processed: {e}")
                return Response(status_code=200)
            result = {"status": "acknowledged", "event_type": "call.initiated", "direction": "outgoing"}

        elif event_type == TelnyxEventType.CALL_MACHINE_DETECTION_ENDED:
            result = await handle_amd_event(event, db)

        elif event_type == TelnyxEventType.CALL_ANSWERED:
            result = await handle_call_answered(event, db)

        elif event_type == TelnyxEventType.CALL_HANGUP:
            result = await handle_call_hangup(event, db)

        elif event_type in [TelnyxEventType.MESSAGE_SENT, TelnyxEventType.MESSAGE_FINALIZED]:
            result = await handle_sms_status(event, db)

        elif event_type == TelnyxEventType.MESSAGE_RECEIVED:
            result = await handle_inbound_sms(event, db)

        elif event_type == TelnyxEventType.CALL_RECORDING_SAVED:
            result = await handle_recording_saved(event, db)

        else:
            logger.info(f"Unhandled Telnyx event type: {event_type}")
            result = {"status": "acknowledged", "event_type": event_type}

        # Mark as successfully processed
        if idem_key:
            try:
                mark_processed(db, idem_key, response_code=200)
            except Exception as e:
                logger.warning(f"Failed to mark webhook as processed: {e}")

        return result

    except Exception as e:
        logger.error(f"Telnyx webhook processing error: {e}", exc_info=True)
        # Mark idempotency record as failed so retries can reprocess
        if idem_key:
            try:
                mark_failed(db, idem_key, response_code=200)
            except Exception:
                pass
        # Return 200 to prevent provider retries — log error for investigation
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=200,
            content={"status": "error", "message": "Processing failed, queued for retry"},
        )


# =============================================================================
# AMD (Answering Machine Detection) Handler
# =============================================================================

@router.post("/amd/{tracking_id}")
async def handle_amd_callback(
    tracking_id: str,
    request: Request,
    raw_body: bytes = Depends(require_telnyx_webhook),
    db: Session = Depends(get_db),
):
    """
    Handle Telnyx AMD callback for a specific call.

    Telnyx AMD result values:
    - "human": Human answered
    - "machine": Machine/voicemail detected
    - "not_sure": Could not determine
    - "unknown": Detection failed
    """
    try:
        payload = json.loads(raw_body)
    except Exception as e:
        logger.error(f"Failed to parse AMD callback: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Idempotency check — deduplicate retried Telnyx AMD callbacks
    _amd_event_id = payload.get("data", {}).get("id")
    if _amd_event_id:
        from middleware.webhook_idempotency import is_duplicate_webhook
        if is_duplicate_webhook("telnyx", f"amd:{_amd_event_id}"):
            logger.info("Telnyx AMD callback duplicate: tracking=%s event=%s", tracking_id, _amd_event_id)
            return {"status": "duplicate"}

    event = parse_telnyx_webhook(payload)

    if not isinstance(event, TelnyxAMDEvent):
        logger.warning(f"Expected AMD event, got {type(event)}")
        return {"status": "ignored"}

    return await process_amd_result(tracking_id, event, db)


async def handle_amd_event(event: TelnyxAMDEvent, db: Session):
    """Handle AMD event from main webhook"""
    call_control_id = event.call_control_id

    # Look up tracking ID and resolve tenant from amd_outbound_calls.
    # Note: amd_outbound_calls has user_id but no organization_id column;
    # resolve org via the user record for logging context.
    result = db.execute(sa_text("""
        SELECT id, user_id FROM amd_outbound_calls
        WHERE call_sid = :call_id
    """), {"call_id": call_control_id}).fetchone()

    if not result:
        logger.warning("AMD event: no tracking record for call_control_id=%s", call_control_id)
        return {"status": "ignored"}

    tracking_id = result[0]
    amd_user_id = result[1]

    # Resolve organization_id from user for tenant context logging
    _amd_org_id = None
    if amd_user_id:
        try:
            _org_row = db.execute(sa_text(
                "SELECT organization_id FROM users WHERE id = :uid"
            ), {"uid": amd_user_id}).fetchone()
            if _org_row:
                _amd_org_id = _org_row[0]
        except Exception as e:
            logger.debug("AMD event: org lookup from user_id=%s failed: %s", amd_user_id, e)

    if _amd_org_id:
        logger.info(
            "AMD event: tenant resolved org_id=%s, tracking_id=%s, user_id=%s",
            _amd_org_id, tracking_id, amd_user_id,
        )
    else:
        logger.warning(
            "AMD event: could not resolve org_id, tracking_id=%s, user_id=%s — proceeding without tenant context",
            tracking_id, amd_user_id,
        )

    return await process_amd_result(str(tracking_id), event, db)


async def process_amd_result(tracking_id: str, event: TelnyxAMDEvent, db: Session):
    """Process AMD result and redirect call accordingly"""
    from telephony import get_telephony_provider

    amd_result = event.result
    call_control_id = event.call_control_id

    # Map to legacy-compatible format for database consistency
    legacy_format = map_telnyx_amd_to_legacy(event)
    answered_by = legacy_format["AnsweredBy"]

    logger.info(f"AMD Result for {tracking_id}: result={amd_result}, answered_by={answered_by}")

    # Determine category
    if amd_result == "human":
        answered_category = "human"
    elif amd_result == "machine":
        answered_category = "machine"
    else:
        answered_category = "unknown"

    # Update AMD results in database
    db.execute(sa_text("""
        UPDATE amd_outbound_calls
        SET amd_status = :amd_status,
            answered_by = :answered_by,
            amd_completed_at = NOW()
        WHERE id = :tracking_id
    """), {
        "amd_status": amd_result,
        "answered_by": answered_category,
        "tracking_id": tracking_id,
    })
    db.commit()

    # Determine redirect URL based on AMD result
    if answered_category == "human" or answered_category == "unknown":
        redirect_url = f"{API_BASE_URL}/api/v1/voice/amd/connect-ai/{tracking_id}"
        action = "connect_ai"
    elif answered_category == "machine":
        redirect_url = f"{API_BASE_URL}/api/v1/voice/amd/voicemail/{tracking_id}"
        action = "play_voicemail"
    else:
        redirect_url = f"{API_BASE_URL}/api/v1/voice/amd/hangup/{tracking_id}"
        action = "hangup"

    # Redirect the call using Telnyx Call Control
    try:
        provider = get_telephony_provider()
        # Use Telnyx transfer command to redirect
        if hasattr(provider, 'client') and provider.client:
            provider.client.calls.transfer(
                call_control_id=call_control_id,
                audio_url=redirect_url,
            )
            logger.info(f"Redirected Telnyx call {call_control_id} to {redirect_url}")
    except Exception as e:
        logger.error(f"Failed to redirect Telnyx call: {e}")

    return {
        "status": "processed",
        "tracking_id": tracking_id,
        "amd_result": amd_result,
        "action": action,
    }


# =============================================================================
# Call Event Handlers
# =============================================================================

async def handle_call_answered(event: TelnyxCallEvent, db: Session):
    """Handle call answered event"""
    call_control_id = event.call_control_id

    # Resolve tenant context from the call record for structured logging
    _ans_org_id = None
    try:
        _ans_row = db.execute(sa_text("""
            SELECT u.organization_id
            FROM amd_outbound_calls a
            JOIN users u ON u.id = a.user_id
            WHERE a.call_sid = :call_id
        """), {"call_id": call_control_id}).fetchone()
        if _ans_row:
            _ans_org_id = _ans_row[0]
    except Exception:
        pass  # Best-effort tenant resolution

    if _ans_org_id:
        logger.info("Call answered: call_control_id=%s, org_id=%s", call_control_id, _ans_org_id)
    else:
        logger.info("Call answered: call_control_id=%s (org unresolved)", call_control_id)

    # Update call status
    try:
        db.execute(sa_text("""
            UPDATE amd_outbound_calls
            SET status = 'answered'
            WHERE call_sid = :call_id
        """), {"call_id": call_control_id})
        db.commit()
    except Exception as e:
        db.rollback()
        logger.debug("amd_outbound_calls update skipped: %s", e)

    return {"status": "acknowledged", "call_id": call_control_id}


async def handle_call_hangup(event: TelnyxCallEvent, db: Session):
    """Handle call hangup event"""
    call_control_id = event.call_control_id
    hangup_cause = event.hangup_cause

    # Resolve tenant context for structured logging
    _hup_org_id = None
    try:
        _hup_row = db.execute(sa_text("""
            SELECT u.organization_id
            FROM amd_outbound_calls a
            JOIN users u ON u.id = a.user_id
            WHERE a.call_sid = :call_id
        """), {"call_id": call_control_id}).fetchone()
        if _hup_row:
            _hup_org_id = _hup_row[0]
    except Exception:
        pass  # Best-effort tenant resolution

    if _hup_org_id:
        logger.info(
            "Call hangup: call_control_id=%s, cause=%s, org_id=%s",
            call_control_id, hangup_cause, _hup_org_id,
        )
    else:
        logger.info(
            "Call hangup: call_control_id=%s, cause=%s (org unresolved)",
            call_control_id, hangup_cause,
        )

    # Update call status
    try:
        db.execute(sa_text("""
            UPDATE amd_outbound_calls
            SET status = 'completed'
            WHERE call_sid = :call_id
        """), {"call_id": call_control_id})
        db.commit()
    except Exception as e:
        db.rollback()
        logger.debug("amd_outbound_calls update skipped: %s", e)

    return {"status": "acknowledged", "call_id": call_control_id, "cause": hangup_cause}


# =============================================================================
# SMS Event Handlers
# =============================================================================

async def handle_sms_status(event: TelnyxSMSEvent, db: Session):
    """Handle SMS delivery status update.

    Updates delivery status in:
    - sms_delivery_log (chokepoint tracking table)
    - sms_panel_messages (two-way SMS Archive panel)
    - sms_messages (general SMS log)
    - bulk_sms_sends (bulk campaign message tracking)

    Also pushes real-time status to WebSocket clients and increments
    campaign-level counters for terminal statuses.
    """
    message_id = event.message_id
    status = event.status
    is_terminal = status in ("delivered", "sent", "failed", "sending_failed", "delivery_failed")

    # Resolve tenant context from delivery_log or sms_messages for logging
    _sms_status_org_id = None
    try:
        _org_row = db.execute(sa_text("""
            SELECT organization_id FROM sms_delivery_log
            WHERE telnyx_message_id = :message_id
            LIMIT 1
        """), {"message_id": message_id}).fetchone()
        if not _org_row:
            _org_row = db.execute(sa_text("""
                SELECT organization_id FROM sms_messages
                WHERE provider_message_id = :message_id
                LIMIT 1
            """), {"message_id": message_id}).fetchone()
        if _org_row:
            _sms_status_org_id = _org_row[0]
    except Exception:
        pass

    logger.info(
        "SMS status update: message_id=%s, status=%s, org_id=%s",
        message_id, status, _sms_status_org_id or "unresolved",
    )

    normalized_status = status
    if status in ("sending_failed", "delivery_failed", "delivery_unconfirmed"):
        normalized_status = "failed"

    # 1. Update sms_delivery_log + sms_panel_messages (SMS Archive)
    try:
        from integrations.sms_delivery_tracker import update_delivery_status
        delivered_at = None
        if normalized_status == "delivered":
            from datetime import datetime as _dt, timezone as _tz
            delivered_at = _dt.now(_tz.utc)

        error_code = None
        carrier_name = None
        to_field = event.payload.get("to", [])
        if isinstance(to_field, list) and to_field:
            first_to = to_field[0] if isinstance(to_field[0], dict) else {}
            error_code = first_to.get("carrier", {}).get("error_code")
            carrier_name = first_to.get("carrier", {}).get("name")

        update_delivery_status(
            db, message_id, normalized_status,
            error_code=str(error_code) if error_code else None,
            carrier_name=carrier_name,
            delivered_at=delivered_at,
        )
    except Exception as e:
        logger.debug(f"sms_delivery_log/panel update skipped: {e}")

    # 2. Push status to WebSocket clients
    if is_terminal:
        try:
            _phone_row = db.execute(sa_text(
                "SELECT to_phone FROM sms_delivery_log WHERE telnyx_message_id = :mid"
            ), {"mid": message_id}).fetchone()
            if _phone_row:
                from routes.sms_conversation_routes import notify_status_update
                await notify_status_update(
                    _phone_row[0], message_id, normalized_status,
                    org_id=_sms_status_org_id,
                )
        except Exception:
            pass

    # 3. Update sms_messages table (general SMS log)
    # SECURITY: update_fields and counter_col below are code-defined constants, not user input
    try:
        update_fields = "delivery_status = :status"
        params = {"status": normalized_status, "message_id": message_id}
        if normalized_status == "delivered":
            update_fields += ", delivered_at = NOW()"
        db.execute(sa_text(f"""
            UPDATE sms_messages
            SET {update_fields}
            WHERE provider_message_id = :message_id
        """), params)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.debug(f"sms_messages update skipped (no match): {e}")

    # 4. Update bulk_sms_sends table (bulk campaign message tracking)
    campaign_id = None
    try:
        update_fields = "status = :status"
        params = {"status": normalized_status, "message_id": message_id}
        if normalized_status == "delivered":
            update_fields += ", delivered_at = NOW()"

        result = db.execute(sa_text(f"""
            UPDATE bulk_sms_sends
            SET {update_fields}
            WHERE telnyx_message_id = :message_id
            RETURNING campaign_id
        """), params)
        row = result.fetchone()
        if row:
            campaign_id = row[0]
        db.commit()
    except Exception as e:
        db.rollback()
        logger.debug(f"bulk_sms_sends update skipped (no match or table missing): {e}")

    # 5. Increment campaign-level counters for terminal statuses
    if campaign_id and is_terminal:
        try:
            if normalized_status == "delivered":
                counter_col = "delivered_count"
            elif normalized_status == "failed":
                counter_col = "failed_count"
            else:
                counter_col = None

            if counter_col:
                db.execute(sa_text(f"""
                    UPDATE bulk_sms_campaigns
                    SET {counter_col} = COALESCE({counter_col}, 0) + 1,
                        updated_at = NOW()
                    WHERE id = :campaign_id
                """), {"campaign_id": campaign_id})
                db.commit()
                logger.info(
                    f"Campaign {campaign_id}: incremented {counter_col} via delivery webhook"
                )
        except Exception as e:
            db.rollback()
            logger.warning(f"Failed to increment campaign counter: {e}")

    return {"status": "acknowledged", "message_id": message_id, "delivery_status": normalized_status}


def _normalize_phone(phone: str) -> str:
    """Normalize phone number to E.164 format for matching."""
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
    elif not digits.startswith('+'):
        return f"+{digits}"
    return phone


# =============================================================================
# SMS Opt-Out / Opt-In Keyword Automation (TCPA + CTIA)
# =============================================================================

# CTIA Short Code Monitoring Handbook & TCPA both require immediate processing
# of these standard keywords.  Carriers may also enforce at the network level,
# but we process on our side to guarantee ChannelPreference + ConsentAuditLog
# stay in sync.
_OPT_OUT_KEYWORDS = frozenset({"stop", "unsubscribe", "quit", "cancel", "end"})
_OPT_IN_KEYWORDS = frozenset({"start", "yes", "unstop", "subscribe", "optin"})

_OPT_OUT_REPLY = (
    "You have been unsubscribed and will no longer receive text messages "
    "from us. Reply START to re-subscribe."
)
_OPT_IN_REPLY = (
    "You have been re-subscribed to text messages. Reply STOP at any time "
    "to opt out."
)


async def _handle_sms_opt_keyword(
    from_phone: str,
    to_phone: str,
    message_body: str | None,
    message_id: str | None,
    db: Session,
) -> dict | None:
    """Process STOP/START keywords.  Returns a result dict if handled, else None.

    When a keyword is detected:
      1. Update ChannelPreference (do_not_sms / sms_consent)
      2. Update any active TCPAConsent records
      3. Log to ConsentAuditLog
      4. Send auto-reply confirmation via Telnyx
      5. Store inbound message in sms_messages for audit trail
    """
    if not message_body:
        return None

    stripped = message_body.strip().lower()
    is_opt_out = stripped in _OPT_OUT_KEYWORDS
    is_opt_in = stripped in _OPT_IN_KEYWORDS

    if not is_opt_out and not is_opt_in:
        return None

    action_label = "opt_out" if is_opt_out else "opt_in"
    logger.warning(
        "sms_opt_keyword: %s detected from ...%s, keyword='%s'",
        action_label, from_phone[-4:] if from_phone else "?", stripped,
    )

    # Resolve org_id from the receiving Telnyx number
    org_id = None
    try:
        org_row = db.execute(sa_text("""
            SELECT organization_id FROM verified_caller_ids
            WHERE phone_number = :to_phone AND organization_id IS NOT NULL
            LIMIT 1
        """), {"to_phone": to_phone}).fetchone()
        if org_row:
            org_id = org_row[0]
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("sms_opt_keyword: org lookup failed: %s", e)

    # --- 1. Update ChannelPreference ---
    channel_prefs_updated = 0
    lead_ids = []
    try:
        from database.models.communication import ChannelPreference
        from database.models.lead_loan import Lead

        lead_query = db.query(Lead.id).filter(Lead.phone == from_phone)
        if org_id is not None:
            lead_query = lead_query.filter(Lead.organization_id == int(org_id))
        lead_ids = [lid for (lid,) in lead_query.all()]

        if lead_ids:
            prefs = (
                db.query(ChannelPreference)
                .filter(ChannelPreference.lead_id.in_(lead_ids))
                .all()
            )
            now_ts = datetime.now(timezone.utc).replace(tzinfo=None)
            for pref in prefs:
                if is_opt_out:
                    pref.sms_consent = False
                    pref.do_not_sms = True
                else:
                    pref.sms_consent = True
                    pref.sms_consent_date = now_ts
                    pref.do_not_sms = False
                pref.updated_at = now_ts
                channel_prefs_updated += 1
    except Exception as e:
        logger.warning("sms_opt_keyword: ChannelPreference update failed: %s", e)

    # --- 2. Update TCPAConsent records ---
    tcpa_updated = 0
    try:
        from database.models.tcpa_consent import TCPAConsent
        import uuid as _uuid_mod

        now_ts = datetime.now(timezone.utc).replace(tzinfo=None)

        if is_opt_out:
            # Revoke active SMS-related consents
            tcpa_query = db.query(TCPAConsent).filter(
                TCPAConsent.phone_number == from_phone,
                TCPAConsent.is_active == True,  # noqa: E712
                TCPAConsent.consent_channel.in_(["sms", "both"]),
            )
            if org_id is not None:
                tcpa_query = tcpa_query.filter(
                    TCPAConsent.organization_id == _uuid_mod.UUID(str(org_id))
                )
            tcpa_records = tcpa_query.all()
            for rec in tcpa_records:
                rec.is_active = False
                rec.revoked_at = now_ts
                rec.revocation_method = "text_reply"
                rec.updated_at = now_ts
                tcpa_updated += 1
        # For opt-in we do NOT auto-create a new TCPAConsent -- the FCC 1:1
        # rule requires explicit consent capture with disclosure text.  We
        # only re-enable ChannelPreference which unblocks future consent
        # capture and non-automated messaging.
    except Exception as e:
        logger.warning("sms_opt_keyword: TCPAConsent update failed: %s", e)

    # --- 3. ConsentAuditLog ---
    try:
        from telephony.consent_audit import log_consent_revoked, log_consent_granted

        for lid in lead_ids:
            if is_opt_out:
                log_consent_revoked(
                    db,
                    organization_id=int(org_id) if org_id else None,
                    contact_id=lid,
                    consent_type="sms",
                    method="text_reply",
                    source_table="channel_preferences",
                    phone=from_phone,
                    reason=f"Auto-processed SMS keyword: {stripped}",
                    details={"keyword": stripped, "channel_prefs_updated": channel_prefs_updated},
                )
            else:
                log_consent_granted(
                    db,
                    organization_id=int(org_id) if org_id else None,
                    contact_id=lid,
                    consent_type="sms",
                    method="text_reply",
                    source_table="channel_preferences",
                    phone=from_phone,
                    details={"keyword": stripped, "channel_prefs_updated": channel_prefs_updated},
                )
        # If no lead_ids found, still log with phone only
        if not lead_ids:
            if is_opt_out:
                log_consent_revoked(
                    db,
                    organization_id=int(org_id) if org_id else None,
                    consent_type="sms",
                    method="text_reply",
                    phone=from_phone,
                    reason=f"Auto-processed SMS keyword: {stripped} (no matching lead)",
                    details={"keyword": stripped, "tcpa_updated": tcpa_updated},
                )
            else:
                log_consent_granted(
                    db,
                    organization_id=int(org_id) if org_id else None,
                    consent_type="sms",
                    method="text_reply",
                    phone=from_phone,
                    details={"keyword": stripped},
                )
    except Exception as e:
        logger.warning("sms_opt_keyword: audit log failed: %s", e)

    # --- 4. Store inbound SMS for audit trail ---
    try:
        db.execute(sa_text("""
            INSERT INTO sms_messages (
                direction, from_number, to_number, message,
                provider_message_id, status, created_at
            ) VALUES (
                'inbound', :from_number, :to_number, :body,
                :message_id, 'received', NOW()
            )
        """), {
            "from_number": from_phone,
            "to_number": to_phone,
            "body": message_body,
            "message_id": message_id,
        })
    except Exception as e:
        logger.warning("sms_opt_keyword: sms_messages insert failed: %s", e)

    # --- Close active Aria conversations so AI doesn't reply to opted-out numbers ---
    if is_opt_out:
        try:
            db.execute(sa_text("""
                UPDATE sms_ai_conversations
                SET status = 'closed', updated_at = NOW()
                WHERE phone_number = :phone AND status = 'active'
            """), {"phone": from_phone})
        except Exception as e:
            logger.warning("sms_opt_keyword: close Aria conversations failed: %s", e)

    # Commit all DB changes in one transaction
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("sms_opt_keyword: commit failed: %s", e)

    # --- 5. Send auto-reply via compliance chokepoint ---
    reply_text = _OPT_OUT_REPLY if is_opt_out else _OPT_IN_REPLY
    try:
        from telephony.sms import send_sms_verified
        _first_lead_id = lead_ids[0] if lead_ids else None
        _reply_result = send_sms_verified(
            to=from_phone,
            text=reply_text,
            lead_id=_first_lead_id,
            organization_id=int(org_id) if org_id else None,
            db=db,
            bypass_compliance=True,  # Legally required opt-out/in confirmation
        )
        logger.info(
            "sms_opt_keyword: auto-reply sent via chokepoint, result=%s, to=...%s, action=%s",
            _reply_result.get("status"), from_phone[-4:] if from_phone else "?", action_label,
        )
    except Exception as e:
        logger.error("sms_opt_keyword: auto-reply send failed: %s", e)

    logger.info(
        "sms_opt_keyword: %s processed, phone=...%s, channel_prefs=%d, tcpa=%d, leads=%s",
        action_label, from_phone[-4:] if from_phone else "?",
        channel_prefs_updated, tcpa_updated, lead_ids,
    )

    return {
        "status": "received",
        "handler": f"sms_{action_label}",
        "keyword": stripped,
        "channel_prefs_updated": channel_prefs_updated,
        "tcpa_records_updated": tcpa_updated,
    }


async def _aria_sms_ai_background_task(
    conv_id,
    org_id,
    stage: str,
    context_data: dict,
    message_body: str,
    normalized_from: str,
) -> None:
    """Background task: generate Claude AI reply and send via Telnyx for Aria SMS conversations.

    Runs outside the webhook request lifecycle with its own DB session so the
    webhook handler returns 200 to Telnyx immediately. Uses httpx for async
    HTTP calls and the Anthropic SDK for Claude API calls (sync, run in thread
    to avoid blocking the event loop).

    All errors are caught and logged -- never propagated to caller.
    """
    import uuid as _uuid_bg
    db: Optional[Session] = None
    try:
        db = SessionLocal()

        if not message_body or not message_body.strip():
            logger.info("aria_sms_bg: empty message body, skipping AI reply for conv_id=%s", conv_id)
            return

        # Fetch conversation history for context
        _history_rows = db.execute(sa_text("""
            SELECT direction, content FROM sms_ai_conversation_messages
            WHERE conversation_id = :conv_id
            ORDER BY created_at ASC
        """), {"conv_id": conv_id}).fetchall()

        _messages = []
        for row in _history_rows:
            role = "user" if row[0] == "inbound" else "assistant"
            _messages.append({"role": role, "content": row[1]})
        # Add current message if not already in history
        if not _messages or _messages[-1].get("content") != message_body:
            _messages.append({"role": "user", "content": message_body})

        # Generate AI reply via Claude (sync SDK call, run in thread)
        _reply_text = None
        try:
            import anthropic as _anthropic
            _client = _anthropic.Anthropic(timeout=15.0)

            borrower_name = context_data.get("borrower_name", "there")
            lo_name = context_data.get("lo_name", "your loan officer")
            appt_type = context_data.get("appointment_type", "consultation")

            # Resolve LO's actual company so borrower-facing copy never
            # mentions the platform vendor. Falls back to "{lo_name}'s team"
            # so we never expose an internal brand name to the borrower.
            lo_company = context_data.get("lo_company") or ""
            if not lo_company:
                try:
                    _co_row = db.execute(sa_text(
                        "SELECT name FROM organizations WHERE id = :oid"
                    ), {"oid": org_id}).fetchone()
                    if _co_row and _co_row[0]:
                        lo_company = _co_row[0]
                except Exception:
                    pass
            lo_company = lo_company or f"{lo_name}'s team"

            # Look up real LO availability for the next 7 days
            _avail_context = ""
            try:
                _lo_user_id = context_data.get("user_id") or context_data.get("lo_id")
                if not _lo_user_id:
                    _lo_row = db.execute(sa_text("""
                        SELECT user_id FROM leads
                        WHERE id = :lead_id AND user_id IS NOT NULL
                        LIMIT 1
                    """), {"lead_id": context_data.get("lead_id")}).fetchone()
                    if not _lo_row:
                        _lo_row = db.execute(sa_text("""
                            SELECT id FROM users
                            WHERE organization_id = :org_id AND role IN ('admin', 'loan_officer', 'lo')
                            LIMIT 1
                        """), {"org_id": org_id}).fetchone()
                    if _lo_row:
                        _lo_user_id = _lo_row[0]

                if _lo_user_id:
                    from agents.tools.scheduler import get_availability
                    _avail_result = get_availability(
                        user_id=str(_lo_user_id),
                        duration_minutes=30,
                        meeting_type=appt_type,
                    )
                    if hasattr(_avail_result, 'to_dict'):
                        _avail_data = _avail_result.to_dict().get("data", {})
                    else:
                        _avail_data = _avail_result.get("data", {}) if isinstance(_avail_result, dict) else {}
                    _avail_slots = _avail_data.get("slots", [])[:6]
                    if _avail_slots:
                        _slot_list = ", ".join(s.get("display", "") for s in _avail_slots)
                        _avail_context = f"\n\nAVAILABLE TIMES (next 7 days): {_slot_list}"
            except Exception as _avail_err:
                logger.warning("aria_sms_bg: availability lookup failed: %s", _avail_err)

            if stage == "general":
                _system = (
                    f"You are Aria, an assistant for {lo_name} at {lo_company}. "
                    f"You represent {lo_name} and {lo_company} — never any other "
                    f"brand or platform. You are texting with {borrower_name}.\n\n"
                    "RULES:\n"
                    "- Keep responses under 160 characters (1 SMS segment)\n"
                    "- Be warm and professional\n"
                    "- Help with mortgage questions, application status, scheduling\n"
                    "- If they want to schedule a call, propose available times\n"
                    "- Do NOT quote rates, fees, or loan terms\n"
                    "- NEVER say 'you qualify' or 'you're approved'\n"
                    "- If they say stop or opt out, respect it immediately\n"
                    "- If you can't answer, say you'll have their LO follow up"
                    f"{_avail_context}"
                )
            else:
                _system = (
                    f"You are Aria, an assistant for {lo_name} at {lo_company}. "
                    f"You represent {lo_name} and {lo_company} — never any other "
                    f"brand or platform. You are texting {borrower_name} "
                    f"to schedule a {appt_type}.\n\n"
                    "RULES:\n"
                    "- Keep responses under 160 characters (1 SMS segment)\n"
                    "- Be warm and professional\n"
                    "- When the borrower suggests a time, check if it's in the available slots and confirm it\n"
                    "- If they suggest a time that isn't available, propose the closest available time\n"
                    "- If they ask a vague question like 'do you have time tomorrow', propose 2-3 specific available slots for that day\n"
                    "- Do NOT quote rates, fees, or loan terms\n"
                    "- If they say stop or opt out, respect it immediately\n"
                    "- Do NOT promise to send calendar invites or emails -- the system sends those automatically\n"
                    "- When confirming, just say the appointment is confirmed for the date/time\n"
                    f"- Current stage: {stage}"
                    f"{_avail_context}"
                )

            # Run synchronous Anthropic SDK call in a thread to avoid blocking event loop
            _resp = await asyncio.to_thread(
                _client.messages.create,
                model=os.environ.get("ARIA_SMS_MODEL", "claude-haiku-4-5-20251001"),
                max_tokens=200,
                system=_system,
                messages=_messages,
            )
            if _resp.content:
                _reply_text = _resp.content[0].text.strip()
            if getattr(_resp, "stop_reason", None) == "max_tokens":
                logger.warning(
                    "aria_sms_bg: Claude reply truncated (hit max_tokens) for conv=%s",
                    conv_id,
                )
        except Exception as e:
            logger.error("aria_sms_bg: Claude response generation failed: %s", e)

        if _reply_text:
            # Store outbound message and update conversation state
            try:
                db.execute(sa_text("""
                    INSERT INTO sms_ai_conversation_messages
                    (id, conversation_id, direction, content, ai_generated, created_at)
                    VALUES (:id, :conv_id, 'outbound', :content, true, NOW())
                """), {
                    "id": str(_uuid_bg.uuid4()),
                    "conv_id": conv_id,
                    "content": _reply_text,
                })
                db.execute(sa_text("""
                    UPDATE sms_ai_conversations
                    SET last_message_at = NOW(),
                        message_count = COALESCE(message_count, 0) + 1,
                        current_stage = CASE
                            WHEN current_stage = 'scheduling' THEN 'confirming'
                            ELSE current_stage
                        END
                    WHERE id = :conv_id
                """), {"conv_id": conv_id})
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error("aria_sms_bg: store reply/update state failed: %s", e)

            # Send reply via centralized SMS chokepoint (compliance + retry)
            try:
                from telephony.sms import send_sms_verified_async
                _send_result = await send_sms_verified_async(
                    to=normalized_from,
                    text=_reply_text,
                    user_id=context_data.get("user_id") or context_data.get("lo_id"),
                    lead_id=context_data.get("lead_id"),
                    organization_id=org_id,
                    db=db,
                    bypass_compliance=True,
                )
                if _send_result.get("status") == "blocked":
                    logger.warning(
                        "aria_sms_bg: reply blocked by compliance: %s", _send_result.get("reason"),
                    )
                elif _send_result.get("id"):
                    logger.info(
                        "aria_sms_bg: reply sent, msg_id=%s, to=...%s, text='%s'",
                        _send_result["id"], normalized_from[-4:], _reply_text[:50],
                    )
                    try:
                        db.execute(sa_text("""
                            INSERT INTO sms_panel_messages
                                (id, phone, organization_id, direction, body,
                                 sender_name, sender_role, status, created_at)
                            VALUES (:id, :phone, :org_id, 'outbound', :body,
                                    'Aria', 'ai_assistant', 'sent', NOW())
                            ON CONFLICT (id) DO NOTHING
                        """), {
                            "id": str(_uuid_bg.uuid4()),
                            "phone": normalized_from,
                            "org_id": org_id,
                            "body": _reply_text,
                        })
                        db.commit()
                    except Exception as _panel_err:
                        db.rollback()
                        logger.debug("aria_sms_bg: outbound panel write: %s", _panel_err)
                else:
                    logger.error("aria_sms_bg: send failed: %s", _send_result)
            except Exception as e:
                logger.error("aria_sms_bg: send reply failed: %s", e)

            # ==========================================================
            # Calendar invite email -- fires when appointment is confirmed
            # ==========================================================
            try:
                _full_convo = "\n".join(
                    f"{'Borrower' if m['role'] == 'user' else 'Aria'}: {m['content']}"
                    for m in _messages
                )
                # Add the reply we just generated
                _full_convo += f"\nAria: {_reply_text}"

                _extract_resp = await asyncio.to_thread(
                    _client.messages.create,
                    model=os.environ.get("ARIA_SMS_MODEL", "claude-haiku-4-5-20251001"),
                    max_tokens=400,
                    system=(
                        "You are a data extractor. Analyze this SMS conversation and determine "
                        "if an appointment has been CONFIRMED (both parties agreed on a specific "
                        "date and time). If confirmed, extract the details.\n\n"
                        "Respond in EXACTLY this format (no markdown, no extra text):\n"
                        "CONFIRMED: yes or no\n"
                        "DATE: YYYY-MM-DD (use the next occurrence if only day-of-week given)\n"
                        "TIME: HH:MM (24-hour format)\n"
                        "EMAILS: comma-separated list of any email addresses mentioned in the conversation\n\n"
                        f"Today's date is {datetime.now().strftime('%Y-%m-%d')} "
                        f"({datetime.now().strftime('%A')}).\n"
                        "If no appointment is confirmed yet, just respond: CONFIRMED: no"
                    ),
                    messages=[{"role": "user", "content": _full_convo}],
                )
                _extract_text = _extract_resp.content[0].text.strip() if _extract_resp.content else ""
                logger.info("aria_sms_bg: appointment extraction: %s", _extract_text[:200])

                if "confirmed: yes" in _extract_text.lower() or "confirmed:yes" in _extract_text.lower():
                    # Parse extracted fields
                    _appt_date = None
                    _appt_time = None
                    _appt_emails = []

                    for _line in _extract_text.split("\n"):
                        _line = _line.strip()
                        if _line.upper().startswith("DATE:"):
                            _appt_date = _line.split(":", 1)[1].strip()
                        elif _line.upper().startswith("TIME:"):
                            _appt_time = _line.split(":", 1)[1].strip()
                        elif _line.upper().startswith("EMAILS:"):
                            _raw_emails = _line.split(":", 1)[1].strip()
                            _appt_emails = [
                                e.strip() for e in _raw_emails.split(",")
                                if "@" in e.strip()
                            ]

                    # Also check context_data for emails collected during voice call
                    _ctx_emails = context_data.get("attendee_emails", [])
                    if isinstance(_ctx_emails, str):
                        _ctx_emails = [e.strip() for e in _ctx_emails.split(",") if "@" in e]
                    for _ce in _ctx_emails:
                        if _ce not in _appt_emails:
                            _appt_emails.append(_ce)

                    # Look up lead's email if not already known
                    if not _appt_emails:
                        try:
                            _lead_id_for_email = context_data.get("lead_id") or (
                                db.execute(sa_text("""
                                    SELECT lead_id FROM sms_ai_conversations WHERE id = :cid
                                """), {"cid": conv_id}).scalar()
                            )
                            if _lead_id_for_email:
                                _lead_email_row = db.execute(sa_text("""
                                    SELECT email FROM leads WHERE id = :lid AND email IS NOT NULL
                                """), {"lid": int(_lead_id_for_email)}).fetchone()
                                if _lead_email_row and _lead_email_row[0]:
                                    _appt_emails.append(_lead_email_row[0])
                        except Exception as _email_err:
                            logger.warning("aria_sms_bg: lead email lookup failed: %s", _email_err)

                    # Create CRM appointment record regardless of email availability
                    if _appt_date and _appt_time:
                        try:
                            _lo_uid = context_data.get("user_id") or context_data.get("lo_id")
                            if _lo_uid:
                                db.execute(sa_text("""
                                    INSERT INTO appointments
                                    (user_id, lead_id, start_time, end_time,
                                     appointment_type, title, status, notes, created_at)
                                    VALUES (:uid, :lid,
                                            CAST(:start AS timestamptz),
                                            CAST(:start AS timestamptz) + INTERVAL '30 minutes',
                                            :atype, :title, 'confirmed',
                                            :notes, NOW())
                                """), {
                                    "uid": int(_lo_uid),
                                    "lid": int(context_data.get("lead_id") or 0) or None,
                                    "start": f"{_appt_date} {_appt_time}:00",
                                    "atype": appt_type,
                                    "title": f"{appt_type.replace('_', ' ').title()} with {borrower_name}",
                                    "notes": f"Scheduled via SMS by Aria. Borrower: {borrower_name}",
                                })
                                db.commit()
                                logger.info("aria_sms_bg: appointment created for %s at %s %s", borrower_name, _appt_date, _appt_time)
                        except Exception as _appt_err:
                            db.rollback()
                            logger.error("aria_sms_bg: appointment creation failed: %s", _appt_err)

                    if _appt_date and _appt_time and _appt_emails:
                        from datetime import timedelta
                        try:
                            _start_dt = datetime.strptime(
                                f"{_appt_date} {_appt_time}", "%Y-%m-%d %H:%M"
                            ).replace(tzinfo=timezone.utc)
                        except ValueError:
                            _start_dt = None
                            logger.warning(
                                "aria_sms_bg: could not parse date/time: %s %s",
                                _appt_date, _appt_time,
                            )

                        if _start_dt:
                            from services.ics_generator import generate_ics_content
                            from services.email_delivery_service import EmailDeliveryService
                            from services.email_delivery_models import EmailAttachment

                            _ics_title = f"{appt_type.replace('_', ' ').title()} with {lo_name}"
                            _ics_content = generate_ics_content(
                                appointment_title=_ics_title,
                                start_datetime=_start_dt,
                                duration_minutes=30,
                                attendee_email=_appt_emails[0],
                                attendee_name=borrower_name,
                                organizer_email="aria@perenniaai.com",
                                organizer_name=f"Aria (on behalf of {lo_name})",
                                description=(
                                    f"Scheduled via SMS by Aria AI assistant.\n"
                                    f"Appointment type: {appt_type.replace('_', ' ')}\n"
                                    f"Borrower: {borrower_name}"
                                ),
                            )

                            _ics_attachment = EmailAttachment(
                                filename="appointment.ics",
                                content_type="text/calendar; method=REQUEST",
                                raw_content=_ics_content.encode("utf-8"),
                            )

                            _email_html = (
                                f"<h2>Appointment Confirmed</h2>"
                                f"<p>Hi {borrower_name},</p>"
                                f"<p>Your <strong>{appt_type.replace('_', ' ')}</strong> "
                                f"with <strong>{lo_name}</strong> has been confirmed.</p>"
                                f"<p><strong>Date:</strong> {_start_dt.strftime('%A, %B %d, %Y')}<br>"
                                f"<strong>Time:</strong> {_start_dt.strftime('%I:%M %p')}</p>"
                                f"<p>A calendar invite is attached to this email. "
                                f"Please add it to your calendar.</p>"
                                f"<p>If you need to reschedule, just reply to the "
                                f"text message thread or call us.</p>"
                                f"<br><p>Best regards,<br>Aria, assistant to {lo_name}<br>{lo_company}</p>"
                            )

                            # Send to all collected emails
                            _all_failed = True
                            _email_svc = EmailDeliveryService(db)
                            for _addr in _appt_emails:
                                try:
                                    _result = await _email_svc.send_email(
                                        to=_addr,
                                        subject=f"Appointment Confirmed: {_ics_title}",
                                        html_body=_email_html,
                                        from_name=f"Aria at {lo_company}",
                                        attachments=[_ics_attachment],
                                        organization_id=str(org_id) if org_id else None,
                                    )
                                    if _result.success:
                                        _all_failed = False
                                    logger.info(
                                        "aria_sms_bg: calendar invite sent to %s, status=%s, provider=%s",
                                        _addr, _result.status.value, _result.provider.value,
                                    )
                                except Exception as _email_err:
                                    logger.error(
                                        "aria_sms_bg: calendar invite to %s failed: %s",
                                        _addr, _email_err,
                                    )

                            # SMTP fallback
                            if _all_failed:
                                _smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
                                _smtp_port = int(os.environ.get("SMTP_PORT", "587"))
                                _smtp_user = os.environ.get("SMTP_USER", "")
                                _smtp_pass = os.environ.get("SMTP_PASSWORD", "")
                                if _smtp_user and _smtp_pass:
                                    import smtplib as _smtplib
                                    from email.mime.multipart import MIMEMultipart as _MMP
                                    from email.mime.text import MIMEText as _MT
                                    from email.mime.base import MIMEBase as _MB
                                    from email import encoders as _enc

                                    for _addr in _appt_emails:
                                        try:
                                            _msg = _MMP("mixed")
                                            _msg["From"] = f"Aria at {lo_company} <{_smtp_user}>"
                                            _msg["To"] = _addr
                                            _msg["Subject"] = f"Appointment Confirmed: {_ics_title}"
                                            _msg.attach(_MT(_email_html, "html"))
                                            _ics_part = _MB("text", "calendar", method="REQUEST")
                                            _ics_part.set_payload(_ics_content.encode("utf-8"))
                                            _enc.encode_base64(_ics_part)
                                            _ics_part.add_header("Content-Disposition", "attachment", filename="appointment.ics")
                                            _msg.attach(_ics_part)
                                            # Run blocking SMTP in thread to avoid blocking event loop
                                            _msg_str = _msg.as_string()
                                            def _send_smtp(_to_addr, _msg_payload):
                                                with _smtplib.SMTP(_smtp_host, _smtp_port) as _srv:
                                                    _srv.starttls()
                                                    _srv.login(_smtp_user, _smtp_pass)
                                                    _srv.sendmail(_smtp_user, _to_addr, _msg_payload)
                                            await asyncio.to_thread(_send_smtp, _addr, _msg_str)
                                            logger.info("aria_sms_bg: SMTP calendar invite sent to %s", _addr)
                                        except Exception as _smtp_err:
                                            logger.error("aria_sms_bg: SMTP invite to %s failed: %s", _addr, _smtp_err)

                            # Update conversation to confirmed
                            try:
                                db.execute(sa_text("""
                                    UPDATE sms_ai_conversations
                                    SET current_stage = 'confirmed',
                                        context_data = context_data || CAST(:extra AS jsonb)
                                    WHERE id = :conv_id
                                """), {
                                    "conv_id": conv_id,
                                    "extra": json.dumps({
                                        "confirmed_date": _appt_date,
                                        "confirmed_time": _appt_time,
                                        "invite_sent_to": _appt_emails,
                                    }),
                                })
                                db.commit()
                            except Exception as _db_err:
                                db.rollback()
                                logger.error(
                                    "aria_sms_bg: update confirmed stage failed: %s",
                                    _db_err,
                                )

                            logger.info(
                                "aria_sms_bg: calendar invite sent to %s for %s %s",
                                _appt_emails, _appt_date, _appt_time,
                            )
                    elif _appt_date and _appt_time:
                        logger.info(
                            "aria_sms_bg: appointment confirmed (%s %s) but no emails in conversation",
                            _appt_date, _appt_time,
                        )
            except Exception as e:
                logger.error("aria_sms_bg: calendar invite flow failed: %s", e)

        logger.info(
            "aria_sms_bg: completed for conv_id=%s, reply_sent=%s",
            conv_id, bool(_reply_text),
        )

    except Exception as e:
        logger.error("aria_sms_bg: unhandled error for conv_id=%s: %s", conv_id, e, exc_info=True)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


async def handle_inbound_sms(event: TelnyxSMSEvent, db: Session):
    """Handle inbound SMS message with full workflow triggers."""
    from_number = event.from_number
    to_number = event.to_number
    message_body = event.text
    normalized_from = _normalize_phone(from_number)
    normalized_to = _normalize_phone(to_number)

    logger.warning(
        "Inbound SMS from ...%s to ...%s: %s...",
        from_number[-4:] if from_number else "?",
        to_number[-4:] if to_number else "?",
        (message_body or "")[:50],
    )

    # ======================================================================
    # SMS Opt-Out / Opt-In Keyword Handler (TCPA / CTIA compliance)
    # STOP, UNSUBSCRIBE, QUIT -> revoke SMS consent immediately
    # START, YES, UNSTOP -> re-grant SMS consent
    # This MUST run before any other intercept so opt-outs are honoured
    # even if the number is in an active AI conversation or workflow.
    # ======================================================================
    _opt_keyword_result = await _handle_sms_opt_keyword(
        normalized_from, normalized_to, message_body, event.message_id, db,
    )
    if _opt_keyword_result is not None:
        return _opt_keyword_result

    # ======================================================================
    # Voice Workflow Scheduling Intercept
    # Check if this SMS belongs to an active voice-commanded scheduling
    # workflow BEFORE other intercepts. These are time-sensitive
    # availability negotiation conversations.
    # ======================================================================
    _vw_intercept_workflow_id = None
    try:
        from services.voice_scheduling_workflow_service import VoiceSchedulingWorkflowService
        from services.scheduling_conversation_service import SchedulingConversationService

        # --- Tenant isolation: derive org_id from the receiving Telnyx number ---
        # VerifiedCallerId maps phone_number -> organization_id.
        # If the receiving number is not in verified_caller_ids, we fall back to
        # querying without an org filter but log a warning so this gap is visible.
        _vw_org_id = None
        try:
            org_row = db.execute(sa_text("""
                SELECT organization_id FROM verified_caller_ids
                WHERE phone_number = :to_phone AND organization_id IS NOT NULL
                LIMIT 1
            """), {"to_phone": normalized_to}).fetchone()
            if org_row:
                _vw_org_id = org_row[0]
            else:
                logger.warning(
                    "voice_scheduling_intercept: no org mapping for receiving number %s "
                    "(last4=%s) — querying workflows without tenant filter",
                    normalized_to, normalized_to[-4:],
                )
        except Exception as e:
            db.rollback()
            logger.warning("voice_scheduling_intercept: org lookup failed, proceeding without tenant filter: %s", e)

        vw_service = VoiceSchedulingWorkflowService(db)

        # Tenant-isolated lookup: org_id is required by the service
        if _vw_org_id is not None:
            active_workflow = vw_service.find_active_workflow_by_phone(normalized_from, organization_id=_vw_org_id)
        else:
            # No org mapping found — cannot safely query without tenant filter
            logger.warning(
                "voice_scheduling_intercept: skipping workflow lookup — no org_id resolved for receiving number ...%s",
                normalized_to[-4:] if normalized_to else "????",
            )
            active_workflow = None

        if active_workflow:
            _vw_intercept_workflow_id = active_workflow.id
            logger.info(
                "voice_scheduling_intercept: matched workflow_id=%d, phone=...%s, org_id=%s",
                active_workflow.id, normalized_from[-4:], active_workflow.organization_id,
            )

            sched_service = SchedulingConversationService(db)
            logger.info(
                "voice_scheduling_intercept: delegating to handle_reply, "
                "workflow_id=%d, message_preview='%s'",
                active_workflow.id, (message_body or "")[:50],
            )
            sched_result = sched_service.handle_reply(
                workflow_id=active_workflow.id,
                sender_phone=normalized_from,
                message_body=message_body,
                organization_id=_vw_org_id,
            )
            if sched_result is not None:
                # Store SMS in sms_messages for compliance audit trail.
                # Note: the message body is ALSO recorded in the workflow's
                # conversation_history via workflow.add_message("contact", ...)
                # inside handle_reply, so audit coverage is dual-path.
                try:
                    db.execute(sa_text("""
                        INSERT INTO sms_messages (
                            direction, from_number, to_number, message,
                            provider_message_id, status, created_at
                        ) VALUES (
                            'inbound', :from_number, :to_number, :body,
                            :message_id, 'received', NOW()
                        )
                    """), {
                        "from_number": from_number,
                        "to_number": to_number,
                        "body": message_body,
                        "message_id": event.message_id,
                    })
                    db.commit()
                except Exception as e:
                    logger.error(
                        "voice_scheduling_intercept: failed to store SMS audit record, "
                        "workflow_id=%d: %s", active_workflow.id, e,
                    )
                logger.info(
                    "voice_scheduling_intercept: completed, workflow_id=%d, result_status=%s",
                    active_workflow.id, sched_result.get("action", "unknown"),
                )
                # Write to SMS panel so intercepted inbound appears in Archive
                try:
                    import uuid as _uuid
                    db.execute(sa_text("""
                        INSERT INTO sms_panel_messages
                            (id, phone, organization_id, direction, body,
                             sender_name, status, telnyx_message_id, created_at)
                        VALUES (:id, :phone, :org_id, 'inbound', :body,
                                :sender_name, 'received', :telnyx_id, NOW())
                        ON CONFLICT (id) DO NOTHING
                    """), {
                        "id": str(_uuid.uuid4()),
                        "phone": normalized_from,
                        "org_id": _vw_org_id,
                        "body": message_body or "",
                        "sender_name": normalized_from,
                        "telnyx_id": event.message_id,
                    })
                    db.commit()
                    from routes.sms_conversation_routes import notify_inbound_sms
                    await notify_inbound_sms(
                        phone=normalized_from, body=message_body or "",
                        telnyx_message_id=event.message_id, org_id=_vw_org_id,
                    )
                except Exception as _panel_err:
                    logger.debug(f"voice_scheduling_intercept: panel write failed: {_panel_err}")
                return {"status": "received", "handler": "voice_scheduling", "result": sched_result}
        else:
            logger.debug(
                "voice_scheduling_intercept: no active workflow for phone=...%s",
                normalized_from[-4:],
            )
    except Exception as e:
        db.rollback()
        logger.exception(
            "voice_scheduling_intercept: error (falling through to next handler), "
            "workflow_id=%s, from=...%s",
            _vw_intercept_workflow_id, normalized_from[-4:],
        )

    # ======================================================================
    # AI Prospect Re-Engagement Intercept
    # Check if this SMS belongs to an active AI conversation BEFORE
    # normal SMS intelligence processing. If handled, still store the
    # raw SMS for audit trail but skip the intelligence queue.
    # Note: ProspectReEngagementService.handle_reply() queries
    # ai_prospect_conversations by phone and active state. That table
    # has organization_id, but the service resolves context internally
    # via the conversation record itself (lead_id -> org_id). The phone
    # lookup is globally scoped because the same phone number should not
    # have active conversations in multiple orgs simultaneously.
    # ======================================================================
    try:
        from services.prospect_reengagement_service import ProspectReEngagementService
        reengagement_svc = ProspectReEngagementService(db)
        reengagement_result = reengagement_svc.handle_reply(normalized_from, message_body)
        if reengagement_result is not None:
            logger.info(
                "re_engagement_intercept: handled reply from ...%s, result_keys=%s",
                normalized_from[-4:], list(reengagement_result.keys()),
            )
            # Store raw SMS for audit trail
            try:
                db.execute(sa_text("""
                    INSERT INTO sms_messages (
                        direction, from_number, to_number, message,
                        provider_message_id, status, created_at
                    ) VALUES (
                        'inbound', :from_number, :to_number, :body,
                        :message_id, 'received', NOW()
                    )
                """), {
                    "from_number": from_number,
                    "to_number": to_number,
                    "body": message_body,
                    "message_id": event.message_id,
                })
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to store intercepted SMS: {e}")
            # Write to SMS panel so intercepted inbound appears in Archive
            _re_org_id = None
            try:
                _re_org_row = db.execute(sa_text("""
                    SELECT organization_id FROM verified_caller_ids
                    WHERE phone_number = :to_phone AND organization_id IS NOT NULL
                    LIMIT 1
                """), {"to_phone": normalized_to}).fetchone()
                if _re_org_row:
                    _re_org_id = _re_org_row[0]
            except Exception:
                pass
            try:
                import uuid as _uuid
                db.execute(sa_text("""
                    INSERT INTO sms_panel_messages
                        (id, phone, organization_id, direction, body,
                         sender_name, status, telnyx_message_id, created_at)
                    VALUES (:id, :phone, :org_id, 'inbound', :body,
                            :sender_name, 'received', :telnyx_id, NOW())
                    ON CONFLICT (id) DO NOTHING
                """), {
                    "id": str(_uuid.uuid4()),
                    "phone": normalized_from,
                    "org_id": _re_org_id,
                    "body": message_body or "",
                    "sender_name": normalized_from,
                    "telnyx_id": event.message_id,
                })
                db.commit()
                from routes.sms_conversation_routes import notify_inbound_sms
                await notify_inbound_sms(
                    phone=normalized_from, body=message_body or "",
                    telnyx_message_id=event.message_id, org_id=_re_org_id,
                )
            except Exception as _panel_err:
                db.rollback()
                logger.debug(f"re_engagement_intercept: panel write failed: {_panel_err}")
            return {"status": "received", "handler": "ai_reengagement"}
    except Exception as e:
        db.rollback()
        logger.error(f"AI re-engagement intercept error (falling through): {e}")

    # ======================================================================
    # Aria SMS AI Conversation Intercept
    # Check if this SMS belongs to an active Aria-initiated conversation
    # (e.g., scheduling via voice command). Generates AI reply via Claude
    # and sends it back via Telnyx.
    # ======================================================================
    try:
        # Resolve org from the receiving number for tenant-scoped lookup
        _aria_intercept_org_id = None
        try:
            _aria_org_row = db.execute(sa_text("""
                SELECT organization_id FROM verified_caller_ids
                WHERE phone_number = :to_phone AND organization_id IS NOT NULL
                LIMIT 1
            """), {"to_phone": normalized_to}).fetchone()
            if _aria_org_row:
                _aria_intercept_org_id = _aria_org_row[0]
                logger.debug(
                    "aria_sms_intercept: tenant resolved org_id=%s from receiving number ...%s",
                    _aria_intercept_org_id, normalized_to[-4:],
                )
            else:
                logger.warning(
                    "aria_sms_intercept: no org mapping for receiving number ...%s — "
                    "querying sms_ai_conversations without tenant filter",
                    normalized_to[-4:],
                )
        except Exception as e:
            db.rollback()
            logger.warning("aria_sms_intercept: org lookup failed: %s", e)

        # Tenant-isolated conversation lookup — never cross org boundaries
        _aria_conv = None
        if _aria_intercept_org_id:
            _aria_conv = db.execute(sa_text("""
                SELECT id, organization_id, current_stage, context_data
                FROM sms_ai_conversations
                WHERE phone_number = :phone AND status = 'active'
                AND organization_id = :org_id
                ORDER BY last_message_at DESC NULLS LAST
                LIMIT 1
            """), {"phone": normalized_from, "org_id": _aria_intercept_org_id}).fetchone()
        else:
            logger.warning(
                "aria_sms_intercept: no org resolved for phone=...%s — skipping conversation lookup",
                normalized_from[-4:],
            )

        if _aria_conv:
            _aria_conv_id = _aria_conv[0]
            _aria_org_id = _aria_conv[1]
            _aria_stage = _aria_conv[2]
            _aria_context = _aria_conv[3] or {}
            logger.info(
                "aria_sms_intercept: matched conversation_id=%s, phone=...%s, stage=%s",
                _aria_conv_id, normalized_from[-4:], _aria_stage,
            )

            # Store inbound message in conversation (fast DB op -- keep in request)
            import uuid as _uuid_mod
            _inbound_msg_id = str(_uuid_mod.uuid4())
            try:
                db.execute(sa_text("""
                    INSERT INTO sms_ai_conversation_messages
                    (id, conversation_id, direction, content, ai_generated, created_at)
                    VALUES (:id, :conv_id, 'inbound', :content, false, NOW())
                """), {
                    "id": _inbound_msg_id,
                    "conv_id": _aria_conv_id,
                    "content": message_body,
                })
                db.commit()
            except Exception:
                db.rollback()

            # Store inbound for audit trail (fast DB op -- keep in request)
            try:
                db.execute(sa_text("""
                    INSERT INTO sms_messages (
                        direction, from_number, to_number, message,
                        provider_message_id, status, created_at
                    ) VALUES (
                        'inbound', :from_number, :to_number, :body,
                        :message_id, 'received', NOW()
                    )
                """), {
                    "from_number": from_number,
                    "to_number": to_number,
                    "body": message_body,
                    "message_id": event.message_id,
                })
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error("aria_sms_intercept: audit SMS store failed: %s", e)

            # Write to SMS panel so Aria-intercepted inbound appears in Archive
            try:
                import uuid as _uuid
                db.execute(sa_text("""
                    INSERT INTO sms_panel_messages
                        (id, phone, organization_id, direction, body,
                         sender_name, status, telnyx_message_id, created_at)
                    VALUES (:id, :phone, :org_id, 'inbound', :body,
                            :sender_name, 'received', :telnyx_id, NOW())
                    ON CONFLICT (id) DO NOTHING
                """), {
                    "id": event.message_id or str(_uuid.uuid4()),
                    "phone": normalized_from,
                    "org_id": _aria_org_id,
                    "body": message_body or "",
                    "sender_name": normalized_from,
                    "telnyx_id": event.message_id,
                })
                db.commit()
                from routes.sms_conversation_routes import notify_inbound_sms
                await notify_inbound_sms(
                    phone=normalized_from, body=message_body or "",
                    telnyx_message_id=event.message_id, org_id=_aria_org_id,
                )
            except Exception as _panel_err:
                db.rollback()
                logger.debug(f"aria_sms_intercept: panel write failed: {_panel_err}")

            # Spawn background task for Claude AI processing + reply sending.
            # This releases the webhook DB connection and returns 200 to Telnyx
            # immediately, preventing the 5s timeout retry and avoiding event
            # loop blocking from synchronous Claude API calls (2-8s each).
            asyncio.create_task(
                _aria_sms_ai_background_task(
                    conv_id=_aria_conv_id,
                    org_id=_aria_org_id,
                    stage=_aria_stage,
                    context_data=_aria_context,
                    message_body=message_body,
                    normalized_from=normalized_from,
                )
            )

            return {
                "status": "received",
                "handler": "aria_sms_conversation",
                "conversation_id": str(_aria_conv_id),
                "reply_sent": False,  # reply happens asynchronously in background
            }
    except Exception as e:
        db.rollback()
        logger.error(f"Aria SMS conversation intercept error (falling through): {e}")

    # ======================================================================
    # Aria SMS Auto-Create — Cold Inbound
    # If no active conversation exists but the phone belongs to a known
    # lead or POS borrower, auto-create an Aria conversation and reply.
    # This lets borrowers text Aria directly without a prior voice call.
    # ======================================================================
    try:
        if not _aria_conv:
            _auto_org_id = _aria_intercept_org_id
            if not _auto_org_id:
                _auto_org_row = db.execute(sa_text("""
                    SELECT organization_id FROM verified_caller_ids
                    WHERE phone_number = :to_phone AND organization_id IS NOT NULL
                    LIMIT 1
                """), {"to_phone": normalized_to}).fetchone()
                if _auto_org_row:
                    _auto_org_id = _auto_org_row[0]

            if _auto_org_id:
                _phone_digits = re.sub(r'\D', '', normalized_from)
                if len(_phone_digits) > 10:
                    _phone_digits = _phone_digits[-10:]
                _auto_lead = db.execute(sa_text("""
                    SELECT l.id, l.first_name, l.last_name, l.owner_id
                    FROM leads l
                    WHERE l.organization_id = :org_id
                    AND l.deleted_at IS NULL
                    AND RIGHT(REGEXP_REPLACE(COALESCE(l.phone, ''), '[^0-9]', '', 'g'), 10) = :digits
                    ORDER BY l.updated_at DESC NULLS LAST
                    LIMIT 1
                """), {"org_id": _auto_org_id, "digits": _phone_digits}).fetchone()

                _auto_from_purl = False
                if not _auto_lead:
                    _auto_lead = db.execute(sa_text("""
                        SELECT pc.id, pc.first_name, pc.last_name, NULL AS owner_id
                        FROM purl_contacts pc
                        WHERE pc.organization_id = :org_id
                        AND RIGHT(REGEXP_REPLACE(COALESCE(pc.phone, ''), '[^0-9]', '', 'g'), 10) = :digits
                        ORDER BY pc.id DESC
                        LIMIT 1
                    """), {"org_id": _auto_org_id, "digits": _phone_digits}).fetchone()
                    if _auto_lead:
                        _auto_from_purl = True

                if _auto_lead:
                    _auto_lead_id = None if _auto_from_purl else _auto_lead[0]
                    _auto_borrower = (
                        f"{_auto_lead[1] or ''} {_auto_lead[2] or ''}".strip() or "there"
                    )
                    _auto_lo_user_id = _auto_lead[3]

                    _auto_lo_name = "your loan officer"
                    if _auto_lo_user_id:
                        _auto_lo_row = db.execute(sa_text("""
                            SELECT first_name, last_name FROM users WHERE id = :uid
                        """), {"uid": _auto_lo_user_id}).fetchone()
                        if _auto_lo_row:
                            _auto_lo_name = (
                                f"{_auto_lo_row[0] or ''} {_auto_lo_row[1] or ''}".strip()
                                or "your loan officer"
                            )
                    else:
                        _auto_lo_row = db.execute(sa_text("""
                            SELECT id, first_name, last_name FROM users
                            WHERE organization_id = :org_id
                            AND role IN ('admin', 'lo', 'loan_officer')
                            ORDER BY id LIMIT 1
                        """), {"org_id": _auto_org_id}).fetchone()
                        if _auto_lo_row:
                            _auto_lo_user_id = _auto_lo_row[0]
                            _auto_lo_name = (
                                f"{_auto_lo_row[1] or ''} {_auto_lo_row[2] or ''}".strip()
                                or "your loan officer"
                            )

                    import uuid as _uuid_auto
                    _auto_conv_id = str(_uuid_auto.uuid4())
                    _auto_context = {
                        "borrower_name": _auto_borrower,
                        "lo_name": _auto_lo_name,
                        "appointment_type": "general",
                        "user_id": str(_auto_lo_user_id) if _auto_lo_user_id else None,
                        "lead_id": str(_auto_lead_id),
                        "auto_created": True,
                    }

                    db.execute(sa_text("""
                        INSERT INTO sms_ai_conversations
                        (id, phone_number, lead_id, organization_id, status,
                         current_stage, context_data, last_message_at,
                         message_count, created_at)
                        VALUES (:id, :phone, :lead_id, :org_id, 'active',
                                'general', CAST(:context AS jsonb), NOW(), 1, NOW())
                        ON CONFLICT DO NOTHING
                    """), {
                        "id": _auto_conv_id,
                        "phone": normalized_from,
                        "lead_id": _auto_lead_id,
                        "org_id": _auto_org_id,
                        "context": json.dumps(_auto_context),
                    })
                    db.execute(sa_text("""
                        INSERT INTO sms_ai_conversation_messages
                        (id, conversation_id, direction, content, ai_generated, created_at)
                        VALUES (:id, :conv_id, 'inbound', :content, false, NOW())
                    """), {
                        "id": str(_uuid_auto.uuid4()),
                        "conv_id": _auto_conv_id,
                        "content": message_body,
                    })
                    db.commit()

                    logger.info(
                        "aria_sms_auto_create: new conversation %s for lead=%s, phone=...%s",
                        _auto_conv_id, _auto_lead_id, normalized_from[-4:],
                    )

                    try:
                        db.execute(sa_text("""
                            INSERT INTO sms_messages (
                                direction, from_number, to_number, message,
                                provider_message_id, status, created_at
                            ) VALUES (
                                'inbound', :from_number, :to_number, :body,
                                :message_id, 'received', NOW()
                            )
                        """), {
                            "from_number": from_number,
                            "to_number": to_number,
                            "body": message_body,
                            "message_id": event.message_id,
                        })
                        db.commit()
                    except Exception:
                        db.rollback()

                    try:
                        import uuid as _uuid_panel
                        db.execute(sa_text("""
                            INSERT INTO sms_panel_messages
                                (id, phone, organization_id, direction, body,
                                 sender_name, status, telnyx_message_id, created_at)
                            VALUES (:id, :phone, :org_id, 'inbound', :body,
                                    :sender_name, 'received', :telnyx_id, NOW())
                            ON CONFLICT (id) DO NOTHING
                        """), {
                            "id": event.message_id or str(_uuid_panel.uuid4()),
                            "phone": normalized_from,
                            "org_id": _auto_org_id,
                            "body": message_body or "",
                            "sender_name": normalized_from,
                            "telnyx_id": event.message_id,
                        })
                        db.commit()
                        from routes.sms_conversation_routes import notify_inbound_sms
                        await notify_inbound_sms(
                            phone=normalized_from, body=message_body or "",
                            telnyx_message_id=event.message_id, org_id=_auto_org_id,
                        )
                    except Exception as _panel_err:
                        db.rollback()
                        logger.debug("aria_sms_auto_create: panel write: %s", _panel_err)

                    asyncio.create_task(
                        _aria_sms_ai_background_task(
                            conv_id=_auto_conv_id,
                            org_id=_auto_org_id,
                            stage="general",
                            context_data=_auto_context,
                            message_body=message_body,
                            normalized_from=normalized_from,
                        )
                    )

                    return {
                        "status": "received",
                        "handler": "aria_sms_auto_created",
                        "conversation_id": _auto_conv_id,
                        "reply_sent": False,
                    }
    except Exception as e:
        db.rollback()
        logger.error("Aria SMS auto-create error (falling through): %s", e)

    # ======================================================================
    # ACO (Application Completion Orchestrator) Intercept
    # Check if SMS is a response to an active application review
    # before standard intelligence processing.
    # ======================================================================
    try:
        from services.smart_docs.app_completion_orchestrator import AppCompletionOrchestrator
        aco_orchestrator = AppCompletionOrchestrator(db)
        aco_result = aco_orchestrator.handle_borrower_response(
            from_number=normalized_from,
            to_number=normalized_to,
            message_body=message_body,
            raw_payload={"message_id": event.message_id},
        )
        if aco_result and aco_result.get("status") == "processed":
            # ACO handled this SMS — store for audit trail, skip intelligence queue
            try:
                db.execute(sa_text("""
                    INSERT INTO sms_messages (
                        direction, from_number, to_number, message,
                        provider_message_id, status, created_at
                    ) VALUES (
                        'inbound', :from_number, :to_number, :body,
                        :message_id, 'received', NOW()
                    )
                """), {
                    "from_number": from_number,
                    "to_number": to_number,
                    "body": message_body,
                    "message_id": event.message_id,
                })
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to store ACO-intercepted SMS: {e}")
            # Write to SMS panel so ACO-intercepted inbound appears in Archive
            try:
                import uuid as _uuid
                _aco_org_id = None
                try:
                    _aco_org_row = db.execute(sa_text(
                        "SELECT organization_id FROM verified_caller_ids "
                        "WHERE phone_number = :to_phone AND organization_id IS NOT NULL LIMIT 1"
                    ), {"to_phone": normalized_to}).fetchone()
                    if _aco_org_row:
                        _aco_org_id = _aco_org_row[0]
                except Exception:
                    pass
                db.execute(sa_text("""
                    INSERT INTO sms_panel_messages
                        (id, phone, organization_id, direction, body,
                         sender_name, status, telnyx_message_id, created_at)
                    VALUES (:id, :phone, :org_id, 'inbound', :body,
                            :sender_name, 'received', :telnyx_id, NOW())
                    ON CONFLICT (id) DO NOTHING
                """), {
                    "id": event.message_id or str(_uuid.uuid4()),
                    "phone": normalized_from,
                    "org_id": _aco_org_id,
                    "body": message_body or "",
                    "sender_name": normalized_from,
                    "telnyx_id": event.message_id,
                })
                db.commit()
                from routes.sms_conversation_routes import notify_inbound_sms
                await notify_inbound_sms(
                    phone=normalized_from, body=message_body or "",
                    telnyx_message_id=event.message_id, org_id=_aco_org_id,
                )
            except Exception as _panel_err:
                db.rollback()
                logger.debug(f"aco_intercept: panel write failed: {_panel_err}")
            return {
                "status": "received",
                "handler": "aco",
                "review_id": aco_result.get("review_id"),
            }
    except ImportError:
        pass  # ACO module not available
    except Exception as e:
        db.rollback()
        logger.error(f"ACO intercept error (falling through): {e}")

    # Store inbound SMS in sms_messages table
    try:
        db.execute(sa_text("""
            INSERT INTO sms_messages (
                direction, from_number, to_number, message,
                provider_message_id, status, created_at
            ) VALUES (
                'inbound', :from_number, :to_number, :body,
                :message_id, 'received', NOW()
            )
        """), {
            "from_number": from_number,
            "to_number": to_number,
            "body": message_body,
            "message_id": event.message_id,
        })
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to store inbound SMS: {e}")

    # ==========================================================================
    # Workflow Trigger: Feed into SMS Intelligence Queue for AI analysis,
    # entity matching, SLA tracking, and notification dispatching.
    # This mirrors the telephony webhook flow in sms_intelligence_routes.py.
    # ==========================================================================

    intelligence_queue_id = None
    try:
        # Insert into sms_intelligence_queue (same schema as telephony webhook path)
        result = db.execute(sa_text("""
            INSERT INTO sms_intelligence_queue (
                sms_provider, provider_message_id, from_phone, to_phone,
                direction, message_body, has_media, media_count,
                received_at, status
            ) VALUES (
                'telnyx', :message_id, :from_phone, :to_phone,
                'inbound', :body, :has_media, :media_count,
                CURRENT_TIMESTAMP, 'pending'
            )
            ON CONFLICT (sms_provider, provider_message_id) DO NOTHING
            RETURNING id
        """), {
            "message_id": event.message_id,
            "from_phone": normalized_from,
            "to_phone": normalized_to,
            "body": message_body,
            "has_media": False,  # Telnyx media handled separately if needed
            "media_count": 0,
        })
        row = result.fetchone()
        if row:
            intelligence_queue_id = row[0]
        db.commit()
        logger.warning(f"Telnyx SMS queued for intelligence processing: id={intelligence_queue_id}")
    except Exception as e:
        logger.error(f"Failed to queue SMS for intelligence processing: {e}")
        db.rollback()

    # Trigger background AI analysis and workflow processing
    if intelligence_queue_id:
        try:
            from routes.sms_intelligence_routes import process_incoming_sms
            asyncio.create_task(process_incoming_sms(intelligence_queue_id))
            logger.info(f"Background SMS processing triggered for queue id {intelligence_queue_id}")
        except ImportError:
            logger.warning("sms_intelligence_routes not available, skipping AI analysis")
        except Exception as e:
            logger.error(f"Failed to trigger background SMS processing: {e}")

    # ==========================================================================
    # Store inbound SMS in sms_panel_messages for Archive visibility
    # ==========================================================================
    _inbound_org_id = None
    _to_digits = re.sub(r'\D', '', normalized_to)
    _to_pattern = f"%{_to_digits[-10:]}" if len(_to_digits) >= 10 else f"%{_to_digits}"
    try:
        # Try exact match first, then fall back to last-10-digit pattern
        _org_row = db.execute(sa_text("""
            SELECT organization_id FROM verified_caller_ids
            WHERE phone_number = :to_phone AND organization_id IS NOT NULL
            LIMIT 1
        """), {"to_phone": normalized_to}).fetchone()
        if not _org_row:
            _org_row = db.execute(sa_text("""
                SELECT organization_id FROM verified_caller_ids
                WHERE REGEXP_REPLACE(phone_number, '[^0-9]', '', 'g') LIKE :pattern
                  AND organization_id IS NOT NULL
                LIMIT 1
            """), {"pattern": _to_pattern}).fetchone()
        if not _org_row:
            # Fallback: resolve org from sender's lead record
            _from_digits = re.sub(r'\D', '', normalized_from)
            _from_pat = f"%{_from_digits[-10:]}" if len(_from_digits) >= 10 else f"%{_from_digits}"
            _org_row = db.execute(sa_text("""
                SELECT organization_id FROM leads
                WHERE REGEXP_REPLACE(phone, '[^0-9]', '', 'g') LIKE :pattern
                  AND organization_id IS NOT NULL
                ORDER BY updated_at DESC LIMIT 1
            """), {"pattern": _from_pat}).fetchone()
            if _org_row:
                logger.info(
                    "Inbound SMS tenant resolved via lead lookup org_id=%s",
                    _org_row[0],
                )
        if not _org_row:
            logger.warning(
                "Inbound SMS tenant unresolved: no org match via verified_caller_ids or lead phone for ...%s — "
                "skipping panel storage and auto-responder",
                normalized_from[-4:],
            )
        if _org_row:
            _inbound_org_id = _org_row[0]
            logger.info(
                "Inbound SMS tenant resolved: org_id=%s from receiving number ...%s",
                _inbound_org_id, normalized_to[-4:],
            )
        else:
            logger.warning(
                "Inbound SMS tenant unresolved: no org mapping for receiving number ...%s — "
                "panel storage, auto-responder, and notification will run without tenant scope",
                normalized_to[-4:],
            )
    except Exception as e:
        db.rollback()
        logger.warning("Org lookup for inbound SMS panel storage failed: %s", e)

    # Resolve contact_id (lead) from the sender's phone number for attribution
    # Use last-10-digit pattern matching to handle format variations (E.164, dashes, parens)
    _inbound_contact_id = None
    _from_digits = re.sub(r'\D', '', normalized_from)
    _from_pattern = f"%{_from_digits[-10:]}" if len(_from_digits) >= 10 else f"%{_from_digits}"
    if _inbound_org_id:
        try:
            _lead_row = db.execute(sa_text("""
                SELECT id FROM leads
                WHERE REGEXP_REPLACE(phone, '[^0-9]', '', 'g') LIKE :pattern
                  AND organization_id = :org_id
                ORDER BY updated_at DESC LIMIT 1
            """), {"pattern": _from_pattern, "org_id": _inbound_org_id}).fetchone()
            if _lead_row:
                _inbound_contact_id = str(_lead_row[0])
        except Exception as e:
            logger.debug(f"Lead lookup for inbound SMS contact_id failed (non-critical): {e}")

    if _inbound_org_id:
        try:
            import uuid as _uuid
            _panel_id = event.message_id or str(_uuid.uuid4())
            db.execute(sa_text("""
                INSERT INTO sms_panel_messages
                    (id, phone, contact_id, organization_id, direction, body,
                     sender_name, status, media_urls,
                     telnyx_message_id, created_at)
                VALUES
                    (:id, :phone, :contact_id, :org_id, 'inbound', :body,
                     :sender_name, 'received', '[]'::jsonb,
                     :telnyx_id, NOW())
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": _panel_id,
                "phone": normalized_from,
                "contact_id": _inbound_contact_id,
                "org_id": _inbound_org_id,
                "body": message_body or "",
                "sender_name": normalized_from,
                "telnyx_id": event.message_id,
            })
            db.commit()
            logger.info("Inbound SMS stored in sms_panel_messages for phone=...%s, org_id=%s", normalized_from[-4:], _inbound_org_id)
        except Exception as e:
            logger.warning("Failed to store inbound SMS in sms_panel_messages: %s", e)
            db.rollback()

    # Link the sms_messages row to org/lead so it shows in client file timeline
    if _inbound_org_id or _inbound_contact_id:
        try:
            db.execute(sa_text("""
                UPDATE sms_messages
                SET organization_id = COALESCE(:org_id, organization_id),
                    lead_id = COALESCE(CAST(:lead_id AS INTEGER), lead_id)
                WHERE provider_message_id = :msg_id
            """), {
                "org_id": _inbound_org_id,
                "lead_id": int(_inbound_contact_id) if _inbound_contact_id else None,
                "msg_id": event.message_id,
            })
            db.commit()
        except Exception as e:
            db.rollback()
            logger.debug("Failed to link inbound SMS to org/lead: %s", e)

    # Create Activity record for inbound SMS so it appears in client file timeline
    if _inbound_contact_id and _inbound_org_id:
        try:
            db.execute(sa_text("""
                INSERT INTO activities (organization_id, lead_id, type, content, created_at)
                VALUES (:org_id, :lead_id, 'SMS', :content, NOW())
            """), {
                "org_id": _inbound_org_id,
                "lead_id": int(_inbound_contact_id),
                "content": message_body or "",
            })
            db.commit()
        except Exception as e:
            db.rollback()
            logger.debug("Failed to create Activity for inbound SMS: %s", e)

    # Push inbound message to SMS panel WebSocket so it appears in real-time
    try:
        _contact_display = None
        if _inbound_contact_id and _inbound_org_id:
            try:
                _name_row = db.execute(sa_text("""
                    SELECT first_name || ' ' || last_name FROM leads
                    WHERE id = :lid AND organization_id = :org_id
                """), {"lid": int(_inbound_contact_id), "org_id": _inbound_org_id}).fetchone()
                if _name_row and _name_row[0] and _name_row[0].strip():
                    _contact_display = _name_row[0].strip()
            except Exception:
                pass

        from routes.sms_conversation_routes import notify_inbound_sms
        await notify_inbound_sms(
            phone=normalized_from,
            body=message_body or "",
            telnyx_message_id=event.message_id,
            org_id=_inbound_org_id,
            contact_name=_contact_display or "",
        )
    except Exception as e:
        logger.debug(f"Inbound SMS WebSocket push failed (non-critical): {e}")

    # ==========================================================================
    # SMS Auto-Responder: create task + AI recommendation + auto-reply
    # ==========================================================================
    if _inbound_org_id:
        try:
            from services.sms_auto_responder import handle_inbound_sms as _auto_respond

            _contact_name = None
            try:
                _lead_name_row = db.execute(sa_text("""
                    SELECT first_name || ' ' || last_name FROM leads
                    WHERE REGEXP_REPLACE(phone, '[^0-9]', '', 'g') LIKE :pattern
                      AND organization_id = :org_id
                    ORDER BY updated_at DESC LIMIT 1
                """), {"pattern": _from_pattern, "org_id": _inbound_org_id}).fetchone()
                if _lead_name_row:
                    _contact_name = _lead_name_row[0]
            except Exception:
                pass

            _ar_result = _auto_respond(
                db=db,
                phone_number=normalized_from,
                message_text=message_body or "",
                telnyx_message_id=event.message_id,
                organization_id=_inbound_org_id,
                contact_name=_contact_name,
            )
            logger.info(
                f"SMS auto-responder result: task_id={_ar_result.get('task_id')}, "
                f"auto_responded={_ar_result.get('auto_responded')}, "
                f"confidence={_ar_result.get('ai_confidence')}"
            )
        except ImportError:
            logger.warning("sms_auto_responder not available, skipping auto-reply")
        except Exception as e:
            logger.error(f"SMS auto-responder failed (non-blocking): {e}", exc_info=True)

    # ==========================================================================
    # Real-time notification: Alert loan officer via WebSocket
    # ==========================================================================

    try:
        # Look up which user owns this phone number (scoped to org if resolved)
        # SECURITY: _lo_org_clause is a code-defined constant, not user-derived input
        _lo_org_clause = "AND l.organization_id = :org_id" if _inbound_org_id else ""
        _lo_params = {"phone": normalized_from}
        if _inbound_org_id:
            _lo_params["org_id"] = _inbound_org_id

        lo_match = db.execute(sa_text(f"""
            SELECT DISTINCT l.loan_officer_id
            FROM loans l
            WHERE l.borrower_phone = :phone
            AND l.loan_officer_id IS NOT NULL
            {_lo_org_clause}
            LIMIT 1
        """), _lo_params).fetchone()

        if not lo_match:
            lo_match = db.execute(sa_text(f"""
                SELECT DISTINCT l.owner_id
                FROM leads l
                WHERE l.phone = :phone
                AND l.owner_id IS NOT NULL
                {_lo_org_clause}
                LIMIT 1
            """), _lo_params).fetchone()

        if lo_match:
            lo_user_id = lo_match[0]
            try:
                from services.workflow_websocket_events import WorkflowWebSocketNotifier
                notifier = WorkflowWebSocketNotifier()
                notifier.notify_user_sync(lo_user_id, {
                    "type": "sms_received",
                    "from_phone": from_number,
                    "preview": message_body[:100] if message_body else "",
                    "provider": "telnyx",
                    "queue_id": intelligence_queue_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                logger.info(f"WebSocket notification sent to LO user_id={lo_user_id}")
            except ImportError:
                logger.debug("WebSocket notifier not available")
            except Exception as e:
                logger.debug(f"WebSocket notification failed (non-critical): {e}")
    except Exception as e:
        logger.debug(f"LO lookup for notification failed (non-critical): {e}")

    return {"status": "received", "from": from_number, "queue_id": intelligence_queue_id}


# =============================================================================
# Recording Handler
# =============================================================================

async def handle_recording_saved(event: TelnyxCallEvent, db: Session):
    """Handle call recording saved event.

    Stores the recording URL, then kicks off a background task to transcribe
    the audio and feed the transcript into the Call Intelligence pipeline.
    """
    call_control_id = event.call_control_id
    recording_url = event.payload.get("recording_urls", {}).get("mp3")

    # Resolve tenant context for structured logging
    _rec_org_id = None
    try:
        _rec_row = db.execute(sa_text("""
            SELECT u.organization_id
            FROM amd_outbound_calls a
            JOIN users u ON u.id = a.user_id
            WHERE a.call_sid = :call_id
        """), {"call_id": call_control_id}).fetchone()
        if _rec_row:
            _rec_org_id = _rec_row[0]
    except Exception:
        pass  # Best-effort

    if _rec_org_id:
        logger.info(
            "Recording saved: call_control_id=%s, org_id=%s, url=%s",
            call_control_id, _rec_org_id, recording_url,
        )
    else:
        logger.info(
            "Recording saved: call_control_id=%s (org unresolved), url=%s",
            call_control_id, recording_url,
        )

    if recording_url:
        # Store recording URL
        db.execute(sa_text("""
            UPDATE call_attempts
            SET recording_url = :url
            WHERE call_sid = :call_id
        """), {"url": recording_url, "call_id": call_control_id})
        db.commit()

        # Kick off background transcription + CI processing
        if CALL_INTELLIGENCE_ENABLED:
            asyncio.create_task(
                _transcribe_and_process_recording(call_control_id, recording_url)
            )
        else:
            logger.debug("Call Intelligence not enabled, skipping recording processing")

    return {"status": "acknowledged", "recording_url": recording_url}


async def _transcribe_and_process_recording(
    call_control_id: str,
    recording_url: str,
) -> None:
    """Background task: transcribe a Telnyx call recording and run CI.

    Creates its own DB session so the webhook handler can return 200
    immediately. All errors are caught and logged — never propagated.
    """
    db: Optional[Session] = None
    try:
        # -----------------------------------------------------------------
        # 1. Transcribe the recording
        # -----------------------------------------------------------------
        from services.media.transcription_service import (
            get_transcription_service,
            TranscriptionService,
        )

        svc = get_transcription_service()
        if svc is None:
            logger.warning(
                "No transcription service available (set DEEPGRAM_API_KEY or "
                "OPENAI_API_KEY) — skipping CI for recording %s",
                call_control_id,
            )
            return

        # Deepgram's TranscriptionService can transcribe directly from URL.
        # WhisperTranscriptionService requires a local file, so we download first.
        if isinstance(svc, TranscriptionService):
            transcript_result = svc.transcribe_url(recording_url)
        else:
            # Whisper fallback — download MP3 to a temp file
            import tempfile
            import httpx

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(recording_url)
                resp.raise_for_status()
                audio_bytes = resp.content

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            try:
                transcript_result = svc.transcribe_file(tmp_path)
            finally:
                import os as _os
                try:
                    _os.unlink(tmp_path)
                except OSError:
                    pass

        full_text = transcript_result.get("full_text", "").strip()
        if not full_text:
            logger.info(
                "Transcription returned empty text for %s — skipping CI",
                call_control_id,
            )
            return

        logger.info(
            "Transcribed recording %s: %d chars, %d words",
            call_control_id,
            len(full_text),
            transcript_result.get("word_count", 0),
        )

        # -----------------------------------------------------------------
        # 2a. Persist transcript to DB for historical access
        # -----------------------------------------------------------------
        db = SessionLocal()

        try:
            # call_logs has transcript_text + transcript_status columns
            db.execute(sa_text("""
                UPDATE call_logs
                SET transcript_text = :transcript,
                    transcript_status = 'completed'
                WHERE call_sid = :call_id
            """), {"transcript": full_text, "call_id": call_control_id})
            db.commit()
            logger.debug(
                "Persisted transcript to call_logs for %s", call_control_id
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist transcript for call %s: %s",
                call_control_id, exc,
            )
            try:
                db.rollback()
            except Exception:
                pass

        # -----------------------------------------------------------------
        # 2b. Resolve organization_id (and optional loan_id) from call record
        #     Note: amd_outbound_calls has NO organization_id column.
        #     We resolve org via user_id -> users.organization_id.
        # -----------------------------------------------------------------
        org_id: Optional[int] = None
        loan_id: Optional[int] = None

        # Try amd_outbound_calls first (AMD / voicemail-drop calls)
        row = db.execute(sa_text("""
            SELECT user_id, to_number
            FROM amd_outbound_calls
            WHERE call_sid = :call_id
            LIMIT 1
        """), {"call_id": call_control_id}).fetchone()

        user_id = None
        to_number = None
        if row:
            user_id = row[0]
            to_number = row[1]
            # Resolve org from user_id immediately
            if user_id:
                _user_org_row = db.execute(sa_text(
                    "SELECT organization_id FROM users WHERE id = :uid"
                ), {"uid": user_id}).fetchone()
                if _user_org_row:
                    org_id = _user_org_row[0]
                    logger.info(
                        "CI org resolution: amd_outbound_calls -> user_id=%s -> org_id=%s for call %s",
                        user_id, org_id, call_control_id,
                    )

        # Fallback: try call_attempts -> call_targets for dialer calls
        if not org_id:
            target_row = db.execute(sa_text("""
                SELECT ct.lead_id, ct.phone_number
                FROM call_attempts ca
                JOIN call_targets ct ON ct.id = ca.call_target_id
                WHERE ca.provider_call_id = :call_id
                LIMIT 1
            """), {"call_id": call_control_id}).fetchone()

            if target_row:
                lead_id_val = target_row[0]
                to_number = target_row[1]
                if lead_id_val:
                    # Resolve org from lead
                    org_row = db.execute(sa_text("""
                        SELECT organization_id FROM leads
                        WHERE id = :lead_id
                    """), {"lead_id": lead_id_val}).fetchone()
                    if org_row:
                        org_id = org_row[0]
                        logger.info(
                            "CI org resolution: call_targets -> lead_id=%s -> org_id=%s for call %s",
                            lead_id_val, org_id, call_control_id,
                        )

        # Fallback: resolve org from user_id (already resolved above for
        # amd_outbound_calls path; this handles the case where
        # call_attempts path found user_id but no lead)
        if not org_id and user_id:
            user_row = db.execute(sa_text("""
                SELECT organization_id FROM users WHERE id = :uid
            """), {"uid": user_id}).fetchone()
            if user_row:
                org_id = user_row[0]
                logger.info(
                    "CI org resolution: user fallback -> user_id=%s -> org_id=%s for call %s",
                    user_id, org_id, call_control_id,
                )

        # Fallback: resolve org from to_number via leads
        if not org_id and to_number:
            lead_row = db.execute(sa_text("""
                SELECT id, organization_id FROM leads
                WHERE phone = :phone AND organization_id IS NOT NULL
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
            """), {"phone": to_number}).fetchone()
            if lead_row:
                loan_id_lookup = db.execute(sa_text("""
                    SELECT id FROM loans
                    WHERE lead_id = :lead_id
                    ORDER BY updated_at DESC NULLS LAST
                    LIMIT 1
                """), {"lead_id": lead_row[0]}).fetchone()
                org_id = lead_row[1]
                if loan_id_lookup:
                    loan_id = loan_id_lookup[0]
                logger.info(
                    "CI org resolution: to_number -> lead phone=%s -> org_id=%s for call %s",
                    to_number[-4:] if to_number else "?", org_id, call_control_id,
                )

        if not org_id:
            logger.warning(
                "CI org resolution: FAILED all fallbacks for recording %s — skipping CI",
                call_control_id,
            )
            return

        # TENANT-017: Set RLS context now that org_id is resolved
        try:
            from database.tenant_mixin import set_tenant_context
            set_tenant_context(db, org_id)
        except Exception:
            pass

        # -----------------------------------------------------------------
        # 3. Feed transcript into Call Intelligence
        # -----------------------------------------------------------------
        integration = CallIntelligenceIntegration(db)
        ci_result = await integration.process_completed_call(
            call_id=f"telnyx-{call_control_id}",
            loan_id=loan_id,
            organization_id=org_id,
            transcript=full_text,
            call_type="follow_up",
            call_metadata={
                "source": "telnyx_recording",
                "recording_url": recording_url,
                "word_count": transcript_result.get("word_count", 0),
                "confidence": transcript_result.get("confidence", 0.0),
            },
        )

        if ci_result.get("success"):
            logger.info(
                "CI processed Telnyx recording %s: %d extractions, %d tasks",
                call_control_id,
                ci_result.get("extractions_count", 0),
                ci_result.get("tasks_created", 0),
            )
        else:
            logger.warning(
                "CI processing failed for Telnyx recording %s: %s",
                call_control_id,
                ci_result.get("error", ci_result.get("errors", "unknown")),
            )

    except Exception as e:
        logger.exception(
            "Background transcription/CI failed for recording %s: %s",
            call_control_id,
            e,
        )
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


# =============================================================================
# TeXML Response Endpoints (for call control)
# =============================================================================

@router.post("/texml/waiting/{tracking_id}")
@router.get("/texml/waiting/{tracking_id}")
async def texml_waiting(tracking_id: str, request: Request):
    """TeXML response while AMD is running - pause briefly"""
    _validate_texml_request(request)
    if not tracking_id or not str(tracking_id).isdigit():
        raise HTTPException(status_code=400, detail="Invalid tracking ID")
    response = TeXMLResponse()
    response.pause(length=3)
    return Response(content=response.to_xml(), media_type="application/xml")


@router.post("/texml/hangup")
@router.get("/texml/hangup")
async def texml_hangup(request: Request):
    """TeXML response to hang up the call"""
    _validate_texml_request(request)
    response = TeXMLResponse()
    response.hangup()
    return Response(content=response.to_xml(), media_type="application/xml")


@router.post("/texml/voicemail/{tracking_id}")
@router.get("/texml/voicemail/{tracking_id}")
async def texml_voicemail(
    tracking_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """TeXML response to play voicemail message"""
    _validate_texml_request(request)
    if not tracking_id or not str(tracking_id).isdigit():
        raise HTTPException(status_code=400, detail="Invalid tracking ID")
    # Get call info
    result = db.execute(sa_text("""
        SELECT voicemail_message, voicemail_audio, client_name, lo_name, purpose
        FROM amd_outbound_calls
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id}).fetchone()

    response = TeXMLResponse()

    if not result:
        response.hangup()
        return Response(content=response.to_xml(), media_type="application/xml")

    voicemail_message, voicemail_audio, client_name, lo_name, purpose = result

    # Update status
    db.execute(sa_text("""
        UPDATE amd_outbound_calls
        SET status = 'voicemail_left', handling_method = 'voicemail_tts'
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id})
    db.commit()

    response.pause(length=1)

    if voicemail_audio:
        # Use pre-generated audio
        audio_url = f"{API_BASE_URL}/api/v1/voice/amd/audio/{tracking_id}"
        response.play(audio_url)
    else:
        # Fall back to TTS
        first_name = client_name.split()[0] if client_name else ""
        greeting = f"Hi {first_name}" if first_name else "Hi"
        message = voicemail_message or (
            f"{greeting}, this is Aria calling on behalf of {lo_name or 'your loan officer'} "
            f"at CMG Home Loans regarding {purpose or 'your loan'}. "
            f"Please give us a call back at your earliest convenience. "
            f"Thank you and have a great day!"
        )
        response.say(message, voice="Polly.Joanna")

    response.pause(length=1)
    response.hangup()

    logger.info(f"Playing voicemail for {tracking_id}")
    return Response(content=response.to_xml(), media_type="application/xml")


@router.post("/texml/connect-ai/{tracking_id}")
@router.get("/texml/connect-ai/{tracking_id}")
async def texml_connect_ai(
    tracking_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """TeXML response to connect call to AI via WebSocket stream"""
    _validate_texml_request(request)
    if not tracking_id or not str(tracking_id).isdigit():
        raise HTTPException(status_code=400, detail="Invalid tracking ID")
    # Get call info
    result = db.execute(sa_text("""
        SELECT client_name, to_number, purpose, lo_name
        FROM amd_outbound_calls
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id}).fetchone()

    response = TeXMLResponse()

    if not result:
        response.hangup()
        return Response(content=response.to_xml(), media_type="application/xml")

    client_name, to_number, purpose, lo_name = result

    # Update status
    db.execute(sa_text("""
        UPDATE amd_outbound_calls
        SET status = 'connected', handling_method = 'ai_stream'
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id})
    db.commit()

    # Get domain for WebSocket
    domain = os.getenv('PRODUCTION_DOMAIN') or os.getenv('RAILWAY_PUBLIC_DOMAIN') or 'api.perenniaai.com'

    # Connect to voice stream via WebSocket
    # Note: Telnyx uses the same Connect/Stream structure as TwiML
    ws_url = f"wss://{domain}/api/v1/voice/ws/voice-stream"

    connect_ctx = response.connect()
    connect_ctx.stream(
        url=ws_url,
        track="both_tracks",
    )
    connect_ctx.end_connect()

    logger.info(f"Connecting call {tracking_id} to AI stream")
    return Response(content=response.to_xml(), media_type="application/xml")


# =========================================================================
# Admin: Send calendar invite for a confirmed appointment
# =========================================================================

@router.post("/send-appointment-invite")
async def send_appointment_invite(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Manually send a calendar invite email for an appointment.

    Requires X-Internal-API-Key header for auth.
    Body: { "emails": [...], "date": "YYYY-MM-DD", "time": "HH:MM",
            "borrower_name": "...", "lo_name": "...", "appointment_type": "..." }
    """
    # Auth check
    api_key = request.headers.get("X-Internal-API-Key", "")
    expected = os.environ.get("INTERNAL_API_KEY", "")
    if not expected or not hmac.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.json()
    emails = body.get("emails", [])
    appt_date = body.get("date")
    appt_time = body.get("time")
    borrower_name = body.get("borrower_name", "there")
    lo_name = body.get("lo_name", "your loan officer")
    appt_type = body.get("appointment_type", "consultation")
    duration = body.get("duration_minutes", 30)

    # Resolve LO's company so the invite is signed from their brokerage,
    # never the platform vendor.
    org_id_body = body.get("organization_id")
    lo_company = body.get("lo_company") or ""
    if not lo_company and org_id_body:
        try:
            _co_row = db.execute(
                sa_text("SELECT name FROM organizations WHERE id = :oid"),
                {"oid": int(org_id_body)},
            ).fetchone()
            if _co_row and _co_row[0]:
                lo_company = _co_row[0]
        except Exception:
            pass
    lo_company = lo_company or f"{lo_name}'s team"

    if not emails or not appt_date or not appt_time:
        raise HTTPException(status_code=400, detail="emails, date, and time are required")

    if len(emails) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 email recipients allowed")

    import re as _re
    _email_re = _re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    for addr in emails:
        if not isinstance(addr, str) or not _email_re.match(addr):
            raise HTTPException(status_code=400, detail=f"Invalid email address: {addr}")

    try:
        start_dt = datetime.strptime(f"{appt_date} {appt_time}", "%Y-%m-%d %H:%M").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date/time: {appt_date} {appt_time}")

    from services.ics_generator import generate_ics_content
    from services.email_delivery_service import EmailDeliveryService
    from services.email_delivery_models import EmailAttachment

    ics_title = f"{appt_type.replace('_', ' ').title()} with {lo_name}"
    ics_content = generate_ics_content(
        appointment_title=ics_title,
        start_datetime=start_dt,
        duration_minutes=duration,
        attendee_email=emails[0],
        attendee_name=borrower_name,
        organizer_email="aria@perenniaai.com",
        organizer_name=f"Aria (on behalf of {lo_name})",
        description=(
            f"Scheduled via SMS by Aria AI assistant.\n"
            f"Appointment type: {appt_type.replace('_', ' ')}\n"
            f"Borrower: {borrower_name}"
        ),
    )

    ics_attachment = EmailAttachment(
        filename="appointment.ics",
        content_type="text/calendar; method=REQUEST",
        raw_content=ics_content.encode("utf-8"),
    )

    email_html = (
        f"<h2>Appointment Confirmed</h2>"
        f"<p>Hi {borrower_name},</p>"
        f"<p>Your <strong>{appt_type.replace('_', ' ')}</strong> "
        f"with <strong>{lo_name}</strong> has been confirmed.</p>"
        f"<p><strong>Date:</strong> {start_dt.strftime('%A, %B %d, %Y')}<br>"
        f"<strong>Time:</strong> {start_dt.strftime('%I:%M %p')}</p>"
        f"<p>A calendar invite is attached to this email. "
        f"Please add it to your calendar.</p>"
        f"<p>If you need to reschedule, just reply to the "
        f"text message thread or call us.</p>"
        f"<br><p>Best regards,<br>Aria, assistant to {lo_name}<br>{lo_company}</p>"
    )

    results = []

    # Try EmailDeliveryService first (SendGrid → MS Graph → Gmail waterfall)
    email_svc = EmailDeliveryService(db)
    all_failed = True
    for addr in emails:
        try:
            result = await email_svc.send_email(
                to=addr,
                subject=f"Appointment Confirmed: {ics_title}",
                html_body=email_html,
                from_name=f"Aria at {lo_company}",
                attachments=[ics_attachment],
                organization_id=body.get("organization_id"),
            )
            if result.success:
                all_failed = False
            results.append({
                "email": addr,
                "status": result.status.value,
                "provider": result.provider.value,
                "success": result.success,
                "message_id": result.message_id,
                "error": result.error,
            })
            logger.info("send-appointment-invite: sent to %s, status=%s", addr, result.status.value)
        except Exception as e:
            results.append({"email": addr, "status": "failed", "error": str(e)})
            logger.error("send-appointment-invite: failed for %s: %s", addr, e)

    # SMTP fallback if all providers failed
    if all_failed:
        smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASSWORD", "")
        if smtp_user and smtp_pass:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.base import MIMEBase
            from email import encoders

            results = []  # Reset results for SMTP attempt
            for addr in emails:
                try:
                    msg = MIMEMultipart("mixed")
                    msg["From"] = f"Aria at {lo_company} <{smtp_user}>"
                    msg["To"] = addr
                    msg["Subject"] = f"Appointment Confirmed: {ics_title}"

                    # HTML body
                    msg.attach(MIMEText(email_html, "html"))

                    # ICS attachment
                    ics_part = MIMEBase("text", "calendar", method="REQUEST")
                    ics_part.set_payload(ics_content.encode("utf-8"))
                    encoders.encode_base64(ics_part)
                    ics_part.add_header("Content-Disposition", "attachment", filename="appointment.ics")
                    msg.attach(ics_part)

                    with smtplib.SMTP(smtp_host, smtp_port) as server:
                        server.starttls()
                        server.login(smtp_user, smtp_pass)
                        server.sendmail(smtp_user, addr, msg.as_string())

                    results.append({
                        "email": addr,
                        "status": "sent",
                        "provider": "smtp",
                        "success": True,
                    })
                    logger.info("send-appointment-invite: SMTP sent to %s", addr)
                except Exception as e:
                    results.append({"email": addr, "status": "failed", "provider": "smtp", "error": str(e)})
                    logger.error("send-appointment-invite: SMTP failed for %s: %s", addr, e)

    return {"results": results, "appointment": {"date": appt_date, "time": appt_time, "type": appt_type}}
