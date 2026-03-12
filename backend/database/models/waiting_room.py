"""
Waiting Room / Queue Management Models

WaitlistEntry tracks people waiting for appointment openings.
When an appointment is cancelled, the system can auto-offer the slot
to the next person on the waitlist whose preferences match.

Tables:
- waitlist_entries: Queue of people waiting for appointment slots
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Text,
    Index, Enum as SQLEnum,
)
from sqlalchemy.orm import relationship
import enum

from db import Base


# ============================================================================
# ENUMS
# ============================================================================

class WaitlistStatus(str, enum.Enum):
    WAITING = "waiting"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# ============================================================================
# WAITLIST ENTRY MODEL
# ============================================================================

class WaitlistEntry(Base):
    """
    A single entry on a waitlist for a specific appointment type within an org.
    Tracks position, preferences, and offer lifecycle.
    """
    __tablename__ = "waitlist_entries"
    __table_args__ = (
        Index("ix_waitlist_org_type_status", "organization_id", "appointment_type_id", "status"),
        Index("ix_waitlist_org_position", "organization_id", "appointment_type_id", "position"),
        Index("ix_waitlist_status", "status"),
        Index("ix_waitlist_email", "email"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    appointment_type_id = Column(
        Integer,
        ForeignKey("appointment_types.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # User reference (nullable for public/anonymous waitlist joins)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Contact info (always stored, even for logged-in users)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(30), nullable=True)

    # Preferences (JSON arrays)
    # preferred_dates: ["2026-03-15", "2026-03-16", ...]
    preferred_dates = Column(JSON, default=list)
    # preferred_times: ["morning", "afternoon", "evening"] or ["09:00-12:00", "14:00-17:00"]
    preferred_times = Column(JSON, default=list)

    # Queue position (1-based, unique per org+appointment_type among active entries)
    position = Column(Integer, nullable=False, default=0)

    # Status lifecycle: WAITING -> OFFERED -> ACCEPTED/EXPIRED/CANCELLED
    status = Column(
        SQLEnum(WaitlistStatus),
        nullable=False,
        default=WaitlistStatus.WAITING,
    )

    # Offer tracking
    offered_at = Column(DateTime, nullable=True)
    offered_slot_time = Column(DateTime, nullable=True)  # The specific slot offered
    expires_at = Column(DateTime, nullable=True)  # When the offer expires (24h after offered_at)

    # Result tracking
    accepted_at = Column(DateTime, nullable=True)
    appointment_id = Column(
        Integer,
        ForeignKey("scheduler_appointments.id", ondelete="SET NULL"),
        nullable=True,
    )  # Set when offer is accepted and appointment created

    # Notes
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    organization = relationship("Organization", backref="waitlist_entries")
