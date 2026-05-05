"""
SOC 2 Type II Password Policy Enforcement — CC6.1

Provides password complexity validation, history-based reuse prevention,
expiry checks, and account lockout with configurable thresholds.

Design decisions:
  - Common password list is embedded as a frozenset (top 10,000) loaded lazily
    from a bundled text file. Falls back to a hardcoded top-200 subset if the
    file is missing.
  - Password history comparison uses bcrypt.checkpw (constant-time)
    against up to HISTORY_DEPTH stored hashes.
  - All datetime comparisons use naive UTC to match the User model's
    Column(DateTime) convention (see account_lockout.py).

Usage:
    from auth.password_policy import (
        validate_password,
        check_password_expiry,
        record_failed_login,
        check_account_locked,
        record_password_change,
    )
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import bcrypt
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — all tunables in one place
# ---------------------------------------------------------------------------

MIN_LENGTH = 12
HISTORY_DEPTH = 12          # Reject reuse of last N passwords
PASSWORD_EXPIRY_DAYS = 90   # Default; overridable per-org in the future
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 30

# Direct bcrypt usage (replaces passlib CryptContext)

# ---------------------------------------------------------------------------
# Common password list
# ---------------------------------------------------------------------------

_COMMON_PASSWORDS: Optional[frozenset] = None


def _load_common_passwords() -> frozenset:
    """Load the common-password blocklist.

    Tries ``auth/common_passwords.txt`` first (one password per line).
    Falls back to a hardcoded top-200 list so the policy still fires even
    if the file is missing.
    """
    global _COMMON_PASSWORDS
    if _COMMON_PASSWORDS is not None:
        return _COMMON_PASSWORDS

    passwords: set = set()

    # Try loading from file
    txt_path = Path(__file__).parent / "common_passwords.txt"
    if txt_path.exists():
        try:
            with open(txt_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    pw = line.strip()
                    if pw and not pw.startswith("#"):
                        passwords.add(pw.lower())
            logger.info("Loaded %d common passwords from %s", len(passwords), txt_path)
        except Exception as exc:
            logger.warning("Failed to read common_passwords.txt: %s", exc)

    # Hardcoded fallback — top 200 most common passwords (NIST / Have I Been Pwned)
    if not passwords:
        passwords = {
            "123456", "password", "12345678", "qwerty", "123456789",
            "12345", "1234", "111111", "1234567", "dragon",
            "123123", "baseball", "abc123", "football", "monkey",
            "letmein", "shadow", "master", "666666", "qwertyuiop",
            "123321", "mustang", "1234567890", "michael", "654321",
            "superman", "1qaz2wsx", "7777777", "121212", "000000",
            "qazwsx", "123qwe", "killer", "trustno1", "jordan",
            "jennifer", "zxcvbnm", "asdfgh", "hunter", "buster",
            "soccer", "harley", "batman", "andrew", "tigger",
            "sunshine", "iloveyou", "2000", "charlie", "robert",
            "thomas", "hockey", "ranger", "daniel", "starwars",
            "klaster", "112233", "george", "computer", "michelle",
            "jessica", "pepper", "1111", "zxcvbn", "555555",
            "11111111", "131313", "freedom", "777777", "pass",
            "maggie", "159753", "aaaaaa", "ginger", "princess",
            "joshua", "cheese", "amanda", "summer", "love",
            "ashley", "nicole", "chelsea", "biteme", "matthew",
            "access", "yankees", "987654321", "dallas", "austin",
            "thunder", "taylor", "matrix", "mobilemail", "mom",
            "monitor", "monitoring", "montana", "moon", "moscow",
            "password1", "password12", "password123", "passw0rd",
            "admin", "admin123", "root", "toor", "login",
            "welcome", "welcome1", "welcome123", "changeme",
            "p@ssw0rd", "p@ssword", "qwerty123", "letmein1",
            "test", "test123", "guest", "guest123", "default",
            "hello", "hello123", "secret", "secret123",
            "fuckyou", "asshole", "fuck", "shit", "damn",
            "1q2w3e4r", "1q2w3e", "q1w2e3r4", "zaq1xsw2",
            "abcdef", "abcd1234", "abc1234", "1a2b3c4d",
            "aaa111", "qwe123", "123abc", "a1b2c3",
            "pass123", "pass1234", "pa55word", "passpass",
            "football1", "baseball1", "basketball", "soccer1",
            "jennifer1", "jordan23", "michael1", "thomas1",
            "internet", "service", "canada", "texas",
            "robert1", "time", "homerun", "yankee",
            "friends", "cool", "lovely", "butterfly",
            "purple", "angel", "angels", "diamond",
            "dolphins", "tiger", "tigers", "phoenix",
            "cookie", "happy", "flower", "flowers",
            "rainbow", "guitar", "samantha", "whatever",
            "nothing", "midnight", "microsoft", "lakers",
            "andrea", "victoria", "jasmine", "animate",
            "prince", "family", "williiam", "fishing",
            "chocolate", "jackson", "richard", "1234abcd",
            "golfer", "cheese1", "goldfish", "garden",
            "graduate", "creative", "sparky", "peanut",
            "scooter", "travis", "racing", "eagles",
            "corvette", "mercedes", "coffee", "brandon",
            "diamond1", "winter", "steven", "junior",
        }
        logger.info("Using hardcoded fallback common-password list (%d entries)", len(passwords))

    _COMMON_PASSWORDS = frozenset(passwords)
    return _COMMON_PASSWORDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    """Naive UTC now — matches Column(DateTime) storage convention."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utcnow_aware() -> datetime:
    """Aware UTC now — for Column(DateTime(timezone=True)) comparisons."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_password(
    password: str,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> Tuple[bool, List[str]]:
    """Validate a password against SOC 2 Type II complexity and reuse rules.

    Args:
        password:  Candidate plaintext password.
        user_id:   If provided (with ``db``), also checks password history.
        db:        SQLAlchemy session for history lookup.

    Returns:
        ``(True, [])`` if the password passes all checks, or
        ``(False, ["violation 1", ...])`` with human-readable violation messages.
    """
    violations: List[str] = []

    # --- Length ---
    if len(password) < MIN_LENGTH:
        violations.append(
            f"Password must be at least {MIN_LENGTH} characters (currently {len(password)})."
        )

    # --- Character class diversity ---
    if not re.search(r"[A-Z]", password):
        violations.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        violations.append("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        violations.append("Password must contain at least one digit.")
    if not re.search(r"""[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?`~]""", password):
        violations.append("Password must contain at least one special character.")

    # --- Common password check ---
    common = _load_common_passwords()
    if password.lower() in common:
        violations.append("Password is too common. Choose a more unique password.")

    # --- Password history (reuse prevention) ---
    if user_id is not None and db is not None:
        try:
            from database.models.password_history import PasswordHistory

            recent_hashes = (
                db.query(PasswordHistory.hashed_password)
                .filter(PasswordHistory.user_id == user_id)
                .order_by(PasswordHistory.created_at.desc())
                .limit(HISTORY_DEPTH)
                .all()
            )
            for (old_hash,) in recent_hashes:
                try:
                    if bcrypt.checkpw(password.encode(), old_hash.encode()):
                        violations.append(
                            f"Password was used recently. "
                            f"You cannot reuse any of your last {HISTORY_DEPTH} passwords."
                        )
                        break
                except Exception:
                    # Corrupted hash — skip silently
                    continue
        except Exception as exc:
            # Table may not exist yet (pre-migration). Log and continue.
            logger.debug("Password history check skipped: %s", exc)

    return (len(violations) == 0, violations)


def check_password_expiry(user) -> bool:
    """Return ``True`` if the user's password is expired (older than PASSWORD_EXPIRY_DAYS).

    Uses ``user.password_changed_at`` (DateTime(timezone=True)).  If the
    column is NULL (never set), the password is considered expired so the
    user is forced to update it.
    """
    changed_at = getattr(user, "password_changed_at", None)
    if changed_at is None:
        # Never recorded — treat as expired to force a reset
        return True

    # Normalize to aware datetime for comparison
    now = _utcnow_aware()
    if changed_at.tzinfo is None:
        # Column stored as naive — assume UTC
        from datetime import timezone as _tz
        changed_at = changed_at.replace(tzinfo=_tz.utc)

    expiry_date = changed_at + timedelta(days=PASSWORD_EXPIRY_DAYS)
    return now > expiry_date


def record_failed_login(
    user_id: int,
    db: Session,
    ip_address: Optional[str] = None,
    failure_reason: Optional[str] = None,
) -> None:
    """Append an immutable failed-login record to the audit log.

    This does NOT update ``User.failed_login_attempts`` or ``User.locked_until``
    — the existing ``auth.account_lockout.record_failed_login`` handles the
    in-model counter. Call both if you want counter-based lockout AND the
    audit trail.
    """
    try:
        from database.models.password_history import LoginAttempt

        attempt = LoginAttempt(
            user_id=user_id,
            ip_address=ip_address,
            success=False,
            failure_reason=failure_reason or "invalid_password",
        )
        db.add(attempt)
        db.commit()
    except Exception as exc:
        logger.debug("Failed to record login attempt: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


def record_successful_login(
    user_id: int,
    db: Session,
    ip_address: Optional[str] = None,
) -> None:
    """Append an immutable successful-login record to the audit log."""
    try:
        from database.models.password_history import LoginAttempt

        attempt = LoginAttempt(
            user_id=user_id,
            ip_address=ip_address,
            success=True,
        )
        db.add(attempt)
        db.commit()
    except Exception as exc:
        logger.debug("Failed to record successful login: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


def check_account_locked(
    user_id: int,
    db: Session,
) -> Tuple[bool, int]:
    """Check whether an account is locked based on the User model columns.

    Returns:
        ``(is_locked, minutes_remaining)`` — if not locked, minutes_remaining
        is 0.

    This reads the same ``User.locked_until`` that
    ``auth.account_lockout`` writes, providing a consistent view.
    """
    try:
        from database.models.core import User

        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            return (False, 0)

        if user.locked_until is None:
            return (False, 0)

        now = _utcnow()
        locked_until = user.locked_until
        # Normalize — strip tzinfo if present (column is naive DateTime)
        if hasattr(locked_until, "tzinfo") and locked_until.tzinfo is not None:
            locked_until = locked_until.replace(tzinfo=None)

        if now < locked_until:
            remaining = (locked_until - now).total_seconds() / 60.0
            return (True, max(1, int(remaining)))

        return (False, 0)
    except Exception as exc:
        logger.debug("Account lock check failed: %s", exc)
        return (False, 0)


def record_password_change(
    user_id: int,
    hashed_password: str,
    db: Session,
) -> None:
    """Store the hashed password in the history table for reuse prevention.

    Also updates ``User.password_changed_at`` so expiry tracking works.
    Should be called every time a user's password is changed.
    """
    try:
        from database.models.password_history import PasswordHistory
        from database.models.core import User

        # Append to history
        entry = PasswordHistory(
            user_id=user_id,
            hashed_password=hashed_password,
        )
        db.add(entry)

        # Update the user's password_changed_at timestamp
        user = db.query(User).filter(User.id == user_id).first()
        if user is not None:
            user.password_changed_at = _utcnow_aware()

        db.commit()
        logger.info("Password change recorded for user_id=%s", user_id)
    except Exception as exc:
        logger.warning("Failed to record password change: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
