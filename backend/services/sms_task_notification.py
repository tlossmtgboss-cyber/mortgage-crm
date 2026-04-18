import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


def create_task_notification(
    db: Session,
    task_id: int,
    organization_id: int,
    assigned_user_id: Optional[int],
    phone_number: str,
    contact_name: Optional[str],
    category: Optional[str],
    ai_confidence: float,
) -> Optional[dict]:
    if not assigned_user_id:
        return None

    display_name = contact_name or phone_number
    title = f"New SMS from {display_name}"

    try:
        msg_row = db.execute(
            text("SELECT inbound_message FROM sms_tasks WHERE id = :tid"),
            {"tid": task_id},
        ).fetchone()
        body = (msg_row[0][:200] + "...") if msg_row and msg_row[0] and len(msg_row[0]) > 200 else (msg_row[0] if msg_row else "")
    except Exception as e:
        logger.warning("Failed to fetch inbound message for task %s: %s", task_id, e)
        body = ""

    try:
        db.execute(
            text("""
                INSERT INTO notifications (user_id, organization_id, title, message, type, link, is_read, created_at)
                VALUES (:user_id, :org_id, :title, :message, :type, :link, false, NOW())
            """),
            {
                "user_id": assigned_user_id,
                "org_id": organization_id,
                "title": title,
                "message": body,
                "type": "sms_task",
                "link": f"/sms-tasks/{task_id}",
            },
        )
        db.flush()
    except Exception as e:
        logger.warning("Could not insert notification (table may not exist): %s", e)
        db.rollback()
        return None

    return {
        "task_id": task_id,
        "user_id": assigned_user_id,
        "organization_id": organization_id,
        "title": title,
        "message": body,
        "type": "sms_task",
        "link": f"/sms-tasks/{task_id}",
        "category": category,
        "ai_confidence": ai_confidence,
    }


def create_auto_response_notification(
    db: Session,
    task_id: int,
    organization_id: int,
    assigned_user_id: Optional[int],
    contact_name: Optional[str],
    ai_confidence: float,
    response_preview: Optional[str],
) -> Optional[dict]:
    if not assigned_user_id:
        return None

    display_name = contact_name or "Unknown"
    title = f"AI responded to {display_name}"
    preview = (response_preview[:100] if response_preview else "")
    message = f"Confidence: {ai_confidence:.0f}% \u2014 {preview}"

    try:
        db.execute(
            text("""
                INSERT INTO notifications (user_id, organization_id, title, message, type, link, is_read, created_at)
                VALUES (:user_id, :org_id, :title, :message, :type, :link, false, NOW())
            """),
            {
                "user_id": assigned_user_id,
                "org_id": organization_id,
                "title": title,
                "message": message,
                "type": "sms_auto_response",
                "link": f"/sms-tasks/{task_id}",
            },
        )
        db.flush()
    except Exception as e:
        logger.warning("Could not insert auto-response notification: %s", e)
        db.rollback()
        return None

    return {
        "task_id": task_id,
        "user_id": assigned_user_id,
        "organization_id": organization_id,
        "title": title,
        "message": message,
        "type": "sms_auto_response",
        "link": f"/sms-tasks/{task_id}",
        "ai_confidence": ai_confidence,
    }


def get_pending_task_count(
    db: Session,
    organization_id: int,
    user_id: Optional[int] = None,
) -> int:
    try:
        if user_id:
            result = db.execute(
                text("""
                    SELECT COUNT(*) FROM sms_tasks
                    WHERE organization_id = :org_id
                      AND assigned_user_id = :user_id
                      AND status = 'pending'
                """),
                {"org_id": organization_id, "user_id": user_id},
            ).scalar()
        else:
            result = db.execute(
                text("""
                    SELECT COUNT(*) FROM sms_tasks
                    WHERE organization_id = :org_id
                      AND status = 'pending'
                """),
                {"org_id": organization_id},
            ).scalar()
        return result or 0
    except Exception as e:
        logger.warning("Failed to count pending SMS tasks: %s", e)
        return 0


def mark_tasks_seen(
    db: Session,
    organization_id: int,
    user_id: int,
    task_ids: List[int],
) -> int:
    if not task_ids:
        return 0

    try:
        result = db.execute(
            text("""
                UPDATE sms_tasks
                SET status = 'in_progress',
                    updated_at = NOW()
                WHERE id = ANY(:task_ids)
                  AND organization_id = :org_id
                  AND assigned_user_id = :user_id
                  AND status = 'pending'
            """),
            {
                "task_ids": task_ids,
                "org_id": organization_id,
                "user_id": user_id,
            },
        )
        db.flush()
        return result.rowcount
    except Exception as e:
        logger.warning("Failed to mark SMS tasks as seen: %s", e)
        db.rollback()
        return 0
