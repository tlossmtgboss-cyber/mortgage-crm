"""
Live Transfer Model

Tracks live call transfers between AI/caller and loan officers,
including whisper context and conference bridge state.

Usage:
    from database.models.live_transfer import LiveTransfer
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Index
)

from db import Base


class LiveTransfer(Base):
    """Tracks a live call transfer with whisper context."""
    __tablename__ = "live_transfers"
    __table_args__ = (
        Index("ix_live_transfers_org_status", "organization_id", "status"),
        Index("ix_live_transfers_lo", "lo_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # Call legs
    call_control_id = Column(String(255), nullable=False, index=True)
    caller_phone = Column(String(20))
    lo_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    lo_phone = Column(String(20))
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)

    # Whisper
    whisper_text = Column(Text)

    # Transfer config
    transfer_type = Column(String(20), default="warm")  # warm, cold

    # Status tracking
    status = Column(String(30), default="initiated")
    # initiated, lo_ringing, lo_answered, whisper_playing, bridged, completed, failed, timeout

    # Telnyx IDs
    conference_id = Column(String(255))
    caller_leg_id = Column(String(255))
    lo_leg_id = Column(String(255))
    lo_call_control_id = Column(String(255))

    # Failure tracking
    failure_reason = Column(Text)

    # Timestamps
    initiated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    lo_answered_at = Column(DateTime)
    whisper_completed_at = Column(DateTime)
    bridged_at = Column(DateTime)
    completed_at = Column(DateTime)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
