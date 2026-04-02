"""Email open/click tracking models."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Index
from db import Base


def _uuid():
    return str(uuid.uuid4())


class EmailTrackingEvent(Base):
    __tablename__ = "email_tracking_events"

    id = Column(String, primary_key=True, default=_uuid)
    tracking_id = Column(String, nullable=False, index=True)
    email_message_id = Column(String, nullable=True)
    event_type = Column(String, nullable=False)  # "open" or "click"
    link_url = Column(String, nullable=True)
    link_hash = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    organization_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_tracking_event_tracking_type", "tracking_id", "event_type"),
    )


class TrackingLinkMap(Base):
    __tablename__ = "tracking_link_maps"

    id = Column(String, primary_key=True, default=_uuid)
    tracking_id = Column(String, nullable=False, index=True)
    link_hash = Column(String, nullable=False)
    original_url = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_link_map_tracking_hash", "tracking_id", "link_hash"),
    )
