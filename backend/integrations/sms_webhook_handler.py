# backend/integrations/sms_webhook_handler.py
# Telnyx webhook endpoint handler - verifies signatures and routes events

import hashlib
import hmac
import json
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from .sms_delivery_tracker import process_telnyx_webhook, update_delivery_status
from .sms_compliance_gate import handle_inbound_keyword
from .sms_retry_queue import mark_failed

logger = logging.getLogger(__name__)


def verify_telnyx_signature(
    payload_bytes: bytes,
    signature_header: str,
    timestamp_header: str,
    public_key: Optional[str] = None,
) -> bool:
    """
    Verify Telnyx webhook signature using HMAC-SHA256.
    Telnyx signs webhooks with: HMAC-SHA256(timestamp + '.' + payload_body, public_key)
    Returns True if signature is valid.
    """
    pub_key = public_key or os.environ.get("TELNYX_PUBLIC_KEY", "")
    if not pub_key:
        logger.warning("TELNYX_PUBLIC_KEY not set - skipping signature verification")
        return True  # Allow through if key not configured (dev mode)

    try:
        # Build the signed payload: timestamp + '.' + body
        signed_payload = (timestamp_header + "." + payload_bytes.decode("utf-8")).encode()
        expected_sig = hmac.new(
            pub_key.encode(),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_sig, signature_header)
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False


def handle_webhook(
    db: Session,
    payload: dict,
    raw_body: Optional[bytes] = None,
    signature: Optional[str] = None,
    timestamp: Optional[str] = None,
    skip_verification: bool = False,
) -> dict:
    """
    Main webhook handler - routes Telnyx webhook events to appropriate handlers.
    Returns dict with processing result.
    """
    # Signature verification
    if not skip_verification and raw_body and signature and timestamp:
        if not verify_telnyx_signature(raw_body, signature, timestamp):
            logger.warning("Telnyx webhook signature verification FAILED")
            return {"status": "rejected", "reason": "invalid_signature"}

    event_type = payload.get("data", {}).get("event_type", "")
    logger.info(f"Telnyx webhook received: {event_type}")

    # Route to handler based on event type
    if event_type in ("message.sent", "message.finalized"):
        result = process_telnyx_webhook(db, payload)
        return result

    if event_type == "message.received":
        return _handle_inbound_message(db, payload)

    if event_type == "message.failed":
        return _handle_message_failed(db, payload)

    logger.debug(f"Unhandled webhook event: {event_type}")
    return {"status": "ignored", "event_type": event_type}


def _handle_inbound_message(db: Session, payload: dict) -> dict:
    """
    Handle inbound SMS messages.
    Auto-processes STOP/START/HELP keywords.
    """
    try:
        record = payload.get("data", {}).get("payload", {})
        from_info = record.get("from", {})
        from_phone = from_info.get("phone_number", "")
        body = record.get("text", "").strip()

        if not from_phone or not body:
            return {"status": "ignored", "reason": "missing from_phone or body"}

        # Check for opt-out/opt-in keywords
        is_keyword, response_msg = handle_inbound_keyword(db, from_phone, body)

        if is_keyword:
            # Auto-respond to keyword
            _send_auto_response(from_phone, response_msg)
            return {
                "status": "processed",
                "action": "keyword_handled",
                "keyword": body.upper(),
                "from": from_phone,
            }

        # Store inbound message for conversation threading
        _store_inbound_message(db, from_phone, body, record)

        return {
            "status": "processed",
            "action": "inbound_stored",
            "from": from_phone,
        }
    except Exception as e:
        logger.error(f"Inbound message handler error: {e}")
        return {"status": "error", "reason": str(e)}


def _handle_message_failed(db: Session, payload: dict) -> dict:
    """Handle message.failed events - mark message as failed for retry."""
    try:
        record = payload.get("data", {}).get("payload", {})
        message_id = record.get("id")
        error_info = record.get("errors", [{}])
        error_code = str(error_info[0].get("code", "")) if error_info else ""
        error_title = error_info[0].get("title", "Unknown error") if error_info else "Unknown"

        if message_id:
            update_delivery_status(db, message_id, "failed", error_code=error_code)

        return {
            "status": "processed",
            "action": "marked_failed",
            "message_id": message_id,
            "error": error_title,
        }
    except Exception as e:
        logger.error(f"Failed message handler error: {e}")
        return {"status": "error", "reason": str(e)}


def _store_inbound_message(db: Session, from_phone: str, body: str, record: dict):
    """Store inbound message in conversation log."""
    try:
        from sqlalchemy import text
        db.execute(
            text("""
                INSERT INTO sms_conversations
                  (phone_number, direction, message_body, telnyx_message_id, received_at)
                VALUES (:phone, 'inbound', :body, :msg_id, NOW())
            """),
            {
                "phone": from_phone,
                "body": body[:500],
                "msg_id": record.get("id"),
            },
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to store inbound message: {e}")


def _send_auto_response(to_phone: str, message: str):
    """Send auto-response to keyword via Telnyx (fire-and-forget)."""
    try:
        import telnyx
        api_key = os.environ.get("TELNYX_API_KEY")
        from_phone = os.environ.get("TELNYX_PHONE_NUMBER")
        if not api_key or not from_phone:
            return
        telnyx.api_key = api_key
        telnyx.Message.create(
            from_=from_phone,
            to=to_phone,
            text=message,
        )
    except Exception as e:
        logger.error(f"Auto-response send failed: {e}")
