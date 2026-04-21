"""
Calendly Integration Service

Handles OAuth flow, availability management, and booking through Calendly's API.
Integrates with the existing Smart Scheduler to provide calendar backend functionality.
"""

import os
import logging
import httpx
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from cryptography.fernet import Fernet
from functools import lru_cache
import json
import time

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

CALENDLY_CLIENT_ID = os.getenv("CALENDLY_CLIENT_ID", "")
CALENDLY_CLIENT_SECRET = os.getenv("CALENDLY_CLIENT_SECRET", "")
CALENDLY_REDIRECT_URI = os.getenv("CALENDLY_REDIRECT_URI", "")
CALENDLY_API_BASE = "https://api.calendly.com"
CALENDLY_AUTH_URL = "https://auth.calendly.com"

# Encryption key for storing tokens (generate with Fernet.generate_key())
ENCRYPTION_KEY = os.getenv("CALENDLY_ENCRYPTION_KEY", "")

# Cache TTL in seconds
AVAILABILITY_CACHE_TTL = 900  # 15 minutes


def get_fernet():
    """Get Fernet cipher for token encryption.

    Raises RuntimeError if CALENDLY_ENCRYPTION_KEY is not set.
    A temporary key would silently encrypt tokens that become
    undecryptable after a restart — fail-closed instead.
    """
    if not ENCRYPTION_KEY:
        raise RuntimeError(
            "CALENDLY_ENCRYPTION_KEY environment variable is not set. "
            "Token encryption requires a persistent Fernet key. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)


# =============================================================================
# TOKEN ENCRYPTION
# =============================================================================

def encrypt_token(token: str) -> str:
    """Encrypt a token for secure storage"""
    fernet = get_fernet()
    return fernet.encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a stored token"""
    fernet = get_fernet()
    return fernet.decrypt(encrypted_token.encode()).decode()


# =============================================================================
# AVAILABILITY CACHE
# =============================================================================

class AvailabilityCache:
    """Simple in-memory cache for availability data with TTL"""

    def __init__(self, ttl_seconds: int = AVAILABILITY_CACHE_TTL):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl_seconds

    def _make_key(self, user_uri: str, start_time: str, end_time: str) -> str:
        """Create cache key from parameters"""
        key_str = f"{user_uri}:{start_time}:{end_time}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, user_uri: str, start_time: str, end_time: str) -> Optional[Dict]:
        """Get cached availability if not expired"""
        key = self._make_key(user_uri, start_time, end_time)
        entry = self._cache.get(key)

        if entry is None:
            return None

        if time.time() > entry["expires_at"]:
            del self._cache[key]
            return None

        return entry["data"]

    def set(self, user_uri: str, start_time: str, end_time: str, data: Dict):
        """Cache availability data"""
        key = self._make_key(user_uri, start_time, end_time)
        self._cache[key] = {
            "data": data,
            "expires_at": time.time() + self._ttl
        }

    def invalidate(self, user_uri: str = None):
        """Invalidate cache entries"""
        if user_uri is None:
            self._cache.clear()
        else:
            keys_to_delete = [k for k in self._cache if user_uri in k]
            for key in keys_to_delete:
                del self._cache[key]


# Global cache instance
availability_cache = AvailabilityCache()


# =============================================================================
# CALENDLY SERVICE
# =============================================================================

class CalendlyService:
    """Service for interacting with Calendly API"""

    def __init__(self, db_session=None):
        self.db = db_session
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

    # =========================================================================
    # OAuth Flow
    # =========================================================================

    def get_authorization_url(self, state: str = None) -> str:
        """
        Get the Calendly OAuth authorization URL.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            URL to redirect user to for Calendly authorization
        """
        params = {
            "client_id": CALENDLY_CLIENT_ID,
            "redirect_uri": CALENDLY_REDIRECT_URI,
            "response_type": "code",
        }
        if state:
            params["state"] = state

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{CALENDLY_AUTH_URL}/oauth/authorize?{query}"

    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Token response including access_token, refresh_token, expires_in
        """
        try:
            response = await self.client.post(
                f"{CALENDLY_AUTH_URL}/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": CALENDLY_CLIENT_ID,
                    "client_secret": CALENDLY_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": CALENDLY_REDIRECT_URI,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()

            data = response.json()
            logger.info("Successfully exchanged code for Calendly token")
            return {
                "success": True,
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "token_type": data["token_type"],
                "expires_in": data["expires_in"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to exchange code: {e}")
            return {"success": False, "error": "Internal server error"}

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh an expired access token.

        Args:
            refresh_token: The refresh token

        Returns:
            New token response
        """
        try:
            response = await self.client.post(
                f"{CALENDLY_AUTH_URL}/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": CALENDLY_CLIENT_ID,
                    "client_secret": CALENDLY_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()

            data = response.json()
            logger.info("Successfully refreshed Calendly token")
            return {
                "success": True,
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", refresh_token),
                "expires_in": data["expires_in"],
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to refresh token: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # User & Organization Info
    # =========================================================================

    async def get_current_user(self, access_token: str) -> Dict[str, Any]:
        """
        Get the current authenticated user's information.

        Args:
            access_token: Valid Calendly access token

        Returns:
            User information including URI, name, email
        """
        try:
            response = await self.client.get(
                f"{CALENDLY_API_BASE}/users/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            data = response.json()
            user = data.get("resource", {})

            return {
                "success": True,
                "uri": user.get("uri"),
                "name": user.get("name"),
                "email": user.get("email"),
                "slug": user.get("slug"),
                "timezone": user.get("timezone"),
                "avatar_url": user.get("avatar_url"),
                "current_organization": user.get("current_organization"),
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to get current user: {e}")
            return {"success": False, "error": "Internal server error"}

    async def get_organization(self, access_token: str, org_uri: str) -> Dict[str, Any]:
        """
        Get organization details.

        Args:
            access_token: Valid Calendly access token
            org_uri: Organization URI

        Returns:
            Organization details
        """
        try:
            response = await self.client.get(
                org_uri,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            data = response.json()
            org = data.get("resource", {})

            return {
                "success": True,
                "uri": org.get("uri"),
                "name": org.get("name"),
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to get organization: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # Event Types
    # =========================================================================

    async def get_event_types(
        self,
        access_token: str,
        user_uri: str = None,
        organization_uri: str = None,
        active: bool = True
    ) -> Dict[str, Any]:
        """
        Get available event types (meeting types).

        Args:
            access_token: Valid Calendly access token
            user_uri: Filter by user URI
            organization_uri: Filter by organization URI
            active: Only return active event types

        Returns:
            List of event types
        """
        try:
            params = {"active": str(active).lower()}
            if user_uri:
                params["user"] = user_uri
            if organization_uri:
                params["organization"] = organization_uri

            response = await self.client.get(
                f"{CALENDLY_API_BASE}/event_types",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            data = response.json()
            event_types = data.get("collection", [])

            return {
                "success": True,
                "event_types": [
                    {
                        "uri": et.get("uri"),
                        "name": et.get("name"),
                        "slug": et.get("slug"),
                        "duration": et.get("duration"),
                        "scheduling_url": et.get("scheduling_url"),
                        "description": et.get("description_plain"),
                        "active": et.get("active"),
                        "color": et.get("color"),
                        "type": et.get("type"),  # StandardEventType, etc.
                    }
                    for et in event_types
                ],
                "pagination": data.get("pagination"),
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to get event types: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # Availability
    # =========================================================================

    async def get_user_availability(
        self,
        access_token: str,
        user_uri: str,
        start_time: datetime,
        end_time: datetime,
        event_type_uri: str = None
    ) -> Dict[str, Any]:
        """
        Get user's available time slots.

        Args:
            access_token: Valid Calendly access token
            user_uri: User URI to check availability for
            start_time: Start of availability window
            end_time: End of availability window
            event_type_uri: Optional event type to check against

        Returns:
            Available time slots
        """
        start_str = start_time.isoformat() + "Z" if start_time.tzinfo is None else start_time.isoformat()
        end_str = end_time.isoformat() + "Z" if end_time.tzinfo is None else end_time.isoformat()

        # Check cache first
        cached = availability_cache.get(user_uri, start_str, end_str)
        if cached:
            logger.debug(f"Returning cached availability for {user_uri}")
            return cached

        try:
            params = {
                "user": user_uri,
                "start_time": start_str,
                "end_time": end_str,
            }
            if event_type_uri:
                params["event_type"] = event_type_uri

            response = await self.client.get(
                f"{CALENDLY_API_BASE}/user_availability_schedules",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            data = response.json()

            result = {
                "success": True,
                "schedules": data.get("collection", []),
            }

            # Cache the result
            availability_cache.set(user_uri, start_str, end_str, result)

            return result
        except httpx.HTTPError as e:
            logger.error(f"Failed to get availability: {e}")
            return {"success": False, "error": "Internal server error"}

    async def get_busy_times(
        self,
        access_token: str,
        user_uri: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Get user's busy times within a date range.

        Args:
            access_token: Valid Calendly access token
            user_uri: User URI to check
            start_time: Start of range
            end_time: End of range

        Returns:
            List of busy time intervals
        """
        try:
            start_str = start_time.isoformat() + "Z" if start_time.tzinfo is None else start_time.isoformat()
            end_str = end_time.isoformat() + "Z" if end_time.tzinfo is None else end_time.isoformat()

            response = await self.client.get(
                f"{CALENDLY_API_BASE}/user_busy_times",
                params={
                    "user": user_uri,
                    "start_time": start_str,
                    "end_time": end_str,
                },
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            data = response.json()

            return {
                "success": True,
                "busy_times": [
                    {
                        "type": bt.get("type"),
                        "start_time": bt.get("start_time"),
                        "end_time": bt.get("end_time"),
                    }
                    for bt in data.get("collection", [])
                ],
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to get busy times: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # Scheduled Events
    # =========================================================================

    async def get_scheduled_events(
        self,
        access_token: str,
        user_uri: str = None,
        organization_uri: str = None,
        min_start_time: datetime = None,
        max_start_time: datetime = None,
        status: str = "active",
        count: int = 100
    ) -> Dict[str, Any]:
        """
        Get scheduled events (booked appointments).

        Args:
            access_token: Valid Calendly access token
            user_uri: Filter by user
            organization_uri: Filter by organization
            min_start_time: Minimum start time
            max_start_time: Maximum start time
            status: Event status filter (active, canceled)
            count: Number of results to return

        Returns:
            List of scheduled events
        """
        try:
            params = {
                "status": status,
                "count": count,
            }
            if user_uri:
                params["user"] = user_uri
            if organization_uri:
                params["organization"] = organization_uri
            if min_start_time:
                params["min_start_time"] = min_start_time.isoformat() + "Z"
            if max_start_time:
                params["max_start_time"] = max_start_time.isoformat() + "Z"

            response = await self.client.get(
                f"{CALENDLY_API_BASE}/scheduled_events",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            data = response.json()
            events = data.get("collection", [])

            return {
                "success": True,
                "events": [
                    {
                        "uri": e.get("uri"),
                        "name": e.get("name"),
                        "status": e.get("status"),
                        "start_time": e.get("start_time"),
                        "end_time": e.get("end_time"),
                        "event_type": e.get("event_type"),
                        "location": e.get("location"),
                        "invitees_counter": e.get("invitees_counter"),
                        "created_at": e.get("created_at"),
                        "updated_at": e.get("updated_at"),
                        "cancellation": e.get("cancellation"),
                    }
                    for e in events
                ],
                "pagination": data.get("pagination"),
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to get scheduled events: {e}")
            return {"success": False, "error": "Internal server error"}

    async def get_event(self, access_token: str, event_uri: str) -> Dict[str, Any]:
        """
        Get details of a specific scheduled event.

        Args:
            access_token: Valid Calendly access token
            event_uri: URI of the event

        Returns:
            Event details
        """
        try:
            response = await self.client.get(
                event_uri,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            data = response.json()
            event = data.get("resource", {})

            return {
                "success": True,
                "event": event,
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to get event: {e}")
            return {"success": False, "error": "Internal server error"}

    async def get_event_invitees(
        self,
        access_token: str,
        event_uri: str
    ) -> Dict[str, Any]:
        """
        Get invitees for a scheduled event.

        Args:
            access_token: Valid Calendly access token
            event_uri: URI of the event

        Returns:
            List of invitees
        """
        try:
            # Extract event UUID from URI
            event_uuid = event_uri.split("/")[-1]

            response = await self.client.get(
                f"{CALENDLY_API_BASE}/scheduled_events/{event_uuid}/invitees",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            data = response.json()
            invitees = data.get("collection", [])

            return {
                "success": True,
                "invitees": [
                    {
                        "uri": inv.get("uri"),
                        "email": inv.get("email"),
                        "name": inv.get("name"),
                        "status": inv.get("status"),
                        "timezone": inv.get("timezone"),
                        "questions_and_answers": inv.get("questions_and_answers", []),
                        "created_at": inv.get("created_at"),
                        "updated_at": inv.get("updated_at"),
                        "cancellation": inv.get("cancellation"),
                    }
                    for inv in invitees
                ],
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to get event invitees: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # Cancellation
    # =========================================================================

    async def cancel_event(
        self,
        access_token: str,
        event_uri: str,
        reason: str = None
    ) -> Dict[str, Any]:
        """
        Cancel a scheduled event.

        Args:
            access_token: Valid Calendly access token
            event_uri: URI of the event to cancel
            reason: Optional cancellation reason

        Returns:
            Cancellation result
        """
        try:
            # Extract event UUID from URI
            event_uuid = event_uri.split("/")[-1]

            payload = {}
            if reason:
                payload["reason"] = reason

            response = await self.client.post(
                f"{CALENDLY_API_BASE}/scheduled_events/{event_uuid}/cancellation",
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                }
            )
            response.raise_for_status()

            # Invalidate availability cache
            availability_cache.invalidate()

            logger.info(f"Event cancelled: {event_uuid}")
            return {
                "success": True,
                "message": "Event cancelled successfully",
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to cancel event: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # Webhooks
    # =========================================================================

    async def create_webhook_subscription(
        self,
        access_token: str,
        url: str,
        events: List[str],
        organization_uri: str,
        user_uri: str = None,
        scope: str = "organization"
    ) -> Dict[str, Any]:
        """
        Create a webhook subscription.

        Args:
            access_token: Valid Calendly access token
            url: URL to receive webhook events
            events: List of events to subscribe to
            organization_uri: Organization URI
            user_uri: Optional user URI for user-scoped webhooks
            scope: "organization" or "user"

        Returns:
            Webhook subscription details
        """
        try:
            payload = {
                "url": url,
                "events": events,
                "organization": organization_uri,
                "scope": scope,
            }
            if user_uri and scope == "user":
                payload["user"] = user_uri

            response = await self.client.post(
                f"{CALENDLY_API_BASE}/webhook_subscriptions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                }
            )
            response.raise_for_status()

            data = response.json()
            webhook = data.get("resource", {})

            logger.info(f"Webhook subscription created: {webhook.get('uri')}")
            return {
                "success": True,
                "webhook": {
                    "uri": webhook.get("uri"),
                    "callback_url": webhook.get("callback_url"),
                    "events": webhook.get("events"),
                    "scope": webhook.get("scope"),
                    "state": webhook.get("state"),
                },
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to create webhook: {e}")
            return {"success": False, "error": "Internal server error"}

    async def delete_webhook_subscription(
        self,
        access_token: str,
        webhook_uri: str
    ) -> Dict[str, Any]:
        """
        Delete a webhook subscription.

        Args:
            access_token: Valid Calendly access token
            webhook_uri: URI of the webhook to delete

        Returns:
            Deletion result
        """
        try:
            response = await self.client.delete(
                webhook_uri,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            logger.info(f"Webhook subscription deleted: {webhook_uri}")
            return {"success": True}
        except httpx.HTTPError as e:
            logger.error(f"Failed to delete webhook: {e}")
            return {"success": False, "error": "Internal server error"}

    async def list_webhook_subscriptions(
        self,
        access_token: str,
        organization_uri: str,
        scope: str = "organization"
    ) -> Dict[str, Any]:
        """
        List webhook subscriptions.

        Args:
            access_token: Valid Calendly access token
            organization_uri: Organization URI
            scope: "organization" or "user"

        Returns:
            List of webhook subscriptions
        """
        try:
            response = await self.client.get(
                f"{CALENDLY_API_BASE}/webhook_subscriptions",
                params={
                    "organization": organization_uri,
                    "scope": scope,
                },
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            data = response.json()

            return {
                "success": True,
                "webhooks": data.get("collection", []),
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to list webhooks: {e}")
            return {"success": False, "error": "Internal server error"}


# =============================================================================
# SERVICE FACTORY
# =============================================================================

_calendly_service = None


def get_calendly_service(db_session=None) -> CalendlyService:
    """Get the Calendly service instance"""
    global _calendly_service
    if _calendly_service is None:
        _calendly_service = CalendlyService(db_session)
    return _calendly_service
