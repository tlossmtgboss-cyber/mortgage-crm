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
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from database import get_db
from telephony.providers.telnyx.webhooks import (
    parse_telnyx_webhook,
    validate_telnyx_webhook,
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

# Telnyx public key for webhook validation
TELNYX_PUBLIC_KEY = os.getenv("TELNYX_PUBLIC_KEY")


def _validate_texml_request(request: Request):
    """Validate TeXML callback requests using a shared secret or Telnyx signature."""
    api_key = request.headers.get("X-API-Key", "")
    expected = os.environ.get("TEXML_CALLBACK_SECRET", "")
    if not expected or not api_key or api_key != expected:
        raise HTTPException(status_code=403, detail="Invalid callback authentication")


# =============================================================================
# Webhook Validation
# =============================================================================

async def validate_webhook(request: Request) -> bool:
    """Validate incoming Telnyx webhook signature. Fail-closed when key not configured."""
    if not TELNYX_PUBLIC_KEY:
        logger.error("TELNYX_PUBLIC_KEY not configured — rejecting webhook")
        return False

    signature = request.headers.get("telnyx-signature-ed25519", "")
    timestamp = request.headers.get("telnyx-timestamp", "")
    if not signature or not timestamp:
        logger.warning("Missing Telnyx signature headers")
        return False

    body = await request.body()

    # Check timestamp freshness (reject webhooks older than 5 minutes)
    try:
        ts = int(timestamp)
        now = int(time.time())
        if abs(now - ts) > 300:  # 5 minutes
            logger.warning(f"Webhook timestamp too old: {ts} (now: {now})")
            return False
    except (ValueError, TypeError):
        pass

    return validate_telnyx_webhook(body, signature, timestamp, TELNYX_PUBLIC_KEY)


# =============================================================================
# Main Webhook Handler
# =============================================================================

@router.post("/webhook")
async def handle_telnyx_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Main Telnyx webhook handler.
    Routes events to appropriate handlers based on event type.
    """
    # Validate webhook signature
    if not await validate_webhook(request):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse webhook payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse Telnyx webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Webhook idempotency - skip if already processed
    webhook_event_id = payload.get("data", {}).get("id", "")
    if webhook_event_id:
        from database.models.communication import Activity
        existing = db.query(Activity).filter(
            Activity.content.contains(webhook_event_id)
        ).first()
        if existing:
            logger.info(f"Duplicate webhook {webhook_event_id}, skipping")
            return {"status": "duplicate", "event_id": webhook_event_id}

    # Parse into typed event
    event = parse_telnyx_webhook(payload)
    event_type = event.event_type

    logger.info(f"Telnyx webhook received: {event_type}")

    # Feature tier check - only process voice features for subscribed orgs
    # TODO: Full enforcement requires org lookup which is costly per webhook.
    # For now, all webhooks are processed. Add tier gating when org resolution
    # is available early in the pipeline without extra DB queries.

    # Route to appropriate handler
    if event_type == TelnyxEventType.CALL_MACHINE_DETECTION_ENDED:
        return await handle_amd_event(event, db)

    elif event_type == TelnyxEventType.CALL_ANSWERED:
        return await handle_call_answered(event, db)

    elif event_type == TelnyxEventType.CALL_HANGUP:
        return await handle_call_hangup(event, db)

    elif event_type in [TelnyxEventType.MESSAGE_SENT, TelnyxEventType.MESSAGE_FINALIZED]:
        return await handle_sms_status(event, db)

    elif event_type == TelnyxEventType.MESSAGE_RECEIVED:
        return await handle_inbound_sms(event, db)

    elif event_type == TelnyxEventType.CALL_RECORDING_SAVED:
        return await handle_recording_saved(event, db)

    else:
        logger.info(f"Unhandled Telnyx event type: {event_type}")
        return {"status": "acknowledged", "event_type": event_type}


# =============================================================================
# AMD (Answering Machine Detection) Handler
# =============================================================================

@router.post("/amd/{tracking_id}")
async def handle_amd_callback(
    tracking_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle Telnyx AMD callback for a specific call.

    Telnyx AMD result values:
    - "human": Human answered
    - "machine": Machine/voicemail detected
    - "not_sure": Could not determine
    - "unknown": Detection failed
    """
    if not await validate_webhook(request):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = await request.json()
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
                    "timestamp": datetime.utcnow().isoformat(),
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
    """Handle call recording saved event"""
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

    return {"status": "acknowledged", "recording_url": recording_url}


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
