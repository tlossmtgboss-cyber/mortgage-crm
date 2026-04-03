# backend/integrations/sms_webhook_handler.py
# Telnyx webhook endpoint handler - verifies Ed25519 signatures and routes events

import base64
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from .sms_delivery_tracker import process_telnyx_webhook, update_delivery_status
from .sms_compliance_gate import handle_inbound_keyword

logger = logging.getLogger(__name__)


def verify_telnyx_signature(
    payload_bytes: bytes,
    signature_header: str,
    timestamp_header: str,
    public_key: Optional[str] = None,
    tolerance: int = 300,
) -> bool:
    """
    Verify Telnyx webhook signature using Ed25519 (API V2).

    Telnyx signs every webhook with Ed25519 public-key cryptography.
    Headers: telnyx-signature-ed25519, telnyx-timestamp.
    Signed payload: {timestamp}|{json_payload}

    Args:
        payload_bytes: Raw request body bytes.
        signature_header: Value of telnyx-signature-ed25519 header (base64).
        timestamp_header: Value of telnyx-timestamp header (unix seconds).
        public_key: Ed25519 public key (base64). Falls back to TELNYX_PUBLIC_KEY env.
        tolerance: Max age in seconds before rejecting stale webhooks (default 5 min).

    Returns True if signature is valid.
    """
    pub_key = public_key or os.environ.get("TELNYX_PUBLIC_KEY", "")
    if not pub_key:
        env = os.environ.get("RAILWAY_ENVIRONMENT", os.environ.get("ENV", "development"))
        if env in ("production", "staging"):
            logger.error("TELNYX_PUBLIC_KEY not set in production - rejecting webhook")
            return False
        logger.warning("TELNYX_PUBLIC_KEY not set - skipping verification (dev mode)")
        return True

    # Try using the telnyx SDK's built-in verification first
    try:
        import telnyx
        telnyx.Webhook.construct_event(
            payload_bytes.decode("utf-8"),
            signature_header,
            timestamp_header,
            tolerance=tolerance,
        )
        return True
    except telnyx.error.SignatureVerificationError:
        logger.warning("Telnyx webhook signature verification FAILED (SDK)")
        return False
    except ImportError:
        pass  # telnyx SDK not available, fall through to manual verification
    except Exception as e:
        logger.debug(f"SDK verification failed, trying manual: {e}")

    # Manual Ed25519 verification fallback
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        import time

        # Reject stale webhooks
        try:
            ts = int(timestamp_header)
            if abs(time.time() - ts) > tolerance:
                logger.warning("Telnyx webhook timestamp outside tolerance window")
                return False
        except (ValueError, TypeError):
            logger.warning("Invalid telnyx-timestamp header")
            return False

        # Build signed payload: timestamp|body
        signed_payload = f"{timestamp_header}|{payload_bytes.decode('utf-8')}".encode()

        # Decode the base64 public key and signature
        pub_key_bytes = base64.b64decode(pub_key)
        signature_bytes = base64.b64decode(signature_header)

        # Load the Ed25519 public key
        public_key_obj = Ed25519PublicKey.from_public_bytes(pub_key_bytes)
        public_key_obj.verify(signature_bytes, signed_payload)
        return True
    except Exception as e:
        logger.error(f"Ed25519 signature verification error: {e}")
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
    # Signature verification — fail-closed when headers are present
    if not skip_verification:
        if raw_body and signature and timestamp:
            if not verify_telnyx_signature(raw_body, signature, timestamp):
                logger.warning("Telnyx webhook signature verification FAILED")
                return {"status": "rejected", "reason": "invalid_signature"}
        elif raw_body:
            # Headers missing but body present — reject in production
            env = os.environ.get("RAILWAY_ENVIRONMENT", os.environ.get("ENV", "development"))
            if env in ("production", "staging"):
                logger.warning("Webhook missing signature headers — rejecting")
                return {"status": "rejected", "reason": "missing_signature_headers"}

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
            # Commit the opt-out/opt-in DB changes (compliance gate only flushes)
            committed = False
            try:
                db.commit()
                committed = True
            except Exception as commit_err:
                db.rollback()
                logger.error(f"Failed to commit keyword action: {commit_err}")
            # Only auto-respond if opt-out/opt-in was persisted successfully
            if committed:
                _send_auto_response(from_phone, response_msg)
            else:
                logger.error(f"Skipping auto-response — keyword action not persisted for {from_phone}")
            return {
                "status": "processed" if committed else "error",
                "action": "keyword_handled" if committed else "commit_failed",
                "keyword": body.upper(),
                "from": from_phone,
            }

        # Store inbound message for conversation threading
        _store_inbound_message(db, from_phone, body, record)
        # Also store in panel messages table for the two-way SMS panel
        _store_panel_inbound(db, from_phone, body, record.get("id", ""))
        try:
            db.commit()
        except Exception as commit_err:
            db.rollback()
            logger.error(f"Failed to commit inbound message: {commit_err}")

        # Push to WebSocket clients watching this phone number
        try:
            import asyncio
            from routes.sms_conversation_routes import notify_inbound_sms
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(notify_inbound_sms(from_phone, body, record.get("id", "")))
            else:
                loop.run_until_complete(notify_inbound_sms(from_phone, body, record.get("id", "")))
        except Exception as ws_err:
            logger.debug(f"WebSocket push skipped: {ws_err}")

        return {
            "status": "processed",
            "action": "inbound_stored",
            "from": from_phone,
        }
    except Exception as e:
        logger.error(f"Inbound message handler error: {e}")
        return {"status": "error", "reason": "inbound_processing_failed"}


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
        return {"status": "error", "reason": "failed_event_processing_error"}


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
        db.flush()
    except Exception as e:
        logger.error(f"Failed to store inbound message: {e}")


def _store_panel_inbound(db: Session, from_phone: str, body: str, telnyx_msg_id: str):
    """Store inbound message in the sms_panel_messages table for the two-way panel."""
    try:
        import uuid
        from sqlalchemy import text as _text
        db.execute(
            _text("""
                INSERT INTO sms_panel_messages
                  (id, phone, direction, body, sender_name, status, telnyx_message_id, created_at)
                VALUES (:id, :phone, 'inbound', :body, 'Customer', 'delivered', :msg_id, NOW())
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": telnyx_msg_id or str(uuid.uuid4()),
                "phone": from_phone,
                "body": body[:2000],
                "msg_id": telnyx_msg_id,
            },
        )
        db.flush()
    except Exception as e:
        logger.debug(f"Panel inbound store skipped: {e}")


def _send_auto_response(to_phone: str, message: str):
    """Send auto-response to keyword via Telnyx REST API (fire-and-forget).

    Uses direct HTTP POST instead of setting telnyx.api_key globally
    to avoid race conditions in multi-worker deployments.
    """
    try:
        import requests
        api_key = os.environ.get("TELNYX_API_KEY")
        from_phone = os.environ.get("TELNYX_PHONE_NUMBER")
        profile_id = os.environ.get("TELNYX_MESSAGING_PROFILE_ID", "")
        if not api_key or not from_phone:
            return
        requests.post(
            "https://api.telnyx.com/v2/messages",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_phone,
                "to": to_phone,
                "text": message,
                "messaging_profile_id": profile_id,
            },
            timeout=10,
        )
    except Exception as e:
        logger.error(f"Auto-response send failed: {e}")
