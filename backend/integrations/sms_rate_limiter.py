# backend/integrations/sms_rate_limiter.py
# DB-backed rate limiting for SMS sends (per-user, per-lead, global)
# Prevents carrier filtering and TCPA overages

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limit tiers (configurable)
# ---------------------------------------------------------------------------
LIMITS = {
    # (window_seconds, max_messages)
    "per_lead_hour": (3600, 3),          # Max 3 SMS to same lead per hour
    "per_lead_day": (86400, 10),         # Max 10 SMS to same lead per day
    "per_user_minute": (60, 10),         # Max 10 SMS per user per minute
    "per_user_hour": (3600, 200),        # Max 200 SMS per user per hour
    "global_minute": (60, 100),          # Global: 100 SMS/min across all users
    "global_hour": (3600, 2000),         # Global: 2000 SMS/hr across all users
}


def check_rate_limit(
    db: Session,
    to_phone: str,
    user_id: Optional[int] = None,
    lead_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """
    Check all rate limits before sending.
    Returns (allowed: bool, reason: str).
    """
    # Per-lead hourly limit
    if lead_id:
        count = _count_recent(db, "lead_id", lead_id, 3600)
        if count >= LIMITS["per_lead_hour"][1]:
            return False, f"Lead rate limit: {count} messages in last hour (max {LIMITS['per_lead_hour'][1]})"

    # Per-lead daily limit
    if lead_id:
        count = _count_recent(db, "lead_id", lead_id, 86400)
        if count >= LIMITS["per_lead_day"][1]:
            return False, f"Lead rate limit: {count} messages today (max {LIMITS['per_lead_day'][1]})"

    # Per-user per-minute limit
    if user_id:
        count = _count_recent(db, "user_id", user_id, 60)
        if count >= LIMITS["per_user_minute"][1]:
            return False, f"User rate limit: {count} messages in last minute (max {LIMITS['per_user_minute'][1]})"

    # Per-user hourly limit
    if user_id:
        count = _count_recent(db, "user_id", user_id, 3600)
        if count >= LIMITS["per_user_hour"][1]:
            return False, f"User rate limit: {count} messages in last hour (max {LIMITS['per_user_hour'][1]})"

    # Global rate limits
    global_count_min = _count_global_recent(db, 60)
    if global_count_min >= LIMITS["global_minute"][1]:
        return False, f"Global rate limit: {global_count_min} messages in last minute"

    global_count_hr = _count_global_recent(db, 3600)
    if global_count_hr >= LIMITS["global_hour"][1]:
        return False, f"Global rate limit: {global_count_hr} messages in last hour"

    return True, "Rate limit check passed"


def record_send_attempt(
    db: Session,
    to_phone: str,
    user_id: Optional[int] = None,
    lead_id: Optional[int] = None,
):
    """Record a send attempt for rate limiting purposes."""
    try:
        db.execute(
            text("""
                INSERT INTO sms_rate_limit_log
                  (to_phone, user_id, lead_id, sent_at)
                VALUES (:phone, :user_id, :lead_id, NOW())
            """),
            {"phone": to_phone, "user_id": user_id, "lead_id": lead_id},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to record rate limit entry: {e}")


def get_current_rates(db: Session, user_id: Optional[int] = None) -> dict:
    """Get current usage rates for display in dashboard."""
    result = {}
    if user_id:
        result["user_last_minute"] = _count_recent(db, "user_id", user_id, 60)
        result["user_last_hour"] = _count_recent(db, "user_id", user_id, 3600)
        result["user_today"] = _count_recent(db, "user_id", user_id, 86400)
    result["global_last_minute"] = _count_global_recent(db, 60)
    result["global_last_hour"] = _count_global_recent(db, 3600)
    result["limits"] = {
        "per_lead_hour": LIMITS["per_lead_hour"][1],
        "per_lead_day": LIMITS["per_lead_day"][1],
        "per_user_hour": LIMITS["per_user_hour"][1],
    }
    return result


def cleanup_old_rate_records(db: Session, hours: int = 48):
    """Remove rate limit records older than specified hours (run periodically)."""
    try:
        db.execute(
            text("""
                DELETE FROM sms_rate_limit_log
                WHERE sent_at < NOW() - INTERVAL ':hours hours'
            """.replace(":hours", str(hours))),
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Rate limit cleanup failed: {e}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _count_recent(
    db: Session, column: str, value: int, window_seconds: int
) -> int:
    """Count messages for a specific lead_id or user_id within a time window."""
    if column not in ("lead_id", "user_id"):
        return 0
    try:
        row = db.execute(
            text(f"""
                SELECT COUNT(*)
                FROM sms_rate_limit_log
                WHERE {column} = :value
                  AND sent_at >= NOW() - INTERVAL '{window_seconds} seconds'
            """),
            {"value": value},
        ).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def _count_global_recent(db: Session, window_seconds: int) -> int:
    """Count all messages within a time window."""
    try:
        row = db.execute(
            text(f"""
                SELECT COUNT(*)
                FROM sms_rate_limit_log
                WHERE sent_at >= NOW() - INTERVAL '{window_seconds} seconds'
            """),
        ).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0
