import logging
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

HIGH_PRIORITY_KEYWORDS = {"urgent", "asap", "emergency", "immediately", "critical", "help me"}
NORMAL_PRIORITY_KEYWORDS = {"question", "help", "info", "information", "wondering"}


def _detect_priority(message: str, explicit_priority: Optional[str] = None) -> str:
    if explicit_priority and explicit_priority in ("high", "normal", "low"):
        return explicit_priority
    lower = message.lower()
    for kw in HIGH_PRIORITY_KEYWORDS:
        if kw in lower:
            return "high"
    for kw in NORMAL_PRIORITY_KEYWORDS:
        if kw in lower:
            return "normal"
    return "normal"


def _word_level_edit_distance(original: str, edited: str) -> int:
    orig_words = original.split()
    edit_words = edited.split()
    m, n = len(orig_words), len(edit_words)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if orig_words[i - 1] == edit_words[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[n]


def _row_to_dict(row) -> dict:
    if hasattr(row, '_mapping'):
        return dict(row._mapping)
    return dict(row)


def create_sms_task(
    db: Session,
    organization_id: int,
    phone_number: str,
    inbound_message: str,
    inbound_message_id: str,
    contact_name: Optional[str] = None,
    lead_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    category: Optional[str] = None,
    priority: str = "normal",
) -> dict:
    from services.sms_phone_utils import normalize_phone
    phone_number = normalize_phone(phone_number)

    try:
        resolved_priority = _detect_priority(inbound_message, priority if priority != "normal" else None)
        now = datetime.now(timezone.utc)

        result = db.execute(
            text("""
                INSERT INTO sms_tasks
                    (organization_id, phone_number, inbound_message, inbound_message_id,
                     inbound_received_at, contact_name, lead_id, assigned_user_id,
                     category, priority, status, created_at, updated_at)
                VALUES
                    (:org_id, :phone, :message, :msg_id,
                     :received_at, :contact_name, :lead_id, :assigned_user_id,
                     :category, :priority, 'pending', :now, :now)
                RETURNING *
            """),
            {
                "org_id": organization_id,
                "phone": phone_number,
                "message": inbound_message,
                "msg_id": inbound_message_id,
                "received_at": now,
                "contact_name": contact_name,
                "lead_id": lead_id,
                "assigned_user_id": assigned_user_id,
                "category": category,
                "priority": resolved_priority,
                "now": now,
            },
        )
        db.flush()
        row = result.fetchone()
        task = _row_to_dict(row)
        logger.info(f"Created SMS task {task.get('id')} for org={organization_id} phone={phone_number}")
        return task
    except SQLAlchemyError as e:
        logger.exception(f"Failed to create SMS task for org={organization_id}: {e}")
        raise


def get_sms_tasks(
    db: Session,
    organization_id: int,
    user_id: Optional[int] = None,
    status: str = "pending",
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[dict], int]:
    try:
        where_clauses = ["t.organization_id = :org_id"]
        params: Dict[str, Any] = {"org_id": organization_id}

        if status:
            where_clauses.append("t.status = :status")
            params["status"] = status

        if user_id is not None:
            where_clauses.append("t.assigned_user_id = :user_id")
            params["user_id"] = user_id

        if category:
            where_clauses.append("t.category = :category")
            params["category"] = category

        where_sql = " AND ".join(where_clauses)

        count_result = db.execute(
            text(f"SELECT COUNT(*) FROM sms_tasks t WHERE {where_sql}"),
            params,
        )
        total = count_result.scalar() or 0

        params["limit"] = limit
        params["offset"] = offset

        rows = db.execute(
            text(f"""
                SELECT t.*
                FROM sms_tasks t
                WHERE {where_sql}
                ORDER BY
                    CASE t.priority
                        WHEN 'high' THEN 0
                        WHEN 'normal' THEN 1
                        WHEN 'low' THEN 2
                        ELSE 3
                    END ASC,
                    t.created_at ASC
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        tasks = [_row_to_dict(r) for r in rows.fetchall()]
        return tasks, total
    except SQLAlchemyError as e:
        logger.exception(f"Failed to fetch SMS tasks for org={organization_id}: {e}")
        return [], 0


def get_sms_task(
    db: Session,
    task_id: int,
    organization_id: int,
) -> Optional[dict]:
    try:
        row = db.execute(
            text("""
                SELECT t.*,
                       l.first_name AS lead_first_name,
                       l.last_name AS lead_last_name,
                       l.email AS lead_email,
                       l.stage AS lead_stage
                FROM sms_tasks t
                LEFT JOIN leads l ON l.id = t.lead_id
                WHERE t.id = :task_id
                  AND t.organization_id = :org_id
            """),
            {"task_id": task_id, "org_id": organization_id},
        ).fetchone()

        if not row:
            return None
        return _row_to_dict(row)
    except SQLAlchemyError as e:
        logger.exception(f"Failed to fetch SMS task {task_id} for org={organization_id}: {e}")
        return None


def respond_to_task(
    db: Session,
    task_id: int,
    organization_id: int,
    user_id: int,
    response_text: str,
    response_source: str,
) -> dict:
    try:
        now = datetime.now(timezone.utc)

        edit_distance = None
        if response_source == "ai_edited":
            existing = db.execute(
                text("""
                    SELECT ai_recommendation FROM sms_tasks
                    WHERE id = :task_id AND organization_id = :org_id
                """),
                {"task_id": task_id, "org_id": organization_id},
            ).fetchone()
            if existing and existing.ai_recommendation:
                edit_distance = _word_level_edit_distance(existing.ai_recommendation, response_text)

        result = db.execute(
            text("""
                UPDATE sms_tasks
                SET response_text = :response_text,
                    response_source = :response_source,
                    response_sent_at = :now,
                    responded_by_user_id = :user_id,
                    edit_distance = :edit_distance,
                    status = 'completed',
                    updated_at = :now
                WHERE id = :task_id
                  AND organization_id = :org_id
                RETURNING *
            """),
            {
                "response_text": response_text,
                "response_source": response_source,
                "now": now,
                "user_id": user_id,
                "edit_distance": edit_distance,
                "task_id": task_id,
                "org_id": organization_id,
            },
        )
        db.flush()
        row = result.fetchone()
        if not row:
            raise ValueError(f"SMS task {task_id} not found in org {organization_id}")

        task = _row_to_dict(row)
        logger.info(f"Responded to SMS task {task_id} via {response_source} by user={user_id}")
        return task
    except SQLAlchemyError as e:
        logger.exception(f"Failed to respond to SMS task {task_id}: {e}")
        raise


def dismiss_task(
    db: Session,
    task_id: int,
    organization_id: int,
    user_id: int,
) -> dict:
    try:
        now = datetime.now(timezone.utc)

        result = db.execute(
            text("""
                UPDATE sms_tasks
                SET status = 'dismissed',
                    responded_by_user_id = :user_id,
                    updated_at = :now
                WHERE id = :task_id
                  AND organization_id = :org_id
                RETURNING *
            """),
            {
                "user_id": user_id,
                "now": now,
                "task_id": task_id,
                "org_id": organization_id,
            },
        )
        db.flush()
        row = result.fetchone()
        if not row:
            raise ValueError(f"SMS task {task_id} not found in org {organization_id}")

        db.execute(
            text("""
                INSERT INTO sms_ai_audit_log
                    (organization_id, task_id, action, details, user_id, created_at)
                VALUES
                    (:org_id, :task_id, 'dismissed', :details, :user_id, :now)
            """),
            {
                "org_id": organization_id,
                "task_id": task_id,
                "details": json.dumps({"dismissed_by": user_id}),
                "user_id": user_id,
                "now": now,
            },
        )
        db.flush()

        task = _row_to_dict(row)
        logger.info(f"Dismissed SMS task {task_id} by user={user_id}")
        return task
    except SQLAlchemyError as e:
        logger.exception(f"Failed to dismiss SMS task {task_id}: {e}")
        raise


def expire_stale_tasks(db: Session, hours: int = 24) -> int:
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        now = datetime.now(timezone.utc)

        result = db.execute(
            text("""
                UPDATE sms_tasks
                SET status = 'expired',
                    updated_at = :now
                WHERE status = 'pending'
                  AND created_at < :cutoff
            """),
            {"now": now, "cutoff": cutoff},
        )
        db.flush()
        count = result.rowcount
        if count > 0:
            logger.info(f"Expired {count} stale SMS tasks older than {hours}h")
        return count
    except SQLAlchemyError as e:
        logger.exception(f"Failed to expire stale SMS tasks: {e}")
        return 0


def get_task_stats(
    db: Session,
    organization_id: int,
    user_id: Optional[int] = None,
) -> dict:
    try:
        user_clause = ""
        params: Dict[str, Any] = {"org_id": organization_id}

        if user_id is not None:
            user_clause = "AND assigned_user_id = :user_id"
            params["user_id"] = user_id

        row = db.execute(
            text(f"""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE status = 'in_progress') AS in_progress,
                    COUNT(*) FILTER (
                        WHERE status = 'completed'
                          AND response_sent_at >= CURRENT_DATE
                    ) AS completed_today,
                    COUNT(*) FILTER (
                        WHERE status = 'completed'
                          AND response_source = 'ai_auto'
                          AND response_sent_at >= CURRENT_DATE
                    ) AS auto_responded_today,
                    COUNT(*) FILTER (
                        WHERE status = 'dismissed'
                          AND updated_at >= CURRENT_DATE
                    ) AS dismissed_today,
                    AVG(
                        EXTRACT(EPOCH FROM (response_sent_at - inbound_received_at))
                    ) FILTER (
                        WHERE status = 'completed'
                          AND response_sent_at >= CURRENT_DATE
                          AND response_sent_at IS NOT NULL
                          AND inbound_received_at IS NOT NULL
                    ) AS avg_response_seconds
                FROM sms_tasks
                WHERE organization_id = :org_id
                  {user_clause}
            """),
            params,
        ).fetchone()

        stats = _row_to_dict(row) if row else {}
        avg_sec = stats.get("avg_response_seconds")
        stats["avg_response_seconds"] = round(float(avg_sec), 1) if avg_sec is not None else None
        return stats
    except SQLAlchemyError as e:
        logger.exception(f"Failed to get SMS task stats for org={organization_id}: {e}")
        return {
            "pending": 0,
            "in_progress": 0,
            "completed_today": 0,
            "auto_responded_today": 0,
            "dismissed_today": 0,
            "avg_response_seconds": None,
        }


def assign_task_to_user(
    db: Session,
    phone_number: str,
    organization_id: int,
) -> Optional[int]:
    from services.sms_phone_utils import normalize_phone
    phone_number = normalize_phone(phone_number)

    try:
        lead_row = db.execute(
            text("""
                SELECT owner_id FROM leads
                WHERE phone = :phone
                  AND organization_id = :org_id
                  AND owner_id IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
            """),
            {"phone": phone_number, "org_id": organization_id},
        ).fetchone()

        if lead_row and lead_row.owner_id:
            return lead_row.owner_id

        least_loaded = db.execute(
            text("""
                SELECT u.id,
                       COUNT(t.id) AS open_tasks
                FROM users u
                LEFT JOIN sms_tasks t
                    ON t.assigned_user_id = u.id
                   AND t.status = 'pending'
                WHERE u.organization_id = :org_id
                  AND u.is_active = true
                GROUP BY u.id
                ORDER BY open_tasks ASC, u.id ASC
                LIMIT 1
            """),
            {"org_id": organization_id},
        ).fetchone()

        if least_loaded:
            return least_loaded.id

        return None
    except SQLAlchemyError as e:
        logger.exception(f"Failed to assign SMS task user for phone={phone_number} org={organization_id}: {e}")
        return None
