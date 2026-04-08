"""SQLAlchemy model for engagement_events table."""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from database import Base


class EngagementEvent(Base):
    __tablename__ = "engagement_events"
    __table_args__ = (
        Index("ix_eng_events_org_lead", "organization_id", "lead_id"),
        Index("ix_eng_events_lead_created", "lead_id", "created_at"),
        Index("ix_eng_events_scheduled", "scheduled_next_at", postgresql_where="scheduled_next_at IS NOT NULL"),
        Index("ix_eng_events_trigger", "trigger_event", "created_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, nullable=False)
    lead_id = Column(Integer, nullable=False)
    trigger_event = Column(String(60), nullable=False)
    channel_chosen = Column(String(20))
    channel_reason = Column(Text)
    action_taken = Column(Text)
    action_result = Column(Text)
    action_metadata = Column(JSONB, default=dict)
    scheduled_next_at = Column(DateTime(timezone=True))
    scheduled_next_trigger = Column(String(60))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
