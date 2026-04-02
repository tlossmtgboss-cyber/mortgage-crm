"""
LO Availability Models — Real-time presence and transfer readiness.

Tracks loan officer online status, call transfer capacity, and weekly
schedule windows.  Used by the telephony layer to determine whether an
LO can receive a live call transfer.

Tables:
- lo_availability:           Real-time presence / status per LO
- lo_availability_schedules: Weekly recurring schedule windows per LO

These are DISTINCT from recurring_availability / AvailabilityException
(which drive the Smart Scheduler booking calendar).  This module tracks
*telephony presence* — whether an LO is online, on a call, in DND, etc.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Time,
    ForeignKey, Index, CheckConstraint,
)
from sqlalchemy.orm import relationship
import enum

from db import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LOStatus(str, enum.Enum):
    """Real-time availability status for call transfers."""
    AVAILABLE = "available"
    BUSY = "busy"
    ON_CALL = "on_call"
    DND = "dnd"
    OFFLINE = "offline"
    AWAY = "away"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class LOAvailability(Base):
    """
    Real-time presence / transfer-readiness record for a single LO.

    One row per user.  Created lazily on first status update or heartbeat.
    """
    __tablename__ = "lo_availability"
    __table_args__ = (
        Index("ix_lo_avail_org_status", "organization_id", "status"),
        Index("ix_lo_avail_user", "user_id", unique=True),
        Index("ix_lo_avail_heartbeat", "last_heartbeat_at"),
        CheckConstraint(
            "status IN ('available', 'busy', 'on_call', 'dnd', 'offline', 'away')",
            name="ck_lo_availability_status",
        ),
        CheckConstraint(
            "active_transfer_count >= 0",
            name="ck_lo_availability_transfer_count_nonneg",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Current status
    status = Column(String(20), nullable=False, default=LOStatus.OFFLINE.value)
    status_reason = Column(String(255), nullable=True)  # "In meeting", "On lunch"

    # Whether status auto-updates from call activity
    auto_status = Column(Boolean, nullable=False, default=True)

    # Daily availability window (nullable = always available during schedule)
    available_from = Column(Time, nullable=True)
    available_until = Column(Time, nullable=True)
    timezone = Column(String(100), nullable=False, default="America/Chicago")

    # Transfer capacity
    max_concurrent_transfers = Column(Integer, nullable=False, default=1)
    active_transfer_count = Column(Integer, nullable=False, default=0)

    # Heartbeat — used to detect stale/offline LOs
    last_heartbeat_at = Column(DateTime, nullable=True)

    # Timestamps
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", lazy="select")
    organization = relationship("Organization", lazy="select")


class LOAvailabilitySchedule(Base):
    """
    Weekly recurring schedule window controlling when an LO accepts transfers.

    Multiple rows per day are allowed (e.g., morning + afternoon blocks).
    day_of_week follows ISO: 0=Monday ... 6=Sunday.
    """
    __tablename__ = "lo_availability_schedules"
    __table_args__ = (
        Index("ix_lo_avail_sched_user_dow", "user_id", "day_of_week"),
        Index("ix_lo_avail_sched_org", "organization_id"),
        CheckConstraint(
            "day_of_week >= 0 AND day_of_week <= 6",
            name="ck_lo_avail_sched_dow",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    day_of_week = Column(Integer, nullable=False)  # 0=Mon ... 6=Sun
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    is_available = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", lazy="select")
    organization = relationship("Organization", lazy="select")
