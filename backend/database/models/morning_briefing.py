"""
Morning Briefing Model

Stores daily autonomous briefings generated for each user.
One briefing per user per day, with level-specific data.
"""
from sqlalchemy import (
    Column, Integer, String, Date, Text, Boolean, DateTime, ForeignKey, Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from db import Base


class MorningBriefing(Base):
    __tablename__ = "morning_briefings"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    briefing_date = Column(Date, nullable=False)
    briefing_level = Column(String, nullable=False, default="individual")  # individual, manager, leadership
    status = Column(String, nullable=False, default="pending")  # pending, generating, delivered, failed
    briefing_data = Column(JSONB, nullable=True)
    team_data = Column(JSONB, nullable=True)
    ai_narrative = Column(Text, nullable=True)
    html_content = Column(Text, nullable=True)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)
    email_message_id = Column(String, nullable=True)
    viewed_in_app_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization", foreign_keys=[organization_id])

    __table_args__ = (
        UniqueConstraint("user_id", "briefing_date", name="uq_user_briefing_date"),
        Index("ix_briefing_date_status", "briefing_date", "status"),
        Index("ix_org_briefing_date", "organization_id", "briefing_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "briefing_date": self.briefing_date.isoformat() if self.briefing_date else None,
            "briefing_level": self.briefing_level,
            "status": self.status,
            "ai_narrative": self.ai_narrative,
            "viewed_in_app": self.viewed_in_app_at is not None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
