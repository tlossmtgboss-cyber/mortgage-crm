"""
Telnyx Webhook Routes

Handles all Telnyx webhook callbacks including:
- Call Control events (initiated, ringing, answered, hangup)
- AMD (Answering Machine Detection) events
- SMS delivery status events
- Recording events
"""

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
    if not expected or not api_key or api_key != expected:
        raise HTTPException(status_code=403, detail="Invalid callback authentication")


# =============================================================================
# Inbound Call Routing — Telnyx → LiveKit SIP Bridge
# =============================================================================

async def _route_inbound_to_livekit(call_control_id: str, from_number: str, db: Session):
    """Route an inbound call to Aria via LiveKit SIP bridge.

    When an inbound call arrives on Telnyx, this function:
    1. Looks up the caller in the CRM (Lead by phone)
    2. Creates a LiveKit room with call metadata
    3. Transfers the Telnyx call into the LiveKit room via SIP
    """
    import requests as http_requests

    # Look up caller in CRM
    from database.models.lead_loan import Lead
    from integrations.sms_service import _to_e164

    normalized = _to_e164(from_number) or from_number
    lead = db.query(Lead).filter(Lead.phone == normalized).first()
    if not lead:
        lead = db.query(Lead).filter(Lead.phone == from_number).first()

    # Routing decision
    route = "aria"  # Default: Aria handles it
    if lead and getattr(lead, "ai_score", 0) and lead.ai_score >= 80:
        from database.models.core import User
        if lead.owner_id:
            lo = db.query(User).filter(User.id == lead.owner_id, User.is_active == True).first()
            if lo and lo.phone:
                # Hot lead + LO available = consider direct transfer
                # For now, always route to Aria (direct_lo requires calendar check)
                pass

    if route == "aria":
        # Create LiveKit room and bridge the Telnyx call into it
        livekit_url = os.getenv("LIVEKIT_URL", "")
        livekit_key = os.getenv("LIVEKIT_API_KEY", "")
        livekit_secret = os.getenv("LIVEKIT_API_SECRET", "")

        if not all([livekit_url, livekit_key, livekit_secret]):
            logger.warning("LiveKit not configured — cannot route inbound call to Aria")
            return

        try:
            from livekit import api as lk_api
            import json as _json

            lk = lk_api.LiveKitAPI(livekit_url, livekit_key, livekit_secret)

            room_name = f"aria-inbound-{call_control_id[:12]}"
            metadata = _json.dumps({
                "trigger": "inbound_call",
                "from_number": from_number,
                "lead_id": lead.id if lead else None,
                "borrower_name": (getattr(lead, "first_name", "") or getattr(lead, "name", "")) if lead else "",
            })

            await lk.room.create_room(
                lk_api.CreateRoomRequest(name=room_name, metadata=metadata)
            )

            # Bridge Telnyx call into LiveKit room as SIP participant
            sip_trunk_id = os.getenv("TELNYX_SIP_TRUNK_ID", "")
            sip_domain = os.getenv("LIVEKIT_SIP_DOMAIN", "")

            if sip_trunk_id and sip_domain:
                # Use Telnyx Call Control to SIP REFER into LiveKit
                telnyx_key = os.getenv("TELNYX_API_KEY", "")
                http_requests.post(
                    f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/transfer",
                    headers={
                        "Authorization": f"Bearer {telnyx_key}",
                        "Content-Type": "application/json",
                    },
                    json={"to": f"sip:{room_name}@{sip_domain}"},
                    timeout=10,
                )
                logger.info(f"Inbound call bridged to LiveKit room {room_name}")
            else:
                logger.warning("SIP trunk or domain not configured — cannot bridge call")
        except Exception as e:
            logger.error(f"Failed to route inbound call to LiveKit: {e}")


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

    logger.info(f"Telnyx webhook received: {event_type}")

    # Feature tier check - only process voice features for subscribed orgs
    # TODO: Full enforcement requires org lookup which is costly per webhook.
    # For now, all webhooks are processed. Add tier gating when org resolution
    # is available early in the pipeline without extra DB queries.

    # Route to appropriate handler
    try:
        if event_type == TelnyxEventType.CALL_INITIATED:
            # Inbound calls → route to Aria via LiveKit SIP bridge
            if hasattr(event, "direction") and event.direction == "incoming":
                if event.from_number and event.call_control_id:
                    try:
                        await _route_inbound_to_livekit(event.call_control_id, event.from_number, db)
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

    # Look up tracking ID by call_control_id
    result = db.execute(sa_text("""
        SELECT id, organization_id FROM amd_outbound_calls
        WHERE call_sid = :call_id
    """), {"call_id": call_control_id}).fetchone()

    if not result:
        logger.warning(f"No tracking record for call {call_control_id}")
        return {"status": "ignored"}

    tracking_id = result[0]
    # After fetching call record, capture org_id for downstream operations
    if result[1]:
        org_id = result[1]
        logger.info(f"AMD event for org_id={org_id}, tracking_id={tracking_id}")

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

    logger.info(f"Call answered: {call_control_id}")

    # Fetch call record to verify org_id context
    call_record = db.execute(sa_text("""
        SELECT id, organization_id FROM amd_outbound_calls
        WHERE call_sid = :call_id
    """), {"call_id": call_control_id}).fetchone()

    if call_record and call_record[1]:
        org_id = call_record[1]
        logger.info(f"Call answered for org_id={org_id}")

    # Update call status
    db.execute(sa_text("""
        UPDATE amd_outbound_calls
        SET status = 'answered'
        WHERE call_sid = :call_id
    """), {"call_id": call_control_id})
    db.commit()

    return {"status": "acknowledged", "call_id": call_control_id}


async def handle_call_hangup(event: TelnyxCallEvent, db: Session):
    """Handle call hangup event"""
    call_control_id = event.call_control_id
    hangup_cause = event.hangup_cause

    logger.info(f"Call hangup: {call_control_id}, cause: {hangup_cause}")

    # Fetch call record to verify org_id context
    call_record = db.execute(sa_text("""
        SELECT id, organization_id FROM amd_outbound_calls
        WHERE call_sid = :call_id
    """), {"call_id": call_control_id}).fetchone()

    if call_record and call_record[1]:
        org_id = call_record[1]
        logger.info(f"Call hangup for org_id={org_id}")

    # Update call status
    db.execute(sa_text("""
        UPDATE amd_outbound_calls
        SET status = 'completed',
            call_ended_at = NOW()
        WHERE call_sid = :call_id
    """), {"call_id": call_control_id})
    db.commit()

    return {"status": "acknowledged", "call_id": call_control_id, "cause": hangup_cause}


# =============================================================================
# SMS Event Handlers
# =============================================================================

async def handle_sms_status(event: TelnyxSMSEvent, db: Session):
    """Handle SMS delivery status update"""
    message_id = event.message_id
    status = event.status

    logger.info(f"SMS status update: {message_id} -> {status}")

    # Update SMS status in database if we're tracking it
    try:
        db.execute(sa_text("""
            UPDATE sms_messages
            SET delivery_status = :status,
                updated_at = NOW()
            WHERE provider_message_id = :message_id
        """), {"status": status, "message_id": message_id})
        db.commit()
    except Exception as e:
        db.rollback()
        logger.debug(f"SMS message not found in tracking table: {e}")

    return {"status": "acknowledged", "message_id": message_id}


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

    logger.info(f"Inbound SMS from {from_number}: {message_body[:50]}...")

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
                            direction, from_number, to_number, body,
                            provider, provider_message_id, status, created_at
                        ) VALUES (
                            'inbound', :from_number, :to_number, :body,
                            'telnyx', :message_id, 'received', NOW()
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
    # ======================================================================
    try:
        from services.prospect_reengagement_service import ProspectReEngagementService
        reengagement_svc = ProspectReEngagementService(db)
        reengagement_result = reengagement_svc.handle_reply(normalized_from, message_body)
        if reengagement_result is not None:
            # Store raw SMS for audit trail
            try:
                db.execute(sa_text("""
                    INSERT INTO sms_messages (
                        direction, from_number, to_number, body,
                        provider, provider_message_id, status, created_at
                    ) VALUES (
                        'inbound', :from_number, :to_number, :body,
                        'telnyx', :message_id, 'received', NOW()
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
        logger.error(f"AI re-engagement intercept error (falling through): {e}")

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
                        direction, from_number, to_number, body,
                        provider, provider_message_id, status, created_at
                    ) VALUES (
                        'inbound', :from_number, :to_number, :body,
                        'telnyx', :message_id, 'received', NOW()
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
        logger.error(f"ACO intercept error (falling through): {e}")

    # ======================================================================
    # Voice Scheduling Workflow Intercept
    # Check if this SMS is a reply to an active scheduling workflow.
    # CRITICAL: Resolve org_id from the "to" number (our Telnyx number) to
    # ensure tenant isolation. The "to" number belongs to a specific org's
    # user via user_twilio_config. Only falls back to cross-org lookup if
    # org resolution fails (e.g., phone number not in config table).
    # ======================================================================
    try:
        from services.voice_scheduling_workflow_service import VoiceSchedulingWorkflowService
        from services.scheduling_conversation_service import SchedulingConversationService

        wf_service = VoiceSchedulingWorkflowService(db)

        # Resolve org_id from the "to" number (our Telnyx number belongs to a specific org)
        workflow = None
        resolved_org_id = None
        if normalized_to:
            org_result = db.execute(
                sa_text(
                    "SELECT u.organization_id FROM user_twilio_config utc "
                    "JOIN users u ON u.id = utc.user_id "
                    "WHERE utc.telnyx_phone_number = :phone "
                    "AND u.organization_id IS NOT NULL "
                    "LIMIT 1"
                ),
                {"phone": normalized_to},
            ).fetchone()
            if org_result:
                resolved_org_id = org_result[0]
                workflow = wf_service.find_active_workflow_by_phone(normalized_from, resolved_org_id)

        # Fallback: cross-org lookup (less safe, but needed if phone number
        # config table doesn't have our "to" number mapped to an org)
        if not workflow and not resolved_org_id:
            logger.debug(
                f"Voice workflow intercept: could not resolve org for to_number={normalized_to}, "
                "trying cross-org fallback"
            )
            workflow = wf_service.find_active_workflow_by_phone_any_org(normalized_from)
            if workflow:
                # Use the workflow's own org_id for downstream tenant isolation
                resolved_org_id = workflow.organization_id

        if workflow and resolved_org_id:
            conv_service = SchedulingConversationService(db)
            conv_result = conv_service.handle_reply(
                workflow_id=workflow.id,
                sender_phone=normalized_from,
                message_body=message_body,
                organization_id=resolved_org_id,
            )
            if conv_result is not None:
                # Workflow handled this SMS — store for audit trail, skip intelligence queue
                try:
                    db.execute(sa_text("""
                        INSERT INTO sms_messages (
                            direction, from_number, to_number, body,
                            provider, provider_message_id, status, created_at
                        ) VALUES (
                            'inbound', :from_number, :to_number, :body,
                            'telnyx', :message_id, 'received', NOW()
                        )
                    """), {
                        "from_number": from_number,
                        "to_number": to_number,
                        "body": message_body,
                        "message_id": event.message_id,
                    })
                    db.commit()
                except Exception as e:
                    logger.error(f"Failed to store workflow-intercepted SMS: {e}")
                return {
                    "status": "received",
                    "handler": "voice_scheduling_workflow",
                    "workflow_id": workflow.id,
                }
    except ImportError:
        pass  # Voice scheduling workflow module not available
    except Exception as e:
        logger.error(f"Voice scheduling workflow intercept error (falling through): {e}")

    # Store inbound SMS in sms_messages table
    try:
        db.execute(sa_text("""
            INSERT INTO sms_messages (
                direction, from_number, to_number, body,
                provider, provider_message_id, status, created_at
            ) VALUES (
                'inbound', :from_number, :to_number, :body,
                'telnyx', :message_id, 'received', NOW()
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
    # Real-time notification: Alert loan officer via WebSocket
    # ==========================================================================

    try:
        # Look up which user owns this phone number / is assigned to the contact
        lo_match = db.execute(sa_text("""
            SELECT DISTINCT l.loan_officer_id
            FROM loans l
            WHERE l.borrower_phone = :phone
            AND l.loan_officer_id IS NOT NULL
            LIMIT 1
        """), {"phone": normalized_from}).fetchone()

        if not lo_match:
            # Try matching via leads table
            lo_match = db.execute(sa_text("""
                SELECT DISTINCT l.assigned_to
                FROM leads l
                WHERE l.phone = :phone
                AND l.assigned_to IS NOT NULL
                LIMIT 1
            """), {"phone": normalized_from}).fetchone()

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

    logger.info(f"Recording saved for {call_control_id}: {recording_url}")

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
        # -----------------------------------------------------------------
        org_id: Optional[int] = None
        loan_id: Optional[int] = None

        # Try amd_outbound_calls first (AMD / voicemail-drop calls)
        row = db.execute(sa_text("""
            SELECT organization_id, user_id, to_number
            FROM amd_outbound_calls
            WHERE call_sid = :call_id
            LIMIT 1
        """), {"call_id": call_control_id}).fetchone()

        user_id = None
        to_number = None
        if row:
            org_id = row[0]
            user_id = row[1]
            to_number = row[2]

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

        # Fallback: resolve org from user_id
        if not org_id and user_id:
            user_row = db.execute(sa_text("""
                SELECT organization_id FROM users WHERE id = :uid
            """), {"uid": user_id}).fetchone()
            if user_row:
                org_id = user_row[0]

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

        if not org_id:
            logger.warning(
                "Could not resolve organization_id for recording %s — skipping CI",
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
            f"{greeting}, this is Sam calling on behalf of {lo_name or 'your loan officer'} "
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
