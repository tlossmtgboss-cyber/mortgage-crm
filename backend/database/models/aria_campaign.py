"""
Aria Campaign models — mass text outreach with two-way SMS coordination.
"""

from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer,
    String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from db import Base


class AriaCampaign(Base):
    __tablename__ = "aria_campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, nullable=False, index=True)
    created_by_user_id = Column(Integer, nullable=False)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    filter_criteria = Column(JSONB, nullable=False)
    message_template = Column(Text, nullable=False)

    status = Column(String(32), nullable=False, default="draft", index=True)

    recipient_count = Column(Integer, nullable=False, default=0)
    sent_count = Column(Integer, nullable=False, default=0)
    replied_count = Column(Integer, nullable=False, default=0)
    booked_count = Column(Integer, nullable=False, default=0)
    declined_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    recipients = relationship(
        "AriaCampaignRecipient",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_aria_campaign_org_status", "organization_id", "status"),
    )


class AriaCampaignRecipient(Base):
    __tablename__ = "aria_campaign_recipients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(
        Integer,
        ForeignKey("aria_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_id = Column(Integer, nullable=True)
    loan_id = Column(Integer, nullable=True)

    phone = Column(String(32), nullable=False)
    email = Column(String(255), nullable=True)
    first_name = Column(String(128), nullable=True)

    status = Column(String(32), nullable=False, default="pending")

    message_id = Column(String(255), nullable=True)
    appointment_id = Column(Integer, nullable=True)

    sent_at = Column(DateTime(timezone=True), nullable=True)
    replied_at = Column(DateTime(timezone=True), nullable=True)
    booked_at = Column(DateTime(timezone=True), nullable=True)

    reminder_day_before_sent = Column(Boolean, nullable=False, default=False)
    reminder_hour_before_sent = Column(Boolean, nullable=False, default=False)
    no_show_followup_sent = Column(Boolean, nullable=False, default=False)

    campaign = relationship("AriaCampaign", back_populates="recipients")

    __table_args__ = (
        Index("ix_aria_recipient_campaign_status", "campaign_id", "status"),
        Index("ix_aria_recipient_phone", "phone"),
        Index("ix_aria_recipient_message_id", "message_id"),
    )
