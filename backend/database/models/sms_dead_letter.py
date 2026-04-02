"""SMS Dead Letter — persists failed SMS messages for retry and monitoring."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, Index, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from db import Base


class SMSDeadLetter(Base):
    __tablename__ = "sms_dead_letters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    workflow_id = Column(Integer, ForeignKey("voice_workflows.id", ondelete="SET NULL"), nullable=True, index=True)
    to_phone = Column(String(20), nullable=False)
    from_phone = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    last_error = Column(Text, nullable=True)
    attempts = Column(Integer, default=3)
    status = Column(String(20), default="pending")  # pending, retried, resolved
    extra_metadata = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    retried_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_sms_dead_letters_org_status", "organization_id", "status"),
        {'extend_existing': True},
    )
