"""
Unified OAuth Token Storage

Consolidates token storage from:
  - microsoft_tokens (MicrosoftToken)
  - microsoft_oauth_tokens (MicrosoftOAuthToken)
  - integration_profiles (Salesforce IntegrationProfile)

All tokens encrypted via EncryptedString (Fernet-based, from services.encryption).
Provider-specific metadata stored in JSON config column.

Legacy tables remain in the database for backward compatibility during migration.
New code should use OAuthToken exclusively.

Usage:
    from database.models.oauth_token import OAuthToken

    token = OAuthToken(
        user_id=1,
        organization_id=1,
        provider="microsoft",
        access_token="...",    # auto-encrypted on write
        refresh_token="...",   # auto-encrypted on write
    )
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    Text, ForeignKey, JSON, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db import Base
from services.encryption import EncryptedString


class OAuthToken(Base):
    """
    Unified OAuth token storage for all providers.

    One row per (user_id, organization_id, provider) combination.
    Tokens are encrypted at rest via Fernet (EncryptedString TypeDecorator).
    """
    __tablename__ = "oauth_tokens"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", "provider", name="uq_oauth_user_org_provider"),
        Index("ix_oauth_user_provider", "user_id", "provider"),
        Index("ix_oauth_org_provider", "organization_id", "provider"),
        Index("ix_oauth_provider_active", "provider", "is_active"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Who and where
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)

    # Provider: "microsoft", "salesforce", "google", "encompass", etc.
    provider = Column(String(50), nullable=False, index=True)

    # Tokens (encrypted at rest)
    access_token = Column(EncryptedString(2000), nullable=True)
    refresh_token = Column(EncryptedString(2000), nullable=True)

    # Token lifecycle
    token_expires_at = Column(DateTime, nullable=True)
    scopes = Column(String(1000), nullable=True)  # Space-separated OAuth scopes

    # Connection metadata
    email_address = Column(String(255), nullable=True)  # e.g. Microsoft email, Salesforce username
    instance_url = Column(String(500), nullable=True)  # e.g. Salesforce instance URL
    external_org_id = Column(String(255), nullable=True)  # e.g. Salesforce org ID

    # Status
    is_active = Column(Boolean, default=True, server_default="true")
    status = Column(String(50), default="connected")  # connected, disconnected, expired, error
    last_error = Column(Text, nullable=True)

    # Sync settings (for providers that sync data)
    sync_enabled = Column(Boolean, default=True, server_default="true")
    sync_folder = Column(String(255), nullable=True)  # e.g. "Inbox" for Microsoft email
    sync_frequency_minutes = Column(Integer, default=15)
    last_sync_at = Column(DateTime, nullable=True)

    # Provider-specific config (JSON blob for anything not in columns above)
    provider_config = Column(JSON, default=dict)

    # Audit
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization", foreign_keys=[organization_id])

    def __repr__(self):
        return f"<OAuthToken provider={self.provider} user={self.user_id} org={self.organization_id}>"

    @property
    def is_expired(self) -> bool:
        """Check if the access token has expired."""
        if not self.token_expires_at:
            return False
        return datetime.now(timezone.utc) > self.token_expires_at


__all__ = ["OAuthToken"]
