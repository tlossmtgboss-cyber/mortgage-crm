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
    consent_record_id: Optional[int] = None,
    consent_verified_at=None,
    consent_method: Optional[str] = None,
) -> int:
    """
    Add an SMS to the retry queue. Returns the queue record ID.
    Initial status is 'pending'.

    consent_record_id/consent_verified_at/consent_method: TCPA consent proof
    from the compliance gate, persisted alongside the queued message for audit.
    """
    try:
        result = db.execute(
            text("""
                INSERT INTO sms_queue
                  (to_phone, from_phone, message_body, lead_id, user_id,
                   template_id, priority, status, retry_count,
                   consent_record_id, consent_verified_at, consent_method,
                   next_attempt_at, created_at)
                VALUES
                  (:to_phone, :from_phone, :body, :lead_id, :user_id,
                   :template_id, :priority, 'pending', 0,
                   :consent_record_id, :consent_verified_at, :consent_method,
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
                "consent_record_id": consent_record_id,
                "consent_verified_at": consent_verified_at,
                "consent_method": consent_method,
            },
        )
        db.commit()
        row = result.fetchone()
        queue_id = row[0] if row else 0
        logger.info(f"SMS enqueued id={queue_id} to=...{to_phone[-4:] if to_phone else '????'}")
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
                       user_id, template_id, retry_count, priority,
                       organization_id
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
                "organization_id": row[9] if len(row) > 9 else None,
            })
        return messages
    except Exception as e:
        logger.error(f"Failed to fetch pending messages: {e}")
        return []


def mark_compliance_blocked(db: Session, queue_id: int, reason: str):
    """Mark a queued message as blocked by compliance re-check at send time."""
    try:
        db.execute(
            text("""
                UPDATE sms_queue
                SET status = 'compliance_blocked',
                    last_error = :reason,
                    failed_at = NOW()
                WHERE id = :id
            """),
            {"reason": reason[:500], "id": queue_id},
        )
        db.commit()
        logger.info(f"SMS {queue_id} blocked at send time: {reason}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to mark SMS {queue_id} as compliance_blocked: {e}")


def process_pending_queue(db: Session, limit: int = 50) -> dict:
    """
    Process pending SMS queue entries: re-verify compliance at send time,
    then send via the Telnyx chokepoint.

    This closes the compliance timing gap where a recipient may opt out
    between queue time and actual send time.

    Returns dict with processing stats.
    """
    from integrations.sms_compliance_gate import check_sms_compliance

    stats = {"processed": 0, "sent": 0, "blocked": 0, "failed": 0}
    messages = get_pending_messages(db, limit=limit)

    for msg in messages:
        stats["processed"] += 1
        queue_id = msg["id"]
        phone = msg["to_phone"]
        lead_id = msg.get("lead_id")
        user_id = msg.get("user_id")
        organization_id = msg.get("organization_id")

        # Re-verify compliance at send time (consent may have changed since queue time)
        try:
            compliance = check_sms_compliance(
                db, phone, msg["message_body"],
                lead_id=lead_id, user_id=user_id,
                organization_id=organization_id,
            )
        except Exception as e:
            # Compliance check itself failed -- fail-closed for TCPA safety
            logger.error(f"Compliance re-check error for SMS {queue_id}: {e}")
            mark_compliance_blocked(db, queue_id, f"Compliance check error: {e}")
            stats["blocked"] += 1
            continue

        if not compliance.allowed:
            logger.info(
                f"Queued SMS {queue_id} to ...{phone[-4:] if phone else '????'} "
                f"blocked at send time: {compliance.reason}"
            )
            mark_compliance_blocked(db, queue_id, compliance.reason)
            stats["blocked"] += 1
            continue

        # Compliance passed -- send via Telnyx chokepoint
        try:
            from telephony.sms import send_sms_verified

            result = send_sms_verified(
                to=phone,
                from_=msg.get("from_phone"),
                text=msg["message_body"],
                user_id=user_id,
                lead_id=lead_id,
                organization_id=organization_id,
                db=db,
                bypass_compliance=True,  # Already re-checked above
            )
            if result.get("status") == "sent":
                mark_sent(db, queue_id, result.get("id", ""))
                stats["sent"] += 1
            else:
                mark_failed(db, queue_id, result.get("reason", "Send failed"))
                stats["failed"] += 1
        except Exception as e:
            mark_failed(db, queue_id, str(e))
            stats["failed"] += 1

    if stats["processed"]:
        logger.info(
            f"Queue processing complete: {stats['processed']} processed, "
            f"{stats['sent']} sent, {stats['blocked']} compliance-blocked, "
            f"{stats['failed']} failed"
        )

    return stats


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
