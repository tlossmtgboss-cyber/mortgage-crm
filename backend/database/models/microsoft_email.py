"""
Microsoft Email OAuth Token Model

Stores Microsoft Graph API OAuth2 tokens for sending email via Graph API.
Each record represents a connected Microsoft 365 account for a user within
an organization.

Usage:
    from database.models.microsoft_email import MicrosoftEmailToken
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    Text, UniqueConstraint, Index,
)

from db import Base


class MicrosoftEmailToken(Base):
    """Stores Microsoft Graph OAuth tokens for sending email on behalf of a user."""

    __tablename__ = "microsoft_email_tokens"
    __table_args__ = (
        UniqueConstraint("organization_id", "email_address", name="uq_org_email_microsoft"),
        Index("ix_microsoft_email_tokens_org_active", "organization_id", "is_active"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=False)
    email_address = Column(String(320), nullable=False)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    token_expiry = Column(DateTime, nullable=False)
    tenant_id = Column(String(255), nullable=True)
    connected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    is_active = Column(Boolean, default=True, nullable=False)


__all__ = ["MicrosoftEmailToken"]
