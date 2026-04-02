# backend/integrations/sms_retry_queue.py
# SMS Retry Queue with exponential backoff for failed Telnyx sends
# Stores failed messages in DB and retries with jitter

import logging
import random
import time as time_module
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------
MAX_RETRIES = 5
BASE_DELAY_SECONDS = 30       # First retry after 30s
MAX_DELAY_SECONDS = 3600      # Cap at 1 hour
JITTER_FACTOR = 0.25          # +/- 25% jitter


# ---------------------------------------------------------------------------
# Queue operations
# ---------------------------------------------------------------------------
def enqueue_sms(
    db: Session,
    to_phone: str,
    message_body: str,
    from_phone: Optional[str] = None,
    lead_id: Optional[int] = None,
    user_id: Optional[int] = None,
    template_id: Optional[int] = None,
    priority: int = 5,  # 1=highest, 10=lowest
) -> int:
    """
    Add an SMS to the retry queue. Returns the queue record ID.
    Initial status is 'pending'.
    """
    try:
        result = db.execute(
            text("""
                INSERT INTO sms_queue
                  (to_phone, from_phone, message_body, lead_id, user_id,
                   template_id, priority, status, retry_count,
                   next_attempt_at, created_at)
                VALUES
                  (:to_phone, :from_phone, :body, :lead_id, :user_id,
                   :template_id, :priority, 'pending', 0,
                   NOW(), NOW())
                RETURNING id
            """),
            {
                "to_phone": to_phone,
                "from_phone": from_phone,
                "body": message_body,
                "lead_id": lead_id,
                "user_id": user_id,
                "template_id": template_id,
                "priority": priority,
            },
        )
        db.commit()
        row = result.fetchone()
        queue_id = row[0] if row else 0
        logger.info(f"SMS enqueued id={queue_id} to={to_phone}")
        return queue_id
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to enqueue SMS: {e}")
        return 0


def mark_sent(db: Session, queue_id: int, telnyx_message_id: str):
    """Mark a queued message as successfully sent."""
    try:
        db.execute(
            text("""
                UPDATE sms_queue
                SET status = 'sent',
                    telnyx_message_id = :msg_id,
                    sent_at = NOW()
                WHERE id = :id
            """),
            {"msg_id": telnyx_message_id, "id": queue_id},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to mark SMS {queue_id} as sent: {e}")


def mark_failed(db: Session, queue_id: int, error: str, permanent: bool = False):
    """
    Mark a message as failed and schedule next retry.
    If permanent=True or max retries reached, mark as dead_letter.
    """
    try:
        row = db.execute(
            text("SELECT retry_count FROM sms_queue WHERE id = :id"),
            {"id": queue_id},
        ).fetchone()

        if not row:
            return

        retry_count = row[0] + 1
        if permanent or retry_count >= MAX_RETRIES:
            db.execute(
                text("""
                    UPDATE sms_queue
                    SET status = 'dead_letter',
                        retry_count = :retry_count,
                        last_error = :error,
                        failed_at = NOW()
                    WHERE id = :id
                """),
                {"retry_count": retry_count, "error": error[:500], "id": queue_id},
            )
            logger.warning(f"SMS {queue_id} moved to dead_letter after {retry_count} attempts")
        else:
            delay = _calculate_backoff(retry_count)
            next_attempt = datetime.now(timezone.utc) + timedelta(seconds=delay)
            db.execute(
                text("""
                    UPDATE sms_queue
                    SET status = 'pending',
                        retry_count = :retry_count,
                        last_error = :error,
                        next_attempt_at = :next_attempt
                    WHERE id = :id
                """),
                {
                    "retry_count": retry_count,
                    "error": error[:500],
                    "next_attempt": next_attempt,
                    "id": queue_id,
                },
            )
            logger.info(
                f"SMS {queue_id} retry #{retry_count} scheduled in {delay:.0f}s"
            )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to mark SMS {queue_id} as failed: {e}")


def get_pending_messages(db: Session, limit: int = 50) -> List[dict]:
    """
    Fetch messages ready for processing (next_attempt_at <= NOW).
    Returns list of dicts with message details.
    """
    try:
        rows = db.execute(
            text("""
                SELECT id, to_phone, from_phone, message_body, lead_id,
                       user_id, template_id, retry_count, priority
                FROM sms_queue
                WHERE status = 'pending'
                  AND next_attempt_at <= NOW()
                ORDER BY priority ASC, next_attempt_at ASC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()

        messages = []
        for row in rows:
            messages.append({
                "id": row[0],
                "to_phone": row[1],
                "from_phone": row[2],
                "message_body": row[3],
                "lead_id": row[4],
                "user_id": row[5],
                "template_id": row[6],
                "retry_count": row[7],
                "priority": row[8],
            })
        return messages
    except Exception as e:
        logger.error(f"Failed to fetch pending messages: {e}")
        return []


def get_dead_letter_messages(db: Session, limit: int = 100) -> List[dict]:
    """Return messages that exhausted all retries."""
    try:
        rows = db.execute(
            text("""
                SELECT id, to_phone, message_body, retry_count, last_error, failed_at
                FROM sms_queue
                WHERE status = 'dead_letter'
                ORDER BY failed_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()

        return [
            {
                "id": r[0],
                "to_phone": r[1],
                "message_body": r[2],
                "retry_count": r[3],
                "last_error": r[4],
                "failed_at": str(r[5]) if r[5] else None,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Failed to fetch dead letter messages: {e}")
        return []


def requeue_dead_letter(db: Session, queue_id: int) -> bool:
    """Manually re-queue a dead letter message for one more attempt."""
    try:
        db.execute(
            text("""
                UPDATE sms_queue
                SET status = 'pending',
                    retry_count = 0,
                    last_error = NULL,
                    next_attempt_at = NOW()
                WHERE id = :id AND status = 'dead_letter'
            """),
            {"id": queue_id},
        )
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to requeue message {queue_id}: {e}")
        return False


def queue_stats(db: Session) -> dict:
    """Return queue statistics for dashboard display."""
    try:
        row = db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending')      AS pending,
                    COUNT(*) FILTER (WHERE status = 'sent')         AS sent,
                    COUNT(*) FILTER (WHERE status = 'dead_letter')  AS dead_letter,
                    COUNT(*)                                        AS total
                FROM sms_queue
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            """)
        ).fetchone()

        return {
            "pending": row[0] if row else 0,
            "sent": row[1] if row else 0,
            "dead_letter": row[2] if row else 0,
            "total_24h": row[3] if row else 0,
        }
    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}")
        return {"pending": 0, "sent": 0, "dead_letter": 0, "total_24h": 0}


# ---------------------------------------------------------------------------
# Backoff calculation
# ---------------------------------------------------------------------------
def _calculate_backoff(retry_count: int) -> float:
    """
    Exponential backoff with jitter.
    retry_count=1 -> ~30s, =2 -> ~60s, =3 -> ~120s ...
    """
    delay = min(BASE_DELAY_SECONDS * (2 ** (retry_count - 1)), MAX_DELAY_SECONDS)
    jitter = delay * JITTER_FACTOR * (2 * random.random() - 1)  # +/- jitter
    return max(delay + jitter, BASE_DELAY_SECONDS)
