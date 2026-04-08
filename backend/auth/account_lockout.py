"""
Account Lockout Service
Prevents brute-force attacks by locking accounts after failed attempts.
Enterprise Readiness Check 4.4
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 30


def _utcnow_naive() -> datetime:
    """Return current UTC time as a naive datetime.

    The User.locked_until column is Column(DateTime) — a PostgreSQL
    ``timestamp without time zone``.  Values written with tzinfo are
    stored with the timezone stripped, and values read back are naive.
    Comparing a naive DB value against an aware datetime raises TypeError.
    Using naive UTC everywhere avoids this mismatch.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def check_account_locked(user) -> bool:
    """Check if account is currently locked."""
    if user.locked_until and user.locked_until > _utcnow_naive():
        return True
    return False


def record_failed_login(db: Session, user) -> dict:
    """Record a failed login attempt and lock if threshold exceeded."""
    try:
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        user.last_failed_login_at = _utcnow_naive()

        locked = user.failed_login_attempts >= MAX_FAILED_ATTEMPTS
        if locked:
            user.locked_until = _utcnow_naive() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            logger.warning(f"Account locked for user {user.email} after {user.failed_login_attempts} failed attempts")

        db.commit()

        if locked:
            return {
                "locked": True,
                "locked_until": user.locked_until.isoformat(),
                "attempts": user.failed_login_attempts,
            }
        return {
            "locked": False,
            "attempts": user.failed_login_attempts,
            "remaining": MAX_FAILED_ATTEMPTS - user.failed_login_attempts,
        }
    except Exception as e:
        logger.warning(f"Failed to record login attempt: {type(e).__name__}: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return {"locked": False, "attempts": 0, "error": str(e)}


def reset_failed_login(db: Session, user):
    """Reset failed login counter after successful login."""
    try:
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_failed_login_at = None
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to reset login counter: {type(e).__name__}: {e}")
        try:
            db.rollback()
        except Exception:
            pass


def unlock_account(db: Session, user):
    """Admin action to manually unlock an account."""
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    logger.info(f"Account manually unlocked for user {user.email}")
