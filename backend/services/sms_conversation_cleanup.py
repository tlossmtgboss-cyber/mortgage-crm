"""
SMS AI Conversation Cleanup Service

Closes stale AI conversations to prevent phantom intercepts on inbound SMS.
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

CONVERSATION_TTL_HOURS = 72  # Close after 72 hours of inactivity


def close_stale_conversations(db: Session, organization_id: int = None) -> dict:
    """Close AI conversations that have been inactive for longer than TTL.

    Uses two signals to detect staleness:
      1. expires_at — explicit deadline set at conversation creation
      2. last_message_at — fallback for older rows without expires_at
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CONVERSATION_TTL_HOURS)

    query = """
        UPDATE sms_ai_conversations
        SET status = 'expired',
            updated_at = NOW()
        WHERE status = 'active'
        AND (
            (expires_at IS NOT NULL AND expires_at < NOW())
            OR (expires_at IS NULL AND last_message_at < :cutoff)
            OR (expires_at IS NULL AND last_message_at IS NULL AND created_at < :cutoff)
        )
    """
    params = {"cutoff": cutoff}

    if organization_id:
        query += " AND organization_id = :org_id"
        params["org_id"] = organization_id

    query += " RETURNING id"

    try:
        result = db.execute(text(query), params)
        closed_ids = [row[0] for row in result.fetchall()]
        db.commit()

        if closed_ids:
            logger.info(f"Closed {len(closed_ids)} stale SMS AI conversations (TTL={CONVERSATION_TTL_HOURS}h)")

        return {"closed_count": len(closed_ids), "closed_ids": closed_ids}
    except Exception as e:
        logger.error(f"Failed to close stale conversations: {e}", exc_info=True)
        db.rollback()
        return {"closed_count": 0, "error": str(e)}


def close_conversation(db: Session, conversation_id, reason: str = "completed") -> bool:
    """Close a specific conversation."""
    try:
        db.execute(text("""
            UPDATE sms_ai_conversations
            SET status = :status, updated_at = NOW()
            WHERE id = :cid AND status = 'active'
        """), {"status": reason, "cid": conversation_id})
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to close conversation {conversation_id}: {e}")
        db.rollback()
        return False
