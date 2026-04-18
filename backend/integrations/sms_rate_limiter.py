# backend/integrations/sms_rate_limiter.py
# DB-backed rate limiting for SMS sends (per-user, per-lead, per-recipient, global)
# Prevents carrier filtering and TCPA overages

import logging
import os
import random
import re
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

# ---------------------------------------------------------------------------
# Per-recipient frequency caps (env-configurable)
# ---------------------------------------------------------------------------
SMS_MAX_PER_DAY = int(os.getenv("SMS_MAX_PER_DAY", "3"))
SMS_MAX_PER_WEEK = int(os.getenv("SMS_MAX_PER_WEEK", "10"))


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

    # Probabilistic cleanup — ~1% of calls trigger old record purge
    if random.random() < 0.01:
        try:
            cleanup_old_rate_records(db, days_to_keep=7)
        except Exception:
            pass  # Non-critical cleanup failure

    return True, "Rate limit check passed"


def record_send_attempt(
    db: Session,
    to_phone: str,
    user_id: Optional[int] = None,
    lead_id: Optional[int] = None,
):
    """Record a send attempt for rate limiting purposes.

    Flushes but does NOT commit — caller controls the transaction.
    """
    try:
        db.execute(
            text("""
                INSERT INTO sms_rate_limit_log
                  (to_phone, user_id, lead_id, sent_at)
                VALUES (:phone, :user_id, :lead_id, NOW())
            """),
            {"phone": to_phone, "user_id": user_id, "lead_id": lead_id},
        )
        db.flush()
    except Exception as e:
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


def check_recipient_frequency(
    phone_number: str,
    organization_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> dict:
    """
    Check per-recipient frequency caps to prevent spamming a single contact.

    Queries sms_rate_limit_log for recent sends to this phone number.
    Returns a dict with:
        allowed (bool), reason (str), sent_today (int), sent_this_week (int)

    Limits are configurable via SMS_MAX_PER_DAY / SMS_MAX_PER_WEEK env vars.
    """
    result = {
        "allowed": True,
        "reason": "Recipient frequency check passed",
        "sent_today": 0,
        "sent_this_week": 0,
    }

    if not db or not phone_number:
        return result

    # Normalize phone for consistent matching
    normalized = _normalize_phone_for_lookup(phone_number)
    if not normalized:
        return result

    try:
        row_day = db.execute(
            text(f"""
                SELECT COUNT(*)
                FROM sms_rate_limit_log
                WHERE to_phone = :phone
                  AND sent_at >= NOW() - INTERVAL '24 hours'
            """),
            {"phone": normalized},
        ).fetchone()
        sent_today = row_day[0] if row_day else 0

        row_week = db.execute(
            text(f"""
                SELECT COUNT(*)
                FROM sms_rate_limit_log
                WHERE to_phone = :phone
                  AND sent_at >= NOW() - INTERVAL '7 days'
            """),
            {"phone": normalized},
        ).fetchone()
        sent_this_week = row_week[0] if row_week else 0

        result["sent_today"] = sent_today
        result["sent_this_week"] = sent_this_week

        if sent_today >= SMS_MAX_PER_DAY:
            result["allowed"] = False
            result["reason"] = (
                f"Daily frequency cap exceeded: {sent_today} messages sent today "
                f"(max {SMS_MAX_PER_DAY}/day per recipient)"
            )
            return result

        if sent_this_week >= SMS_MAX_PER_WEEK:
            result["allowed"] = False
            result["reason"] = (
                f"Weekly frequency cap exceeded: {sent_this_week} messages sent this week "
                f"(max {SMS_MAX_PER_WEEK}/week per recipient)"
            )
            return result

    except Exception as e:
        # Fail-open: rate limiting is carrier protection, not TCPA compliance.
        # Consent/DNC checks already gate TCPA; missing rate-limit infrastructure
        # should not block sends entirely.
        logger.warning(f"Recipient frequency check failed (allowing send): {e}")
        try:
            db.rollback()
        except Exception:
            pass

    return result


def _normalize_phone_for_lookup(phone: str) -> Optional[str]:
    """Normalize phone to E.164 for consistent rate-limit lookups."""
    if not phone:
        return None
    digits = re.sub(r"[^\d]", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if phone.startswith("+") and len(digits) >= 10:
        return f"+{digits}"
    # Return as-is if already formatted — the rate_limit_log stores whatever was passed
    return phone


def cleanup_old_rate_records(db: Session, days_to_keep: int = 7):
    """Remove rate limit records older than specified days.

    Default 7 days preserves the window needed for weekly frequency caps.
    Deletes in bounded batches (10,000 rows) to avoid long-running queries.
    Flushes but does NOT commit — caller controls the transaction.
    """
    try:
        result = db.execute(
            text("""
                DELETE FROM sms_rate_limit_log
                WHERE ctid IN (
                    SELECT ctid FROM sms_rate_limit_log
                    WHERE sent_at < NOW() - INTERVAL '1 day' * :days
                    LIMIT 10000
                )
            """),
            {"days": days_to_keep},
        )
        db.flush()
        deleted = result.rowcount
        if deleted > 0:
            logger.info(f"Rate limit cleanup: deleted {deleted} records older than {days_to_keep} days")
    except Exception as e:
        logger.error(f"Rate limit cleanup failed: {e}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
VALID_COLUMNS = {"lead_id": "lead_id", "user_id": "user_id"}


def _count_recent(
    db: Session, column: str, value: int, window_seconds: int
) -> int:
    """Count messages for a specific lead_id or user_id within a time window."""
    if column not in VALID_COLUMNS:
        return 0
    safe_column = VALID_COLUMNS[column]
    try:
        row = db.execute(
            text(f"""
                SELECT COUNT(*)
                FROM sms_rate_limit_log
                WHERE {safe_column} = :value
                  AND sent_at >= NOW() - make_interval(secs => :window)
            """),
            {"value": value, "window": window_seconds},
        ).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def _count_global_recent(db: Session, window_seconds: int) -> int:
    """Count all messages within a time window."""
    try:
        row = db.execute(
            text("""
                SELECT COUNT(*)
                FROM sms_rate_limit_log
                WHERE sent_at >= NOW() - make_interval(secs => :window)
            """),
            {"window": window_seconds},
        ).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0
