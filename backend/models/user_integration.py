"""
User Integration Model
======================
Stores OAuth tokens and integration credentials for external services
(Microsoft Graph, Google, etc.) linked to individual users.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Index, UniqueConstraint
)
from database import Base


class UserIntegration(Base):
    """
    Stores OAuth tokens for user-delegated API access.

    Each user can have one integration per provider (Microsoft, Google, etc.).
    Tokens are refreshed automatically when expired.
    """
    __tablename__ = "user_integrations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    provider = Column(String(50), nullable=False)  # 'microsoft', 'google', etc.

    # OAuth tokens
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # Additional metadata
    scopes = Column(Text, nullable=True)  # Comma-separated list of granted scopes
    email = Column(String(255), nullable=True)  # User's email on the provider
    provider_user_id = Column(String(255), nullable=True)  # User ID on provider

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Ensure one integration per user per provider
    __table_args__ = (
        UniqueConstraint('user_id', 'provider', name='uix_user_provider'),
        Index('ix_user_integrations_user_provider', 'user_id', 'provider'),
    )

    def __repr__(self):
        return f"<UserIntegration(user_id={self.user_id}, provider='{self.provider}')>"

    @property
    def is_expired(self) -> bool:
        """Check if the access token is expired."""
        if not self.expires_at:
            return True
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def is_connected(self) -> bool:
        """Check if this integration has valid tokens."""
        return bool(self.access_token) and not self.is_expired
