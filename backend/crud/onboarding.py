from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timedelta, timezone
from typing import Optional, TYPE_CHECKING
import random

# Avoid circular import - models are accessed through db.query()
# Type hints use string literals to avoid import at runtime
if TYPE_CHECKING:
    from database.models import VerificationToken


def generate_verification_code() -> str:
    """Generate a 6-digit verification code"""
    return str(random.randint(100000, 999999))


def create_verification_token(
    db: Session,
    user_id: int,
    token_type: str
):
    """Create a new verification token"""
    # Import here to avoid circular import
    from database.models import VerificationToken

    token = generate_verification_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    token_obj = VerificationToken(
        user_id=user_id,
        token_type=token_type,
        token=token,
        expires_at=expires_at
    )

    db.add(token_obj)
    db.commit()
    db.refresh(token_obj)
    return token_obj


def verify_token(
    db: Session,
    user_id: int,
    token: str,
    token_type: str
):
    """Verify a token and mark it as used"""
    # Import here to avoid circular import
    from database.models import VerificationToken

    token_obj = db.query(VerificationToken).filter(
        and_(
            VerificationToken.user_id == user_id,
            VerificationToken.token == token,
            VerificationToken.token_type == token_type,
            VerificationToken.used_at.is_(None),
            VerificationToken.expires_at > datetime.now(timezone.utc)
        )
    ).first()

    if token_obj:
        token_obj.used_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(token_obj)

    return token_obj


def count_recent_verifications(
    db: Session,
    user_id: int,
    token_type: str,
    hours: int = 1
) -> int:
    """Count verification attempts in the last N hours"""
    # Import here to avoid circular import
    from database.models import VerificationToken

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    count = db.query(VerificationToken).filter(
        and_(
            VerificationToken.user_id == user_id,
            VerificationToken.token_type == token_type,
            VerificationToken.created_at > cutoff
        )
    ).count()

    return count


def cleanup_expired_tokens(db: Session) -> int:
    """Delete expired tokens (run as scheduled job)"""
    # Import here to avoid circular import
    from database.models import VerificationToken

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)

    deleted = db.query(VerificationToken).filter(
        VerificationToken.expires_at < cutoff
    ).delete()

    db.commit()
    return deleted
