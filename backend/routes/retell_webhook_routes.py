"""Retell AI Webhook Routes -- handles call completion events.

Dedicated webhook receiver for Retell AI call events. This supplements the
inline webhook handler in retell_routes.py (/webhooks/call-events) with a
standalone router that can be registered independently and uses the standard
webhook verification pattern from middleware.webhook_verification.

Endpoints:
    POST /api/v1/retell/webhook  - Receive Retell call events
"""
import logging
import os
import hmac
import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/retell", tags=["Retell Webhooks"])

RETELL_WEBHOOK_SECRET = os.getenv("RETELL_WEBHOOK_SECRET", "")


def verify_retell_signature(payload: bytes, signature: str) -> bool:
    """Verify HMAC-SHA256 signature from Retell webhook.

    Retell signs webhook payloads with the API key using HMAC-SHA256.
    The signature is sent in the X-Retell-Signature header.
    """
    if not RETELL_WEBHOOK_SECRET:
        logger.error("RETELL_WEBHOOK_SECRET not configured")
        return False
    expected = hmac.new(
        RETELL_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook")
async def retell_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Receive Retell AI webhook events.

    Events handled:
    - call_ended: Call has completed, update local records
    - call_analyzed: Post-call analysis available (transcript, sentiment, summary)

    Authentication: HMAC-SHA256 via X-Retell-Signature header when
    RETELL_WEBHOOK_SECRET is configured. Fails closed -- rejects all
    webhooks if the secret is set but the signature is missing/invalid.
    """
    body = await request.body()
    signature = request.headers.get("x-retell-signature", "")

    # Fail closed: reject if secret is configured but signature is invalid
    if RETELL_WEBHOOK_SECRET and not verify_retell_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Fail closed: reject if no secret is configured at all
    if not RETELL_WEBHOOK_SECRET:
        logger.error("RETELL_WEBHOOK_SECRET not configured -- rejecting webhook")
        raise HTTPException(status_code=503, detail="Webhook verification not configured")

    payload = json.loads(body)
    event_type = payload.get("event")

    logger.info(f"Retell webhook received: event={event_type}")

    # Return 200 immediately, process in background
    if event_type == "call_ended":
        background_tasks.add_task(_process_call_ended, payload)
    elif event_type == "call_analyzed":
        background_tasks.add_task(_process_call_analyzed, payload)
    else:
        logger.info(f"Retell webhook: unhandled event type '{event_type}'")

    return JSONResponse(status_code=200, content={"status": "received"})


async def _process_call_ended(payload: dict):
    """Process call_ended event -- update local call record with duration and status."""
    from database import SessionLocal

    db = SessionLocal()
    try:
        call_data = payload.get("data", {})
        call_id = call_data.get("call_id")
        duration_ms = call_data.get("call_duration_ms", 0)
        disconnection_reason = call_data.get("disconnection_reason")

        logger.info(
            f"Retell call ended: call_id={call_id}, duration={duration_ms}ms, "
            f"reason={disconnection_reason}"
        )

        from sqlalchemy import text

        # Update local call record
        db.execute(
            text("""
                UPDATE retell_calls
                SET status = 'completed',
                    ended_at = :now,
                    duration_seconds = :duration,
                    disconnection_reason = :reason
                WHERE retell_call_id = :call_id
            """),
            {
                "call_id": call_id,
                "now": datetime.now(timezone.utc),
                "duration": duration_ms / 1000 if duration_ms else 0,
                "reason": disconnection_reason,
            },
        )

        # Update lead last_contact_at if call is linked to a lead
        call_record = db.execute(
            text("SELECT lead_id FROM retell_calls WHERE retell_call_id = :call_id"),
            {"call_id": call_id},
        ).fetchone()

        if call_record and call_record.lead_id:
            db.execute(
                text("""
                    UPDATE leads
                    SET last_contact_at = :now, last_contact_method = 'phone'
                    WHERE id = :lead_id
                """),
                {"lead_id": call_record.lead_id, "now": datetime.now(timezone.utc)},
            )

        db.commit()
    except Exception as e:
        logger.error(f"Retell call_ended processing failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


async def _process_call_analyzed(payload: dict):
    """Process call_analyzed event -- store transcript, summary, and sentiment."""
    from database import SessionLocal

    db = SessionLocal()
    try:
        call_data = payload.get("data", {})
        call_id = call_data.get("call_id")
        transcript = call_data.get("transcript", "")
        analysis = call_data.get("call_analysis", {})

        logger.info(f"Retell call analyzed: call_id={call_id}")

        from sqlalchemy import text

        db.execute(
            text("""
                UPDATE retell_calls
                SET transcript = :transcript,
                    call_summary = :summary,
                    user_sentiment = :sentiment,
                    call_successful = :successful,
                    custom_analysis = :custom
                WHERE retell_call_id = :call_id
            """),
            {
                "call_id": call_id,
                "transcript": transcript,
                "summary": analysis.get("call_summary"),
                "sentiment": analysis.get("user_sentiment"),
                "successful": analysis.get("call_successful"),
                "custom": str(analysis.get("custom_analysis_data", {})),
            },
        )
        db.commit()

        # Trigger Call Intelligence processing if transcript is available
        if transcript:
            try:
                from services.call_intelligence.integration import handle_retell_call_ended

                ci_result = await handle_retell_call_ended(
                    db=db,
                    call_id=call_id,
                    call_data=call_data,
                )
                if ci_result and ci_result.get("success"):
                    logger.info(
                        f"Call Intelligence processed {call_id}: "
                        f"{ci_result.get('extractions_count', 0)} extractions"
                    )
                else:
                    logger.warning(
                        f"Call Intelligence failed for {call_id}: "
                        f"{ci_result.get('error', 'Unknown') if ci_result else 'No result'}"
                    )
            except ImportError:
                logger.debug("Call Intelligence not available, skipping")
            except Exception as ci_error:
                logger.error(f"Call Intelligence error for {call_id}: {ci_error}", exc_info=True)

    except Exception as e:
        logger.error(f"Retell call_analyzed processing failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()
