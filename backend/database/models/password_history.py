"""
Password Policy Models — SOC 2 Type II CC6.1

Tracks password history (reuse prevention) and login attempts (lockout audit trail).

PasswordHistory: Stores bcrypt hashes of previous passwords so users cannot
cycle back to a recently used credential. SOC 2 requires retaining at least
the last 12 hashes.

LoginAttempt: Immutable append-only log of every authentication attempt
(success or failure) with IP address for forensic analysis. Distinct from the
in-model `failed_login_attempts` counter on the User table — this table
provides the audit trail while the counter drives the lockout decision.

Usage:
    from database.models.password_history import PasswordHistory, LoginAttempt
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)

from db import Base


class PasswordHistory(Base):
    """Hashed password archive for reuse prevention (SOC 2 CC6.1)."""
    __tablename__ = "password_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # Speed up "last N passwords for user" lookups
        Index("ix_password_history_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<PasswordHistory user_id={self.user_id} created_at={self.created_at}>"


class LoginAttempt(Base):
    """Immutable login attempt log for lockout tracking and forensics (SOC 2 CC6.1)."""
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    attempted_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    success = Column(Boolean, nullable=False, default=False)
    failure_reason = Column(String(100), nullable=True)  # locked, invalid_password, expired, etc.

    __table_args__ = (
        # Speed up "recent attempts for user" and lockout window queries
        Index("ix_login_attempts_user_attempted", "user_id", "attempted_at"),
    )

    def __repr__(self) -> str:
        return f"<LoginAttempt user_id={self.user_id} success={self.success} at={self.attempted_at}>"
