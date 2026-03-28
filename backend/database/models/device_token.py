"""DeviceToken model — stores APNs/FCM push notification tokens per user."""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship

from db import Base


class DeviceToken(Base):
    __tablename__ = 'device_tokens'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    device_token = Column(String(500), nullable=False)
    platform = Column(String(20), nullable=False)  # "ios" or "android"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="device_tokens")

    __table_args__ = (
        UniqueConstraint('user_id', 'device_token', name='uq_user_device_token'),
        Index('idx_device_tokens_user_id', 'user_id'),
        Index('idx_device_tokens_active', 'is_active', postgresql_where=(is_active == True)),
    )

    def __repr__(self):
        return f"<DeviceToken(id={self.id}, user_id={self.user_id}, platform={self.platform})>"
