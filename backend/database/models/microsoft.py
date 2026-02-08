"""
Microsoft Integration Models

MicrosoftToken, MicrosoftOAuthToken, and MicrosoftAppConfig models.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.microsoft import MicrosoftToken, MicrosoftOAuthToken, MicrosoftAppConfig
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    Text, ForeignKey
)
from sqlalchemy.orm import relationship

from db import Base


class MicrosoftToken(Base):
    """Stores Microsoft Graph OAuth tokens for email access"""
    __tablename__ = "microsoft_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    access_token = Column(Text)  # Encrypted
    refresh_token = Column(Text)  # Encrypted
    token_type = Column(String)
    expires_at = Column(DateTime)
    scope = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MicrosoftOAuthToken(Base):
    __tablename__ = "microsoft_oauth_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    access_token = Column(Text)  # Encrypted token
    refresh_token = Column(Text)  # Encrypted token
    token_expires_at = Column(DateTime)
    email_address = Column(String)  # Microsoft email address
    sync_enabled = Column(Boolean, default=True)
    last_sync_at = Column(DateTime)
    sync_folder = Column(String, default="Inbox")  # Which folder to sync
    sync_frequency_minutes = Column(Integer, default=15)  # How often to sync
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MicrosoftAppConfig(Base):
    """Stores Microsoft Azure App Registration credentials per organization (multi-tenant)"""
    __tablename__ = "microsoft_app_config"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), unique=True, index=True)  # One config per org
    client_id = Column(String)  # Azure App Client ID
    client_secret = Column(Text)  # Encrypted client secret
    tenant_id = Column(String, default="common")  # Azure Tenant ID or 'common'
    redirect_uri = Column(String)  # OAuth redirect URI
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    organization = relationship("Organization", back_populates="microsoft_config")


__all__ = [
    "MicrosoftToken",
    "MicrosoftOAuthToken",
    "MicrosoftAppConfig",
]
