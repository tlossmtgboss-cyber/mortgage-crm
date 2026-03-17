"""
Recovery Opt-Out Model

Tracks attendees who have opted out of no-show recovery message sequences.
Supports per-organization opt-out so that an attendee can opt out from one
company's recovery messages without affecting another.

Tables:
    - recovery_opt_outs: Per-email, per-org opt-out records
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text,
    UniqueConstraint, Index,
)

from db import Base


class RecoveryOptOut(Base):
    """
    Tracks attendees who have opted out of automated no-show recovery
    messages (SMS and email).

    An attendee can opt out by:
    - Clicking the opt-out link in a recovery email
    - Replying STOP to a recovery SMS
    - Being flagged as a chronic no-show (3+ in 90 days)

    Opt-outs are scoped per organization so that opting out of recovery
    messages from Company A does not affect Company B.
    """
    __tablename__ = "recovery_opt_outs"
    __table_args__ = (
        UniqueConstraint('email', 'organization_id', name='uq_optout_email_org'),
        Index('ix_recovery_optout_org', 'organization_id'),
        Index('ix_recovery_optout_email', 'email'),
        {'extend_existing': True},
    )

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # When and why the opt-out occurred
    opted_out_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    reason = Column(String(500), nullable=True)
    # Source of the opt-out: "link", "sms_stop", "chronic_no_show", "manual"
    opt_out_source = Column(String(50), default="link")

    # Optional: the appointment that triggered the opt-out
    triggered_by_appointment_id = Column(
        Integer,
        ForeignKey("scheduler_appointments.id", ondelete="SET NULL"),
        nullable=True,
    )
