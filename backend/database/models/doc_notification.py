"""
Smart Docs Notification Center Models

Persistent notification storage and user preference management for the
Smart Docs V2 notification center. Supports multi-channel delivery
(in-app, email, push), per-user opt-in/opt-out per notification type,
severity filtering, and auto-expiry.

Models:
    - DocNotification: Individual notification record with delivery tracking
    - NotificationPreference: Per-user, per-type channel preferences

Usage:
    from database.models.doc_notification import DocNotification, NotificationPreference

    # Get unread notifications for a user
    unread = db.query(DocNotification).filter(
        DocNotification.user_id == user_id,
        DocNotification.organization_id == org_id,
        DocNotification.is_read == False,
    ).order_by(DocNotification.created_at.desc()).all()
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from db import Base


def utcnow():
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class DocNotification(Base):
    """Individual Smart Docs notification record.

    Notification types:
        DOC_UPLOADED         - New document uploaded by borrower or processor
        DOC_CLASSIFIED       - AI classification completed on a document
        DOC_APPROVED         - Document passed review and was approved
        DOC_REJECTED         - Document failed review and was rejected
        DOC_EXPIRING         - Document approaching expiration date
        CONDITION_ADDED      - New underwriting condition added to loan
        CONDITION_CLEARED    - Existing condition has been cleared/satisfied
        INCOME_CALCULATED    - AI income calculation completed
        FRAUD_ALERT          - Fraud detection flagged a document
        SIGNATURE_COMPLETED  - E-signature envelope completed by all parties
        PACKAGE_READY        - Closing package or document package assembled
        SLA_WARNING          - Document request SLA approaching breach
        BATCH_COMPLETE       - Batch processing job finished

    Severity levels:
        info     - Informational, no action needed
        warning  - Attention suggested but not urgent
        urgent   - Requires prompt attention
        critical - Immediate action required (fraud, compliance)
    """

    __tablename__ = "smart_docs_notifications"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    loan_id = Column(
        Integer, ForeignKey("loans.id"), nullable=True, index=True
    )

    notification_type = Column(String(50), nullable=False)
    severity = Column(String(10), default="info")  # info, warning, urgent, critical

    title = Column(String(300), nullable=False)
    body = Column(Text)

    # Deep link to relevant page/action in the frontend
    action_url = Column(String(500))
    action_label = Column(String(100))  # e.g. "Review Document", "Clear Condition"

    # Arbitrary context data (document_id, classification result, etc.)
    extra_data = Column("metadata", JSON)

    # Read/dismiss state
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime)
    is_dismissed = Column(Boolean, default=False)
    dismissed_at = Column(DateTime)

    # Multi-channel delivery tracking
    delivery_channels = Column(JSON)  # ["in_app", "email", "push"]
    email_sent = Column(Boolean, default=False)
    push_sent = Column(Boolean, default=False)

    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime)  # Auto-dismiss after expiry

    __table_args__ = (
        Index(
            "ix_notifications_user_unread",
            "user_id",
            "is_read",
            "created_at",
        ),
        Index(
            "ix_notifications_org_type",
            "organization_id",
            "notification_type",
        ),
    )


class NotificationPreference(Base):
    """Per-user, per-notification-type channel preferences.

    Controls which channels a user receives each notification type on
    and the minimum severity that triggers delivery. A missing row for
    a given (user_id, notification_type) pair means the user has not
    customized preferences and the system defaults apply (in-app + email
    enabled, push disabled, minimum severity = info).
    """

    __tablename__ = "smart_docs_notification_preferences"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    notification_type = Column(String(50), nullable=False)

    in_app_enabled = Column(Boolean, default=True)
    email_enabled = Column(Boolean, default=True)
    push_enabled = Column(Boolean, default=False)

    minimum_severity = Column(String(10), default="info")

    __table_args__ = (
        Index(
            "ix_notif_prefs_user_type",
            "user_id",
            "notification_type",
            unique=True,
        ),
    )
