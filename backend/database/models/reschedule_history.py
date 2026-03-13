"""
Reschedule History Model

Tracks all reschedule events for appointments, including the original
and new times, reason, who requested it, and the self-service token
used for borrower-facing reschedule links.

Tables:
- reschedule_history: Append-only log of every reschedule action
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Index,
)
from sqlalchemy.orm import relationship

from db import Base


class RescheduleHistory(Base):
    """
    One row per reschedule action on an appointment.

    The combination of appointment_id rows forms the complete reschedule
    trail.  The reschedule_token + token_expires_at columns power the
    borrower self-service flow (public link, no login required).
    """
    __tablename__ = "reschedule_history"
    __table_args__ = (
        Index("ix_resched_hist_appointment", "appointment_id"),
        Index("ix_resched_hist_org", "organization_id"),
        Index("ix_resched_hist_token", "reschedule_token"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(
        Integer,
        ForeignKey("scheduler_appointments.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Original time window
    original_start = Column(DateTime, nullable=False)
    original_end = Column(DateTime, nullable=False)

    # New time window (populated when reschedule is confirmed)
    new_start = Column(DateTime, nullable=True)
    new_end = Column(DateTime, nullable=True)

    # Why and who
    reason = Column(String(1000), nullable=True)
    requested_by_type = Column(
        String(20), nullable=False, default="lo",
    )  # "borrower", "lo", "system"

    # Borrower self-service token (JWT, opaque to the DB)
    reschedule_token = Column(String(500), nullable=True, unique=True)
    token_expires_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
