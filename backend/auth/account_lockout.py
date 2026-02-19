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


def check_account_locked(user) -> bool:
    """Check if account is currently locked."""
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        return True
    return False


def record_failed_login(db: Session, user) -> dict:
    """Record a failed login attempt and lock if threshold exceeded."""
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    user.last_failed_login_at = datetime.now(timezone.utc)

    if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        logger.warning(f"Account locked for user {user.email} after {user.failed_login_attempts} failed attempts")
        db.commit()
        return {
            "locked": True,
            "locked_until": user.locked_until.isoformat(),
            "attempts": user.failed_login_attempts,
        }

    db.commit()
    return {
        "locked": False,
        "attempts": user.failed_login_attempts,
        "remaining": MAX_FAILED_ATTEMPTS - user.failed_login_attempts,
    }


def reset_failed_login(db: Session, user):
    """Reset failed login counter after successful login."""
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_failed_login_at = None
    db.commit()


def unlock_account(db: Session, user):
    """Admin action to manually unlock an account."""
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    logger.info(f"Account manually unlocked for user {user.email}")
