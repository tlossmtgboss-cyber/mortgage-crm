"""
Salesforce OAuth Service
Handles per-user Salesforce authentication and token management
"""
import os
import secrets
import logging
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
import httpx

from urllib.parse import urlencode

from sqlalchemy import text
from sqlalchemy.orm import Session

from encryption_utils import encrypt_value, decrypt_value
from salesforce_integration_models import (
    IntegrationProfile,
    OAuthState,
    SyncQueueItem,
    IntegrationEvent
)
from models.calendar_sync_models import CalendarSyncSettings
from .http_client import get_sf_client, SF_TIMEOUT

logger = logging.getLogger(__name__)


def _get_settings():
    """Lazy load settings to avoid import-time config parsing errors"""
    try:
        from config import settings
        return settings
    except Exception as e:
        logger.warning(f"Could not load config settings: {e}")
        return None


class SalesforceOAuthConfig:
    """Salesforce OAuth Configuration - uses centralized config settings or environment variables"""
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        use_sandbox: Optional[bool] = None
    ):
        # Store passed values for lazy loading
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._use_sandbox = use_sandbox
        self._initialized = False

    def _ensure_initialized(self):
        """Lazy initialize config when first accessed"""
        if self._initialized:
            return
        self._initialized = True

        settings = _get_settings()

        # Use passed values, then settings, then env vars
        self._resolved_client_id = self._client_id or (settings.SALESFORCE_CLIENT_ID if settings else None) or os.getenv("SALESFORCE_CLIENT_ID", "")
        self._resolved_client_secret = self._client_secret or (settings.SALESFORCE_CLIENT_SECRET if settings else None) or os.getenv("SALESFORCE_CLIENT_SECRET", "")

        # Build default redirect URI if not specified
        base_url = (settings.BASE_URL if settings else None) or os.getenv("BASE_URL", "http://localhost:8000")
        default_redirect = f"{base_url}/api/integrations/salesforce/callback"
        sf_redirect = (settings.SALESFORCE_REDIRECT_URI if settings else None) or os.getenv("SALESFORCE_REDIRECT_URI")
        self._resolved_redirect_uri = self._redirect_uri or sf_redirect or default_redirect

        # Determine if using sandbox
        if self._use_sandbox is not None:
            is_sandbox = self._use_sandbox
        elif settings:
            is_sandbox = settings.SALESFORCE_SANDBOX
        else:
            is_sandbox = os.getenv("SALESFORCE_SANDBOX", "false").lower() == "true"

        if is_sandbox:
            self._resolved_base_url = 'https://test.salesforce.com'
        else:
            self._resolved_base_url = 'https://login.salesforce.com'

    @property
    def client_id(self):
        self._ensure_initialized()
        return self._resolved_client_id

    @property
    def client_secret(self):
        self._ensure_initialized()
        return self._resolved_client_secret

    @property
    def redirect_uri(self):
        self._ensure_initialized()
        return self._resolved_redirect_uri

    @property
    def base_url(self):
        self._ensure_initialized()
        return self._resolved_base_url


class SalesforceOAuthService:
    """Manages per-user Salesforce OAuth authentication"""

    def __init__(self, config: Optional[SalesforceOAuthConfig] = None):
        self.config = config or SalesforceOAuthConfig()

    def _generate_pkce(self) -> Tuple[str, str]:
        """Generate PKCE code verifier and challenge"""
        # Generate a random code verifier (43-128 characters)
        code_verifier = secrets.token_urlsafe(64)

        # Create code challenge using S256 method
        code_challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge_bytes).decode('utf-8').rstrip('=')

        return code_verifier, code_challenge

    def generate_auth_url(self, db: Session, user_id: int, return_url: Optional[str] = None) -> str:
        """
        Step 1: Generate OAuth authorization URL
        User clicks 'Connect Salesforce' button
        """
        # Generate secure state token
        state_token = secrets.token_hex(32)
        logger.info(f"Generated OAuth state token for user {user_id}: {state_token[:20]}...")

        # Generate PKCE values
        code_verifier, code_challenge = self._generate_pkce()

        # Store state for CSRF protection (include code_verifier for token exchange)
        try:
            oauth_state = OAuthState(
                state_token=state_token,
                user_id=user_id,
                provider='salesforce',
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
                return_url=return_url,
                state_metadata={
                    'created_from': 'user_settings',
                    'code_verifier': code_verifier  # Store for token exchange
                }
            )
            db.add(oauth_state)
            db.commit()
            logger.info(f"Successfully stored OAuth state in database for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to store OAuth state in database: {type(e).__name__}: {e}")
            try:
                db.rollback()
            except Exception as e2:
                logger.exception(f"Failed to rollback after OAuth state storage failure: {e2}")
            # Re-raise with more detail
            raise Exception(f"OAuth state storage failed ({type(e).__name__}): {e}")

        # Build authorization URL with PKCE
        params = {
            'response_type': 'code',
            'client_id': self.config.client_id,
            'redirect_uri': self.config.redirect_uri,
            'state': state_token,
            'scope': 'api refresh_token',
            'prompt': 'consent',  # Force consent to ensure refresh token
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256'
        }

        query_string = urlencode(params)
        return f"{self.config.base_url}/services/oauth2/authorize?{query_string}"

    async def handle_callback(
        self,
        db: Session,
        code: str,
        state: str
    ) -> Dict[str, Any]:
        """
        Step 2: Handle OAuth callback
        Salesforce redirects back with authorization code
        """
        # Validate state token
        oauth_state = db.query(OAuthState).filter(
            OAuthState.state_token == state
        ).first()

        if not oauth_state:
            raise ValueError("Invalid or expired state token")

        if oauth_state.used:
            raise ValueError("State token already used")

        if datetime.now(timezone.utc) > oauth_state.expires_at:
            raise ValueError("State token expired")

        # Get code_verifier from state metadata for PKCE
        code_verifier = None
        if oauth_state.state_metadata and isinstance(oauth_state.state_metadata, dict):
            code_verifier = oauth_state.state_metadata.get('code_verifier')

        # Exchange code for tokens
        tokens = await self._exchange_code_for_tokens(code, code_verifier)

        # Mark state as used AFTER successful token exchange
        oauth_state.used = True
        db.commit()

        # Get user identity from Salesforce
        identity = await self._get_user_identity(tokens['access_token'], tokens['id'])

        # Create or update integration profile
        profile = self._create_or_update_profile(
            db,
            oauth_state.user_id,
            tokens,
            identity
        )

        # Non-critical post-connect setup — failures here must not break the connection
        try:
            self._initialize_calendar_sync_settings(db, oauth_state.user_id)
        except Exception as e:
            logger.warning(f"Calendar sync init failed (non-fatal): {e}")
            try:
                db.rollback()
            except Exception:
                pass

        try:
            self._queue_schema_discovery(db, profile.id)
        except Exception as e:
            logger.warning(f"Schema discovery queue failed (non-fatal): {e}")
            try:
                db.rollback()
            except Exception:
                pass

        return {
            'user_id': oauth_state.user_id,
            'profile': profile,
            'return_url': oauth_state.return_url
        }

    async def _exchange_code_for_tokens(self, code: str, code_verifier: Optional[str] = None) -> Dict[str, Any]:
        """Exchange authorization code for access/refresh tokens"""
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
            'redirect_uri': self.config.redirect_uri
        }

        # Add code_verifier for PKCE if present
        if code_verifier:
            data['code_verifier'] = code_verifier

        async with get_sf_client() as client:
            response = await client.post(
                f"{self.config.base_url}/services/oauth2/token",
                data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )

            if response.status_code != 200:
                error = response.text
                raise ValueError(f"Token exchange failed: {error}")

            return response.json()

    async def _get_user_identity(self, access_token: str, identity_url: str) -> Dict[str, Any]:
        """Get Salesforce user identity"""
        async with get_sf_client() as client:
            response = await client.get(
                identity_url,
                headers={'Authorization': f'Bearer {access_token}'}
            )

            if response.status_code != 200:
                raise ValueError("Failed to fetch user identity")

            return response.json()

    def _create_or_update_profile(
        self,
        db: Session,
        user_id: int,
        tokens: Dict[str, Any],
        identity: Dict[str, Any]
    ) -> IntegrationProfile:
        """Create or update integration profile with tokens"""
        now = datetime.now(timezone.utc)

        # Encrypt tokens
        access_token_encrypted = encrypt_value(tokens['access_token'])
        refresh_token_encrypted = encrypt_value(tokens['refresh_token'])

        # Salesforce access tokens typically expire in ~2 hours
        token_expires_at = (now + timedelta(hours=2)).isoformat()

        # Check for existing profile
        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.user_id == user_id,
            IntegrationProfile.provider == 'salesforce'
        ).first()

        if profile:
            # Update existing
            profile.status = 'connected'
            profile.access_token_encrypted = access_token_encrypted
            profile.refresh_token_encrypted = refresh_token_encrypted
            profile.instance_url = tokens['instance_url']
            profile.sf_org_id = identity.get('organization_id')
            profile.sf_user_id = identity.get('user_id')
            profile.sf_username = identity.get('username')
            profile.connected_at = now
            profile.last_error = None
            # Store token expiry in sync_metadata
            metadata = profile.sync_metadata or {}
            metadata['token_expires_at'] = token_expires_at
            profile.sync_metadata = metadata
        else:
            # Create new
            profile = IntegrationProfile(
                user_id=user_id,
                provider='salesforce',
                status='connected',
                access_token_encrypted=access_token_encrypted,
                refresh_token_encrypted=refresh_token_encrypted,
                instance_url=tokens['instance_url'],
                sf_org_id=identity.get('organization_id'),
                sf_user_id=identity.get('user_id'),
                sf_username=identity.get('username'),
                connected_at=now,
                sync_enabled=True,
                sync_interval_minutes=15,
                sync_direction='bidirectional',
                sync_metadata={'token_expires_at': token_expires_at}
            )
            db.add(profile)

        db.commit()
        db.refresh(profile)
        return profile

    def _initialize_calendar_sync_settings(self, db: Session, user_id: int):
        """Initialize calendar sync settings for a user when they connect Salesforce."""
        # Check if settings already exist for this user
        existing = db.query(CalendarSyncSettings).filter(
            CalendarSyncSettings.user_id == user_id
        ).first()

        if existing:
            # Settings already exist, just ensure sync is enabled
            if not existing.sync_enabled:
                existing.sync_enabled = True
                db.flush()  # Flush changes, parent transaction will commit
            logger.info(f"Calendar sync settings already exist for user {user_id}")
            return existing

        # Create new calendar sync settings with defaults
        settings = CalendarSyncSettings(
            user_id=user_id,
            sync_enabled=True,
            sync_direction='bidirectional',
            conflict_policy='last_write_wins',
            delete_policy='soft_cancel',
            echo_ignore_window_seconds=60,
            polling_enabled=True,
            polling_interval_seconds=120,  # 2 minutes
            batch_size=50
        )
        db.add(settings)
        db.flush()  # Flush to get the ID without committing

        logger.info(f"Created calendar sync settings for user {user_id}")
        return settings

    def _queue_schema_discovery(self, db: Session, integration_profile_id: int):
        """Queue schema discovery after connection"""
        queue_item = SyncQueueItem(
            integration_profile_id=integration_profile_id,
            operation='schema_refresh',
            direction='inbound',
            priority=10,  # High priority
            status='pending'
        )
        db.add(queue_item)
        db.commit()

    async def refresh_access_token(self, db: Session, integration_profile_id: int) -> str:
        """Refresh access token using refresh token with advisory lock to prevent concurrent refreshes."""
        # Use advisory lock to prevent concurrent refresh attempts
        lock_id = hash(f"sf_refresh_{integration_profile_id}") % (2**31)
        lock_acquired = db.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": lock_id}
        ).scalar()

        if not lock_acquired:
            # Another process is refreshing — wait briefly and read the new token
            import asyncio
            await asyncio.sleep(2)
            profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.id == integration_profile_id
            ).first()
            if profile and profile.access_token_encrypted:
                return decrypt_value(profile.access_token_encrypted)
            raise ValueError("Token refresh in progress by another process and no token available")

        try:
            profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.id == integration_profile_id
            ).first()

            if not profile or not profile.refresh_token_encrypted:
                raise ValueError("Integration profile not found or no refresh token")

            refresh_token = decrypt_value(profile.refresh_token_encrypted)

            async with get_sf_client() as client:
                response = await client.post(
                    f"{self.config.base_url}/services/oauth2/token",
                    data={
                        'grant_type': 'refresh_token',
                        'refresh_token': refresh_token,
                        'client_id': self.config.client_id,
                        'client_secret': self.config.client_secret
                    },
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                )

                if response.status_code != 200:
                    error = response.text

                    # If refresh token is invalid, mark profile as disconnected
                    if response.status_code == 400:
                        profile.status = 'error'
                        profile.last_error = 'Refresh token invalid - user needs to reconnect'
                        db.commit()

                    raise ValueError(f"Token refresh failed: {error}")

                tokens = response.json()

            # Update stored tokens and expiry
            profile.access_token_encrypted = encrypt_value(tokens['access_token'])
            profile.instance_url = tokens['instance_url']
            profile.last_error = None
            # Track token expiry (Salesforce tokens typically expire in ~2 hours)
            token_expires_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
            metadata = profile.sync_metadata or {}
            metadata['token_expires_at'] = token_expires_at
            profile.sync_metadata = metadata
            db.commit()

            return tokens['access_token']
        finally:
            # Release advisory lock
            db.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": lock_id}
            )

    async def get_access_token(self, db: Session, integration_profile_id: int) -> Tuple[str, str]:
        """Get valid access token, proactively refreshing if expired or about to expire"""
        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.id == integration_profile_id
        ).first()

        if not profile or not profile.access_token_encrypted:
            raise ValueError("Integration profile not found or not connected")

        # Check if token is about to expire (within 5 minutes)
        metadata = profile.sync_metadata or {}
        token_expires_at = metadata.get('token_expires_at')
        if token_expires_at:
            try:
                expires = datetime.fromisoformat(token_expires_at)
                # Ensure timezone-aware comparison
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) >= expires - timedelta(minutes=5):
                    logger.info(f"Token for profile {integration_profile_id} expires at {token_expires_at}, proactively refreshing")
                    refreshed = await self.refresh_access_token(db, integration_profile_id)
                    # Re-read profile to get updated instance_url
                    db.refresh(profile)
                    return refreshed, profile.instance_url
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse token_expires_at '{token_expires_at}': {e}")

        try:
            # Try to use existing token
            access_token = decrypt_value(profile.access_token_encrypted)
            return access_token, profile.instance_url
        except Exception as e:
            logger.exception(f"Failed to decrypt access token, attempting refresh: {e}")
            # If decryption fails or token is invalid, refresh it
            access_token = await self.refresh_access_token(db, integration_profile_id)
            return access_token, profile.instance_url

    async def force_refresh_and_get_token(self, db: Session, integration_profile_id: int) -> Tuple[str, str]:
        """Force-refresh the access token using the refresh token and return the new token.

        Called when a 401 INVALID_SESSION_ID is encountered during sync.
        """
        logger.info(f"Force-refreshing Salesforce token for profile {integration_profile_id}")
        access_token = await self.refresh_access_token(db, integration_profile_id)
        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.id == integration_profile_id
        ).first()
        instance_url = profile.instance_url if profile else ""
        return access_token, instance_url

    async def _revoke_salesforce_token(self, token: str, instance_url: str) -> None:
        """Revoke a token on Salesforce's side."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{instance_url}/services/oauth2/revoke",
                    data={"token": token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                if response.status_code == 200:
                    logger.info("Salesforce token revoked successfully")
                else:
                    logger.warning(f"Salesforce token revocation returned status {response.status_code}")
        except Exception as e:
            logger.warning(f"Failed to revoke Salesforce token: {e}")
            # Continue with local cleanup even if revocation fails

    async def disconnect(self, db: Session, integration_profile_id: int):
        """Disconnect Salesforce integration, revoking tokens on Salesforce's side"""
        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.id == integration_profile_id
        ).first()

        if not profile:
            raise ValueError("Integration profile not found")

        # Revoke tokens on Salesforce's side before clearing locally
        instance_url = profile.instance_url or ''
        if profile.access_token_encrypted and instance_url:
            try:
                access_token = decrypt_value(profile.access_token_encrypted)
                await self._revoke_salesforce_token(access_token, instance_url)
            except Exception as e:
                logger.warning(f"Could not revoke access token: {e}")
        if profile.refresh_token_encrypted and instance_url:
            try:
                refresh_token = decrypt_value(profile.refresh_token_encrypted)
                await self._revoke_salesforce_token(refresh_token, instance_url)
            except Exception as e:
                logger.warning(f"Could not revoke refresh token: {e}")

        # Update profile status
        profile.status = 'disconnected'
        profile.access_token_encrypted = None
        profile.refresh_token_encrypted = None
        profile.sync_enabled = False
        profile.last_error = 'Manually disconnected by user'

        # Clear any pending sync queue items
        db.query(SyncQueueItem).filter(
            SyncQueueItem.integration_profile_id == integration_profile_id
        ).delete()

        # Log event
        event = IntegrationEvent(
            integration_profile_id=integration_profile_id,
            event_type='disconnected',
            status='success',
            event_data={'reason': 'user_initiated'}
        )
        db.add(event)
        db.commit()

    async def cleanup_expired_states(self, db: Session) -> int:
        """Clean up expired and used OAuth state records. Returns count deleted."""
        result = db.execute(
            text("""
                DELETE FROM oauth_states
                WHERE expires_at < :now OR (used = true AND created_at < :cutoff)
            """),
            {
                "now": datetime.now(timezone.utc),
                "cutoff": datetime.now(timezone.utc) - timedelta(hours=24)
            }
        )
        db.commit()
        deleted = result.rowcount
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired OAuth state records")
        return deleted

    def get_profile(self, db: Session, user_id: int) -> Optional[IntegrationProfile]:
        """Get integration profile for a user"""
        return db.query(IntegrationProfile).filter(
            IntegrationProfile.user_id == user_id,
            IntegrationProfile.provider == 'salesforce'
        ).first()

    def get_profile_by_id(self, db: Session, profile_id: int) -> Optional[IntegrationProfile]:
        """Get integration profile by ID"""
        return db.query(IntegrationProfile).filter(
            IntegrationProfile.id == profile_id
        ).first()


# Export singleton instance
salesforce_oauth = SalesforceOAuthService()
