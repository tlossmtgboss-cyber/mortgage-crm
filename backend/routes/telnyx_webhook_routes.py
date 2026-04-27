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

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from database import get_db, SessionLocal
from middleware.webhook_verification import require_telnyx_webhook

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
    """
    import requests as http_requests

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

    # Step 1: Answer the inbound call immediately
    try:
        resp = http_requests.post(f"{base_url}/answer", headers=headers, json={}, timeout=10)
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
            http_requests.post(
                f"{base_url}/speak",
                headers=headers,
                json={
                    "payload": "I'm sorry, I'm unable to connect you right now. Please try again shortly.",
                    "voice": "female",
                    "language": "en-US",
                },
                timeout=10,
            )
            await asyncio.sleep(4)
            http_requests.post(f"{base_url}/hangup", headers=headers, json={}, timeout=10)
        except Exception:
            pass
        return

    try:
        resp = http_requests.post(
            f"{base_url}/transfer",
            headers=headers,
            json={
                "to": transfer_to,
                "from": to_number,
                "timeout_secs": 30,
            },
            timeout=10,
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
            http_requests.post(
                f"{base_url}/speak",
                headers=headers,
                json={
                    "payload": "I'm sorry, I'm unable to connect you right now. Please try again shortly.",
                    "voice": "female",
                    "language": "en-US",
                },
                timeout=10,
            )
            await asyncio.sleep(4)
            http_requests.post(f"{base_url}/hangup", headers=headers, json={}, timeout=10)
    except Exception as e:
        logger.error(f"[AriaInbound] Transfer failed: {e}", exc_info=True)


# =============================================================================
# Main Webhook Handler
# =============================================================================

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

    # Webhook idempotency — use WebhookIdempotencyRecord (database-backed)
    # instead of Activity.content.contains() which was unreliable and slow
    webhook_event_id = payload.get("data", {}).get("id", "")
    event_type_raw = payload.get("data", {}).get("event_type", "")
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

        # Insert a 'processing' record (race-condition safe via unique constraint)
        try:
            db.add(WebhookIdempotencyRecord(
                idempotency_key=idem_key,
                provider="telnyx",
                event_type=event_type_raw,
                event_id=webhook_event_id,
                status="processing",
            ))
            db.flush()
        except Exception:
            # IntegrityError = another worker already inserted — treat as duplicate
            db.rollback()
            logger.info(f"Duplicate webhook (race) {webhook_event_id}, skipping")
            return {"status": "duplicate", "event_id": webhook_event_id}
    else:
        idem_key = None

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


async def handle_inbound_sms(event: TelnyxSMSEvent, db: Session):
    """Handle inbound SMS message with full workflow triggers."""
    from_number = event.from_number
    to_number = event.to_number
    message_body = event.text
    normalized_from = _normalize_phone(from_number)
    normalized_to = _normalize_phone(to_number)

    logger.info(
        "Inbound SMS from ...%s to ...%s: %s...",
        from_number[-4:] if from_number else "?",
        to_number[-4:] if to_number else "?",
        (message_body or "")[:50],
    )

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

        # Query with org scope when available for tenant isolation
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
            _aria_conv = db.execute(sa_text("""
                SELECT id, organization_id, current_stage, context_data
                FROM sms_ai_conversations
                WHERE phone_number = :phone AND status = 'active'
                ORDER BY last_message_at DESC NULLS LAST
                LIMIT 1
            """), {"phone": normalized_from}).fetchone()

        if _aria_conv:
            _aria_conv_id = _aria_conv[0]
            _aria_org_id = _aria_conv[1]
            _aria_stage = _aria_conv[2]
            _aria_context = _aria_conv[3] or {}
            logger.info(
                "aria_sms_intercept: matched conversation_id=%s, phone=...%s, stage=%s",
                _aria_conv_id, normalized_from[-4:], _aria_stage,
            )

            # Store inbound message in conversation
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

            # Fetch conversation history for context
            _history_rows = db.execute(sa_text("""
                SELECT direction, content FROM sms_ai_conversation_messages
                WHERE conversation_id = :conv_id
                ORDER BY created_at ASC
            """), {"conv_id": _aria_conv_id}).fetchall()

            _messages = []
            for row in _history_rows:
                role = "user" if row[0] == "inbound" else "assistant"
                _messages.append({"role": role, "content": row[1]})
            # Add current message if not already in history
            if not _messages or _messages[-1].get("content") != message_body:
                _messages.append({"role": "user", "content": message_body})

            # Generate AI reply via Claude
            _reply_text = None
            try:
                import anthropic as _anthropic
                _client = _anthropic.Anthropic(timeout=15.0)

                borrower_name = _aria_context.get("borrower_name", "there")
                lo_name = _aria_context.get("lo_name", "your loan officer")
                appt_type = _aria_context.get("appointment_type", "consultation")

                _system = (
                    f"You are Aria, an AI assistant for {lo_name} at Perennia AI, "
                    f"a mortgage lending company. You are texting {borrower_name} "
                    f"to schedule a {appt_type}.\n\n"
                    "RULES:\n"
                    "- Keep responses under 160 characters (1 SMS segment)\n"
                    "- Be warm and professional\n"
                    "- When the borrower confirms a time, acknowledge it and confirm the appointment\n"
                    "- If they suggest a different time, accommodate it\n"
                    "- Do NOT quote rates, fees, or loan terms\n"
                    "- If they say stop or opt out, respect it immediately\n"
                    "- Do NOT promise to send calendar invites or emails — the system sends those automatically\n"
                    "- When confirming, just say the appointment is confirmed for the date/time\n"
                    f"- Current stage: {_aria_stage}"
                )

                _resp = _client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=200,
                    system=_system,
                    messages=_messages,
                )
                if _resp.content:
                    _reply_text = _resp.content[0].text.strip()
            except Exception as e:
                logger.error("aria_sms_intercept: Claude response generation failed: %s", e)

            if _reply_text:
                # Store outbound message and update conversation state
                try:
                    db.execute(sa_text("""
                        INSERT INTO sms_ai_conversation_messages
                        (id, conversation_id, direction, content, ai_generated, created_at)
                        VALUES (:id, :conv_id, 'outbound', :content, true, NOW())
                    """), {
                        "id": str(_uuid_mod.uuid4()),
                        "conv_id": _aria_conv_id,
                        "content": _reply_text,
                    })
                    db.execute(sa_text("""
                        UPDATE sms_ai_conversations
                        SET last_message_at = NOW(),
                            message_count = COALESCE(message_count, 0) + 2,
                            current_stage = CASE
                                WHEN current_stage = 'scheduling' THEN 'confirming'
                                ELSE current_stage
                            END
                        WHERE id = :conv_id
                    """), {"conv_id": _aria_conv_id})
                    db.commit()
                except Exception as e:
                    db.rollback()
                    logger.error("aria_sms_intercept: store reply/update state failed: %s", e)

                # Send reply via Telnyx
                try:
                    import requests as _req
                    _telnyx_key = os.environ.get("TELNYX_API_KEY", "")
                    _telnyx_from = os.environ.get(
                        "TELNYX_FROM_NUMBER",
                        os.environ.get("TELNYX_PHONE_NUMBER", ""),
                    )
                    _telnyx_profile = os.environ.get(
                        "TELNYX_MESSAGING_PROFILE_ID", "",
                    )
                    if _telnyx_key:
                        _send_resp = _req.post(
                            "https://api.telnyx.com/v2/messages",
                            headers={
                                "Authorization": f"Bearer {_telnyx_key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "from": _telnyx_from,
                                "to": normalized_from,
                                "text": _reply_text,
                                "messaging_profile_id": _telnyx_profile,
                            },
                            timeout=10,
                        )
                        logger.info(
                            "aria_sms_intercept: reply sent, status=%d, to=...%s, text='%s'",
                            _send_resp.status_code, normalized_from[-4:], _reply_text[:50],
                        )
                    else:
                        logger.error("aria_sms_intercept: TELNYX_API_KEY not set")
                except Exception as e:
                    logger.error("aria_sms_intercept: send reply failed: %s", e)

                # ==========================================================
                # Calendar invite email — fires when appointment is confirmed
                # ==========================================================
                try:
                    _full_convo = "\n".join(
                        f"{'Borrower' if m['role'] == 'user' else 'Aria'}: {m['content']}"
                        for m in _messages
                    )
                    # Add the reply we just generated
                    _full_convo += f"\nAria: {_reply_text}"

                    _extract_resp = _client.messages.create(
                        model="claude-haiku-4-5-20251001",
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
                    logger.info("aria_sms_intercept: appointment extraction: %s", _extract_text[:200])

                    if "CONFIRMED: yes" in _extract_text.lower() or "CONFIRMED:yes" in _extract_text.lower():
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
                        _ctx_emails = _aria_context.get("attendee_emails", [])
                        if isinstance(_ctx_emails, str):
                            _ctx_emails = [e.strip() for e in _ctx_emails.split(",") if "@" in e]
                        for _ce in _ctx_emails:
                            if _ce not in _appt_emails:
                                _appt_emails.append(_ce)

                        if _appt_date and _appt_time and _appt_emails:
                            from datetime import timedelta
                            try:
                                _start_dt = datetime.strptime(
                                    f"{_appt_date} {_appt_time}", "%Y-%m-%d %H:%M"
                                ).replace(tzinfo=timezone.utc)
                            except ValueError:
                                _start_dt = None
                                logger.warning(
                                    "aria_sms_intercept: could not parse date/time: %s %s",
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
                                    f"<br><p>Best regards,<br>Aria — Perennia AI</p>"
                                )

                                # Send to all collected emails
                                async def _send_invite():
                                    _all_failed = True
                                    _email_svc = EmailDeliveryService(db)
                                    for _addr in _appt_emails:
                                        try:
                                            _result = await _email_svc.send_email(
                                                to=_addr,
                                                subject=f"Appointment Confirmed: {_ics_title}",
                                                html_body=_email_html,
                                                from_name="Aria — Perennia AI",
                                                attachments=[_ics_attachment],
                                                organization_id=str(_aria_org_id) if _aria_org_id else None,
                                            )
                                            if _result.success:
                                                _all_failed = False
                                            logger.info(
                                                "aria_sms_intercept: calendar invite sent to %s, status=%s, provider=%s",
                                                _addr, _result.status.value, _result.provider.value,
                                            )
                                        except Exception as _email_err:
                                            logger.error(
                                                "aria_sms_intercept: calendar invite to %s failed: %s",
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
                                                    _msg["From"] = f"Aria — Perennia AI <{_smtp_user}>"
                                                    _msg["To"] = _addr
                                                    _msg["Subject"] = f"Appointment Confirmed: {_ics_title}"
                                                    _msg.attach(_MT(_email_html, "html"))
                                                    _ics_part = _MB("text", "calendar", method="REQUEST")
                                                    _ics_part.set_payload(_ics_content.encode("utf-8"))
                                                    _enc.encode_base64(_ics_part)
                                                    _ics_part.add_header("Content-Disposition", "attachment", filename="appointment.ics")
                                                    _msg.attach(_ics_part)
                                                    with _smtplib.SMTP(_smtp_host, _smtp_port) as _srv:
                                                        _srv.starttls()
                                                        _srv.login(_smtp_user, _smtp_pass)
                                                        _srv.sendmail(_smtp_user, _addr, _msg.as_string())
                                                    logger.info("aria_sms_intercept: SMTP calendar invite sent to %s", _addr)
                                                except Exception as _smtp_err:
                                                    logger.error("aria_sms_intercept: SMTP invite to %s failed: %s", _addr, _smtp_err)

                                # We're inside an async handler — schedule the send
                                await _send_invite()

                                # Update conversation to confirmed
                                try:
                                    db.execute(sa_text("""
                                        UPDATE sms_ai_conversations
                                        SET current_stage = 'confirmed',
                                            context_data = context_data || CAST(:extra AS jsonb)
                                        WHERE id = :conv_id
                                    """), {
                                        "conv_id": _aria_conv_id,
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
                                        "aria_sms_intercept: update confirmed stage failed: %s",
                                        _db_err,
                                    )

                                logger.info(
                                    "aria_sms_intercept: calendar invite sent to %s for %s %s",
                                    _appt_emails, _appt_date, _appt_time,
                                )
                        elif _appt_date and _appt_time:
                            logger.info(
                                "aria_sms_intercept: appointment confirmed (%s %s) but no emails in conversation",
                                _appt_date, _appt_time,
                            )
                except Exception as e:
                    logger.error("aria_sms_intercept: calendar invite flow failed: %s", e)

            # Store inbound for audit trail
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

            return {
                "status": "received",
                "handler": "aria_sms_conversation",
                "conversation_id": str(_aria_conv_id),
                "reply_sent": bool(_reply_text),
            }
    except Exception as e:
        db.rollback()
        logger.error(f"Aria SMS conversation intercept error (falling through): {e}")

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
        logger.info(f"Telnyx SMS queued for intelligence processing: id={intelligence_queue_id}")
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
            # Final fallback: use the default (first) organization
            _org_row = db.execute(sa_text("""
                SELECT id FROM organizations ORDER BY id LIMIT 1
            """)).fetchone()
            if _org_row:
                logger.info(
                    "Inbound SMS tenant resolved via fallback to default org_id=%s",
                    _org_row[0],
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

    try:
        import uuid as _uuid
        _panel_id = str(_uuid.uuid4())
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
        logger.info(f"Inbound SMS stored in sms_panel_messages for phone=...{normalized_from[-4:]}, contact_id={_inbound_contact_id}")
    except Exception as e:
        logger.warning(f"Failed to store inbound SMS in sms_panel_messages: {e}")
        db.rollback()

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
        f"<br><p>Best regards,<br>Aria — Perennia AI</p>"
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
                from_name="Aria — Perennia AI",
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
                    msg["From"] = f"Aria — Perennia AI <{smtp_user}>"
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
