"""DeviceToken and PushNotificationPreference models for push notification infrastructure."""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, JSON,
    UniqueConstraint, Index
)
from sqlalchemy.orm import relationship

from db import Base


class DeviceToken(Base):
    """Stores APNs/FCM push notification tokens per user device."""
    __tablename__ = 'device_tokens'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True, index=True)
    device_token = Column(String(500), nullable=False)
    platform = Column(String(20), nullable=False)  # "ios" or "android"
    device_name = Column(String(200), nullable=True)  # optional human-readable label
    app_version = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    failure_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="device_tokens")

    __table_args__ = (
        UniqueConstraint('user_id', 'device_token', name='uq_user_device_token'),
        Index('idx_device_tokens_user_id', 'user_id'),
        Index('idx_device_tokens_org_id', 'organization_id'),
        Index('idx_device_tokens_active', 'is_active', postgresql_where=(is_active == True)),
    )

    def __repr__(self):
        return f"<DeviceToken(id={self.id}, user_id={self.user_id}, platform={self.platform})>"


class PushNotificationPreference(Base):
    """Per-user push notification category preferences.

    Each row stores a user's opt-in/opt-out for a specific notification category.
    Missing categories default to enabled.
    """
    __tablename__ = 'push_notification_preferences'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True, index=True)

    # JSON map of category -> enabled boolean
    # e.g. {"lead_assigned": true, "sla_alert": true, "appointment_reminder": false, ...}
    categories = Column(JSON, default=dict)

    # Global mute (overrides individual categories)
    muted = Column(Boolean, default=False)

    # Quiet hours (no push during these times, UTC)
    quiet_hours_start = Column(String(5), nullable=True)  # "22:00"
    quiet_hours_end = Column(String(5), nullable=True)    # "07:00"

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('user_id', name='uq_push_pref_user_id'),
        Index('idx_push_pref_user_id', 'user_id'),
    )

    def __repr__(self):
        return f"<PushNotificationPreference(user_id={self.user_id}, muted={self.muted})>"
