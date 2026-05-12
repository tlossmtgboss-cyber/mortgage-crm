"""
Mobile Audit Event Model

Persists hash-chained security audit events received from the iOS app's
AuditLogger. Provides durable storage for SOC 2 compliance — Railway stdout
logs rotate at ~1MB, so database persistence is required.

90-day retention policy: A scheduled cron job should DELETE rows where
created_at < NOW() - INTERVAL '90 days'. This keeps the table size manageable
while satisfying SOC 2 audit window requirements.

Usage:
    from database.models.audit import MobileAuditEvent

    event = MobileAuditEvent(
        organization_id=org_id,
        user_id=user_id,
        event_type="auth.success",
        event_category="auth",
        details={"method": "biometric"},
        device_info={"model": "iPhone", "osVersion": "17.4", "appVersion": "1.0.0"},
        event_hash="sha256-hex",
        previous_hash="sha256-hex",
        chain_valid=True,
        event_timestamp=datetime.utcnow(),
    )
    db.add(event)
    db.commit()
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
)

from db import Base


class MobileAuditEvent(Base):
    """Durable storage for iOS security audit events.

    Each row corresponds to one AuditEntry from the iOS AuditLogger's hash
    chain. Events are append-only; rows should never be updated or deleted
    outside of the 90-day retention cleanup.
    """

    __tablename__ = "mobile_audit_events"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Event classification
    event_type = Column(String, nullable=False, index=True)  # e.g. "auth.success"
    event_category = Column(String, nullable=True)  # e.g. "auth", "biometric", "security"

    # Payload
    details = Column(JSON, nullable=True)  # arbitrary key/value from iOS
    device_info = Column(JSON, nullable=True)  # {model, osVersion, appVersion}

    # Hash chain integrity
    event_hash = Column(String(64), nullable=True)  # SHA-256 from iOS client
    previous_hash = Column(String(64), nullable=True)  # previous entry's hash
    chain_valid = Column(Boolean, default=True)  # whether batch chain verification passed

    # Timestamps
    event_timestamp = Column(DateTime, nullable=True)  # when the event occurred on device
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Composite indexes for common query patterns
    __table_args__ = (
        Index("ix_mobile_audit_org_event_type", "organization_id", "event_type"),
        Index("ix_mobile_audit_org_created", "organization_id", "created_at"),
        Index("ix_mobile_audit_user_event_type", "user_id", "event_type"),
    )
