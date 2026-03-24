"""
Calendar Feed Token Model

Stores per-user iCalendar feed subscription tokens.
Each user can have one active feed token; generating a new token
revokes any previous one. The token is URL-safe and used in the
public ICS endpoint (no login required).

Tables:
- calendar_feed_tokens: Feed subscription tokens with access tracking
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship

from db import Base


class CalendarFeedToken(Base):
    """
    A URL-safe token that grants read-only access to a user's appointment
    calendar via an iCalendar (.ics) feed.
    """
    __tablename__ = "calendar_feed_tokens"
    __table_args__ = (
        Index("ix_calendar_feed_org_user", "organization_id", "user_id"),
        Index("ix_calendar_feed_token", "token", unique=True),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # URL-safe token (used in the public feed URL)
    token = Column(String(64), nullable=False, unique=True)

    # Controls
    is_active = Column(Boolean, default=True, nullable=False)
    include_details = Column(
        Boolean, default=True, nullable=False,
    )  # False = show only busy/free blocks (no titles, descriptions, attendees)

    # Expiration — tokens auto-expire after a set period (default 90 days)
    expires_at = Column(DateTime, nullable=True)  # NULL = legacy token (treat as expired)

    # Access tracking
    access_count = Column(Integer, default=0, nullable=False)
    last_accessed_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    organization = relationship("Organization", backref="calendar_feed_tokens")
    user = relationship("User", backref="calendar_feed_tokens")
