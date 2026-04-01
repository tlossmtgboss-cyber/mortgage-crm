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

import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship

from db import Base

logger = logging.getLogger(__name__)

try:
    from services.encryption import EncryptedString
    _HAS_ENCRYPTION = True
except ImportError:
    _HAS_ENCRYPTION = False
    is_production = any([
        os.getenv("RAILWAY_ENVIRONMENT", "").lower() in ("production", "staging"),
        os.getenv("ENVIRONMENT", "").lower() in ("production", "staging"),
    ])
    if is_production:
        raise RuntimeError("Encryption service required in production/staging for credential storage")
    logger.warning("EncryptedString unavailable; secrets stored as plaintext in dev mode")


class EncompassConfig(Base):
    """Per-organization Encompass API configuration.

    Stores OAuth credentials, webhook secrets, and sync behavior preferences
    for the Encompass LOS integration. Each organization can have at most
    one active configuration (enforced by the unique constraint on organization_id).

    Security: client_secret and webhook_secret are encrypted at rest using
    Fernet symmetric encryption (EncryptedString TypeDecorator). Legacy
    plaintext values are returned as-is on read for backward compatibility.

    Health tracking:
        last_failed_at and consecutive_auth_failures track authentication
        failures so the health endpoint can report degraded state even when
        the service is currently recovering.
    """
    __tablename__ = "encompass_configs"
    __table_args__ = (
        # Composite index on org_id + is_active for the common query pattern
        Index("ix_encompass_configs_org_active", "organization_id", "is_active"),
        # Explicit unique constraint (the Column-level unique=True also creates one,
        # but naming it makes it easier to reference in migrations)
        UniqueConstraint("organization_id", name="uq_encompass_configs_org_id"),
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
    client_id = Column(String, nullable=False)         # OAuth client ID (not a secret, but identifies the app)
    # COMP-004: OAuth client secret encrypted at rest via Fernet (EncryptedString TypeDecorator).
    # Sized to 500 chars to accommodate ciphertext. Legacy plaintext returned as-is on read.
    client_secret = Column(
        EncryptedString(500) if _HAS_ENCRYPTION else String(500),
        nullable=False,
    )
    api_user = Column(String, nullable=True)           # Service account username (optional)
    # COMP-004: Webhook HMAC secret encrypted at rest via Fernet (EncryptedString TypeDecorator).
    webhook_secret = Column(
        EncryptedString(500) if _HAS_ENCRYPTION else String(500),
        nullable=True,
    )

    # Sync behavior
    auto_pull_on_webhook = Column(Boolean, default=True)        # Auto-pull loan data when webhook received
    auto_push_on_stage_change = Column(Boolean, default=False)  # Auto-push when CRM stage changes
    sync_frequency_minutes = Column(Integer, default=60)        # Scheduled sync interval

    # Status tracking
    last_sync_at = Column(DateTime, nullable=True)             # Timestamp of the last successful sync
    last_failed_at = Column(DateTime, nullable=True)           # Timestamp of the last auth/sync failure
    consecutive_auth_failures = Column(Integer, default=0)     # Count of consecutive auth failures;
                                                                # reset to 0 on successful auth
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

    @property
    def is_healthy(self) -> bool:
        """True when the config is active and has not had excessive auth failures.

        More than 5 consecutive auth failures indicates the credentials may have
        been revoked. The health endpoint uses this to report degraded state.
        """
        return self.is_active and (self.consecutive_auth_failures or 0) < 5

    @property
    def health_status(self) -> str:
        """Return a human-readable health status string."""
        if not self.is_active:
            return "inactive"
        failures = self.consecutive_auth_failures or 0
        if failures >= 5:
            return "degraded"
        if failures > 0:
            return "warning"
        return "healthy"


__all__ = [
    "EncompassConfig",
]
