"""
Encompass OAuth Service

Manages per-organization Encompass credentials, authentication, and
client lifecycle. Provides a clean interface for routes to obtain
authenticated EncompassClient instances without handling OAuth details.

Key responsibilities:
    - Store/retrieve per-org Encompass credentials (EncompassConfig)
    - Authenticate and cache EncompassClient instances per org
    - Re-authenticate when tokens expire (Encompass tokens are ~30 min)
    - Test connectivity before saving credentials

Usage:
    from services.los_integration.encompass_oauth_service import EncompassOAuthService

    service = EncompassOAuthService()
    await service.connect(org_id, instance_id, client_id, client_secret)
    client = await service.get_authenticated_client(org_id)
    result = await client.pull_loan("some-guid")
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from .encompass_client import EncompassClient

logger = logging.getLogger(__name__)

# In-memory cache of authenticated clients per organization.
# Keys are organization_id (int), values are EncompassClient instances.
# Clients are re-authenticated when their tokens expire.
_client_cache: Dict[int, EncompassClient] = {}


class EncompassOAuthService:
    """Service for managing Encompass OAuth credentials and client instances.

    Handles the full lifecycle of Encompass API authentication per organization:
    storing credentials, creating authenticated clients, testing connections,
    and disconnecting.
    """

    def __init__(self):
        pass

    # =========================================================================
    # Connect / Disconnect
    # =========================================================================

    async def connect(
        self,
        db: Session,
        org_id: int,
        instance_id: str,
        client_id: str,
        client_secret: str,
        api_user: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Connect an organization to Encompass.

        Stores credentials, tests the connection, and activates the config.
        If a config already exists for the org, it is updated.

        Args:
            db: Database session
            org_id: Organization ID
            instance_id: Encompass instance ID (e.g., "BE11200822")
            client_id: OAuth client ID
            client_secret: OAuth client secret
            api_user: Optional service account username
            webhook_secret: Optional HMAC secret for webhook verification

        Returns:
            Dict with connection status and config ID

        Raises:
            ValueError: If credentials fail to authenticate
        """
        from database.models.encompass_config import EncompassConfig

        # Test the credentials before saving
        test_client = EncompassClient(
            instance_id=instance_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        auth_success = await test_client.authenticate()
        if not auth_success:
            raise ValueError(
                "Failed to authenticate with Encompass. "
                "Please verify your instance_id, client_id, and client_secret."
            )

        # Upsert the config
        config = db.query(EncompassConfig).filter(
            EncompassConfig.organization_id == org_id
        ).first()

        if config:
            config.instance_id = instance_id
            config.client_id = client_id
            config.client_secret = client_secret
            config.api_user = api_user
            config.webhook_secret = webhook_secret
            config.is_active = True
            config.updated_at = datetime.now(timezone.utc)
        else:
            config = EncompassConfig(
                organization_id=org_id,
                instance_id=instance_id,
                client_id=client_id,
                client_secret=client_secret,
                api_user=api_user,
                webhook_secret=webhook_secret,
                is_active=True,
            )
            db.add(config)

        db.flush()

        # Cache the authenticated client
        _client_cache[org_id] = test_client

        logger.info(
            f"Encompass connected for org {org_id} "
            f"(instance={instance_id}, config_id={config.id})"
        )

        return {
            "status": "connected",
            "config_id": config.id,
            "instance_id": instance_id,
            "authenticated": True,
        }

    async def disconnect(self, db: Session, org_id: int) -> Dict[str, Any]:
        """Disconnect an organization from Encompass.

        Deactivates the config and removes the cached client.

        Args:
            db: Database session
            org_id: Organization ID

        Returns:
            Dict with disconnection status
        """
        from database.models.encompass_config import EncompassConfig

        config = db.query(EncompassConfig).filter(
            EncompassConfig.organization_id == org_id
        ).first()

        if not config:
            return {"status": "not_connected", "message": "No Encompass config found"}

        config.is_active = False
        config.updated_at = datetime.now(timezone.utc)
        db.flush()

        # Remove from cache
        _client_cache.pop(org_id, None)

        logger.info(f"Encompass disconnected for org {org_id}")

        return {
            "status": "disconnected",
            "config_id": config.id,
        }

    # =========================================================================
    # Client Access
    # =========================================================================

    async def get_authenticated_client(
        self,
        db: Session,
        org_id: int,
    ) -> EncompassClient:
        """Get an authenticated EncompassClient for an organization.

        Returns a cached client if the token is still valid, otherwise
        re-authenticates using stored credentials.

        Encompass OAuth tokens expire after ~30 minutes and are not
        refreshable -- a new token must be obtained via client_credentials
        grant each time.

        Args:
            db: Database session
            org_id: Organization ID

        Returns:
            Authenticated EncompassClient instance

        Raises:
            ValueError: If no active config exists for the org
            RuntimeError: If authentication fails
        """
        # Check cache first
        cached = _client_cache.get(org_id)
        if cached and cached.is_authenticated:
            return cached

        # Load config from database
        config = await self._get_active_config(db, org_id)
        if not config:
            raise ValueError(
                f"No active Encompass configuration found for organization {org_id}. "
                "Please connect via the Encompass integration settings."
            )

        # Create and authenticate client
        client = EncompassClient(
            instance_id=config.instance_id,
            client_id=config.client_id,
            client_secret=config.client_secret,
        )

        auth_success = await client.authenticate()
        if not auth_success:
            raise RuntimeError(
                f"Failed to authenticate with Encompass for org {org_id}. "
                "Credentials may have been revoked or expired."
            )

        # Cache the client
        _client_cache[org_id] = client

        return client

    # =========================================================================
    # Connection Status & Testing
    # =========================================================================

    async def test_connection(
        self,
        db: Session,
        org_id: int,
    ) -> Dict[str, Any]:
        """Test the Encompass connection for an organization.

        Attempts to authenticate with stored credentials and reports
        the result including latency.

        Args:
            db: Database session
            org_id: Organization ID

        Returns:
            Dict with test results including status, latency, and any errors
        """
        import time

        config = await self._get_active_config(db, org_id)
        if not config:
            return {
                "status": "not_configured",
                "message": "No active Encompass configuration found",
                "authenticated": False,
            }

        start = time.monotonic()
        client = EncompassClient(
            instance_id=config.instance_id,
            client_id=config.client_id,
            client_secret=config.client_secret,
        )

        try:
            auth_success = await client.authenticate()
            latency_ms = round((time.monotonic() - start) * 1000, 1)

            if auth_success:
                # Update cache with fresh client
                _client_cache[org_id] = client
                return {
                    "status": "healthy",
                    "authenticated": True,
                    "instance_id": config.instance_id,
                    "latency_ms": latency_ms,
                }
            else:
                return {
                    "status": "auth_failed",
                    "authenticated": False,
                    "instance_id": config.instance_id,
                    "latency_ms": latency_ms,
                    "message": "Authentication failed - check credentials",
                }
        except Exception as e:
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            logger.error(f"Encompass connection test failed for org {org_id}: {e}")
            return {
                "status": "error",
                "authenticated": False,
                "instance_id": config.instance_id,
                "latency_ms": latency_ms,
                "error": str(e),
            }

    async def get_config(
        self,
        db: Session,
        org_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Get the Encompass configuration for an organization.

        Returns configuration details without exposing secrets.

        Args:
            db: Database session
            org_id: Organization ID

        Returns:
            Dict with config details (secrets masked), or None if not configured
        """
        from database.models.encompass_config import EncompassConfig

        config = db.query(EncompassConfig).filter(
            EncompassConfig.organization_id == org_id
        ).first()

        if not config:
            return None

        return {
            "id": config.id,
            "organization_id": config.organization_id,
            "instance_id": config.instance_id,
            "client_id": _mask_secret(config.client_id),
            "client_secret_set": bool(config.client_secret),
            "api_user": config.api_user,
            "webhook_secret_set": bool(config.webhook_secret),
            "auto_pull_on_webhook": config.auto_pull_on_webhook,
            "auto_push_on_stage_change": config.auto_push_on_stage_change,
            "sync_frequency_minutes": config.sync_frequency_minutes,
            "last_sync_at": config.last_sync_at.isoformat() if config.last_sync_at else None,
            "is_active": config.is_active,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    async def _get_active_config(self, db: Session, org_id: int):
        """Get the active EncompassConfig for an organization.

        Args:
            db: Database session
            org_id: Organization ID

        Returns:
            EncompassConfig instance or None
        """
        from database.models.encompass_config import EncompassConfig

        return db.query(EncompassConfig).filter(
            EncompassConfig.organization_id == org_id,
            EncompassConfig.is_active == True,  # noqa: E712
        ).first()


def _mask_secret(value: Optional[str]) -> Optional[str]:
    """Mask a secret value for display, showing only last 4 characters."""
    if not value:
        return None
    if len(value) <= 4:
        return "****"
    return f"****{value[-4:]}"
