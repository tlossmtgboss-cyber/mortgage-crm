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
    env = os.environ.get("RAILWAY_ENVIRONMENT", os.environ.get("ENV", "development"))
    if not pub_key:
        if env == "production":
            logger.error("TELNYX_PUBLIC_KEY not set in production — rejecting webhook")
            return False
        elif env == "staging":
            logger.critical(
                "TELNYX_PUBLIC_KEY not set in %s — webhook signatures NOT verified", env
            )
            return True
        else:
            logger.warning(
                "TELNYX_PUBLIC_KEY not set — skipping verification (env=%s)", env
            )
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
    Handle inbound SMS/MMS messages.
    Auto-processes STOP/START/HELP keywords.
    Downloads and persists MMS media attachments to S3.
    """
    try:
        record = payload.get("data", {}).get("payload", {})
        from_info = record.get("from", {})
        from_phone = from_info.get("phone_number", "")
        body = record.get("text", "").strip()

        if not from_phone and not body:
            return {"status": "ignored", "reason": "missing from_phone or body"}

        # ── MMS media handling ───────────────────────────────────────────
        # Telnyx message.received payloads include a "media" array for MMS:
        #   [{"url": "https://...", "content_type": "image/jpeg", ...}, ...]
        # These URLs are temporary — download and persist to S3 immediately.
        media_items = record.get("media", []) or []
        s3_keys = []
        media_urls = []
        if media_items:
            try:
                from utils.media_storage import get_media_storage
                storage = get_media_storage()
                for idx, item in enumerate(media_items):
                    media_url = item.get("url", "")
                    content_type = item.get("content_type", "application/octet-stream")
                    if not media_url:
                        continue
                    media_urls.append(media_url)
                    # Build a sensible filename from content type
                    import mimetypes as _mt
                    ext = _mt.guess_extension(content_type) or ".bin"
                    filename = f"inbound_{idx}{ext}"
                    s3_key = storage.store_from_url(media_url, filename)
                    if s3_key:
                        s3_keys.append(s3_key)
                    else:
                        logger.warning("Failed to persist MMS media %d to S3", idx)
            except Exception as media_err:
                logger.error(f"MMS media persistence error: {media_err}")

        # Allow MMS-only messages (no body text, only media)
        if not from_phone:
            return {"status": "ignored", "reason": "missing from_phone"}

        # Check for opt-out/opt-in keywords
        if body:
            is_keyword, response_msg = handle_inbound_keyword(db, from_phone, body)
        else:
            is_keyword = False
            response_msg = ""

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
                logger.error(f"Skipping auto-response — keyword action not persisted for ...{from_phone[-4:] if from_phone else '????'}")
            return {
                "status": "processed" if committed else "error",
                "action": "keyword_handled" if committed else "commit_failed",
                "keyword": body.upper(),
                "from": from_phone,
            }

        # ── Campaign reply routing ───────────────────────────────────────
        # Check if this inbound message is a reply to an Aria campaign.
        # Must run AFTER keyword handling (STOP/START always takes priority)
        # but BEFORE normal inbound storage / auto-responder.
        try:
            from aria.campaigns.reply_handler import CampaignReplyHandler
            import asyncio as _asyncio

            # Resolve organization_id for this phone number
            _org_id = None
            try:
                from sqlalchemy import text as _org_text
                _org_row = db.execute(
                    _org_text(
                        "SELECT organization_id FROM verified_caller_ids "
                        "WHERE phone_number = :phone AND organization_id IS NOT NULL LIMIT 1"
                    ),
                    {"phone": from_phone},
                ).fetchone()
                if _org_row:
                    _org_id = _org_row[0]
            except Exception as _exc:  # noqa: BLE001
                pass

            _handler = CampaignReplyHandler()
            _loop = _asyncio.get_event_loop()
            if _loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    campaign_result = pool.submit(
                        _asyncio.run,
                        _handler.handle_inbound(
                            from_phone=from_phone,
                            message_body=body,
                            org_id=str(_org_id or ""),
                        )
                    ).result(timeout=10)
            else:
                campaign_result = _asyncio.run(_handler.handle_inbound(
                    from_phone=from_phone,
                    message_body=body,
                    org_id=str(_org_id or ""),
                ))
            if campaign_result:
                if campaign_result.get("response"):
                    from aria.tools.communication_tools import CommunicationTools
                    _comms = CommunicationTools()
                    if _loop.is_running():
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            pool.submit(
                                _asyncio.run,
                                _comms.send_sms(
                                    to_phone=from_phone,
                                    from_user={"id": campaign_result.get("lo_user_id", "")},
                                    message=campaign_result["response"],
                                    org_id=str(_org_id or ""),
                                )
                            ).result(timeout=10)
                    else:
                        _asyncio.run(_comms.send_sms(
                            to_phone=from_phone,
                            from_user={"id": campaign_result.get("lo_user_id", "")},
                            message=campaign_result["response"],
                            org_id=str(_org_id or ""),
                        ))
                logger.info("Campaign reply handled: %s -> %s", from_phone, campaign_result.get("action"))
                return campaign_result
        except ImportError:
            pass
        except Exception as e:
            logger.warning("Campaign reply check failed (non-blocking): %s", e)

        # Store inbound message for conversation threading
        _store_inbound_message(db, from_phone, body, record)
        # Also store in panel messages table for the two-way SMS panel (with S3 keys)
        _store_panel_inbound(db, from_phone, body, record.get("id", ""),
                             media_urls=media_urls, media_s3_keys=s3_keys)
        try:
            db.commit()
        except Exception as commit_err:
            db.rollback()
            logger.error(f"Failed to commit inbound message: {commit_err}")

        # Create SMS task for follow-up
        telnyx_msg_id = record.get("id", "")
        try:
            from services.sms_auto_responder import handle_inbound_sms
            task_result = handle_inbound_sms(
                db=db,
                phone_number=from_phone,
                message_text=body,
                telnyx_message_id=telnyx_msg_id,
                organization_id=None,  # Will be resolved inside the service
                contact_name=None,  # Will be resolved from lead lookup
            )
            logger.info(
                "SMS task created: id=%s auto=%s confidence=%.0f",
                task_result.get("task_id"),
                task_result.get("auto_responded"),
                task_result.get("ai_confidence", 0),
            )
        except Exception as task_err:
            logger.error(
                "SMS task creation FAILED — inbound message needs manual review: "
                "telnyx_message_id=%s from=%s error=%s",
                telnyx_msg_id,
                from_phone,
                task_err,
            )
            # Flag the stored message so it can be found in manual review
            try:
                from sqlalchemy import text as _text
                db.execute(
                    _text("""
                        UPDATE sms_panel_messages
                        SET status = 'needs_review'
                        WHERE telnyx_message_id = :msg_id
                    """),
                    {"msg_id": telnyx_msg_id},
                )
                db.commit()
            except Exception as flag_err:
                logger.error(
                    "Failed to flag message for review: telnyx_message_id=%s error=%s",
                    telnyx_msg_id,
                    flag_err,
                )

        # Push to WebSocket clients watching this phone number
        try:
            import asyncio
            from routes.sms_conversation_routes import notify_inbound_sms
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(
                    notify_inbound_sms(from_phone, body, record.get("id", ""))
                )
        except Exception as ws_err:
            logger.debug(f"WebSocket push skipped: {ws_err}")

        return {
            "status": "processed",
            "action": "inbound_stored",
            "from": from_phone,
            "media_count": len(media_items),
            "media_persisted": len(s3_keys),
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


def _store_panel_inbound(
    db: Session,
    from_phone: str,
    body: str,
    telnyx_msg_id: str,
    media_urls: list = None,
    media_s3_keys: list = None,
    organization_id: int = None,
):
    """Store inbound message in the sms_panel_messages table for the two-way panel.

    Includes MMS media URLs and their persisted S3 keys so the panel can
    display attachments even after Telnyx's temporary URLs expire.
    """
    try:
        import json
        import uuid
        from sqlalchemy import text as _text

        media_urls_json = json.dumps(media_urls) if media_urls else "[]"
        s3_keys_json = json.dumps(media_s3_keys) if media_s3_keys else "[]"

        org_id = organization_id
        if not org_id:
            try:
                row = db.execute(
                    _text("SELECT organization_id FROM verified_caller_ids WHERE phone_number = :phone AND organization_id IS NOT NULL LIMIT 1"),
                    {"phone": from_phone},
                ).fetchone()
                if row:
                    org_id = row[0]
            except Exception as _exc:  # noqa: BLE001
                pass

        db.execute(
            _text("""
                INSERT INTO sms_panel_messages
                  (id, phone, organization_id, direction, body, sender_name, status,
                   telnyx_message_id, media_urls, media_s3_keys, created_at)
                VALUES (:id, :phone, :org_id, 'inbound', :body, 'Customer', 'delivered',
                        :msg_id, :media_urls::jsonb, :s3_keys::jsonb, NOW())
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": telnyx_msg_id or str(uuid.uuid4()),
                "phone": from_phone,
                "org_id": org_id,
                "body": body[:2000],
                "msg_id": telnyx_msg_id,
                "media_urls": media_urls_json,
                "s3_keys": s3_keys_json,
            },
        )
        db.flush()
    except Exception as e:
        logger.debug(f"Panel inbound store skipped: {e}")


def _send_auto_response(to_phone: str, message: str):
    """Send auto-response to keyword via the centralized SMS chokepoint.

    Auto-responses (STOP/START confirmations) bypass the compliance gate
    because they are legally required replies.
    """
    try:
        from telephony.sms import send_sms_verified

        send_sms_verified(
            to=to_phone,
            text=message,
            bypass_compliance=True,  # Keyword auto-responses are legally required
        )
    except Exception as e:
        logger.error(f"Auto-response send failed: {e}")
