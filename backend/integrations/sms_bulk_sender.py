# backend/integrations/sms_bulk_sender.py
# Bulk SMS sending with compliance, rate limiting, and queue integration
# Supports campaign sends to lead segments with per-campaign tracking

import logging
import time
from typing import Optional, List, Dict

from sqlalchemy.orm import Session
from sqlalchemy import text

from .sms_compliance_gate import check_sms_compliance
from .sms_rate_limiter import check_rate_limit, record_send_attempt
from .sms_retry_queue import enqueue_sms, mark_sent, mark_failed
from .sms_template_engine import render_template

logger = logging.getLogger(__name__)

# Throttle between bulk sends to avoid carrier filtering
BULK_DELAY_SECONDS = 0.15  # 150ms between messages = ~400/min max


def send_campaign(
    db: Session,
    recipients: List[Dict],  # List of {phone, first_name, lead_id, ...vars}
    message_body: str,
    user_id: int,
    from_phone: Optional[str] = None,
    campaign_name: Optional[str] = None,
    template_id: Optional[int] = None,
    dry_run: bool = False,
) -> dict:
    """
    Send bulk SMS to a list of recipients.
    Each recipient dict can have variable substitution data.
    Returns campaign summary stats.
    """
    campaign_id = _create_campaign_record(db, campaign_name, user_id, len(recipients))
    stats = {
        "campaign_id": campaign_id,
        "total": len(recipients),
        "queued": 0,
        "skipped_compliance": 0,
        "skipped_rate_limit": 0,
        "errors": 0,
        "dry_run": dry_run,
    }

    for recipient in recipients:
        phone = recipient.get("phone") or recipient.get("to_phone")
        lead_id = recipient.get("lead_id")

        if not phone:
            stats["errors"] += 1
            continue

        # Render template with recipient variables
        rendered_body = render_template(message_body, recipient)

        if dry_run:
            stats["queued"] += 1
            continue

        # Compliance check
        compliance = check_sms_compliance(
            db, phone, rendered_body,
            lead_id=lead_id, user_id=user_id
        )
        if not compliance.allowed:
            stats["skipped_compliance"] += 1
            logger.info(f"Bulk SMS skipped {phone}: {compliance.reason}")
            continue

        # Rate limit check
        rate_ok, rate_reason = check_rate_limit(db, phone, user_id=user_id, lead_id=lead_id)
        if not rate_ok:
            stats["skipped_rate_limit"] += 1
            logger.info(f"Bulk SMS rate limited {phone}: {rate_reason}")
            continue

        # Queue the message (with TCPA consent proof from compliance gate)
        queue_id = enqueue_sms(
            db, phone, rendered_body,
            from_phone=from_phone,
            lead_id=lead_id,
            user_id=user_id,
            template_id=template_id,
            priority=7,  # Bulk = lower priority than 1:1 messages
            consent_record_id=compliance.consent_record_id,
            consent_verified_at=compliance.consent_verified_at,
            consent_method=compliance.consent_method,
        )

        if queue_id:
            record_send_attempt(db, phone, user_id=user_id, lead_id=lead_id)
            _update_campaign_stats(db, campaign_id, "queued")
            stats["queued"] += 1
        else:
            stats["errors"] += 1

        # Throttle
        time.sleep(BULK_DELAY_SECONDS)

    _finalize_campaign(db, campaign_id, stats)
    logger.info(f"Bulk campaign complete: {stats}")
    return stats


def get_campaign_status(db: Session, campaign_id: int) -> Optional[dict]:
    """Get current status of a bulk campaign."""
    try:
        row = db.execute(
            text("""
                SELECT id, name, status, total_recipients,
                       queued_count, sent_count, failed_count,
                       created_at, completed_at
                FROM sms_campaigns
                WHERE id = :id
            """),
            {"id": campaign_id},
        ).fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "name": row[1],
            "status": row[2],
            "total_recipients": row[3],
            "queued": row[4],
            "sent": row[5],
            "failed": row[6],
            "created_at": str(row[7]) if row[7] else None,
            "completed_at": str(row[8]) if row[8] else None,
        }
    except Exception as e:
        logger.error(f"Failed to get campaign status: {e}")
        return None


def list_campaigns(
    db: Session,
    user_id: Optional[int] = None,
    limit: int = 20,
) -> List[dict]:
    """List recent campaigns for a user."""
    try:
        user_filter = "WHERE user_id = :user_id" if user_id else ""
        params = {"limit": limit}
        if user_id:
            params["user_id"] = user_id

        rows = db.execute(
            text(f"""
                SELECT id, name, status, total_recipients,
                       sent_count, created_at
                FROM sms_campaigns
                {user_filter}
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            params,
        ).fetchall()

        return [
            {
                "id": r[0],
                "name": r[1],
                "status": r[2],
                "total": r[3],
                "sent": r[4],
                "created_at": str(r[5]) if r[5] else None,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Failed to list campaigns: {e}")
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _create_campaign_record(
    db: Session,
    name: Optional[str],
    user_id: int,
    total: int,
) -> Optional[int]:
    try:
        result = db.execute(
            text("""
                INSERT INTO sms_campaigns
                  (name, user_id, status, total_recipients, created_at)
                VALUES (:name, :user_id, 'running', :total, NOW())
                RETURNING id
            """),
            {"name": name or f"Campaign {__import__('datetime').datetime.now():%Y-%m-%d %H:%M}",
             "user_id": user_id, "total": total},
        )
        db.commit()
        row = result.fetchone()
        return row[0] if row else None
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create campaign record: {e}")
        return None


def _update_campaign_stats(db: Session, campaign_id: Optional[int], field: str):
    if not campaign_id:
        return
    col = {"queued": "queued_count", "sent": "sent_count", "failed": "failed_count"}.get(field)
    if not col:
        return
    try:
        db.execute(
            text(f"UPDATE sms_campaigns SET {col} = COALESCE({col}, 0) + 1 WHERE id = :id"),
            {"id": campaign_id},
        )
        db.commit()
    except Exception:
        db.rollback()


def _finalize_campaign(db: Session, campaign_id: Optional[int], stats: dict):
    if not campaign_id:
        return
    try:
        db.execute(
            text("""
                UPDATE sms_campaigns
                SET status = 'completed',
                    queued_count = :queued,
                    failed_count = :errors,
                    completed_at = NOW()
                WHERE id = :id
            """),
            {"queued": stats["queued"], "errors": stats["errors"], "id": campaign_id},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to finalize campaign: {e}")
