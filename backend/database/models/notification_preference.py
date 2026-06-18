"""NotificationPreference model — per-user push notification category toggles.

Each user has at most one row.  Category booleans control which notification
types are delivered via push.  Quiet hours suppress all push delivery during
the configured window (user's local time).
"""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Index, Integer
)

from db import Base


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    # Integer FK matching users.id (Integer primary key)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Category toggles — each maps to a push notification type family
    loan_updates = Column(Boolean, default=True)
    lead_alerts = Column(Boolean, default=True)
    task_reminders = Column(Boolean, default=True)
    rate_lock_alerts = Column(Boolean, default=True)
    closing_reminders = Column(Boolean, default=True)
    compliance_alerts = Column(Boolean, default=True)
    system_notifications = Column(Boolean, default=True)

    # Quiet hours — stored as HH:MM strings in user's local timezone
    quiet_hours_start = Column(String(5), nullable=True)  # e.g. "22:00"
    quiet_hours_end = Column(String(5), nullable=True)    # e.g. "07:00"

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_notification_preferences_user", "user_id", unique=True),
        {"extend_existing": True},
    )

    def __repr__(self):
        return f"<NotificationPreference(id={self.id}, user_id={self.user_id})>"

    def to_dict(self):
        """Serialize to dict for API responses."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "loan_updates": self.loan_updates,
            "lead_alerts": self.lead_alerts,
            "task_reminders": self.task_reminders,
            "rate_lock_alerts": self.rate_lock_alerts,
            "closing_reminders": self.closing_reminders,
            "compliance_alerts": self.compliance_alerts,
            "system_notifications": self.system_notifications,
            "quiet_hours_start": self.quiet_hours_start,
            "quiet_hours_end": self.quiet_hours_end,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
