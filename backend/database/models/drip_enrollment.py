"""
Drip Enrollment Models — persistent enrollment and event tracking for drip campaigns.

Replaces in-memory dict storage that was lost on every deployment.

Models:
    DripEnrollment: Tracks a lead's enrollment in a drip sequence
    DripEnrollmentEvent: Immutable event log for enrollment lifecycle
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from db import Base


class DripEnrollment(Base):
    """Persistent drip sequence enrollment record.

    Tracks a lead's progress through a drip campaign sequence including
    current step, status, and scheduling for the next outreach.
    """
    __tablename__ = "drip_enrollments"
    __table_args__ = (
        Index("ix_drip_enroll_org_lead", "organization_id", "lead_id"),
        Index("ix_drip_enroll_seq_status", "sequence_id", "status"),
        Index("ix_drip_enroll_next_step", "next_step_at"),
        Index("ix_drip_enroll_status", "status"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)

    # Which sequence — references drip_sequences table if DB-managed,
    # or stores template key name for static templates
    sequence_id = Column(Integer, ForeignKey("drip_sequences.id", ondelete="SET NULL"), nullable=True)
    sequence_name = Column(String(100), nullable=False)  # template key, e.g. "purchase_12_month"

    # Lifecycle
    status = Column(String(20), nullable=False, default="active")
    # Valid statuses: active, paused, completed, cancelled, exited

    # Progress tracking
    current_step_index = Column(Integer, default=0)

    # Timestamps
    enrolled_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    paused_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    next_step_at = Column(DateTime, nullable=True)

    # Exit / cancellation context
    exit_reason = Column(Text, nullable=True)

    # Flexible metadata (trigger data, channel preferences, etc.)
    extra_metadata = Column("metadata", JSONB, default=dict)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    events = relationship("DripEnrollmentEvent", back_populates="enrollment",
                          cascade="all, delete-orphan", lazy="dynamic")


class DripEnrollmentEvent(Base):
    """Immutable event log for drip enrollment lifecycle.

    Every state change (enroll, step sent, pause, resume, complete, exit, switch)
    is recorded as an append-only event for audit and analytics.
    """
    __tablename__ = "drip_enrollment_events"
    __table_args__ = (
        Index("ix_drip_event_enrollment", "enrollment_id"),
        Index("ix_drip_event_created", "created_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    enrollment_id = Column(Integer, ForeignKey("drip_enrollments.id", ondelete="CASCADE"), nullable=False, index=True)

    # Event classification
    event_type = Column(String(30), nullable=False)
    # Valid types: enrolled, step_sent, paused, resumed, completed, exited, switched, cancelled

    # Step context (which step triggered this event)
    step_index = Column(Integer, nullable=True)
    channel = Column(String(20), nullable=True)  # sms, email, voicemail, push
    message_id = Column(String(100), nullable=True)  # external message ID for tracking

    # Additional context
    detail = Column(Text, nullable=True)
    extra_metadata = Column("metadata", JSONB, default=dict)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    enrollment = relationship("DripEnrollment", back_populates="events")


__all__ = [
    "DripEnrollment",
    "DripEnrollmentEvent",
]
