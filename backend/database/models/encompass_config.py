"""
Encompass LOS Configuration Model

Per-organization credential and configuration storage for Encompass
(ICE Mortgage Technology) API integration.

Each organization can have one active Encompass configuration that stores
OAuth credentials, webhook secrets, and sync preferences.

Usage:
    from database.models.encompass_config import EncompassConfig

    config = db.query(EncompassConfig).filter(
        EncompassConfig.organization_id == org_id,
        EncompassConfig.is_active == True,
    ).first()
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Index
)
from sqlalchemy.orm import relationship

from db import Base


class EncompassConfig(Base):
    """Per-organization Encompass API configuration.

    Stores OAuth credentials, webhook secrets, and sync behavior preferences
    for the Encompass LOS integration. Each organization can have at most
    one active configuration (enforced by the unique constraint on organization_id).

    Security note: client_id and client_secret should be encrypted at rest
    in production. The current implementation stores them as plain strings;
    a production deployment should use application-level encryption (e.g.,
    Fernet or AWS KMS) before persisting.
    """
    __tablename__ = "encompass_configs"
    __table_args__ = (
        Index('ix_encompass_configs_org_id', 'organization_id'),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    # Encompass connection details
    instance_id = Column(String, nullable=False)       # Encompass instance ID (e.g., "BE11200822")
    client_id = Column(String, nullable=False)         # OAuth client ID (encrypted in production)
    client_secret = Column(String, nullable=False)     # OAuth client secret (encrypted in production)
    api_user = Column(String, nullable=True)           # Service account username (optional)
    webhook_secret = Column(String, nullable=True)     # HMAC secret for webhook signature verification

    # Sync behavior
    auto_pull_on_webhook = Column(Boolean, default=True)       # Auto-pull loan data when webhook received
    auto_push_on_stage_change = Column(Boolean, default=False) # Auto-push when CRM stage changes
    sync_frequency_minutes = Column(Integer, default=60)       # Scheduled sync interval

    # Status tracking
    last_sync_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    organization = relationship("Organization", backref="encompass_config")


__all__ = [
    "EncompassConfig",
]
