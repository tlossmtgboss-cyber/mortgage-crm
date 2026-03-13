"""
Cancellation Policy Model

Stores per-organization cancellation policy configuration for appointment scheduling.
Controls minimum notice periods, borrower cancellation limits, required reasons,
and late-cancel messaging.

Table: cancellation_policies (one row per org, upserted on save)

Usage:
    from database.models.cancellation_policy import CancellationPolicy
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from db import Base


DEFAULT_CANCELLATION_REASONS = [
    "Schedule conflict",
    "No longer needed",
    "Found another provider",
    "Personal emergency",
    "Need to reschedule",
    "Other",
]

DEFAULT_LATE_CANCEL_MESSAGE = (
    "This appointment is within the minimum notice period. "
    "Late cancellations may count toward your cancellation limit. "
    "Please consider rescheduling instead."
)


class CancellationPolicy(Base):
    """
    Organization-level cancellation policy for the appointment scheduler.

    One row per organization. Created with defaults on first access
    (via the service layer's get_or_create pattern).

    Fields:
        min_notice_hours: Minimum hours before appointment start for a free cancellation.
                          Cancellations within this window are flagged as "late".
        max_cancellations_per_borrower: Rolling 30-day limit on cancellations per borrower
                                         email. 0 = unlimited.
        allow_borrower_cancel: Whether borrowers can self-cancel via the portal/link.
                               When False, only staff can cancel.
        require_reason: Whether a cancellation reason is mandatory.
        cancellation_reasons: JSON array of preset reason strings shown in the UI dropdown.
        late_cancel_message: Message displayed to the user when cancelling within the
                             minimum notice window.
    """
    __tablename__ = "cancellation_policies"
    __table_args__ = (
        Index("ix_cancellation_policies_org", "organization_id", unique=True),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Policy settings
    min_notice_hours = Column(Integer, nullable=False, default=24)
    max_cancellations_per_borrower = Column(Integer, nullable=False, default=3)
    allow_borrower_cancel = Column(Boolean, nullable=False, default=True)
    require_reason = Column(Boolean, nullable=False, default=True)
    cancellation_reasons = Column(JSON, nullable=False, default=lambda: list(DEFAULT_CANCELLATION_REASONS))
    late_cancel_message = Column(Text, nullable=True, default=DEFAULT_LATE_CANCEL_MESSAGE)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
