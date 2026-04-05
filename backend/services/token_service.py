"""
Unified Token Service

Single interface for storing, retrieving, and refreshing OAuth tokens.
Replaces the scattered token access patterns across:
  - calendly_service.encrypt_token/decrypt_token
  - encryption_utils.EncryptionManager
  - main.decrypt_token (Microsoft)
  - direct model queries in route files

All encryption handled by services.encryption.FieldEncryptor (Fernet/PBKDF2).

Usage:
    from services.token_service import token_service

    # Store tokens
    token_service.store_token(
        db, user_id=1, organization_id=1,
        provider="microsoft",
        access_token="...",
        refresh_token="...",
        expires_at=datetime(...),
    )

    # Retrieve (auto-decrypted)
    token = token_service.get_token(db, user_id=1, provider="microsoft")
    if token and not token.is_expired:
        access_token = token.access_token  # already decrypted

    # Refresh
    token_service.update_access_token(
        db, user_id=1, provider="microsoft",
        access_token="new_token",
        expires_at=datetime(...),
    )

    # Disconnect
    token_service.disconnect(db, user_id=1, provider="microsoft")
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class TokenService:
    """Unified service for OAuth token CRUD operations."""

    def _get_model(self):
        """Lazy import to avoid circular imports."""
        from database.models.oauth_token import OAuthToken
        return OAuthToken

    def get_token(
        self,
        db: Session,
        user_id: int,
        provider: str,
        organization_id: Optional[int] = None,
    ) -> Optional["OAuthToken"]:
        """Get active token for a user/provider combination."""
        OAuthToken = self._get_model()
        query = db.query(OAuthToken).filter(
            OAuthToken.user_id == user_id,
            OAuthToken.provider == provider,
            OAuthToken.is_active == True,
        )
        if organization_id:
            query = query.filter(OAuthToken.organization_id == organization_id)

        return query.first()

    def get_tokens_for_org(
        self,
        db: Session,
        organization_id: int,
        provider: str,
        active_only: bool = True,
    ) -> List["OAuthToken"]:
        """Get all tokens for an organization and provider."""
        OAuthToken = self._get_model()
        query = db.query(OAuthToken).filter(
            OAuthToken.organization_id == organization_id,
            OAuthToken.provider == provider,
        )
        if active_only:
            query = query.filter(OAuthToken.is_active == True)
        return query.all()

    def store_token(
        self,
        db: Session,
        user_id: int,
        organization_id: int,
        provider: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        scopes: Optional[str] = None,
        email_address: Optional[str] = None,
        instance_url: Optional[str] = None,
        external_org_id: Optional[str] = None,
        sync_enabled: bool = True,
        sync_folder: Optional[str] = None,
        sync_frequency_minutes: int = 15,
        provider_config: Optional[dict] = None,
    ) -> "OAuthToken":
        """
        Store or update OAuth token. Upserts on (user_id, organization_id, provider).
        Tokens are encrypted transparently by the EncryptedString column type.
        """
        OAuthToken = self._get_model()

        existing = db.query(OAuthToken).filter(
            OAuthToken.user_id == user_id,
            OAuthToken.organization_id == organization_id,
            OAuthToken.provider == provider,
        ).first()

        if existing:
            existing.access_token = access_token
            if refresh_token is not None:
                existing.refresh_token = refresh_token
            existing.token_expires_at = expires_at
            existing.is_active = True
            existing.status = "connected"
            existing.last_error = None
            if scopes is not None:
                existing.scopes = scopes
            if email_address is not None:
                existing.email_address = email_address
            if instance_url is not None:
                existing.instance_url = instance_url
            if external_org_id is not None:
                existing.external_org_id = external_org_id
            existing.sync_enabled = sync_enabled
            if sync_folder is not None:
                existing.sync_folder = sync_folder
            existing.sync_frequency_minutes = sync_frequency_minutes
            if provider_config is not None:
                existing.provider_config = provider_config

            logger.info(f"Updated {provider} token for user {user_id}")
            return existing
        else:
            token = OAuthToken(
                user_id=user_id,
                organization_id=organization_id,
                provider=provider,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=expires_at,
                scopes=scopes,
                email_address=email_address,
                instance_url=instance_url,
                external_org_id=external_org_id,
                is_active=True,
                status="connected",
                sync_enabled=sync_enabled,
                sync_folder=sync_folder,
                sync_frequency_minutes=sync_frequency_minutes,
                provider_config=provider_config or {},
            )
            db.add(token)
            logger.info(f"Stored new {provider} token for user {user_id}")
            return token

    def update_access_token(
        self,
        db: Session,
        user_id: int,
        provider: str,
        access_token: str,
        expires_at: Optional[datetime] = None,
        organization_id: Optional[int] = None,
    ) -> bool:
        """Update just the access token (e.g. after refresh). Returns True if found."""
        token = self.get_token(db, user_id, provider, organization_id)
        if not token:
            logger.warning(f"No {provider} token found for user {user_id} to update")
            return False

        token.access_token = access_token
        if expires_at:
            token.token_expires_at = expires_at
        token.status = "connected"
        token.last_error = None
        return True

    def disconnect(
        self,
        db: Session,
        user_id: int,
        provider: str,
        organization_id: Optional[int] = None,
    ) -> bool:
        """Mark a token as disconnected (soft delete). Returns True if found."""
        token = self.get_token(db, user_id, provider, organization_id)
        if not token:
            return False

        token.is_active = False
        token.status = "disconnected"
        token.access_token = None
        token.refresh_token = None
        logger.info(f"Disconnected {provider} for user {user_id}")
        return True

    def mark_error(
        self,
        db: Session,
        user_id: int,
        provider: str,
        error: str,
        organization_id: Optional[int] = None,
    ) -> bool:
        """Mark a token as having an error (e.g. refresh failed)."""
        token = self.get_token(db, user_id, provider, organization_id)
        if not token:
            return False

        token.status = "error"
        token.last_error = error
        return True

    def update_sync_status(
        self,
        db: Session,
        user_id: int,
        provider: str,
        last_sync_at: Optional[datetime] = None,
        organization_id: Optional[int] = None,
    ) -> bool:
        """Update the last sync timestamp."""
        token = self.get_token(db, user_id, provider, organization_id)
        if not token:
            return False

        token.last_sync_at = last_sync_at or datetime.now(timezone.utc)
        return True


# Singleton instance
token_service = TokenService()
