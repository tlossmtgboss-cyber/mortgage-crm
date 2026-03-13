# backend/integrations/sms_delivery_tracker.py
# Tracks SMS delivery status via Telnyx webhooks and DB updates

import logging
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Telnyx delivery status codes
STATUS_MAP = {
    "queued": "queued",
    "sending": "sending",
    "sent": "sent",
    "delivered": "delivered",
    "delivery_failed": "failed",
    "delivery_unconfirmed": "unconfirmed",
    "received": "received",
    "failed": "failed",
}


def record_message_sent(
    db: Session,
    telnyx_message_id: str,
    to_phone: str,
    from_phone: str,
    message_body: str,
    lead_id: Optional[int] = None,
    user_id: Optional[int] = None,
    queue_id: Optional[int] = None,
    segments: int = 1,
) -> int:
    """Record a newly sent SMS message. Returns tracking record ID."""
    try:
        result = db.execute(
            text("""
                INSERT INTO sms_delivery_log
                  (telnyx_message_id, to_phone, from_phone, message_body,
                   lead_id, user_id, queue_id, status, segments,
                   sent_at, created_at)
                VALUES
                  (:msg_id, :to_phone, :from_phone, :body,
                   :lead_id, :user_id, :queue_id, 'queued', :segments,
                   NOW(), NOW())
                ON CONFLICT (telnyx_message_id) DO UPDATE SET
                  status = 'queued', updated_at = NOW()
                RETURNING id
            """),
            {
                "msg_id": telnyx_message_id,
                "to_phone": to_phone,
                "from_phone": from_phone,
                "body": message_body[:500],
                "lead_id": lead_id,
                "user_id": user_id,
                "queue_id": queue_id,
                "segments": segments,
            },
        )
        db.commit()
        row = result.fetchone()
        return row[0] if row else 0
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to record message sent: {e}")
        return 0


def update_delivery_status(
    db: Session,
    telnyx_message_id: str,
    status: str,
    error_code: Optional[str] = None,
    carrier_name: Optional[str] = None,
    delivered_at: Optional[datetime] = None,
) -> bool:
    """Update delivery status from Telnyx webhook payload."""
    normalized_status = STATUS_MAP.get(status, status)
    try:
        db.execute(
            text("""
                UPDATE sms_delivery_log
                SET status = :status,
                    error_code = :error_code,
                    carrier_name = :carrier,
                    delivered_at = :delivered_at,
                    updated_at = NOW()
                WHERE telnyx_message_id = :msg_id
            """),
            {
                "status": normalized_status,
                "error_code": error_code,
                "carrier": carrier_name,
                "delivered_at": delivered_at,
                "msg_id": telnyx_message_id,
            },
        )
        db.commit()
        logger.info(f"Delivery status updated: {telnyx_message_id} -> {normalized_status}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update delivery status: {e}")
        return False


def get_message_status(db: Session, telnyx_message_id: str) -> Optional[dict]:
    """Look up current delivery status for a message."""
    try:
        row = db.execute(
            text("""
                SELECT telnyx_message_id, to_phone, status, error_code,
                       carrier_name, segments, sent_at, delivered_at, updated_at
                FROM sms_delivery_log
                WHERE telnyx_message_id = :msg_id
            """),
            {"msg_id": telnyx_message_id},
        ).fetchone()

        if not row:
            return None

        return {
            "message_id": row[0],
            "to_phone": row[1],
            "status": row[2],
            "error_code": row[3],
            "carrier": row[4],
            "segments": row[5],
            "sent_at": str(row[6]) if row[6] else None,
            "delivered_at": str(row[7]) if row[7] else None,
            "updated_at": str(row[8]) if row[8] else None,
        }
    except Exception as e:
        logger.error(f"Failed to get message status: {e}")
        return None


def get_lead_message_history(
    db: Session,
    lead_id: int,
    limit: int = 50,
    offset: int = 0,
) -> List[dict]:
    """Get SMS history for a specific lead."""
    try:
        rows = db.execute(
            text("""
                SELECT telnyx_message_id, to_phone, from_phone,
                       message_body, status, segments,
                       sent_at, delivered_at, error_code
                FROM sms_delivery_log
                WHERE lead_id = :lead_id
                ORDER BY sent_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"lead_id": lead_id, "limit": limit, "offset": offset},
        ).fetchall()

        return [
            {
                "message_id": r[0],
                "to_phone": r[1],
                "from_phone": r[2],
                "body": r[3],
                "status": r[4],
                "segments": r[5],
                "sent_at": str(r[6]) if r[6] else None,
                "delivered_at": str(r[7]) if r[7] else None,
                "error_code": r[8],
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Failed to get lead message history: {e}")
        return []


def get_delivery_stats(db: Session, days: int = 7) -> dict:
    """Return delivery statistics for the dashboard."""
    try:
        row = db.execute(
            text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 'delivered') AS delivered,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                    COUNT(*) FILTER (WHERE status = 'queued' OR status = 'sending') AS pending,
                    ROUND(
                        COUNT(*) FILTER (WHERE status = 'delivered')::numeric /
                        NULLIF(COUNT(*), 0) * 100, 2
                    ) AS delivery_rate
                FROM sms_delivery_log
                WHERE sent_at >= NOW() - INTERVAL ':days days'
            """.replace(":days", str(days))),
        ).fetchone()

        return {
            "total": row[0] if row else 0,
            "delivered": row[1] if row else 0,
            "failed": row[2] if row else 0,
            "pending": row[3] if row else 0,
            "delivery_rate_pct": float(row[4]) if row and row[4] else 0.0,
            "period_days": days,
        }
    except Exception as e:
        logger.error(f"Failed to get delivery stats: {e}")
        return {"total": 0, "delivered": 0, "failed": 0, "pending": 0, "delivery_rate_pct": 0.0}


def process_telnyx_webhook(db: Session, payload: dict) -> dict:
    """
    Process a Telnyx messaging webhook event.
    Returns dict with action taken.
    """
    try:
        event_type = payload.get("data", {}).get("event_type", "")
        record = payload.get("data", {}).get("payload", {})

        message_id = record.get("id") or record.get("message_id")
        if not message_id:
            return {"status": "ignored", "reason": "no message_id in payload"}

        if "message.sent" in event_type:
            update_delivery_status(db, message_id, "sent")
            return {"status": "processed", "action": "marked_sent"}

        if "message.finalized" in event_type:
            to_status = record.get("to", [{}])
            if isinstance(to_status, list) and to_status:
                dlr = to_status[0].get("status", "delivered")
                error_code = to_status[0].get("carrier", {}).get("error_code")
                carrier = to_status[0].get("carrier", {}).get("name")
            else:
                dlr = record.get("status", "delivered")
                error_code = None
                carrier = None

            delivered_at = None
            if dlr == "delivered":
                delivered_at = datetime.utcnow()

            update_delivery_status(
                db, message_id, dlr,
                error_code=str(error_code) if error_code else None,
                carrier_name=carrier,
                delivered_at=delivered_at,
            )
            return {"status": "processed", "action": f"marked_{dlr}"}

        return {"status": "ignored", "reason": f"unhandled event_type: {event_type}"}

    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return {"status": "error", "reason": str(e)}
