"""
Account Lockout Service
Prevents brute-force attacks by locking accounts after failed attempts.
Enterprise Readiness Check 4.4

Two layers:
  1. **Per-username in-memory/Redis tracker** — catches distributed credential
     stuffing (same username, many IPs) and works even for non-existent accounts.
  2. **Per-user DB columns** (User.failed_login_attempts, User.locked_until) —
     persistent record that survives process restarts.

Both layers must pass for a login attempt to proceed.
"""
import logging
import os
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 10
LOCKOUT_DURATION_MINUTES = 30
LOCKOUT_WINDOW_SECONDS = LOCKOUT_DURATION_MINUTES * 60  # 1800 seconds

LOCKOUT_MESSAGE = (
    "Account temporarily locked due to too many failed attempts. "
    "Try again in 30 minutes."
)

# ---------------------------------------------------------------------------
# In-memory per-username tracker (fallback when Redis is unavailable)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
# {username_lower: [timestamp, timestamp, ...]}
_attempts: dict[str, list[float]] = {}
# {username_lower: unlock_timestamp}
_locked_until: dict[str, float] = {}


def _normalize(username: str) -> str:
    return username.strip().lower()


def _prune_old_attempts(key: str, now: float) -> list[float]:
    """Remove attempts outside the sliding window."""
    cutoff = now - LOCKOUT_WINDOW_SECONDS
    _attempts[key] = [ts for ts in _attempts.get(key, []) if ts > cutoff]
    return _attempts[key]


# ---------------------------------------------------------------------------
# Redis helpers (optional — degrades gracefully to in-memory)
# ---------------------------------------------------------------------------

_redis_client = None
_redis_init_attempted = False


def _get_redis():
    """Lazy-init Redis connection. Returns None if unavailable."""
    global _redis_client, _redis_init_attempted
    if _redis_init_attempted:
        return _redis_client
    _redis_init_attempted = True
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.debug("Account lockout: REDIS_URL not set, using in-memory fallback")
        return None
    try:
        import redis as _redis_lib
        _redis_client = _redis_lib.from_url(redis_url, socket_timeout=3)
        _redis_client.ping()
        logger.info("Account lockout: Redis connected for per-username tracking")
        return _redis_client
    except Exception as exc:
        logger.warning("Account lockout: Redis unavailable (%s), using in-memory fallback", exc)
        _redis_client = None
        return None


def _redis_key(username: str) -> str:
    return f"acct_lockout:{username}"


def _redis_lock_key(username: str) -> str:
    return f"acct_lockout_lock:{username}"


# ---------------------------------------------------------------------------
# Public API — per-username (in-memory / Redis)
# ---------------------------------------------------------------------------

def check_username_locked(username: str) -> Tuple[bool, int]:
    """Check if a username is locked due to too many failed attempts.

    Works for ANY username — the account does not need to exist in the DB.
    This is the first line of defense against distributed credential stuffing.

    Returns:
        (is_locked, minutes_remaining)
    """
    key = _normalize(username)
    r = _get_redis()

    if r is not None:
        try:
            lock_val = r.get(_redis_lock_key(key))
            if lock_val:
                remaining_seconds = r.ttl(_redis_lock_key(key))
                if remaining_seconds and remaining_seconds > 0:
                    return (True, max(1, remaining_seconds // 60))
                # TTL expired or key doesn't exist — not locked
            return (False, 0)
        except Exception as exc:
            logger.debug("Redis check_username_locked failed: %s", exc)
            # Fall through to in-memory

    # In-memory path
    now = time.time()
    with _lock:
        unlock_at = _locked_until.get(key, 0)
        if now < unlock_at:
            remaining = (unlock_at - now) / 60.0
            return (True, max(1, int(remaining)))
        elif unlock_at > 0:
            # Lock expired — clean up
            _locked_until.pop(key, None)
            _attempts.pop(key, None)
        return (False, 0)


def record_username_failure(username: str) -> dict:
    """Record a failed login attempt for a username.

    If the threshold is reached, locks the username for LOCKOUT_DURATION_MINUTES.

    Returns:
        dict with keys: locked (bool), attempts (int), remaining (int),
        and optionally locked_until (str).
    """
    key = _normalize(username)
    now = time.time()
    r = _get_redis()

    if r is not None:
        try:
            redis_key = _redis_key(key)
            # Atomic increment + expire via pipeline
            pipe = r.pipeline()
            pipe.lpush(redis_key, now)
            pipe.ltrim(redis_key, 0, MAX_FAILED_ATTEMPTS + 5)  # keep a bit more than needed
            pipe.expire(redis_key, LOCKOUT_WINDOW_SECONDS)
            pipe.execute()

            # Count recent attempts within window
            raw_attempts = r.lrange(redis_key, 0, -1)
            cutoff = now - LOCKOUT_WINDOW_SECONDS
            recent = [ts for ts in raw_attempts if float(ts) > cutoff]
            attempt_count = len(recent)

            if attempt_count >= MAX_FAILED_ATTEMPTS:
                # Set lock key
                r.setex(_redis_lock_key(key), LOCKOUT_WINDOW_SECONDS, "1")
                unlock_at = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
                logger.warning(
                    "Account lockout: username '%s' locked after %d failed attempts (Redis)",
                    key, attempt_count,
                )
                return {
                    "locked": True,
                    "locked_until": unlock_at.isoformat(),
                    "attempts": attempt_count,
                }

            return {
                "locked": False,
                "attempts": attempt_count,
                "remaining": MAX_FAILED_ATTEMPTS - attempt_count,
            }
        except Exception as exc:
            logger.debug("Redis record_username_failure failed: %s", exc)
            # Fall through to in-memory

    # In-memory path
    with _lock:
        attempts = _prune_old_attempts(key, now)
        attempts.append(now)
        attempt_count = len(attempts)

        if attempt_count >= MAX_FAILED_ATTEMPTS:
            unlock_at = now + LOCKOUT_WINDOW_SECONDS
            _locked_until[key] = unlock_at
            unlock_dt = datetime.fromtimestamp(unlock_at, tz=timezone.utc)
            logger.warning(
                "Account lockout: username '%s' locked after %d failed attempts (in-memory)",
                key, attempt_count,
            )
            return {
                "locked": True,
                "locked_until": unlock_dt.isoformat(),
                "attempts": attempt_count,
            }

        return {
            "locked": False,
            "attempts": attempt_count,
            "remaining": MAX_FAILED_ATTEMPTS - attempt_count,
        }


def clear_username_failures(username: str) -> None:
    """Clear failed attempt tracking for a username after successful login."""
    key = _normalize(username)
    r = _get_redis()

    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.delete(_redis_key(key))
            pipe.delete(_redis_lock_key(key))
            pipe.execute()
        except Exception as exc:
            logger.debug("Redis clear_username_failures failed: %s", exc)

    # Always clear in-memory too (may have been used as fallback)
    with _lock:
        _attempts.pop(key, None)
        _locked_until.pop(key, None)


# ---------------------------------------------------------------------------
# Public API — per-user DB columns (persistent, requires User ORM object)
# ---------------------------------------------------------------------------

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
    """Check if account is currently locked via DB columns."""
    if user.locked_until and user.locked_until > _utcnow_naive():
        return True
    return False


def record_failed_login(db: Session, user) -> dict:
    """Record a failed login attempt on the User model and lock if threshold exceeded."""
    try:
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        user.last_failed_login_at = _utcnow_naive()

        locked = user.failed_login_attempts >= MAX_FAILED_ATTEMPTS
        if locked:
            user.locked_until = _utcnow_naive() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            logger.warning(
                "Account locked (DB) for user %s after %d failed attempts",
                user.email, user.failed_login_attempts,
            )

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
        logger.warning("Failed to record login attempt (DB): %s: %s", type(e).__name__, e)
        try:
            db.rollback()
        except Exception:
            pass
        return {"locked": False, "attempts": 0, "error": str(e)}


def reset_failed_login(db: Session, user) -> None:
    """Reset failed login counter after successful login."""
    try:
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_failed_login_at = None
        db.commit()
    except Exception as e:
        logger.warning("Failed to reset login counter: %s: %s", type(e).__name__, e)
        try:
            db.rollback()
        except Exception:
            pass


def unlock_account(db: Session, user) -> None:
    """Admin action to manually unlock an account (clears both layers)."""
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    clear_username_failures(user.email)
    logger.info("Account manually unlocked for user %s", user.email)
